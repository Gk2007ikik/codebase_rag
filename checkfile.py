from ingest import get_repo_path, collect_chunks

repo_path = get_repo_path('https://github.com/Goku-2307/arm-developer-autopilot')
chunks = collect_chunks(repo_path)

matches = [c for c in chunks if 'dashboard' in c.file_path.lower()]
print("Chunks matching 'dashboard':", len(matches))
for c in matches:
    print(" -", c.file_path, "|", c.name, "|", c.start_line, "-", c.end_line)
