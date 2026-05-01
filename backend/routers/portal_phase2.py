"""Phase 2 — Portal: AI Advisor, threat briefings, journey data, competitor benchmark."""

from __future__ import annotations

import html as html_mod
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
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
from services.portal_milestones import (
    ensure_portal_milestones,
    hawk_certified_progress,
)
from services.portal_patient_trust_badge import (
    embed_snippets as patient_trust_embed_snippets,
    patient_trust_eligibility,
    render_patient_trust_badge_svg,
)
from services.scanner import run_scan
from services.threat_briefing_pdf import (
    briefing_filename,
    render_weekly_briefing_pdf,
)

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


@router.get("/threat-briefing/latest.pdf")
def portal_latest_briefing_pdf(uid: str = Depends(require_supabase_uid)) -> Response:
    """Download the latest weekly briefing as a branded PDF.

    Renders on the fly from the stored markdown so we don't have to keep
    PDF blobs in Supabase. Same renderer the cron uses to build the
    email attachment, so the file looks identical either way.
    """
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")
    bundle = load_portal_client_bundle(uid)
    if not bundle:
        raise HTTPException(status_code=404, detail="No portal profile")
    cid = bundle["client"]["id"]
    br = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_threat_briefings",
        headers=_sb(),
        params={
            "client_id": f"eq.{cid}",
            "select": "week_start,title,body_md",
            "order": "week_start.desc",
            "limit": "1",
        },
        timeout=20.0,
    )
    br.raise_for_status()
    rows = br.json() or []
    if not rows:
        raise HTTPException(status_code=404, detail="No briefing yet")
    row = rows[0]
    company = str(
        bundle["cpp"].get("company_name")
        or (bundle.get("prospect") or {}).get("domain")
        or ""
    )
    pdf_bytes = render_weekly_briefing_pdf(
        company=company,
        title=str(row.get("title") or ""),
        body_md=str(row.get("body_md") or ""),
        industry=(bundle.get("prospect") or {}).get("industry"),
        week_start=str(row.get("week_start") or ""),
    )
    if not pdf_bytes:
        raise HTTPException(status_code=503, detail="PDF renderer unavailable")
    fname = briefing_filename(
        company=company, week_start=str(row.get("week_start") or "")
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


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

    milestone_rows = ms.json() or []
    return {
        "milestones": milestone_rows,
        "scans": scans,
        "certified_at": client.get("certified_at"),
        "readiness": client.get("hawk_readiness_score"),
        "events": events,
        "hawk_certified": hawk_certified_progress(
            milestone_rows,
            certified_at=client.get("certified_at"),
        ),
    }


def _render_certified_badge_svg(company_name: str, certified_on: str) -> str:
    """SVG badge — embeds company name and certification date.

    Pure-function so it stays testable without httpx/Supabase. Both inputs are
    XML-escaped before interpolation.
    """
    safe_company = html_mod.escape((company_name or "Your business")[:64])
    safe_date = html_mod.escape((certified_on or "")[:32])
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="380" viewBox="0 0 600 380" '
        'role="img" aria-label="HAWK Certified badge">'
        '<defs>'
        '<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
        '<stop offset="0" stop-color="#0b1117"/><stop offset="1" stop-color="#11161d"/>'
        '</linearGradient>'
        '</defs>'
        '<rect width="600" height="380" rx="24" fill="url(#bg)"/>'
        '<rect x="10" y="10" width="580" height="360" rx="20" fill="none" '
        'stroke="#f5b62b" stroke-width="2"/>'
        '<text x="300" y="78" text-anchor="middle" '
        'font-family="ui-sans-serif,-apple-system,Segoe UI,Roboto,Helvetica,sans-serif" '
        'font-size="14" letter-spacing="6" fill="#f5b62b" font-weight="700">'
        'HAWK · CYBERSECURITY GUARANTEE'
        '</text>'
        '<text x="300" y="160" text-anchor="middle" '
        'font-family="ui-sans-serif,-apple-system,Segoe UI,Roboto,Helvetica,sans-serif" '
        'font-size="48" fill="#ffffff" font-weight="800">'
        'CERTIFIED'
        '</text>'
        '<text x="300" y="210" text-anchor="middle" '
        'font-family="ui-sans-serif,-apple-system,Segoe UI,Roboto,Helvetica,sans-serif" '
        'font-size="20" fill="#cbd5e1" font-weight="500">'
        f'{safe_company}'
        '</text>'
        '<text x="300" y="266" text-anchor="middle" '
        'font-family="ui-sans-serif,-apple-system,Segoe UI,Roboto,Helvetica,sans-serif" '
        'font-size="13" letter-spacing="3" fill="#94a3b8">'
        'CERTIFIED ON'
        '</text>'
        '<text x="300" y="294" text-anchor="middle" '
        'font-family="ui-sans-serif,-apple-system,Segoe UI,Roboto,Helvetica,sans-serif" '
        'font-size="20" fill="#ffffff" font-weight="600">'
        f'{safe_date}'
        '</text>'
        '<text x="300" y="346" text-anchor="middle" '
        'font-family="ui-sans-serif,-apple-system,Segoe UI,Roboto,Helvetica,sans-serif" '
        'font-size="11" fill="#64748b">'
        'securedbyhawk.com'
        '</text>'
        '</svg>'
    )


@router.get("/journey/badge.svg")
def portal_journey_badge(uid: str = Depends(require_supabase_uid)):
    """Return the HAWK Certified badge as SVG. 404 until ``clients.certified_at`` is set."""
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")
    cpp_r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_portal_profiles",
        headers=_sb(),
        params={"user_id": f"eq.{uid}", "select": "client_id,company_name", "limit": "1"},
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
        params={"id": f"eq.{cid}", "select": "company_name,domain,certified_at", "limit": "1"},
        timeout=20.0,
    )
    cl.raise_for_status()
    client = (cl.json() or [None])[0] or {}
    certified_at = client.get("certified_at")
    if not certified_at:
        raise HTTPException(status_code=404, detail="Not yet HAWK Certified")

    company = (
        cpp.get("company_name")
        or client.get("company_name")
        or client.get("domain")
        or "Your business"
    )
    on = str(certified_at)[:10]
    svg = _render_certified_badge_svg(str(company), on)
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Content-Disposition": 'inline; filename="hawk-certified-badge.svg"'},
    )


@router.get("/journey/badge.png")
def portal_journey_badge_png(uid: str = Depends(require_supabase_uid)):
    """Return the HAWK Certified badge as PNG (2x DPI). 404 until certified."""
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")
    cpp_r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_portal_profiles",
        headers=_sb(),
        params={"user_id": f"eq.{uid}", "select": "client_id,company_name", "limit": "1"},
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
        params={"id": f"eq.{cid}", "select": "company_name,domain,certified_at", "limit": "1"},
        timeout=20.0,
    )
    cl.raise_for_status()
    client = (cl.json() or [None])[0] or {}
    certified_at = client.get("certified_at")
    if not certified_at:
        raise HTTPException(status_code=404, detail="Not yet HAWK Certified")

    company = (
        cpp.get("company_name")
        or client.get("company_name")
        or client.get("domain")
        or "Your business"
    )
    on = str(certified_at)[:10]
    svg = _render_certified_badge_svg(str(company), on)

    try:
        import cairosvg
        png_bytes = cairosvg.svg2png(bytestring=svg.encode("utf-8"), dpi=192)
    except Exception as exc:
        logger.warning("cairosvg PNG render failed: %s", exc)
        raise HTTPException(status_code=500, detail="PNG rendering unavailable")

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Content-Disposition": 'inline; filename="hawk-certified-badge.png"'},
    )


# ---------------------------------------------------------------------------
# Patient Trust Badge — priority list item #38
# ---------------------------------------------------------------------------


def _patient_trust_company(bundle: dict[str, Any]) -> str:
    """Pick the friendliest display name for the badge's practice line."""
    cpp = bundle.get("cpp") or {}
    client = bundle.get("client") or {}
    prospect = bundle.get("prospect") or {}
    return str(
        cpp.get("company_name")
        or client.get("company_name")
        or prospect.get("company_name")
        or prospect.get("domain")
        or cpp.get("domain")
        or "Your practice"
    )


def _patient_trust_earned_on(bundle: dict[str, Any]) -> str:
    client = bundle.get("client") or {}
    raw = client.get("certified_at") or ""
    return str(raw)[:10]


@router.get("/patient-trust-badge")
def portal_patient_trust_badge_status(
    uid: str = Depends(require_supabase_uid),
) -> dict[str, Any]:
    """Return eligibility + embed snippets for the Patient Trust Badge.

    Always returns 200 — the UI inspects ``eligible`` and renders either
    the download/embed UI or a "what you need to do to earn this" tile.
    """
    bundle = load_portal_client_bundle(uid)
    if not bundle:
        raise HTTPException(status_code=404, detail="No portal profile")

    eligibility = patient_trust_eligibility(bundle)

    base = os.environ.get("CRM_PUBLIC_BASE_URL", "https://securedbyhawk.com").rstrip("/")
    badge_url = f"{base}/api/portal/patient-trust-badge.svg"
    verify_url = f"{base}/portal/patient-trust-badge"
    snippets = patient_trust_embed_snippets(
        badge_url=badge_url,
        verify_url=verify_url,
        company_name=_patient_trust_company(bundle),
    )
    return {
        "eligibility": eligibility,
        "company_name": _patient_trust_company(bundle),
        "earned_on": _patient_trust_earned_on(bundle),
        "badge_url": badge_url,
        "verify_url": verify_url,
        "embed": snippets,
    }


@router.get("/patient-trust-badge.svg")
def portal_patient_trust_badge_svg(
    uid: str = Depends(require_supabase_uid),
) -> Response:
    """Return the Patient Trust Badge SVG. 403 if the client isn't eligible."""
    bundle = load_portal_client_bundle(uid)
    if not bundle:
        raise HTTPException(status_code=404, detail="No portal profile")
    elig = patient_trust_eligibility(bundle)
    if not elig.get("eligible"):
        raise HTTPException(
            status_code=403,
            detail=f"Not eligible: {elig.get('reason') or 'unknown'}",
        )
    svg = render_patient_trust_badge_svg(
        company_name=_patient_trust_company(bundle),
        earned_on=_patient_trust_earned_on(bundle),
    )
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={
            "Content-Disposition": 'inline; filename="hawk-patient-trust-badge.svg"',
            # Public cache for 1h — badge content only changes when
            # certification status flips, so a short TTL is safe and
            # offloads CDN traffic.
            "Cache-Control": "public, max-age=3600",
        },
    )


@router.get("/patient-trust-badge.png")
def portal_patient_trust_badge_png(
    uid: str = Depends(require_supabase_uid),
) -> Response:
    """Return the Patient Trust Badge as PNG (2x DPI). 403 if not eligible."""
    bundle = load_portal_client_bundle(uid)
    if not bundle:
        raise HTTPException(status_code=404, detail="No portal profile")
    elig = patient_trust_eligibility(bundle)
    if not elig.get("eligible"):
        raise HTTPException(
            status_code=403,
            detail=f"Not eligible: {elig.get('reason') or 'unknown'}",
        )
    svg = render_patient_trust_badge_svg(
        company_name=_patient_trust_company(bundle),
        earned_on=_patient_trust_earned_on(bundle),
    )
    try:
        import cairosvg
        png_bytes = cairosvg.svg2png(bytestring=svg.encode("utf-8"), dpi=192)
    except Exception as exc:
        logger.warning("cairosvg patient trust PNG render failed: %s", exc)
        raise HTTPException(status_code=500, detail="PNG rendering unavailable")
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "Content-Disposition": 'inline; filename="hawk-patient-trust-badge.png"',
            "Cache-Control": "public, max-age=3600",
        },
    )


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
                # Render a branded PDF copy of the briefing for the
                # client's compliance binder. ``render_weekly_briefing_pdf``
                # returns ``b""`` if reportlab is unavailable so the email
                # still goes out with the inline body.
                pdf_bytes = render_weekly_briefing_pdf(
                    company=str(
                        bundle["cpp"].get("company_name")
                        or (bundle.get("prospect") or {}).get("domain")
                        or ""
                    ),
                    title=title,
                    body_md=body_md,
                    industry=(bundle.get("prospect") or {}).get("industry"),
                    week_start=week.isoformat(),
                )
                attachments: list[dict[str, Any]] | None = None
                if pdf_bytes:
                    import base64

                    attachments = [
                        {
                            "filename": briefing_filename(
                                company=str(
                                    bundle["cpp"].get("company_name")
                                    or (bundle.get("prospect") or {}).get("domain")
                                    or ""
                                ),
                                week_start=week.isoformat(),
                            ),
                            "content": base64.b64encode(pdf_bytes).decode("ascii"),
                        }
                    ]
                # Only claim "PDF attached" when we actually attached one;
                # ``render_weekly_briefing_pdf`` returns ``b""`` if reportlab
                # is unavailable and the email still goes out without the
                # attachment.
                pdf_note = " (PDF attached)" if attachments else ""
                send_resend(
                    to_email=to_email,
                    subject=f"HAWK Weekly Threat Briefing — {title[:80]}",
                    html=(
                        f"<p>Your weekly sector briefing is ready{pdf_note}.</p>"
                        f"<pre style='white-space:pre-wrap;font-family:system-ui,sans-serif'>{html_mod.escape(body_md)}</pre>"
                        f"<p><a href='{html_mod.escape(portal_url)}'>Open portal</a></p>"
                    ),
                    tags=[{"name": "category", "value": "threat_briefing"}],
                    attachments=attachments,
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
