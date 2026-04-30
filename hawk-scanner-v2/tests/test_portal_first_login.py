"""Unit tests for the first-portal-login helper (priority list #32).

Exercises :mod:`services.portal_first_login` directly against a stub
Supabase endpoint via ``httpx.patch`` monkey-patched to a fake. We care
about two behaviours:

1. When ``get_client_id_for_portal_user`` returns ``None`` (no portal
   client linked to the auth user) we raise an HTTP 400 so the frontend
   can show the "no portal linked" fallback instead of silently pass.
2. When the Supabase PATCH succeeds we surface the new
   ``last_portal_login_at`` ISO timestamp so the UI can update local
   state without a round-trip read.
"""
from __future__ import annotations

import pathlib
import sys
from collections.abc import Iterator
from typing import Any

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_BACKEND = _REPO_ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


class _FakeResponse:
    def __init__(self, status_code: int = 204, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


@pytest.fixture
def stub_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """portal_first_login reads SUPABASE_URL at call time — pin it for the test."""
    from services import portal_first_login

    monkeypatch.setattr(portal_first_login, "SUPABASE_URL", "https://stub.supabase.co")
    yield


def test_mark_first_portal_login_raises_when_no_client_linked(
    monkeypatch: pytest.MonkeyPatch, stub_env: None
) -> None:
    from fastapi import HTTPException
    from services import portal_first_login

    monkeypatch.setattr(portal_first_login, "get_client_id_for_portal_user", lambda _uid: None)

    with pytest.raises(HTTPException) as exc:
        portal_first_login.mark_first_portal_login("auth-uid-1")
    assert exc.value.status_code == 400
    assert "No portal client" in str(exc.value.detail)


def test_mark_first_portal_login_returns_iso_timestamp_on_success(
    monkeypatch: pytest.MonkeyPatch, stub_env: None
) -> None:
    from services import portal_first_login

    monkeypatch.setattr(portal_first_login, "get_client_id_for_portal_user", lambda _uid: "cid-42")

    captured: dict[str, Any] = {}

    def _fake_patch(url: str, **kwargs: Any) -> _FakeResponse:
        captured["url"] = url
        captured["params"] = kwargs.get("params")
        captured["json"] = kwargs.get("json")
        return _FakeResponse(status_code=204)

    monkeypatch.setattr(portal_first_login.httpx, "patch", _fake_patch)

    out = portal_first_login.mark_first_portal_login("auth-uid-2")

    assert out["ok"] == "true"
    assert out["last_portal_login_at"].endswith("+00:00")
    assert captured["url"].endswith("/rest/v1/clients")
    assert captured["params"] == {"id": "eq.cid-42"}
    assert list(captured["json"].keys()) == ["last_portal_login_at"]


def test_mark_first_portal_login_502s_on_supabase_error(
    monkeypatch: pytest.MonkeyPatch, stub_env: None
) -> None:
    from fastapi import HTTPException
    from services import portal_first_login

    monkeypatch.setattr(portal_first_login, "get_client_id_for_portal_user", lambda _uid: "cid-42")
    monkeypatch.setattr(
        portal_first_login.httpx,
        "patch",
        lambda *_a, **_kw: _FakeResponse(status_code=500, text="boom"),
    )

    with pytest.raises(HTTPException) as exc:
        portal_first_login.mark_first_portal_login("auth-uid-3")
    assert exc.value.status_code == 502
