"""Phase 2 — Portal: AI Advisor, threat briefings, journey data, competitor benchmark."""

from __future__ import annotations

import html as html_mod
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from routers.crm_auth import require_supabase_uid
from services.crm_portal_email import send_resend
from services.portal_ai import (
    build_advisor_system_prompt,
    discover_competitor_domains,
    generate_competitor_benchmark,
    generate_weekly_threat_briefing_md,
    load_portal_client_bundle,
    monday_week_start,
    advisor_chat,
)
from services.portal_milestones import ensure_portal_milestones
from services.scanner import run_scan

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/portal", tags=["portal-phase2"])

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def _sb() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def _public_benchmark_row(row: dict[str, Any]) -> dict[str, Any]:
    """Strip internal competitor domains from API responses."""
    out = dict(row)
    out.pop("competitor_domains", None)
    return out


def _benchmark_needs_refresh(existing: dict[str, Any] | None) -> bool:
    if not existing or not existing.get("narrative_md"):
        return True
    scores = existing.get("scores") if isinstance(existing.get("scores"), dict) else {}
    has_peer = scores.get("peer_scan_average") is not None or scores.get("peer_sample_size")
    if not has_peer:
        return True
    raw = existing.get("refreshed_at")
    if not raw:
        return True
    try:
        ref = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)
    except Exception:
        return True
    return datetime.now(timezone.utc) - ref >= timedelta(days=7)


def _run_peer_scan_scores(domains: list[str]) -> tuple[list[float], list[str]]:
    scores: list[float] = []
    kept: list[str] = []
    for d in domains:
        try:
            r = run_scan(d, scan_id=None, scan_depth="fast", trust_level="public")
            s = r.get("score")
            if isinstance(s, (int, float)):
                scores.append(float(s))
                kept.append(d)
        except Exception as e:
            logger.warning("peer scan failed for %s: %s", d, e)
    return scores, kept


def _persist_benchmark(cid: str, data: dict[str, Any], existing: dict[str, Any] | None) -> dict[str, Any] | None:
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "competitor_domains": data.get("competitor_domains") or [],
        "scores": data.get("scores") or {},
        "narrative_md": data.get("narrative_md"),
        "refreshed_at": now,
    }
    if existing:
        pr = httpx.patch(
            f"{SUPABASE_URL}/rest/v1/client_competitor_benchmarks",
            headers=_sb(),
            params={"client_id": f"eq.{cid}"},
            json=payload,
            timeout=60.0,
        )
        if pr.status_code >= 400:
            logger.warning("benchmark patch failed: %s", pr.text[:200])
            return None
    else:
        ins = httpx.post(
            f"{SUPABASE_URL}/rest/v1/client_competitor_benchmarks",
            headers=_sb(),
            json={"client_id": cid, **payload},
            timeout=60.0,
        )
        if ins.status_code >= 400:
            logger.warning("benchmark insert failed: %s", ins.text[:200])
            return None
    gr = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_competitor_benchmarks",
        headers=_sb(),
        params={"client_id": f"eq.{cid}", "limit": "1"},
        timeout=20.0,
    )
    gr.raise_for_status()
    return (gr.json() or [None])[0]


class PortalChatBody(BaseModel):
    message: str = Field(..., min_length=1, max_length=12000)
    conversation_history: list[dict[str, Any]] = Field(default_factory=list)


@router.post("/chat")
def portal_chat(body: PortalChatBody, uid: str = Depends(require_supabase_uid)):
    bundle = load_portal_client_bundle(uid)
    if not bundle:
        raise HTTPException(status_code=404, detail="Portal profile not found")
    system = build_advisor_system_prompt(bundle)
    reply = advisor_chat(
        system=system,
        user_message=body.message.strip(),
        conversation_history=body.conversation_history,
    )
    return {"reply": reply}


@router.get("/attack-paths")
def portal_attack_paths(uid: str = Depends(require_supabase_uid)):
    """Latest scan: LLM-derived attack path chains (same data as CRM scan view)."""
    bundle = load_portal_client_bundle(uid)
    if not bundle:
        raise HTTPException(status_code=404, detail="Portal profile not found")
    scan = bundle.get("scan") or {}
    raw = scan.get("attack_paths")
    paths = raw if isinstance(raw, list) else []
    prospect = bundle.get("prospect") or {}
    cpp = bundle.get("cpp") or {}
    return {
        "paths": paths,
        "domain": str(prospect.get("domain") or cpp.get("domain") or ""),
        "company_name": str(cpp.get("company_name") or prospect.get("company_name") or ""),
        "scan_id": scan.get("id"),
        "scan_at": scan.get("created_at"),
    }


@router.get("/threat-briefing/latest")
def portal_latest_briefing(uid: str = Depends(require_supabase_uid)):
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")
    cpp_r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_portal_profiles",
        headers=_sb(),
        params={"user_id": f"eq.{uid}", "select": "client_id", "limit": "1"},
        timeout=20.0,
    )
    cpp_r.raise_for_status()
    cpp = (cpp_r.json() or [None])[0]
    if not cpp:
        raise HTTPException(status_code=404, detail="No portal profile")
    cid = cpp["client_id"]
    br = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_threat_briefings",
        headers=_sb(),
        params={
            "client_id": f"eq.{cid}",
            "select": "id,week_start,title,body_md,industry_snapshot,email_sent_at,created_at",
            "order": "week_start.desc",
            "limit": "1",
        },
        timeout=20.0,
    )
    br.raise_for_status()
    rows = br.json()
    if not rows:
        return {"briefing": None}
    return {"briefing": rows[0]}


@router.get("/benchmark")
def portal_benchmark(uid: str = Depends(require_supabase_uid)):
    bundle = load_portal_client_bundle(uid)
    if not bundle:
        raise HTTPException(status_code=404, detail="Portal profile not found")
    cid = bundle["client"]["id"]
    scan = bundle.get("scan") or {}
    score = scan.get("hawk_score")
    try:
        sc = int(score) if score is not None else None
    except (TypeError, ValueError):
        sc = None

    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    ex = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_competitor_benchmarks",
        headers=_sb(),
        params={"client_id": f"eq.{cid}", "limit": "1"},
        timeout=20.0,
    )
    ex.raise_for_status()
    existing = (ex.json() or [None])[0]
    if existing and not _benchmark_needs_refresh(existing):
        return {"benchmark": _public_benchmark_row(existing), "persisted": True}

    peer_domains = discover_competitor_domains(bundle)
    peer_scores: list[float] = []
    peer_kept: list[str] = []
    if peer_domains:
        # Cap at 2 sequential fast scans to keep the request within API timeouts.
        peer_scores, peer_kept = _run_peer_scan_scores(peer_domains[:2])

    data = generate_competitor_benchmark(
        bundle,
        sc,
        peer_scores=peer_scores if peer_scores else None,
        peer_domains=peer_kept or peer_domains,
    )
    row = _persist_benchmark(cid, data, existing)
    if row:
        return {"benchmark": _public_benchmark_row(row), "persisted": True}
    return {"benchmark": _public_benchmark_row({"client_id": cid, **data}), "persisted": False}


@router.get("/journey")
def portal_journey(uid: str = Depends(require_supabase_uid)):
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")
    cpp_r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_portal_profiles",
        headers=_sb(),
        params={"user_id": f"eq.{uid}", "select": "client_id", "limit": "1"},
        timeout=20.0,
    )
    cpp_r.raise_for_status()
    cpp = (cpp_r.json() or [None])[0]
    if not cpp:
        raise HTTPException(status_code=404, detail="No portal profile")
    cid = cpp["client_id"]

    cl = httpx.get(
        f"{SUPABASE_URL}/rest/v1/clients",
        headers=_sb(),
        params={"id": f"eq.{cid}", "select": "certified_at,hawk_readiness_score,prospect_id", "limit": "1"},
        timeout=20.0,
    )
    cl.raise_for_status()
    client = (cl.json() or [None])[0] or {}
    pid = client.get("prospect_id")
    ensure_portal_milestones(str(cid), str(pid) if pid else None)

    ms = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_security_milestones",
        headers=_sb(),
        params={"client_id": f"eq.{cid}", "select": "milestone_key,achieved_at,metadata", "order": "achieved_at.asc"},
        timeout=20.0,
    )
    ms.raise_for_status()

    scans: list[dict[str, Any]] = []
    if pid:
        sc = httpx.get(
            f"{SUPABASE_URL}/rest/v1/crm_prospect_scans",
            headers=_sb(),
            params={
                "prospect_id": f"eq.{pid}",
                "select": "id,created_at,hawk_score,grade",
                "order": "created_at.asc",
                "limit": "200",
            },
            timeout=30.0,
        )
        sc.raise_for_status()
        scans = sc.json() or []

    st_rows: list[dict[str, Any]] = []
    st = httpx.get(
        f"{SUPABASE_URL}/rest/v1/portal_finding_status",
        headers=_sb(),
        params={
            "client_id": f"eq.{cid}",
            "select": "finding_id,status,verified_at,updated_at",
            "order": "updated_at.desc",
            "limit": "100",
        },
        timeout=20.0,
    )
    if st.status_code == 200:
        st_rows = st.json() or []

    events: list[dict[str, Any]] = []
    for s in scans:
        events.append(
            {
                "type": "scan",
                "at": s.get("created_at"),
                "title": "Security scan",
                "detail": f"Score {s.get('hawk_score')}/100 · Grade {s.get('grade') or '—'}",
            }
        )
    for row in st_rows:
        va = row.get("verified_at")
        if va:
            fid = str(row.get("finding_id") or "")
            events.append(
                {
                    "type": "fix_verified",
                    "at": va,
                    "title": "Fix verified",
                    "detail": f"Finding {fid[:12]}…" if len(fid) > 12 else f"Finding {fid}",
                }
            )
    for m in ms.json() or []:
        if isinstance(m, dict) and m.get("milestone_key"):
            events.append(
                {
                    "type": "milestone",
                    "at": m.get("achieved_at"),
                    "title": f"Milestone · {m.get('milestone_key')}",
                    "detail": "",
                }
            )

    def _sort_key(ev: dict[str, Any]) -> str:
        return str(ev.get("at") or "")

    events.sort(key=_sort_key)

    return {
        "milestones": ms.json() or [],
        "scans": scans,
        "certified_at": client.get("certified_at"),
        "readiness": client.get("hawk_readiness_score"),
        "events": events,
    }


def run_weekly_threat_briefings_for_all_clients() -> dict[str, Any]:
    """Called from cron — generates this week's briefing per portal client and emails."""
    if not SUPABASE_URL or not SERVICE_KEY:
        return {"ok": False, "error": "supabase not configured"}
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_portal_profiles",
        headers=_sb(),
        params={"select": "user_id,client_id,email", "limit": "500"},
        timeout=60.0,
    )
    r.raise_for_status()
    profiles = r.json() or []
    week = monday_week_start()
    created = 0
    emailed = 0
    for p in profiles:
        uid = p.get("user_id")
        cid = p.get("client_id")
        to_email = (p.get("email") or "").strip()
        if not uid or not cid:
            continue
        ex = httpx.get(
            f"{SUPABASE_URL}/rest/v1/client_threat_briefings",
            headers=_sb(),
            params={
                "client_id": f"eq.{cid}",
                "week_start": f"eq.{week.isoformat()}",
                "select": "id",
                "limit": "1",
            },
            timeout=20.0,
        )
        ex.raise_for_status()
        if ex.json():
            continue
        bundle = load_portal_client_bundle(str(uid))
        if not bundle:
            continue
        title, body_md = generate_weekly_threat_briefing_md(bundle)
        ins = httpx.post(
            f"{SUPABASE_URL}/rest/v1/client_threat_briefings",
            headers={**_sb(), "Prefer": "return=representation"},
            json={
                "client_id": cid,
                "week_start": week.isoformat(),
                "title": title[:200],
                "body_md": body_md,
                "industry_snapshot": (bundle.get("prospect") or {}).get("industry"),
            },
            timeout=30.0,
        )
        if ins.status_code >= 400:
            logger.error("briefing insert failed: %s", ins.text[:300])
            continue
        created += 1
        row = (ins.json() or [None])[0]
        bid = row.get("id") if isinstance(row, dict) else None
        base = os.environ.get("CRM_PUBLIC_BASE_URL", "https://securedbyhawk.com").rstrip("/")
        portal_url = f"{base}/portal"
        if to_email and "@" in to_email:
            try:
                send_resend(
                    to_email=to_email,
                    subject=f"HAWK Weekly Threat Briefing — {title[:80]}",
                    html=(
                        f"<p>Your weekly sector briefing is ready.</p>"
                        f"<pre style='white-space:pre-wrap;font-family:system-ui,sans-serif'>{html_mod.escape(body_md)}</pre>"
                        f"<p><a href='{html_mod.escape(portal_url)}'>Open portal</a></p>"
                    ),
                    tags=[{"name": "category", "value": "threat_briefing"}],
                )
                sent_at = datetime.now(timezone.utc).isoformat()
                if bid:
                    httpx.patch(
                        f"{SUPABASE_URL}/rest/v1/client_threat_briefings",
                        headers=_sb(),
                        params={"id": f"eq.{bid}"},
                        json={"email_sent_at": sent_at},
                        timeout=20.0,
                    )
                emailed += 1
            except Exception:
                logger.exception("threat briefing email failed for client %s", cid)
    return {"ok": True, "week_start": week.isoformat(), "briefings_created": created, "emails_sent": emailed}
