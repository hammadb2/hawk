"""ARIA Phase 4 — OpenAI embedding helpers for semantic memory.

Uses text-embedding-3-small (1536 dimensions) to embed CRM event summaries
and user queries for cosine-similarity retrieval via pgvector.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from openai import OpenAI

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536


def get_embedding(text: str) -> list[float] | None:
    """Return a 1536-dim embedding vector for *text*, or None on failure."""
    if not OPENAI_API_KEY or not text.strip():
        return None
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        r = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text.strip()[:8000],  # API limit guard
            dimensions=EMBEDDING_DIMENSIONS,
        )
        return r.data[0].embedding
    except Exception as e:
        logger.warning("embedding failed: %s", e)
        return None


def get_embeddings_batch(texts: list[str]) -> list[list[float] | None]:
    """Return embeddings for a batch of texts. None for any that fail."""
    if not OPENAI_API_KEY or not texts:
        return [None] * len(texts)
    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        cleaned = [t.strip()[:8000] for t in texts]
        r = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=cleaned,
            dimensions=EMBEDDING_DIMENSIONS,
        )
        result: list[list[float] | None] = [None] * len(texts)
        for item in r.data:
            result[item.index] = item.embedding
        return result
    except Exception as e:
        logger.warning("batch embedding failed: %s", e)
        return [None] * len(texts)


def format_embedding_for_pgvector(embedding: list[float]) -> str:
    """Format a Python list of floats as a pgvector-compatible string '[0.1,0.2,...]'."""
    return "[" + ",".join(f"{v:.8f}" for v in embedding) + "]"
