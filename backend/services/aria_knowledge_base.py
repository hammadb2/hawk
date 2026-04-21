"""ARIA prospect-conversation knowledge base loader + retrieval.

The knowledge base is a single markdown file at ``backend/data/aria_knowledge_base.md``.
It's the source of truth ARIA consults before drafting any outbound reply —
pricing, US regulatory angles (HIPAA / FTC Safeguards / ABA Op 24-514), common findings, objection playbooks, FAQ.

Why not a vector store? At current scale (one file, <10k tokens) string
matching + section slicing outperforms an embedding round-trip and is
deterministic for A/B comparison. Swap in ``aria_embedding`` later if the
file grows beyond ~20k tokens.
"""

from __future__ import annotations

import logging
import os
import re
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

# ``backend/data/aria_knowledge_base.md`` — resolve relative to this file so it
# works regardless of the caller's CWD.
_KB_PATH = Path(__file__).resolve().parent.parent / "data" / "aria_knowledge_base.md"

_lock = threading.Lock()
_cache: dict[str, object] | None = None


def _load() -> dict[str, object]:
    """Load + cache the KB. Cache invalidates on mtime change."""
    global _cache
    with _lock:
        try:
            mtime = _KB_PATH.stat().st_mtime
        except FileNotFoundError:
            _cache = {"full": "", "sections": {}, "mtime": 0}
            return _cache
        if _cache is not None and _cache.get("mtime") == mtime:
            return _cache
        text = _KB_PATH.read_text(encoding="utf-8")
        _cache = {
            "full": text,
            "sections": _split_sections(text),
            "mtime": mtime,
        }
        return _cache


def _split_sections(text: str) -> dict[str, str]:
    """Split markdown by level-2 headings (``## …``).

    Keys are lowercased heading text with punctuation stripped; values are the
    raw section text up to the next ``##``. Keeps the heading on the first line
    so the LLM knows the context it was pulled from.
    """
    sections: dict[str, str] = {}
    chunks = re.split(r"^## +", text, flags=re.MULTILINE)
    for chunk in chunks[1:]:
        lines = chunk.splitlines()
        if not lines:
            continue
        heading = lines[0].strip().rstrip(" #")
        key = re.sub(r"[^a-z0-9 ]", "", heading.lower()).strip()
        sections[key] = "## " + chunk.strip()
    return sections


def get_full_kb() -> str:
    """Return the full KB text (~8k tokens). Use only when no hint is available."""
    kb = _load()
    return str(kb.get("full", ""))


def retrieve_snippets(question_text: str, max_sections: int = 4) -> list[str]:
    """Return the KB sections most relevant to ``question_text``.

    Uses a simple keyword-overlap score over section bodies — deterministic,
    cheap, and good enough for a one-file KB. If nothing scores above zero,
    returns the top defaults (HAWK product + US regulatory context + common findings) so the
    LLM always has baseline context.
    """
    kb = _load()
    sections = dict(kb.get("sections") or {})
    if not sections:
        return []

    if not question_text:
        return _default_snippets(sections, max_sections)

    q = re.findall(r"[a-zA-Z][a-zA-Z0-9\-']{2,}", question_text.lower())
    q = [w for w in q if w not in _STOP_WORDS]
    if not q:
        return _default_snippets(sections, max_sections)

    scored: list[tuple[int, str, str]] = []
    for key, body in sections.items():
        body_lc = body.lower()
        score = sum(body_lc.count(word) for word in q)
        # Bonus when the heading itself matches a keyword.
        score += sum(3 for word in q if word in key)
        if score > 0:
            scored.append((score, key, body))

    scored.sort(key=lambda t: (-t[0], t[1]))
    picked = [body for _, _, body in scored[:max_sections]]
    if not picked:
        picked = _default_snippets(sections, max_sections)
    return picked


def _default_snippets(sections: dict[str, str], n: int) -> list[str]:
    preferred_order = [
        "what hawk security is plain english",
        "how the scanner works",
        "service tiers and pricing",
        "pipeda context  why this matters in plain language",
        "common findings and what they mean",
    ]
    out: list[str] = []
    for key in preferred_order:
        body = sections.get(key)
        if body:
            out.append(body)
        if len(out) >= n:
            break
    return out


_STOP_WORDS = {
    "the", "and", "for", "you", "your", "our", "are", "was", "were",
    "with", "what", "when", "where", "how", "why", "this", "that", "have",
    "has", "had", "will", "would", "could", "should", "any", "all",
    "not", "but", "from", "into", "just", "about", "some", "much",
    "more", "can", "there", "their", "they", "them", "then", "than",
    "does", "did", "get", "got", "got", "been", "being", "its", "his",
    "her", "which", "who", "whose", "because",
}


__all__ = ["retrieve_snippets", "get_full_kb"]
