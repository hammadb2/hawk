"""Tests for scripts/check_railway_env.py (priority list #8).

The audit script must:

* Treat ``HAWK_SECRET_KEY`` and ``DATABASE_URL`` as REQUIRED.
* Resolve aliases (``CRON_SECRET`` for ``HAWK_CRON_SECRET``,
  ``NEXT_PUBLIC_SUPABASE_ANON_KEY`` for ``SUPABASE_ANON_KEY``,
  ``HAWK_CEO_PHONE`` for ``CRM_CEO_PHONE_E164``).
* Exit 1 in ``--strict`` mode when any REQUIRED is missing.
* Exit 1 in production mode (``HAWK_ENV=production``) when any REQUIRED is
  missing, even without ``--strict``.
* Exit 0 in dev mode when REQUIRED is missing (so import-time tests still pass).
* Emit valid JSON with ``--json``.
"""
from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import subprocess
import sys

_SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "check_railway_env.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_railway_env", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    # Register in sys.modules so dataclasses can resolve field types via the
    # module's __dict__ during class creation.
    sys.modules["check_railway_env"] = mod
    spec.loader.exec_module(mod)
    return mod


def _run(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    """Invoke the script in a clean subprocess with a controlled environment."""
    base_env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", "/tmp"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    base_env.update(env)
    return subprocess.run(
        [sys.executable, str(_SCRIPT), *args],
        env=base_env,
        check=False,
        capture_output=True,
        text=True,
    )


# ── Catalog correctness ────────────────────────────────────────────────


def test_required_catalog_lists_secret_key_and_database_url() -> None:
    mod = _load_module()
    names = {v.name for v in mod.REQUIRED}
    assert "HAWK_SECRET_KEY" in names
    assert "DATABASE_URL" in names


def test_aliases_resolve_when_primary_unset() -> None:
    """``HAWK_CRON_SECRET`` aliases ``CRON_SECRET``; only the alias is set
    here so we expect the script to resolve it."""
    out = _run(
        {"HAWK_ENV": "development", "CRON_SECRET": "abc123def456"},
        "--json",
    )
    assert out.returncode == 0, out.stderr
    payload = json.loads(out.stdout)
    cron = next(r for r in payload["recommended"] if r["name"] == "HAWK_CRON_SECRET")
    assert cron["set"] is True
    assert cron["resolved_name"] == "CRON_SECRET"


def test_anon_key_resolves_via_next_public_alias() -> None:
    out = _run(
        {
            "HAWK_ENV": "development",
            "NEXT_PUBLIC_SUPABASE_ANON_KEY": "eyJhbGciOiJ.aaa.bbb",
        },
        "--json",
    )
    assert out.returncode == 0, out.stderr
    payload = json.loads(out.stdout)
    anon = next(r for r in payload["recommended"] if r["name"] == "SUPABASE_ANON_KEY")
    assert anon["set"] is True
    assert anon["resolved_name"] == "NEXT_PUBLIC_SUPABASE_ANON_KEY"


# ── Exit codes ─────────────────────────────────────────────────────────


def test_dev_mode_missing_required_exits_zero() -> None:
    """In dev, missing REQUIRED is non-fatal so test suites still pass."""
    out = _run({"HAWK_ENV": "development"})
    assert out.returncode == 0, out.stdout + out.stderr


def test_strict_flag_fails_when_required_missing() -> None:
    out = _run({"HAWK_ENV": "development"}, "--strict")
    assert out.returncode == 1, out.stdout + out.stderr
    assert "HAWK_SECRET_KEY" in out.stdout


def test_production_fails_when_required_missing() -> None:
    out = _run({"HAWK_ENV": "production"})
    assert out.returncode == 1, out.stdout + out.stderr


def test_production_passes_when_required_set() -> None:
    out = _run({
        "HAWK_ENV": "production",
        "HAWK_SECRET_KEY": "a" * 64,
        "DATABASE_URL": "postgresql://user:pass@host:5432/hawk",
    })
    assert out.returncode == 0, out.stdout + out.stderr


def test_railway_environment_is_recognized_as_production_alias() -> None:
    out = _run({"RAILWAY_ENVIRONMENT": "production"})
    assert out.returncode == 1, out.stdout + out.stderr


# ── JSON output ────────────────────────────────────────────────────────


def test_json_output_well_formed() -> None:
    out = _run({"HAWK_ENV": "development"}, "--json")
    assert out.returncode == 0, out.stdout + out.stderr
    payload = json.loads(out.stdout)
    assert set(payload.keys()) == {"production", "required", "recommended", "optional", "summary"}
    assert payload["production"] is False
    assert payload["summary"]["missing_required"] == 2
    # Sanity-check structure on a row
    row = payload["required"][0]
    assert {"name", "tier", "feature", "set", "resolved_name", "aliases", "notes"} <= set(row.keys())
