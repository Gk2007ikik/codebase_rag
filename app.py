
import os
import streamlit as st

from ingest import get_repo_path, collect_chunks, build_repo_map, group_by_file
from vectorstore import get_client, get_collection, index_chunks, retrieve, get_chunks_by_file
from llm import (
    generate_answer, is_per_file_request, summarize_file,
    extract_filename_mention, find_mentioned_files,
)

try:
    if "GROQ_API_KEY" in st.secrets:
        os.environ.setdefault("GROQ_API_KEY", st.secrets["GROQ_API_KEY"])
except Exception:
    pass

st.set_page_config(page_title="Chat With a Codebase", page_icon="🧠", layout="wide")
st.title("🧠 Chat With a Codebase")
st.caption("Point this at a repo, then ask questions about how the code works. "
           "Answers are grounded in retrieved code snippets, with file/line citations.")

if not os.environ.get("GROQ_API_KEY"):
    st.warning(
        "No GROQ_API_KEY found. Get a free key at "
        "[console.groq.com](https://console.groq.com), then set it as an "
        "environment variable locally, or as a Streamlit secret when deployed."
    )


if "collection" not in st.session_state:
    st.session_state.collection = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "indexed_repo" not in st.session_state:
    st.session_state.indexed_repo = None
if "repo_map" not in st.session_state:
    st.session_state.repo_map = None
if "chunks" not in st.session_state:
    st.session_state.chunks = None


with st.sidebar:
    st.header("1. Index a repo")
    repo_input = st.text_input(
        "GitHub URL or local path",
        placeholder="https://github.com/user/repo or /path/to/repo",
    )
    model_name = st.text_input(
        "Groq model",
        value="llama-3.1-8b-instant",
        help="See console.groq.com/docs/models for the current list of free models.",
    )
    top_k = st.slider("Chunks to retrieve per question", 1, 10, 5)

    if st.button("Index repo", type="primary"):
        if not repo_input.strip():
            st.error("Enter a repo URL or path first.")
        else:
            with st.spinner("Cloning / reading repo..."):
                try:
                    repo_path = get_repo_path(repo_input.strip())
                except Exception as e:
                    st.error(f"Couldn't get repo: {e}")
                    st.stop()

            with st.spinner("Chunking files..."):
                chunks = collect_chunks(repo_path)

            if not chunks:
                st.warning("No supported code files found in this repo.")
            else:
                with st.spinner(f"Embedding {len(chunks)} chunks (first run downloads the model)..."):
                    client = get_client()
                    collection = get_collection(client, reset=True)
                    index_chunks(collection, chunks)

                st.session_state.collection = collection
                st.session_state.indexed_repo = repo_input.strip()
                st.session_state.messages = []
                st.session_state.repo_map = build_repo_map(chunks)
                st.session_state.chunks = chunks
                st.success(f"Indexed {len(chunks)} chunks from {len(set(c.file_path for c in chunks))} files.")

    if st.session_state.indexed_repo:
        st.info(f"Currently indexed:\n\n`{st.session_state.indexed_repo}`")


def show_referenced_code(collection, known_files, answer_text):
    mentioned = find_mentioned_files(answer_text, known_files)
    if not mentioned:
        return
    with st.expander("📄 Code for files mentioned in this answer (" + str(len(mentioned)) + ")"):
        for fp in mentioned:
            file_hits = get_chunks_by_file(collection, fp)
            if not file_hits:
                continue
            st.markdown("**" + fp + "**")
            for h in sorted(file_hits, key=lambda x: x["meta"]["start_line"]):
                st.code(h["code"], language="python")


# --- main: chat ----------------------------------------------------------
if st.session_state.collection is None:
    st.info("👈 Index a repo in the sidebar to get started.")
else:
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    question = st.chat_input("Ask something about this codebase...")
    if question:
        st.session_state.messages.append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            known_files = sorted(set(c.file_path for c in st.session_state.chunks))
            named_file = extract_filename_mention(question, known_files)

            if named_file:
                with st.spinner("Reading " + named_file + "..."):
                    hits = get_chunks_by_file(st.session_state.collection, named_file)

                with st.spinner("Generating answer..."):
                    answer = generate_answer(
                        question, hits, model=model_name,
                        repo_map=st.session_state.repo_map,
                    )

                st.markdown(answer)
                show_referenced_code(st.session_state.collection, known_files, answer)

            elif is_per_file_request(question):
                by_file = group_by_file(st.session_state.chunks)
                lines = []
                progress = st.progress(0.0, text="Summarizing files...")
                for i, (file_path, file_chunks) in enumerate(sorted(by_file.items())):
                    code_sample = "\n\n".join(c.code for c in file_chunks)[:1500]
                    summary = summarize_file(file_path, code_sample, model=model_name)
                    lines.append(f"- **{file_path}**: {summary}")
                    progress.progress((i + 1) / len(by_file), text=f"Summarizing files... ({i+1}/{len(by_file)})")
                progress.empty()
                answer = "\n".join(lines)
                st.markdown(answer)

            else:
                effective_top_k = max(top_k, 10)

                with st.spinner("Retrieving relevant code..."):
                    hits = retrieve(st.session_state.collection, question, top_k=effective_top_k)

                with st.spinner("Generating answer..."):
                    answer = generate_answer(
                        question, hits, model=model_name,
                        repo_map=st.session_state.repo_map,
                    )

                st.markdown(answer)
                show_referenced_code(st.session_state.collection, known_files, answer)

                with st.expander("🔍 Retrieved chunks (what the model saw)"):
                    for h in hits:
                        meta = h["meta"]
                        st.markdown(
                            f"**{meta['file_path']}** (lines {meta['start_line']}-{meta['end_line']}, "
                            f"`{meta['name']}`) — distance: {h['distance']:.3f}"
                        )
                        st.code(h["code"], language="python")

        st.session_state.messages.append({"role": "assistant", "content": answer})