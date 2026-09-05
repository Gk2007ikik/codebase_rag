import re
from dataclasses import dataclass

# Extensions we bother indexing. Add more as needed.
SKIP_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".webp", ".svg", ".tiff",
    ".woff", ".woff2", ".ttf", ".otf", ".eot",
    ".zip", ".tar", ".gz", ".tgz", ".rar", ".7z", ".whl", ".jar", ".war",
    ".exe", ".dll", ".so", ".dylib", ".class", ".pyc", ".o", ".a", ".wasm",
    ".mp3", ".mp4", ".mov", ".avi", ".wav", ".flac", ".pdf",
    ".csv", ".tsv", ".parquet", ".db", ".sqlite", ".sqlite3",
    ".lock",
}

SKIP_FILENAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "Cargo.lock",
    "poetry.lock", "Pipfile.lock", ".DS_Store", "composer.lock",
}

MAX_FILE_SIZE_BYTES = 500_000

# Folders we never want to walk into.
SKIP_DIRS = {
    ".git", "node_modules", "venv", ".venv", "__pycache__",
    "dist", "build", ".next", "target", "vendor", "bin", "obj",
}

# One regex per chunk boundary "shape". If a line matches any of these
# (after stripping leading whitespace), we start a new chunk there.
BOUNDARY_PATTERNS = [
    r"^def\s+\w+\s*\(",
    r"^class\s+\w+",
    r"^(export\s+)?(default\s+)?(async\s+)?function\s+\w+\s*\(",
    r"^(export\s+)?(default\s+)?class\s+\w+",
    r"^(export\s+)?(default\s+)?interface\s+\w+",          # NEW: ts interface
    r"^(public|private|protected|static)[\w\s<>\[\],]*\(",
    r"^func\s+\w+\s*\(",
    r"^(pub\s+)?(async\s+)?fn\s+\w+",                       # NEW: rust
    r"^fun\s+\w+\s*\(",                                     # NEW: kotlin
    r"^module\s+\w+",                                       # NEW: ruby module
    r"^sub\s+\w+",                                          # NEW: perl
    r"^\w+\s*::\s*\w+\s*=",                                 # NEW: erlang/elixir-style
]
BOUNDARY_RE = re.compile("|".join(f"({p})" for p in BOUNDARY_PATTERNS))

MAX_CHUNK_LINES = 200   # hard cap so one giant function doesn't dominate context
MIN_CHUNK_LINES = 3     # ignore trivial one-line "chunks"


@dataclass
class Chunk:
    code: str
    file_path: str      # path relative to repo root
    start_line: int      # 1-indexed
    end_line: int
    name: str            # best-guess function/class name, or "module-level"


def _guess_name(first_line: str) -> str:
    line = first_line.strip()
    match = re.search(
        r"(?:def|class|function|func|fn|fun|sub|module|interface)\s+(\w+)", line
    )
    if match:
        return match.group(1)
    match = re.search(r"(\w+)\s*\(", line)
    if match:
        return match.group(1)
    return "block"

def chunk_file(file_path: str, content: str) -> list[Chunk]:
    """Split one file's content into function/class-level chunks."""
    lines = content.splitlines()
    boundaries = [i for i, line in enumerate(lines) if BOUNDARY_RE.match(line.strip())]

    chunks: list[Chunk] = []

    # Anything before the first boundary is "module-level" code (imports,
    # constants, etc.) - still worth indexing.
    if boundaries and boundaries[0] > 0:
        head = lines[: boundaries[0]]
        if len(head) >= MIN_CHUNK_LINES:
            chunks.append(Chunk(
                code="\n".join(head), file_path=file_path,
                start_line=1, end_line=boundaries[0], name="module-level",
            ))

    if not boundaries:
        # No recognizable function/class in this file - just chunk it
        # in fixed windows so it's still searchable.
        for start in range(0, len(lines), MAX_CHUNK_LINES):
            block = lines[start:start + MAX_CHUNK_LINES]
            if len(block) >= MIN_CHUNK_LINES:
                chunks.append(Chunk(
                    code="\n".join(block), file_path=file_path,
                    start_line=start + 1, end_line=start + len(block),
                    name="block",
                ))
        return chunks

    for idx, start in enumerate(boundaries):
        end = boundaries[idx + 1] if idx + 1 < len(boundaries) else len(lines)
        # Cap runaway chunks (e.g. a 500-line function).
        end = min(end, start + MAX_CHUNK_LINES)
        block = lines[start:end]
        if len(block) < MIN_CHUNK_LINES:
            continue
        chunks.append(Chunk(
            code="\n".join(block),
            file_path=file_path,
            start_line=start + 1,
            end_line=end,
            name=_guess_name(lines[start]),
        ))

    return chunks

def group_by_file(chunks: list[Chunk]) -> dict:
    from collections import defaultdict
    by_file = defaultdict(list)
    for c in chunks:
        by_file[c.file_path].append(c)
    return dict(by_file)