"""Backward-compatible shim over ``services.llm_router``.

All existing callers (Charlotte, ARIA, Guardian, portal AI, hawk_chat) import
``chat_text_sync`` / ``chat_text_async`` / ``default_openai_model`` from this
module. They keep working unchanged; the router transparently picks Ollama
(qwen3) or OpenAI per the rules in ``services.llm_router``.
"""

from __future__ import annotations

from services.llm_router import chat_text_async, chat_text_sync, default_openai_model, get_chat_client

__all__ = ["chat_text_async", "chat_text_sync", "default_openai_model", "get_chat_client"]
