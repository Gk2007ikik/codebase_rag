# 🧠 Chat With a Codebase

Point this at any GitHub repo and ask questions about it in plain
English — get answers grounded in the actual code, with file and line
citations, not hallucinated APIs.

Built as a RAG (Retrieval-Augmented Generation) project: chunk the
repo, embed it, retrieve the relevant pieces for a question, and hand
only those pieces to an LLM to answer from.

## Try asking things like

- *"What is the purpose of this repository?"*
- *"How does the retry logic work?"*
- *"Explain dashboard.py in detail"*
- *"Give me explanations for all the files"*
- *"Is there anything in the README that the project itself doesn't do?"*

## How it works (the one-paragraph version)

> The repo is broken into chunks at function/class boundaries (not
> arbitrary line counts), each chunk is turned into a vector using a
> local embedding model, and those vectors are stored for similarity
> search. When you ask a question, it's embedded the same way, the
> closest-matching code chunks are retrieved, and only those chunks
> (plus a map of the whole repo's structure) are handed to an LLM
> along with your question. The model answers using just that
> material — and if it can't find anything relevant, it says so
> instead of guessing.

## What makes this more than the tutorial version

- **Function-aware chunking.** Code is split at function/class
  boundaries using language-agnostic pattern matching, not arbitrary
  character counts — so a chunk is never half of one function and
  half of another.
- **Universal language support.** Instead of an allowlist of "code"
  extensions, every file is checked for whether it's actually text
  (via binary detection) — so Rust, Kotlin, Lua, or anything else
  works without extra configuration.
- **Multiple retrieval strategies depending on the question:**
  | Question type | What happens |
  |---|---|
  | Names a specific file | Exact lookup — every chunk from that file, no embedding guesswork |
  | "all files" / "every file" | Loops through every indexed file, summarizes each individually |
  | Anything else | Wide similarity search **+** a full repo map (files, functions, classes) as background context |
- **Automatic code surfacing.** Any answer that names real files
  automatically gets an expander underneath showing those files'
  actual source — no need to separately ask "show me the code."
- **Filename disambiguation.** If a repo has two files with the same
  name (e.g. two `README.md`s), the one closest to the repo root is
  preferred, since that's almost always the "main" one being asked
  about.
- **Answers honestly when it doesn't know.** If nothing retrieved is
  a close enough match, it says so instead of inventing an answer.
- **Handles messy input.** Pasting a GitHub folder/file link
  (`.../tree/branch/...` or `.../blob/branch/...`) instead of the
  repo root URL is automatically corrected before cloning.

## Architecture

Repo (GitHub URL or local path)
│
▼
ingest.py ──► clone/read files, detect text vs. binary, walk the tree
│
▼
chunker.py ──► split each file into function/class-level chunks
│
▼
vectorstore.py ──► embed chunks (sentence-transformers) + store in ChromaDB
│
▼
[ user asks a question in the Streamlit UI ]
│
▼
vectorstore.py ──► embed the question, retrieve the closest chunks
│
▼
llm.py ──► build a prompt (question + chunks + repo map), send to Groq
│
▼
app.py ──► display the answer, auto-surface any files it referenced


## Setup

### 1. Get a free Groq API key
Groq runs the LLM — it's free (no credit card), and fast (custom LPU
hardware, hundreds of tokens/sec).

1. Sign up at [console.groq.com](https://console.groq.com)
2. Create an API key

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Set your API key
```bash
export GROQ_API_KEY=your_key_here
```

### 4. Run it
```bash
streamlit run app.py
```

### 5. Use it
1. Paste a GitHub URL (e.g. `https://github.com/psf/requests`) or a
   local folder path into the sidebar, click **Index repo**.
2. Wait for it to clone, chunk, and embed (first run also downloads
   the small local embedding model — a few hundred MB, one-time).
3. Ask questions in the chat box.
4. Expand **🔍 Retrieved chunks** or **📄 Code for files mentioned**
   under any answer to see exactly what the model was given.

## Deploying it as a website (free)

This is set up to deploy on [Streamlit Community
Cloud](https://share.streamlit.io) for $0:

1. Push this project to a **public** GitHub repo (required for the
   free tier).
2. On share.streamlit.io, click **New app**, point it at your repo
   and `app.py`.
3. In the app's **Settings → Secrets**, add:

GROQ_API_KEY = "your_key_here"

4. Deploy.

Each app on the free tier gets 1GB RAM/CPU. The embedding model here
is intentionally small to fit comfortably within that, but avoid
indexing extremely large repos on the free tier. Multiple people can
use the deployed app at once safely — each browser session gets its
own fully isolated in-memory index, so one person's indexed repo can
never overwrite another's.

## Project structure

codebase_rag/
├── app.py # Streamlit UI
├── ingest.py # clone/read repo, detect text files, walk the tree
├── chunker.py # split files into function/class chunks
├── vectorstore.py # embeddings + ChromaDB storage/retrieval
├── llm.py # prompt building + calls to Groq's API
└── requirements.txt


## Things you could add next

- Swap the regex-based chunker for `tree-sitter` for fully
  language-aware parsing instead of pattern matching.
- Cache indexed repos so re-opening the app doesn't require
  re-indexing from scratch.
- Add a confidence indicator in the UI based on retrieval distance.
- Support comparing multiple repos side by side.