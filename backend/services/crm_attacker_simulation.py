"""Phase 4 — Weekly attacker-style narrative for portal clients (OpenAI)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

from config import OPENAI_API_KEY
from services.openai_chat import chat_text_sync
from services.portal_ai import (
    PORTAL_LLM_MODEL,
    _findings_for_prompt,
    load_portal_client_bundle_by_client_id,
    monday_week_start,
)

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def _sb() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def _generate_body_md(bundle: dict[str, Any]) -> tuple[str, str]:
    cpp = bundle.get("cpp") or {}
    prospect = bundle.get("prospect") or {}
    scan = bundle.get("scan")
    company = str(cpp.get("company_name") or prospect.get("company_name") or cpp.get("domain") or "Organization")
    domain = str(cpp.get("domain") or prospect.get("domain") or "")
    findings_txt = _findings_for_prompt(scan)
    paths = ""
    if scan and isinstance(scan.get("attack_paths"), list):
        paths = str(scan.get("attack_paths"))[:6000]

    prompt = (
        f"You are a careful red-team style analyst writing for a Canadian SMB security portal.\n"
        f"Company: {company} ({domain}).\n"
        f"Summarized findings from their latest HAWK scan:\n{findings_txt}\n\n"
        f"Optional attack-path hints from tooling:\n{paths or '(none)'}\n\n"
        "Write a concise weekly 'attacker simulation' in Markdown (no scare tactics, no illegal instructions).\n"
        "Structure: ## Overview, ## Likely paths, ## What to fix first, ## If you only do three things.\n"
        "Use short bullets where helpful. Stay under 900 words."
    )

    text = chat_text_sync(
        api_key=OPENAI_API_KEY,
        system=None,
        user_messages=[{"role": "user", "content": prompt}],
        max_tokens=2200,
        model=PORTAL_LLM_MODEL,
    )
    title = f"Week of {monday_week_start().isoformat()} — attacker view"
    return title.strip(), (text or "").strip()


def run_weekly_attacker_simulations() -> dict[str, Any]:
    if not SUPABASE_URL or not SERVICE_KEY:
        return {"ok": False, "error": "supabase not configured", "written": 0}
    if not OPENAI_API_KEY:
        return {"ok": False, "error": "OPENAI_API_KEY not configured", "written": 0}

    ws = monday_week_start()
    week_s = ws.isoformat()

    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_portal_profiles",
        headers=_sb(),
        params={"select": "client_id", "limit": "500"},
        timeout=60.0,
    )
    r.raise_for_status()
    cids = {str(row["client_id"]) for row in (r.json() or []) if row.get("client_id")}

    written = 0
    errors: list[str] = []

    for cid in sorted(cids):
        bundle = load_portal_client_bundle_by_client_id(cid)
        if not bundle:
            continue
        try:
            title, body_md = _generate_body_md(bundle)
        except Exception as e:
            logger.exception("attacker sim generate failed client=%s", cid)
            errors.append(f"{cid}: {e!s}")
            continue

        payload = {
            "client_id": cid,
            "week_start": week_s,
            "title": title[:500],
            "body_md": body_md[:120000],
        }

        ex = httpx.get(
            f"{SUPABASE_URL}/rest/v1/client_attacker_simulation_reports",
            headers=_sb(),
            params={
                "client_id": f"eq.{cid}",
                "week_start": f"eq.{week_s}",
                "select": "id",
                "limit": "1",
            },
            timeout=20.0,
        )
        if ex.status_code == 200 and ex.json():
            rid = ex.json()[0]["id"]
            patch = httpx.patch(
                f"{SUPABASE_URL}/rest/v1/client_attacker_simulation_reports",
                headers=_sb(),
                params={"id": f"eq.{rid}"},
                json={"title": payload["title"], "body_md": payload["body_md"]},
                timeout=20.0,
            )
            if patch.status_code >= 400:
                errors.append(f"{cid}: patch {patch.status_code}")
                continue
        else:
            ins = httpx.post(
                f"{SUPABASE_URL}/rest/v1/client_attacker_simulation_reports",
                headers=_sb(),
                json=payload,
                timeout=30.0,
            )
            if ins.status_code >= 400:
                errors.append(f"{cid}: insert {ins.status_code} {ins.text[:120]}")
                continue
        written += 1

    return {"ok": True, "week_start": week_s, "written": written, "errors": errors[:25]}
