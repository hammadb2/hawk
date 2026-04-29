"""LLM router: Ollama primary (qwen3) with OpenAI fallback.

Drop-in replacement for the public surface of ``backend/services/openai_chat.py``.
All existing callers (Charlotte, ARIA, Guardian, portal AI) keep their
signatures unchanged; ``openai_chat`` is now a 3-line re-export shim over
this module.

Routing (in order):
    1. Explicit ``model=`` arg.
       * ``gpt-*`` / ``o1-*`` / ``o3-*`` / ``text-*`` -> OpenAI.
       * Anything else -> Ollama.
    2. ``task=`` hint (optional):
       * ``short`` / ``classify`` / ``autoreply_triage``     -> fast model.
       * ``email`` / ``reasoning`` / ``long_form`` / ``nurture`` -> primary.
    3. ``LLM_ROUTER_MODE`` env:
       * ``ollama`` -> always Ollama.
       * ``openai`` -> always OpenAI (router is a no-op passthrough).
       * ``auto``   -> Ollama primary; fall back to fast Ollama, then
                       OpenAI on error/timeout. Disabled with
                       ``LLM_ROUTER_FALLBACK=none``.

One log line is emitted per terminal call, e.g.:
    llm_router route=email primary=qwen3.5:122b final=qwen3.5:122b latency_ms=1843 status=ok
    llm_router route=email primary=qwen3.5:122b final=gpt-4o fallback_reason=timeout latency_ms=62100

Config vars (all optional; defaults chosen to match the current Railway wiring):
    OLLAMA_BASE_URL         http://localhost:11434
    OLLAMA_BASIC_USER       (optional HTTP basic auth user)
    OLLAMA_BASIC_PASS       (optional HTTP basic auth pass)
    LLM_ROUTER_MODE         auto | ollama | openai    (default: auto)
    LLM_ROUTER_FALLBACK     openai | none             (default: openai)
    LLM_ROUTER_TIMEOUT_S    60
    LLM_ROUTER_PRIMARY_MODEL   qwen3.5:122b
    LLM_ROUTER_FAST_MODEL      qwen3:30b-a3b
    OPENAI_MODEL            existing (fallback target)
    OPENAI_API_KEY          existing (fallback only in auto)
"""

from __future__ import annotations

import logging
import os
import time
from typing import Any

import httpx
from openai import AsyncOpenAI, OpenAI

logger = logging.getLogger(__name__)


# --- config helpers ---------------------------------------------------------


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip() or default


def default_openai_model() -> str:
    return _env("OPENAI_MODEL", "gpt-4o") or "gpt-4o"


def _router_mode() -> str:
    m = _env("LLM_ROUTER_MODE", "auto").lower()
    return m if m in ("auto", "ollama", "openai") else "auto"


def _fallback_enabled() -> bool:
    return _env("LLM_ROUTER_FALLBACK", "openai").lower() != "none"


def _timeout_s() -> float:
    try:
        return float(_env("LLM_ROUTER_TIMEOUT_S", "60"))
    except ValueError:
        return 60.0


def _primary_model() -> str:
    return _env("LLM_ROUTER_PRIMARY_MODEL", "qwen3.5:122b") or "qwen3.5:122b"


def _fast_model() -> str:
    return _env("LLM_ROUTER_FAST_MODEL", "qwen3:30b-a3b") or "qwen3:30b-a3b"


def _ollama_base_url() -> str:
    return _env("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")


def _ollama_auth() -> tuple[str, str] | None:
    u = _env("OLLAMA_BASIC_USER")
    p = _env("OLLAMA_BASIC_PASS")
    return (u, p) if u and p else None


# --- model classification ---------------------------------------------------

_OPENAI_PREFIXES = ("gpt-", "gpt4", "o1-", "o3-", "text-")
_TASK_FAST = {"short", "classify", "triage", "autoreply_triage", "label"}
_TASK_PRIMARY = {"email", "reasoning", "long_form", "nurture", "draft"}


def _is_openai_model(model: str) -> bool:
    m = (model or "").lower()
    return any(m.startswith(p) for p in _OPENAI_PREFIXES)


def _pick_ollama_model(task: str | None) -> str:
    t = (task or "").strip().lower()
    if t in _TASK_FAST:
        return _fast_model()
    # Default everything else (incl. unknown / None / _TASK_PRIMARY) to primary.
    return _primary_model()


# --- core providers ---------------------------------------------------------


def _ollama_messages(system: str | None, user_messages: list[dict[str, str]]) -> list[dict[str, str]]:
    msgs: list[dict[str, str]] = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.extend(user_messages)
    return msgs


def _ollama_payload(model: str, msgs: list[dict[str, str]], max_tokens: int) -> dict[str, Any]:
    return {
        "model": model,
        "messages": msgs,
        "stream": False,
        "think": False,  # keep the response free of <think>...</think> reasoning
        "options": {"num_predict": int(max_tokens)},
    }


def _extract_ollama_text(data: dict[str, Any]) -> str:
    msg = data.get("message") or {}
    content = msg.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()
    # Some Ollama builds put the assistant text in `response` instead.
    resp = data.get("response")
    if isinstance(resp, str):
        return resp.strip()
    return ""


def _call_ollama_sync(
    *, model: str, user_messages: list[dict[str, str]], max_tokens: int, system: str | None
) -> str:
    msgs = _ollama_messages(system, user_messages)
    payload = _ollama_payload(model, msgs, max_tokens)
    auth = _ollama_auth()
    with httpx.Client(timeout=_timeout_s(), auth=auth) as client:
        r = client.post(f"{_ollama_base_url()}/api/chat", json=payload)
        r.raise_for_status()
        text = _extract_ollama_text(r.json())
    if not text:
        raise RuntimeError(f"ollama returned empty content for model={model}")
    return text


async def _call_ollama_async(
    *, model: str, user_messages: list[dict[str, str]], max_tokens: int, system: str | None
) -> str:
    msgs = _ollama_messages(system, user_messages)
    payload = _ollama_payload(model, msgs, max_tokens)
    auth = _ollama_auth()
    async with httpx.AsyncClient(timeout=_timeout_s(), auth=auth) as client:
        r = await client.post(f"{_ollama_base_url()}/api/chat", json=payload)
        r.raise_for_status()
        text = _extract_ollama_text(r.json())
    if not text:
        raise RuntimeError(f"ollama returned empty content for model={model}")
    return text


def _call_openai_sync(
    *,
    api_key: str,
    user_messages: list[dict[str, str]],
    max_tokens: int,
    system: str | None,
    model: str | None,
) -> str:
    client = OpenAI(api_key=api_key)
    msgs: list[dict[str, Any]] = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.extend(user_messages)
    m = (model or default_openai_model()).strip() or default_openai_model()
    r = client.chat.completions.create(model=m, messages=msgs, max_tokens=max_tokens)
    return (r.choices[0].message.content or "").strip()


async def _call_openai_async(
    *,
    api_key: str,
    user_messages: list[dict[str, str]],
    max_tokens: int,
    system: str | None,
    model: str | None,
) -> str:
    client = AsyncOpenAI(api_key=api_key)
    msgs: list[dict[str, Any]] = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.extend(user_messages)
    m = (model or default_openai_model()).strip() or default_openai_model()
    r = await client.chat.completions.create(model=m, messages=msgs, max_tokens=max_tokens)
    return (r.choices[0].message.content or "").strip()


# --- routing ----------------------------------------------------------------


def _chain(primary: str, fast: str, openai_model: str, *, mode: str, fallback: bool) -> list[tuple[str, str]]:
    """Build an ordered (provider, model) chain for a given request."""
    if mode == "openai":
        return [("openai", openai_model)]
    if mode == "ollama":
        # Never touch OpenAI in this mode.
        if primary == fast:
            return [("ollama", primary)]
        return [("ollama", primary), ("ollama", fast)]
    # auto
    chain: list[tuple[str, str]] = [("ollama", primary)]
    if primary != fast:
        chain.append(("ollama", fast))
    if fallback:
        chain.append(("openai", openai_model))
    return chain


def _route(*, explicit_model: str | None, task: str | None) -> tuple[str, list[tuple[str, str]]]:
    """Decide the provider chain. Returns (route_label, [(provider, model)...])."""
    mode = _router_mode()
    openai_model = default_openai_model()

    if explicit_model:
        if _is_openai_model(explicit_model):
            return (f"explicit:{explicit_model}", [("openai", explicit_model)])
        # Explicit non-OpenAI model = Ollama with that exact tag; no fallback to a different tag.
        chain: list[tuple[str, str]] = [("ollama", explicit_model)]
        if mode == "auto" and _fallback_enabled():
            chain.append(("openai", openai_model))
        return (f"explicit:{explicit_model}", chain)

    picked = _pick_ollama_model(task)
    chain = _chain(picked, _fast_model(), openai_model, mode=mode, fallback=_fallback_enabled())
    route_label = task or ("primary" if picked == _primary_model() else "fast")
    return (route_label, chain)


def _log(route: str, primary: str, final: str, *, status: str, started: float, reason: str = "") -> None:
    latency_ms = int((time.monotonic() - started) * 1000)
    extra = f" fallback_reason={reason}" if reason else ""
    logger.info(
        "llm_router route=%s primary=%s final=%s latency_ms=%d status=%s%s",
        route, primary, final, latency_ms, status, extra,
    )


# --- public API (signature-compatible with openai_chat) --------------------


def chat_text_sync(
    *,
    api_key: str,
    user_messages: list[dict[str, str]],
    max_tokens: int,
    system: str | None = None,
    model: str | None = None,
    task: str | None = None,
) -> str:
    """Synchronous chat completion. Routes per module docstring."""
    route, chain = _route(explicit_model=model, task=task)
    primary_model = chain[0][1]
    started = time.monotonic()
    last_exc: Exception | None = None

    for provider, m in chain:
        try:
            if provider == "ollama":
                text = _call_ollama_sync(
                    model=m, user_messages=user_messages, max_tokens=max_tokens, system=system
                )
            else:
                text = _call_openai_sync(
                    api_key=api_key, user_messages=user_messages, max_tokens=max_tokens,
                    system=system, model=m,
                )
            reason = "" if provider == chain[0][0] and m == primary_model else _reason(last_exc)
            _log(route, primary_model, m, status="ok", started=started, reason=reason)
            return text
        except Exception as exc:  # noqa: BLE001 — we intentionally fall through to fallback
            last_exc = exc
            logger.warning(
                "llm_router hop_failed provider=%s model=%s err=%s", provider, m, _brief(exc)
            )
            continue

    _log(route, primary_model, chain[-1][1], status="error", started=started, reason=_reason(last_exc))
    raise last_exc if last_exc else RuntimeError("llm_router: empty chain")


async def chat_text_async(
    *,
    api_key: str,
    user_messages: list[dict[str, str]],
    max_tokens: int,
    system: str | None = None,
    model: str | None = None,
    task: str | None = None,
) -> str:
    """Async chat completion. Routes per module docstring."""
    route, chain = _route(explicit_model=model, task=task)
    primary_model = chain[0][1]
    started = time.monotonic()
    last_exc: Exception | None = None

    for provider, m in chain:
        try:
            if provider == "ollama":
                text = await _call_ollama_async(
                    model=m, user_messages=user_messages, max_tokens=max_tokens, system=system
                )
            else:
                text = await _call_openai_async(
                    api_key=api_key, user_messages=user_messages, max_tokens=max_tokens,
                    system=system, model=m,
                )
            reason = "" if provider == chain[0][0] and m == primary_model else _reason(last_exc)
            _log(route, primary_model, m, status="ok", started=started, reason=reason)
            return text
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            logger.warning(
                "llm_router hop_failed provider=%s model=%s err=%s", provider, m, _brief(exc)
            )
            continue

    _log(route, primary_model, chain[-1][1], status="error", started=started, reason=_reason(last_exc))
    raise last_exc if last_exc else RuntimeError("llm_router: empty chain")


def _brief(exc: Exception | None) -> str:
    if exc is None:
        return ""
    s = f"{type(exc).__name__}: {exc}"
    return s if len(s) <= 200 else s[:200] + "..."


def _reason(exc: Exception | None) -> str:
    if exc is None:
        return ""
    name = type(exc).__name__.lower()
    if "timeout" in name:
        return "timeout"
    if "connect" in name or "network" in name:
        return "network"
    return "error"


def get_chat_client() -> tuple[OpenAI, str]:
    """Return an OpenAI-compatible client + model name routed through Ollama.

    For callers that need the full OpenAI client interface (e.g. tool/function
    calling), this returns a client pointed at the Ollama OpenAI-compatible
    endpoint when the router is in ``auto`` or ``ollama`` mode.  Falls back
    to OpenAI when the mode is ``openai``.
    """
    mode = _router_mode()
    if mode == "openai":
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        return OpenAI(api_key=api_key), default_openai_model()

    # Ollama exposes an OpenAI-compatible API at /v1
    base = _ollama_base_url()
    auth = _ollama_auth()
    http_client = None
    if auth:
        http_client = httpx.Client(auth=auth, timeout=_timeout_s())
    return (
        OpenAI(
            base_url=f"{base}/v1",
            api_key="ollama",  # Ollama ignores the key but OpenAI client requires one
            http_client=http_client,
            timeout=_timeout_s(),
        ),
        _primary_model(),
    )


__all__ = [
    "chat_text_sync",
    "chat_text_async",
    "default_openai_model",
    "get_chat_client",
]
