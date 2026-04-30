"""Unit tests for scripts/pick_worst_dental.py (priority list #45).

Covers the pure ranking logic — loading seeds, severity counting, and
picking the worst scan — without hitting the public scan endpoint.
Networked integration is exercised manually against staging/prod by the
operator running the script; we only pin the ranking contract in CI.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "pick_worst_dental.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("pick_worst_dental", _SCRIPT)
    assert spec and spec.loader, f"could not load {_SCRIPT}"
    mod = importlib.util.module_from_spec(spec)
    sys.modules["pick_worst_dental"] = mod
    spec.loader.exec_module(mod)
    return mod


def test_load_seeds_skips_blank_and_comments(tmp_path: pathlib.Path) -> None:
    mod = _load_module()
    f = tmp_path / "s.txt"
    f.write_text(
        "# header comment\n"
        "aspendental.com\n"
        "\n"
        "  westerndental.com  \n"
        "# inline comment\n"
        "heartland.com\n",
        encoding="utf-8",
    )
    assert mod.load_seeds(f) == [
        "aspendental.com",
        "westerndental.com",
        "heartland.com",
    ]


def test_severity_counts_from_findings_preview() -> None:
    mod = _load_module()
    scan = {
        "findings_preview": [
            {"severity": "critical", "text": "a"},
            {"severity": "high", "text": "b"},
            {"severity": "high", "text": "c"},
            {"severity": "medium", "text": "d"},
            {"severity": "info", "text": "e"},
        ]
    }
    crit, high = mod._severity_counts(scan)
    assert crit == 1
    assert high == 2


def test_rank_key_prefers_lower_score() -> None:
    mod = _load_module()
    low = {"domain": "bad.com", "score": 32, "issues_count": 5, "findings_preview": []}
    high = {"domain": "ok.com", "score": 78, "issues_count": 5, "findings_preview": []}
    assert mod.rank_key(low) < mod.rank_key(high)


def test_rank_key_tiebreaks_by_issues_then_critical_then_high() -> None:
    mod = _load_module()
    a = {"domain": "a.com", "score": 55, "issues_count": 3, "findings_preview": []}
    b = {"domain": "b.com", "score": 55, "issues_count": 7, "findings_preview": []}
    # same score, b has more issues → b is worse → sorts first (smaller tuple)
    assert mod.rank_key(b) < mod.rank_key(a)

    c = {
        "domain": "c.com",
        "score": 55,
        "issues_count": 7,
        "findings_preview": [{"severity": "critical"}, {"severity": "critical"}],
    }
    # same score+issues, c has 2 criticals → c is worse than b
    assert mod.rank_key(c) < mod.rank_key(b)

    d = {
        "domain": "d.com",
        "score": 55,
        "issues_count": 7,
        "findings_preview": [
            {"severity": "critical"}, {"severity": "critical"},
            {"severity": "high"}, {"severity": "high"},
        ],
    }
    # same score+issues+criticals, d has more highs → d is worst
    assert mod.rank_key(d) < mod.rank_key(c)


def test_pick_worst_returns_lowest_score_entry() -> None:
    mod = _load_module()
    scans = [
        {"domain": "mid.com", "score": 70, "issues_count": 3, "findings_preview": []},
        {"domain": "good.com", "score": 92, "issues_count": 0, "findings_preview": []},
        {"domain": "worst.com", "score": 41, "issues_count": 6,
         "findings_preview": [{"severity": "critical"}]},
    ]
    winner = mod.pick_worst(scans)
    assert winner is not None
    assert winner["domain"] == "worst.com"


def test_pick_worst_empty_list_returns_none() -> None:
    mod = _load_module()
    assert mod.pick_worst([]) is None
    # scans missing `domain` are also ignored.
    assert mod.pick_worst([{"score": 10}]) is None


def test_write_cache_round_trips(tmp_path: pathlib.Path) -> None:
    mod = _load_module()
    target = tmp_path / "nested" / "homepage_preset_scan.json"
    payload = {"domain": "worst.com", "score": 41, "grade": "F"}
    mod.write_cache(target, payload)
    assert target.exists()
    import json as _json
    assert _json.loads(target.read_text(encoding="utf-8")) == payload
