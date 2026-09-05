from ingest import get_repo_path, collect_chunks

repo_path = get_repo_path('https://github.com/Goku-2307/arm-developer-autopilot')
print('Repo path:', repo_path)

chunks = collect_chunks(repo_path)
print('Chunks produced:', len(chunks))

for c in chunks[:5]:
    print(' -', c.file_path, '|', c.name, '|', c.start_line, '-', c.end_line)
