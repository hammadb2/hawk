"""Client portal PDFs + CRM finding verification (2D + verify-fix)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from routers.crm_auth import require_supabase_uid
from services.crm_pipeda_report import build_pipeda_html, html_to_pdf_bytes
from services.crm_openphone import send_sms
from services.portal_milestones import ensure_portal_milestones
from services.scanner import run_scan

logger = logging.getLogger(__name__)

router = APIRouter(tags=["crm-portal"])

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def _sb() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def _soft_finding_key(f: dict[str, Any]) -> str:
    """Match across rescans (IDs change)."""
    return "|".join(
        [
            str(f.get("layer") or "").lower()[:80],
            str(f.get("title") or "").lower()[:200],
            str(f.get("affected_asset") or "").lower()[:200],
        ]
    )


def _findings_blob(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, dict):
        inner = raw.get("findings")
        if isinstance(inner, list):
            return [x for x in inner if isinstance(x, dict)]
    return []


def _portal_owns_prospect(uid: str, prospect_id: str) -> bool:
    """True if this auth user is the linked portal user for the client tied to the prospect."""
    cpp_r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_portal_profiles",
        headers=_sb(),
        params={"user_id": f"eq.{uid}", "select": "client_id", "limit": "1"},
        timeout=20.0,
    )
    if cpp_r.status_code != 200:
        return False
    cpp = (cpp_r.json() or [None])[0]
    if not cpp:
        return False
    cid = cpp.get("client_id")
    cl_r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/clients",
        headers=_sb(),
        params={"id": f"eq.{cid}", "select": "prospect_id", "limit": "1"},
        timeout=20.0,
    )
    if cl_r.status_code != 200:
        return False
    cl = (cl_r.json() or [None])[0]
    return str((cl or {}).get("prospect_id") or "") == str(prospect_id)


def _can_access_prospect(uid: str, prospect_id: str) -> bool:
    pr = httpx.get(
        f"{SUPABASE_URL}/rest/v1/prospects",
        headers=_sb(),
        params={"id": f"eq.{prospect_id}", "select": "assigned_rep_id", "limit": "1"},
        timeout=20.0,
    )
    if pr.status_code != 200 or not pr.json():
        return False
    assigned = (pr.json()[0] or {}).get("assigned_rep_id")

    prof = httpx.get(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=_sb(),
        params={"id": f"eq.{uid}", "select": "role,team_lead_id", "limit": "1"},
        timeout=20.0,
    )
    if prof.status_code != 200 or not prof.json():
        return False
    role = (prof.json()[0] or {}).get("role")
    if role in ("ceo", "hos"):
        return True
    if assigned and str(assigned) == uid:
        return True
    # team lead: members under them — lightweight check via crm_is_team_member not available; skip
    return False


@router.get("/api/portal/pipeda-report.pdf")
def pipeda_report_pdf(uid: str = Depends(require_supabase_uid)):
    """2D — One-click PIPEDA overview PDF for authenticated portal user."""
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    cpp_r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_portal_profiles",
        headers=_sb(),
        params={"user_id": f"eq.{uid}", "select": "client_id,company_name,domain", "limit": "1"},
        timeout=20.0,
    )
    cpp_r.raise_for_status()
    cpp = (cpp_r.json() or [None])[0]
    if not cpp:
        raise HTTPException(status_code=404, detail="No portal profile")

    client_id = cpp["client_id"]
    cl_r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/clients",
        headers=_sb(),
        params={"id": f"eq.{client_id}", "select": "prospect_id", "limit": "1"},
        timeout=20.0,
    )
    cl_r.raise_for_status()
    client = (cl_r.json() or [None])[0]
    prospect_id = (client or {}).get("prospect_id")
    scan = None
    if prospect_id:
        sc_r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/crm_prospect_scans",
            headers=_sb(),
            params={
                "prospect_id": f"eq.{prospect_id}",
                "select": "hawk_score,grade,findings",
                "order": "created_at.desc",
                "limit": "1",
            },
            timeout=20.0,
        )
        if sc_r.status_code == 200 and sc_r.json():
            scan = sc_r.json()[0]

    html = build_pipeda_html(
        company_name=str(cpp.get("company_name") or cpp.get("domain") or "Client"),
        domain=str(cpp.get("domain") or ""),
        scan=scan,
    )
    pdf = html_to_pdf_bytes(html)
    if not pdf:
        raise HTTPException(status_code=503, detail="PDF engine unavailable (install weasyprint on API host)")

    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="hawk-pipeda-overview.pdf"'},
    )


class VerifyFindingBody(BaseModel):
    prospect_id: str = Field(..., min_length=1)
    scan_id: str = Field(..., min_length=1)
    finding_id: str = Field(..., min_length=1)


PORTAL_STATUSES = frozenset({"open", "in_progress", "fixed", "accepted_risk"})


def finding_verify_core(
    uid: str,
    prospect_id: str,
    scan_id: str,
    finding_id: str,
    *,
    scan_depth: str = "fast",
) -> dict[str, Any]:
    """
    Re-scan (fast by default) and mark finding verified if exposure cleared vs prior severity.
    Returns JSON-serializable dict; raises HTTPException for HTTP errors.
    """
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")
    portal_user = _portal_owns_prospect(uid, prospect_id)
    if not _can_access_prospect(uid, prospect_id) and not portal_user:
        raise HTTPException(status_code=403, detail="Not allowed for this prospect")

    sc_r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/crm_prospect_scans",
        headers=_sb(),
        params={
            "id": f"eq.{scan_id}",
            "prospect_id": f"eq.{prospect_id}",
            "select": "id,findings,hawk_score,grade",
            "limit": "1",
        },
        timeout=20.0,
    )
    sc_r.raise_for_status()
    rows = sc_r.json()
    if not rows:
        raise HTTPException(status_code=404, detail="Scan not found")
    row = rows[0]
    findings_wrap = row.get("findings") if isinstance(row.get("findings"), dict) else {}
    flist = _findings_blob(row.get("findings"))
    target = next((f for f in flist if str(f.get("id")) == finding_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Finding not in scan")

    pr_r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/prospects",
        headers=_sb(),
        params={"id": f"eq.{prospect_id}", "select": "domain", "limit": "1"},
        timeout=20.0,
    )
    pr_r.raise_for_status()
    dom_row = (pr_r.json() or [None])[0]
    domain = (dom_row or {}).get("domain")
    if not domain:
        raise HTTPException(status_code=400, detail="Prospect has no domain")

    depth = (scan_depth or "fast").strip().lower()
    if depth not in ("full", "fast"):
        depth = "fast"

    try:
        fresh = run_scan(str(domain).strip().lower(), scan_id=None, scan_depth=depth)
    except Exception as e:
        logger.exception("verify rescan failed")
        raise HTTPException(status_code=502, detail=f"Rescan failed: {e}") from e

    new_list = fresh.get("findings") if isinstance(fresh.get("findings"), list) else []
    old_soft = _soft_finding_key(target)
    old_sev = str(target.get("severity") or "").lower()

    def _sev_rank(s: str) -> int:
        x = (s or "").lower()
        return {"critical": 0, "high": 1, "medium": 2, "warning": 2, "low": 3, "info": 4}.get(x, 5)

    matches = [nf for nf in new_list if isinstance(nf, dict) and _soft_finding_key(nf) == old_soft]
    if matches:
        if _sev_rank(str(matches[0].get("severity"))) <= _sev_rank(old_sev):
            msg = "Finding still present at similar severity."
            if portal_user:
                _portal_patch_finding_verify_state(uid, prospect_id, finding_id, verified=False, err=msg)
            return {"ok": True, "verified": False, "message": msg}

    for f in flist:
        if str(f.get("id")) == finding_id:
            f["verified_at"] = datetime.now(timezone.utc).isoformat()
            break

    new_wrap = {**findings_wrap, "findings": flist}
    patch_body: dict[str, Any] = {"findings": new_wrap}
    if isinstance(fresh.get("score"), (int, float)):
        patch_body["hawk_score"] = int(fresh["score"])
    if isinstance(fresh.get("grade"), str) and fresh["grade"].strip():
        patch_body["grade"] = fresh["grade"].strip()

    patch_r = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/crm_prospect_scans",
        headers={**_sb(), "Prefer": "return=minimal"},
        params={"id": f"eq.{scan_id}"},
        json=patch_body,
        timeout=20.0,
    )
    if patch_r.status_code >= 400:
        raise HTTPException(status_code=502, detail=patch_r.text[:400])

    if portal_user:
        _portal_patch_finding_verify_state(uid, prospect_id, finding_id, verified=True, err=None)
        _portal_celebrate_fix(
            uid=uid,
            prospect_id=prospect_id,
            finding_id=finding_id,
            old_severity=old_sev,
            new_score=fresh.get("score"),
        )
        pcid = _portal_client_id_for_user(uid)
        if pcid:
            ensure_portal_milestones(pcid, prospect_id)

    return {
        "ok": True,
        "verified": True,
        "new_score": fresh.get("score"),
        "message": "Marked verified; rescan did not show the same exposure at prior severity.",
    }


def _portal_auto_verify_bg(uid: str, prospect_id: str, scan_id: str, finding_id: str) -> None:
    try:
        finding_verify_core(uid, prospect_id, scan_id, finding_id, scan_depth="fast")
    except HTTPException as e:
        logger.warning("portal auto-verify: %s", e.detail)
    except Exception:
        logger.exception("portal auto-verify failed")


class PortalFindingStatusBody(BaseModel):
    prospect_id: str = Field(..., min_length=1)
    scan_id: str = Field(..., min_length=1)
    finding_id: str = Field(..., min_length=1)
    status: str = Field(..., min_length=1)


@router.post("/api/portal/finding-status")
def portal_set_finding_status(
    body: PortalFindingStatusBody,
    background_tasks: BackgroundTasks,
    uid: str = Depends(require_supabase_uid),
):
    """Portal user sets workflow status; marking fixed queues automatic verification (fast rescan)."""
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")
    st = body.status.strip().lower()
    if st not in PORTAL_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid status")
    if not _portal_owns_prospect(uid, body.prospect_id):
        raise HTTPException(status_code=403, detail="Portal access only")

    cid = _portal_client_id_for_user(uid)
    if not cid:
        raise HTTPException(status_code=404, detail="No portal profile")

    row_body = {
        "client_id": cid,
        "scan_id": body.scan_id,
        "finding_id": body.finding_id,
        "status": st,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    ex = httpx.get(
        f"{SUPABASE_URL}/rest/v1/portal_finding_status",
        headers=_sb(),
        params={
            "client_id": f"eq.{cid}",
            "finding_id": f"eq.{body.finding_id}",
            "select": "id",
            "limit": "1",
        },
        timeout=20.0,
    )
    ex.raise_for_status()
    if ex.json():
        pr = httpx.patch(
            f"{SUPABASE_URL}/rest/v1/portal_finding_status",
            headers=_sb(),
            params={"client_id": f"eq.{cid}", "finding_id": f"eq.{body.finding_id}"},
            json=row_body,
            timeout=20.0,
        )
        if pr.status_code >= 400:
            raise HTTPException(status_code=502, detail=pr.text[:400])
    else:
        ir = httpx.post(
            f"{SUPABASE_URL}/rest/v1/portal_finding_status",
            headers=_sb(),
            json=row_body,
            timeout=20.0,
        )
        if ir.status_code >= 400:
            raise HTTPException(status_code=502, detail=ir.text[:400])

    if st == "fixed":
        background_tasks.add_task(_portal_auto_verify_bg, uid, body.prospect_id, body.scan_id, body.finding_id)
    return {"ok": True, "auto_verify_queued": st == "fixed"}


@router.post("/api/crm/finding-verify")
def crm_verify_finding(body: VerifyFindingBody, uid: str = Depends(require_supabase_uid)):
    """Manual verify (same as auto-verify): fast perimeter rescan for this finding."""
    return finding_verify_core(
        uid,
        body.prospect_id,
        body.scan_id,
        body.finding_id,
        scan_depth="fast",
    )


def _portal_client_id_for_user(uid: str) -> str | None:
    cpp_r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_portal_profiles",
        headers=_sb(),
        params={"user_id": f"eq.{uid}", "select": "client_id", "limit": "1"},
        timeout=20.0,
    )
    if cpp_r.status_code != 200:
        return None
    cpp = (cpp_r.json() or [None])[0]
    return str(cpp["client_id"]) if cpp and cpp.get("client_id") else None


def _portal_patch_finding_verify_state(
    uid: str,
    prospect_id: str,
    finding_id: str,
    *,
    verified: bool,
    err: str | None,
) -> None:
    cid = _portal_client_id_for_user(uid)
    if not cid:
        return
    body: dict[str, Any] = {"verify_error": err, "updated_at": datetime.now(timezone.utc).isoformat()}
    if verified:
        body["verified_at"] = datetime.now(timezone.utc).isoformat()
        body["verify_error"] = None
    httpx.patch(
        f"{SUPABASE_URL}/rest/v1/portal_finding_status",
        headers=_sb(),
        params={"client_id": f"eq.{cid}", "finding_id": f"eq.{finding_id}"},
        json=body,
        timeout=20.0,
    )


def _portal_celebrate_fix(
    *,
    uid: str,
    prospect_id: str,
    finding_id: str,
    old_severity: str,
    new_score: Any,
) -> None:
    """WhatsApp streak message + milestone rows for portal users."""
    cid = _portal_client_id_for_user(uid)
    if not cid:
        return
    pr = httpx.get(
        f"{SUPABASE_URL}/rest/v1/prospects",
        headers=_sb(),
        params={"id": f"eq.{prospect_id}", "select": "phone,company_name,domain", "limit": "1"},
        timeout=20.0,
    )
    if pr.status_code != 200:
        return
    prow = (pr.json() or [None])[0] or {}
    phone = (prow.get("phone") or "").strip()
    company = str(prow.get("company_name") or prow.get("domain") or "your business")

    def _milestone_post(payload: dict[str, Any]) -> None:
        mr = httpx.post(
            f"{SUPABASE_URL}/rest/v1/client_security_milestones",
            headers=_sb(),
            json=payload,
            timeout=20.0,
        )
        if mr.status_code >= 400 and mr.status_code != 409:
            logger.warning("milestone insert: %s", mr.text[:200])

    if old_severity == "critical":
        _milestone_post(
            {
                "client_id": cid,
                "milestone_key": "first_critical_fix",
                "metadata": {"finding_id": finding_id},
            }
        )

    try:
        sc = int(new_score) if new_score is not None else None
    except (TypeError, ValueError):
        sc = None
    if sc is not None and sc >= 70:
        _milestone_post({"client_id": cid, "milestone_key": "score_above_70", "metadata": {"score": sc}})

    if phone and len(phone) >= 10:
        emoji = "🔥" if old_severity == "critical" else "✅"
        msg = (
            f"{emoji} HAWK — Fix verified\n"
            f"{company}: exposure cleared on rescan.\n"
            f"New score: {sc if sc is not None else '—'}/100. Keep the streak going in your portal."
        )
        try:
            send_sms(phone, msg)
        except Exception:
            logger.exception("portal fix SMS failed")
