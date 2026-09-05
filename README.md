cat > README.md << 'MDEOF'
# 🧠 Chat With a Codebase

Point this at any GitHub repo and ask questions about it in plain English — get answers grounded in the actual code, with file and line citations, not hallucinated APIs.

Built as a RAG (Retrieval-Augmented Generation) project: chunk the repo, embed it, retrieve the relevant pieces for a question, and hand only those pieces to an LLM to answer from.

## What it does

Ask things like:

- *"What is the purpose of this repository?"*
- *"How does the retry logic work?"*
- *"Explain dashboard.py in detail"*
- *"Give me explanations for all the files"*
- *"Is there anything in the README that the project itself doesn't do?"*

The repo is broken into chunks at function/class boundaries (not arbitrary line counts), each chunk is turned into a vector using a local embedding model, and those vectors are stored for similarity search. When you ask a question, it's embedded the same way, the closest-matching code chunks are retrieved, and only those chunks (plus a map of the whole repo's structure) are handed to an LLM along with your question. The model answers using just that material — and if it can't find anything relevant, it says so instead of guessing.

A few things that make this more than the basic tutorial version of RAG:

- **Function-aware chunking.** Code is split at function/class boundaries using language-agnostic pattern matching, not arbitrary character counts — so a chunk is never half of one function and half of another.
- **Universal language support.** Instead of an allowlist of "code" extensions, every file is checked for whether it's actually text (via binary detection) — so Rust, Kotlin, Lua, or anything else works without extra configuration.
- **Multiple retrieval strategies depending on the question:**

  | Question type | What happens |
  |---|---|
  | Names a specific file | Exact lookup — every chunk from that file, no embedding guesswork |
  | "all files" / "every file" | Loops through every indexed file, summarizes each individually |
  | Anything else | Wide similarity search **+** a full repo map (files, functions, classes) as background context |

- **Automatic code surfacing.** Any answer that names real files automatically gets an expander underneath showing those files' actual source — no need to separately ask "show me the code."
- **Filename disambiguation.** If a repo has two files with the same name (e.g. two `README.md`s), the one closest to the repo root is preferred, since that's almost always the "main" one being asked about.
- **Answers honestly when it doesn't know.** If nothing retrieved is a close enough match, it says so instead of inventing an answer.
- **Handles messy input.** Pasting a GitHub folder/file link (`.../tree/branch/...` or `.../blob/branch/...`) instead of the repo root URL is automatically corrected before cloning.

## Architecture

Repo (GitHub URL or local path)
|
v
ingest.py --> clone/read files, detect text vs. binary, walk the tree
|
v
chunker.py --> split each file into function/class-level chunks
|
v
vectorstore.py --> embed chunks (sentence-transformers) + store in ChromaDB
|
v
[ user asks a question in the Streamlit UI ]
|
v
vectorstore.py --> embed the question, retrieve the closest chunks
|
v
llm.py --> build a prompt (question + chunks + repo map), send to Groq
|
v
app.py --> display the answer, auto-surface any files it referenced


**Files:**

- `app.py` — Streamlit UI
- `ingest.py` — clones/reads the repo, detects text files, walks the tree
- `chunker.py` — splits files into function/class-level chunks
- `vectorstore.py` — embeddings + ChromaDB storage/retrieval
- `llm.py` — prompt building + calls to Groq's API
MDEOF
echo "WROTE README.md"
