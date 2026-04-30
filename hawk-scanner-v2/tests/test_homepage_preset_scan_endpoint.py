"""Smoke tests for GET /api/marketing/homepage-preset-scan (priority list #45).

Boots FastAPI's TestClient against ``backend/main.py`` and exercises both
the 404 (cache missing) and 200 (cache present) paths. Keeps the contract
pinned so `home-scanner.tsx` can rely on the shape matching
``PublicScanResult`` on the frontend.
"""
from __future__ import annotations

import json
import pathlib
import sys
from collections.abc import Iterator

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_BACKEND = _REPO_ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


def _cache_path() -> pathlib.Path:
    from routers.marketing import _PRESET_SCAN_PATH

    return pathlib.Path(_PRESET_SCAN_PATH)


@pytest.fixture
def client() -> Iterator["TestClient"]:  # type: ignore[name-defined]
    from fastapi.testclient import TestClient
    from main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture
def preserve_cache() -> Iterator[pathlib.Path]:
    """Save and restore whatever cache file exists so tests don't clobber it."""
    path = _cache_path()
    had_cache = path.exists()
    saved = path.read_bytes() if had_cache else None
    try:
        # Start each test with NO cache; tests that need one write it themselves.
        if had_cache:
            path.unlink()
        yield path
    finally:
        if had_cache and saved is not None:
            path.write_bytes(saved)
        elif path.exists():
            path.unlink()


def test_preset_scan_returns_404_when_cache_missing(client, preserve_cache) -> None:
    assert not preserve_cache.exists()
    r = client.get("/api/marketing/homepage-preset-scan")
    assert r.status_code == 404
    body = r.json()
    assert "preset-scan" in (body.get("detail") or "").lower()


def test_preset_scan_returns_payload_when_cache_present(client, preserve_cache) -> None:
    payload = {
        "domain": "worst.example",
        "score": 38,
        "grade": "F",
        "issues_count": 9,
        "findings_preview": [
            {"severity": "critical", "text": "DMARC missing"},
            {"severity": "high", "text": "TLS cipher weak"},
        ],
    }
    preserve_cache.parent.mkdir(parents=True, exist_ok=True)
    preserve_cache.write_text(json.dumps(payload), encoding="utf-8")

    r = client.get("/api/marketing/homepage-preset-scan")
    assert r.status_code == 200
    got = r.json()
    assert got["domain"] == "worst.example"
    assert got["score"] == 38
    # Preview preserved end-to-end so the frontend can render rows directly.
    assert got["findings_preview"][0]["severity"] == "critical"


def test_preset_scan_malformed_cache_returns_500(client, preserve_cache) -> None:
    preserve_cache.parent.mkdir(parents=True, exist_ok=True)
    preserve_cache.write_text("not json at all", encoding="utf-8")
    r = client.get("/api/marketing/homepage-preset-scan")
    assert r.status_code == 500


def test_preset_scan_empty_dict_returns_500(client, preserve_cache) -> None:
    """No `domain` key → refuse to serve so the frontend falls back to idle."""
    preserve_cache.parent.mkdir(parents=True, exist_ok=True)
    preserve_cache.write_text("{}", encoding="utf-8")
    r = client.get("/api/marketing/homepage-preset-scan")
    assert r.status_code == 500
