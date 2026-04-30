#!/usr/bin/env python3
"""Pick the worst-scoring dental site and cache it for the homepage widget.

Priority list #45. Runs each domain in ``scripts/seeds_dental.txt`` through
the public scan endpoint, picks the one with the lowest HAWK score (ties
broken by highest finding count, then most CRITICAL + HIGH findings), and
overwrites ``backend/content/homepage_preset_scan.json``. The backend
endpoint ``GET /api/marketing/homepage-preset-scan`` reads that file and
returns it to ``home-scanner.tsx`` on page load so the homepage widget
lands on a pre-populated "ugly" scan instead of an empty input.

Usage
-----

    # Scan the default seeds against your deployed backend.
    HAWK_API_BASE=https://api.hawksecurity.com \
        python scripts/pick_worst_dental.py

    # Dry-run (don't overwrite the cache, just print the winner).
    python scripts/pick_worst_dental.py --dry-run

    # Use a custom seed file and/or a subset (first N lines).
    python scripts/pick_worst_dental.py \
        --seeds scripts/seeds_dental.txt --limit 25

The script exits 0 on success, 1 on any unrecoverable error (no seeds,
every scan failed, can't write cache, etc.). Partial failures are logged
and skipped — as long as one domain scans cleanly we pick a winner.

The output JSON shape matches :class:`PublicScanResult` in the frontend
(``frontend/lib/api.ts``) so no extra transformation is needed on the
client.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import pathlib
import sys
import time
from typing import Any

import httpx

log = logging.getLogger("pick_worst_dental")


_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_DEFAULT_SEEDS = _REPO_ROOT / "scripts" / "seeds_dental.txt"
_DEFAULT_CACHE = _REPO_ROOT / "backend" / "content" / "homepage_preset_scan.json"


def load_seeds(path: pathlib.Path) -> list[str]:
    """Read non-comment, non-blank lines from ``path`` as domain seeds."""
    if not path.exists():
        raise FileNotFoundError(f"seed file not found: {path}")
    seeds: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        seeds.append(line.lower())
    return seeds


def scan_one(base_url: str, domain: str, timeout: float) -> dict[str, Any] | None:
    """POST ``/api/scan/public`` and return the JSON body, or ``None`` on error."""
    url = f"{base_url.rstrip('/')}/api/scan/public"
    try:
        r = httpx.post(
            url,
            json={"domain": domain, "scan_depth": "fast"},
            timeout=timeout,
        )
        r.raise_for_status()
        data = r.json()
        if not isinstance(data, dict):
            log.warning("scan %s: unexpected payload shape %s", domain, type(data))
            return None
        return data
    except Exception as exc:
        log.warning("scan %s failed: %s", domain, exc)
        return None


def _severity_counts(scan: dict[str, Any]) -> tuple[int, int]:
    """Return (critical_count, high_count) from a scan payload."""
    crit = high = 0
    preview = scan.get("findings_preview") or []
    if isinstance(preview, list):
        for row in preview:
            if not isinstance(row, dict):
                continue
            sev = str(row.get("severity") or "").lower()
            if sev == "critical":
                crit += 1
            elif sev == "high":
                high += 1
    return crit, high


def rank_key(scan: dict[str, Any]) -> tuple[int, int, int, int]:
    """Lower-is-worse ranking key for scan payloads.

    Order: score asc, then issues desc, then critical desc, then high desc.
    Expressed as a tuple that sorts ascending so the winner has the
    smallest tuple.
    """
    score = scan.get("score")
    try:
        score_i = int(score) if score is not None else 100
    except (TypeError, ValueError):
        score_i = 100
    issues = scan.get("issues_count") or scan.get("findings_count") or 0
    try:
        issues_i = int(issues)
    except (TypeError, ValueError):
        issues_i = 0
    crit, high = _severity_counts(scan)
    # Lower score = worse (rank first). We negate the "more is worse" fields
    # so the composite tuple is strictly ascending = strictly worse.
    return (score_i, -issues_i, -crit, -high)


def pick_worst(scans: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Return the single worst scan by :func:`rank_key`, or None if empty."""
    viable = [s for s in scans if s and s.get("domain")]
    if not viable:
        return None
    viable.sort(key=rank_key)
    return viable[0]


def write_cache(path: pathlib.Path, scan: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(scan, indent=2, sort_keys=True), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--seeds", type=pathlib.Path, default=_DEFAULT_SEEDS)
    parser.add_argument("--cache", type=pathlib.Path, default=_DEFAULT_CACHE)
    parser.add_argument(
        "--api-base",
        default=os.environ.get("HAWK_API_BASE", "http://localhost:8000"),
        help="Backend base URL (default: $HAWK_API_BASE or http://localhost:8000).",
    )
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--limit", type=int, default=None,
                        help="Only scan the first N seeds (useful for smoke tests).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print the winner but do not write the cache.")
    parser.add_argument("--pause", type=float, default=1.0,
                        help="Seconds between scan requests to avoid rate-limits.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    seeds = load_seeds(args.seeds)
    if args.limit is not None:
        seeds = seeds[: args.limit]
    if not seeds:
        log.error("no seeds to scan — nothing to do")
        return 1

    log.info("scanning %d seed domains against %s", len(seeds), args.api_base)
    scans: list[dict[str, Any]] = []
    for i, dom in enumerate(seeds, 1):
        log.info("[%d/%d] %s", i, len(seeds), dom)
        res = scan_one(args.api_base, dom, args.timeout)
        if res is not None:
            scans.append(res)
        if args.pause > 0 and i < len(seeds):
            time.sleep(args.pause)

    winner = pick_worst(scans)
    if winner is None:
        log.error("no usable scan results — nothing to write")
        return 1

    log.info(
        "winner: %s  score=%s  grade=%s  issues=%s",
        winner.get("domain"),
        winner.get("score"),
        winner.get("grade"),
        winner.get("issues_count"),
    )

    if args.dry_run:
        print(json.dumps(winner, indent=2, sort_keys=True))
        return 0

    write_cache(args.cache, winner)
    log.info("wrote %s", args.cache)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
