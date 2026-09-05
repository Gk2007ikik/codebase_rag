"""
ingest.py
---------
Turns a repo (local path or GitHub URL) into a flat list of Chunks,
ready to be embedded and stored.
"""

import os
import re
import shutil
import subprocess
import tempfile

from chunker import (
    chunk_file, SKIP_DIRS, SKIP_EXTENSIONS, SKIP_FILENAMES,
    MAX_FILE_SIZE_BYTES, Chunk,
)


def _is_url(path_or_url: str) -> bool:
    return path_or_url.startswith("http://") or path_or_url.startswith("https://") \
        or path_or_url.startswith("git@")


def normalize_github_url(url: str):
    """
    If given a GitHub link to a specific folder or file
    (.../tree/<branch>/<path> or .../blob/<branch>/<path>), extract just
    the repo root and the branch, so we can still clone it. Returns
    (clean_repo_url, branch_or_None). Anything else passes through
    unchanged.
    """
    url = url.strip().rstrip("/")

    match = re.match(
        r"^(https://github\.com/[^/]+/[^/]+?)(?:\.git)?/(?:tree|blob)/([^/]+)(?:/.*)?$",
        url,
    )
    if match:
        repo_root = match.group(1)
        branch = match.group(2)
        return repo_root, branch

    return url, None


def get_repo_path(path_or_url: str, workdir: str | None = None) -> str:
    """
    If given a URL, clone it into a temp dir and return that path.
    If given a local path, just return it.
    """
    if not _is_url(path_or_url):
        if not os.path.isdir(path_or_url):
            raise FileNotFoundError(f"Local path does not exist: {path_or_url}")
        return path_or_url

    clean_url, branch = normalize_github_url(path_or_url)

    workdir = workdir or tempfile.mkdtemp(prefix="codebase_rag_")
    dest = os.path.join(workdir, "repo")
    if os.path.exists(dest):
        shutil.rmtree(dest)

    cmd = ["git", "clone", "--depth", "1"]
    if branch:
        cmd += ["--branch", branch]
    cmd += [clean_url, dest]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"git clone failed: {result.stderr.strip()}")

    return dest


def is_probably_text(file_path: str, sniff_bytes: int = 8000) -> bool:
    """
    Cheap binary-vs-text detection: read the first chunk of raw bytes and
    check for a null byte. Text files (in virtually any language, any
    encoding) don't contain null bytes; compiled binaries, images, etc.
    almost always do within the first few KB. This is what lets us index
    "any" language without maintaining an extension allowlist.
    """
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(sniff_bytes)
    except OSError:
        return False
    return b"\x00" not in chunk


def collect_chunks(repo_path: str) -> list[Chunk]:
    """Walk the repo, chunk every code file, return one flat list."""
    all_chunks: list[Chunk] = []

    for root, dirs, files in os.walk(repo_path):
        # Prune skip-dirs in place so os.walk doesn't descend into them.
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]

        for fname in files:
            if fname in SKIP_FILENAMES:
                continue

            ext = os.path.splitext(fname)[1].lower()
            if ext in SKIP_EXTENSIONS:
                continue

            full_path = os.path.join(root, fname)

            try:
                if os.path.getsize(full_path) > MAX_FILE_SIZE_BYTES:
                    continue
            except OSError:
                continue

            if not is_probably_text(full_path):
                continue

            rel_path = os.path.relpath(full_path, repo_path)

            try:
                with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except OSError:
                continue

            if not content.strip():
                continue

            all_chunks.extend(chunk_file(rel_path, content))

    return all_chunks


def build_repo_map(chunks: list[Chunk], max_chars: int = 6000) -> str:
    """
    A compact 'table of contents' for the whole repo: every file, and the
    functions/classes found in it. Similarity search only ever surfaces a
    handful of the closest-matching chunks, so it can't answer big-picture
    questions like "how does this project work overall?" - this map gives
    the model that missing bird's-eye view.
    """
    from collections import defaultdict

    by_file = defaultdict(list)
    for c in chunks:
        by_file[c.file_path].append(c.name)

    lines = ["Repository structure (files and their top-level functions/classes):"]
    for file_path in sorted(by_file.keys()):
        names = sorted(set(n for n in by_file[file_path] if n not in ("block", "module-level")))
        if names:
            lines.append(f"- {file_path}: {', '.join(names)}")
        else:
            lines.append(f"- {file_path}: (script / no named functions)")

    overview = "\n".join(lines)
    if len(overview) > max_chars:
        overview = overview[:max_chars] + "\n... (truncated, repo is large)"
    return overview


def group_by_file(chunks: list[Chunk]) -> dict:
    """Group chunks by file_path, e.g. for per-file summarization."""
    from collections import defaultdict
    by_file = defaultdict(list)
    for c in chunks:
        by_file[c.file_path].append(c)
    return dict(by_file)