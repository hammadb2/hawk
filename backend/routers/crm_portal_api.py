"""Client portal PDFs + CRM finding verification (2D + verify-fix)."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from routers.crm_auth import require_supabase_uid
from services.crm_pipeda_report import build_pipeda_html, html_to_pdf_bytes
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


@router.post("/api/crm/finding-verify")
def crm_verify_finding(body: VerifyFindingBody, uid: str = Depends(require_supabase_uid)):
    """
    Re-scan domain and mark finding verified if it no longer appears at same severity.
    """
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")
    if not _can_access_prospect(uid, body.prospect_id):
        raise HTTPException(status_code=403, detail="Not allowed for this prospect")

    sc_r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/crm_prospect_scans",
        headers=_sb(),
        params={
            "id": f"eq.{body.scan_id}",
            "prospect_id": f"eq.{body.prospect_id}",
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
    target = next((f for f in flist if str(f.get("id")) == body.finding_id), None)
    if not target:
        raise HTTPException(status_code=404, detail="Finding not in scan")

    pr_r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/prospects",
        headers=_sb(),
        params={"id": f"eq.{body.prospect_id}", "select": "domain", "limit": "1"},
        timeout=20.0,
    )
    pr_r.raise_for_status()
    dom_row = (pr_r.json() or [None])[0]
    domain = (dom_row or {}).get("domain")
    if not domain:
        raise HTTPException(status_code=400, detail="Prospect has no domain")

    try:
        fresh = run_scan(str(domain).strip().lower())
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
            return {"ok": True, "verified": False, "message": "Finding still present at similar severity."}

    for f in flist:
        if str(f.get("id")) == body.finding_id:
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
        params={"id": f"eq.{body.scan_id}"},
        json=patch_body,
        timeout=20.0,
    )
    if patch_r.status_code >= 400:
        raise HTTPException(status_code=502, detail=patch_r.text[:400])

    return {
        "ok": True,
        "verified": True,
        "new_score": fresh.get("score"),
        "message": "Marked verified; rescan did not show the same exposure at prior severity.",
    }
