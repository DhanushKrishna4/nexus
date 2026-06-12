"""
Embeddings for semantic search, computed by an Ollama embedding model (bge-m3).

We compute embeddings ourselves and hand them to ChromaDB explicitly (both when
storing documents and when querying), rather than relying on ChromaDB's built-in
default embedder. Two reasons:

  1. Quality — bge-m3 is dramatically better than ChromaDB's tiny default
     (all-MiniLM-L6-v2), and retrieval quality caps how useful the whole RAG
     system is.
  2. One inference server — embeddings run on the same Ollama/GPU as the chat
     and vision models; no extra Python ML stack to install or load.

Because we always pass embeddings explicitly, the read path stays light (no
heavy chromadb client needed just to embed a query).
"""
from __future__ import annotations

from functools import lru_cache

import config


@lru_cache(maxsize=1)
def _client():
    import ollama
    return ollama.Client(host=config.OLLAMA_HOST)


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Return one embedding vector per input string (order preserved)."""
    texts = list(texts)
    if not texts:
        return []
    resp = _client().embed(model=config.EMBED_MODEL, input=texts,
                           keep_alive=config.KEEP_ALIVE)
    # The ollama client returns either an object with `.embeddings` or a dict.
    return getattr(resp, "embeddings", None) or resp["embeddings"]


def embed_one(text: str) -> list[float]:
    """Convenience: embedding for a single string."""
    return embed_texts([text])[0]
