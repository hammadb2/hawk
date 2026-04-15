"""Shared OpenAI Chat Completions helpers (sync + async)."""

from __future__ import annotations

import os
from typing import Any

from openai import AsyncOpenAI, OpenAI


def default_openai_model() -> str:
    return os.environ.get("OPENAI_MODEL", "gpt-4o").strip() or "gpt-4o"


def chat_text_sync(
    *,
    api_key: str,
    user_messages: list[dict[str, str]],
    max_tokens: int,
    system: str | None = None,
    model: str | None = None,
) -> str:
    client = OpenAI(api_key=api_key)
    msgs: list[dict[str, Any]] = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.extend(user_messages)
    m = (model or default_openai_model()).strip() or default_openai_model()
    r = client.chat.completions.create(model=m, messages=msgs, max_tokens=max_tokens)
    return (r.choices[0].message.content or "").strip()


async def chat_text_async(
    *,
    api_key: str,
    user_messages: list[dict[str, str]],
    max_tokens: int,
    system: str | None = None,
    model: str | None = None,
) -> str:
    client = AsyncOpenAI(api_key=api_key)
    msgs: list[dict[str, Any]] = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.extend(user_messages)
    m = (model or default_openai_model()).strip() or default_openai_model()
    r = await client.chat.completions.create(model=m, messages=msgs, max_tokens=max_tokens)
    return (r.choices[0].message.content or "").strip()
