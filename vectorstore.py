"""
vectorstore.py
--------------
Embeds code chunks with a local sentence-transformers model and stores
them in an in-memory (ephemeral) ChromaDB collection.

Uses an ephemeral client rather than a persistent on-disk one on
purpose: on a deployed, multi-user site, every browser session calls
get_client() independently when it clicks "Index repo". An ephemeral
client creates a fresh, fully isolated in-memory store each time, so
one visitor's indexed repo can never collide with or overwrite another
visitor's. The trade-off is that the index doesn't survive an app
restart - acceptable here since re-indexing is a normal part of the
workflow anyway.
"""

import chromadb
from chromadb.utils import embedding_functions

from chunker import Chunk

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
COLLECTION_NAME = "codebase_chunks"


def get_client():
    return chromadb.EphemeralClient()


def get_collection(client, reset: bool = False):
    embed_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=EMBEDDING_MODEL_NAME
    )

    if reset:
        try:
            client.delete_collection(COLLECTION_NAME)
        except Exception:
            pass

    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embed_fn,
    )


def index_chunks(collection, chunks: list[Chunk], batch_size: int = 100):
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        collection.add(
            ids=[f"{c.file_path}:{c.start_line}-{c.end_line}:{i+j}" for j, c in enumerate(batch)],
            documents=[c.code for c in batch],
            metadatas=[{
                "file_path": c.file_path,
                "start_line": c.start_line,
                "end_line": c.end_line,
                "name": c.name,
            } for c in batch],
        )


def retrieve(collection, question: str, top_k: int = 5):
    results = collection.query(query_texts=[question], n_results=top_k)
    hits = []
    for doc, meta, dist in zip(
        results["documents"][0], results["metadatas"][0], results["distances"][0]
    ):
        hits.append({"code": doc, "meta": meta, "distance": dist})
    return hits


def get_chunks_by_file(collection, file_path):
    results = collection.get(where={"file_path": file_path})
    hits = []
    for doc, meta in zip(results["documents"], results["metadatas"]):
        hits.append({"code": doc, "meta": meta, "distance": 0.0})
    return hits