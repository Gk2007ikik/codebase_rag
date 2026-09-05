"""
llm.py
------
Sends the question + retrieved code chunks to Groq's free, fast LLM API
and gets back an answer.

Setup: get a free API key at https://console.groq.com (no credit card
required), then set it as an environment variable or Streamlit secret
named GROQ_API_KEY.
"""

import os
import re
import time
import requests

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"

DISTANCE_THRESHOLD = 1.0

PER_FILE_KEYWORDS = [
    "all the files", "every file", "each file", "all files", "per file",
]

SYSTEM_PROMPT = "You are a helpful assistant that explains a codebase to the user. You are given a question and several code snippets retrieved from the repository. Answer ONLY using the provided snippets. Always mention which file (and line numbers) your answer is based on. If the snippets don't actually answer the question, say so honestly instead of guessing."


def _call_groq(prompt, model, timeout=60, max_retries=1):
    """
    Shared call to Groq's OpenAI-compatible chat completions endpoint.
    Returns (text, error). Retries once on a 429 (rate limit) using the
    Retry-After header if present, since the free tier is rate-limited
    per minute and a short wait usually clears it.
    """
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        return None, "GROQ_API_KEY is not set. Add it as a Streamlit secret or environment variable."

    headers = {
        "Authorization": "Bearer " + api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }

    attempt = 0
    while True:
        try:
            response = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=timeout)
            if response.status_code == 429 and attempt < max_retries:
                retry_after = 2.0
                try:
                    retry_after = float(response.headers.get("Retry-After", 2))
                except ValueError:
                    pass
                time.sleep(retry_after)
                attempt += 1
                continue
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"].strip(), None
        except requests.exceptions.HTTPError:
            return None, "Groq API error (" + str(response.status_code) + "): " + response.text[:200]
        except requests.exceptions.RequestException as e:
            return None, "Couldn't reach Groq API: " + str(e)
        except Exception as e:
            return None, "Unexpected error calling Groq: " + str(e)


def extract_filename_mention(question, known_files):
    """
    Find an indexed file the question is referring to. Matches either the
    full filename ("dashboard.py") or the bare name without extension
    ("readme", "dashboard"), using word-boundaries so "log" doesn't match
    inside "dialog.py". When multiple indexed files share the same name
    (e.g. two README.md files), prefer the one closest to the repo root -
    that's almost always the "main" one a bare mention refers to.
    """
    q = question.lower()
    candidates = []

    for file_path in known_files:
        fname = file_path.split("/")[-1].lower()
        base = fname.rsplit(".", 1)[0] if "." in fname else fname

        for name in (fname, base):
            if not name:
                continue
            pattern = r"(?<![a-z0-9])" + re.escape(name) + r"(?![a-z0-9])"
            if re.search(pattern, q):
                candidates.append(file_path)
                break

    if not candidates:
        return None

    candidates.sort(key=lambda p: p.count("/"))
    return candidates[0]


def find_mentioned_files(text, known_files):
    """Scan any text (typically the model's own answer) for mentions of
    indexed files by filename, preserving first-mention order. This is
    what lets us reliably surface real code under an answer without
    trying to guess every way a person might phrase 'show me the code'."""
    text_lower = text.lower()
    found = []
    for file_path in known_files:
        fname = file_path.split("/")[-1].lower()
        if fname in text_lower and file_path not in found:
            found.append(file_path)
    return found


def is_per_file_request(question):
    q = question.lower()
    return any(kw in q for kw in PER_FILE_KEYWORDS)


def summarize_file(file_path, code_sample, model="llama-3.1-8b-instant", max_words=20):
    prompt = (
        "In " + str(max_words) + " words or fewer, summarize what this file does. "
        "Be specific and concrete, no filler like 'This file contains...'.\n\n"
        "File: " + file_path + "\n"
        "```\n" + code_sample + "\n```\n\n"
        "One-line summary:"
    )
    text, error = _call_groq(prompt, model, timeout=30)
    if error:
        return "(couldn't summarize: " + error + ")"
    return text


def build_prompt(question, hits, repo_map=None):
    context_blocks = []
    for h in hits:
        meta = h["meta"]
        context_blocks.append(
            "File: " + meta["file_path"] + " (lines " + str(meta["start_line"]) + "-" + str(meta["end_line"]) +
            ", '" + meta["name"] + "')\n```\n" + h["code"] + "\n```"
        )
    context = "\n\n".join(context_blocks)
    repo_map_section = ("\n" + repo_map + "\n") if repo_map else ""
    return (
        SYSTEM_PROMPT + "\n" +
        repo_map_section + "\n" +
        "Retrieved code:\n" + context + "\n\n" +
        "Question: " + question + "\n\n" +
        "Answer:"
    )


def has_relevant_context(hits):
    if not hits:
        return False
    return min(h["distance"] for h in hits) <= DISTANCE_THRESHOLD


def generate_answer(question, hits, model="llama-3.1-8b-instant", repo_map=None):
    if repo_map is None and not has_relevant_context(hits):
        return (
            "I couldn't find anything in this codebase that clearly answers that. "
            "Try rephrasing, or it might genuinely not be in here."
        )
    prompt = build_prompt(question, hits, repo_map=repo_map)
    text, error = _call_groq(prompt, model, timeout=60)
    if error:
        return error
    return text