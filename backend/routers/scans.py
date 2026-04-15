from __future__ import annotations

import json
import logging
import threading
import time
from uuid import uuid4
from datetime import datetime, timedelta, timezone
import secrets
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, Header, Query, Request

logger = logging.getLogger(__name__)


class _RateLimiter:
    """Simple in-memory sliding-window rate limiter keyed by client IP."""

    def __init__(self, max_requests: int = 5, window_seconds: int = 60):
        self._max = max_requests
        self._window = window_seconds
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()
        self._last_prune: float = 0.0

    def check(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            # Periodically prune stale keys (every 5 minutes)
            if now - self._last_prune > 300:
                self._hits = {k: v for k, v in self._hits.items() if v and now - v[-1] < self._window}
                self._last_prune = now
            hits = self._hits.get(key, [])
            hits = [t for t in hits if now - t < self._window]
            if len(hits) >= self._max:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            return True


# Homepage full scans are heavier; allow a few more attempts per minute per IP.
_public_scan_limiter = _RateLimiter(max_requests=8, window_seconds=60)
from sqlalchemy import desc
from sqlalchemy.orm import Session

from auth import get_current_user
from config import CRON_SECRET
from database import get_db
from models import User, Scan, Domain, Report
from schemas import ScanEnqueueRequest, ScanStartRequest, ScanResponse, ScanListItem
from services.scanner import enqueue_async_scan, get_async_job, run_scan
from services.scanner_trust import scanner_trust_level
from services.charlotte import critical_finding_alert, weekly_digest_email, monthly_report_ready_email
from config import PLAN_DOMAINS

router = APIRouter(tags=["scans"])


def _severity_rank(severity: str | None) -> int:
    order = {"critical": 0, "high": 1, "medium": 2, "warning": 2, "low": 3, "info": 4, "ok": 99}
    return order.get((severity or "").lower(), 50)


def _finding_plain_english(f: dict, interpreted_row: dict | None) -> str:
    """Plain English for homepage / CRM — no raw technical strings."""
    if interpreted_row:
        plain = interpreted_row.get("plain_english") or interpreted_row.get("plainEnglish")
        if isinstance(plain, str) and plain.strip():
            return plain.strip()
    interp = f.get("interpretation")
    if isinstance(interp, str) and interp.strip():
        return interp.strip()
    desc = (f.get("description") or "").strip()
    if desc:
        return desc
    return (f.get("title") or "").strip()


_HOMEPAGE_PREVIEW_MAX = 6


def _public_scan_findings_preview(result: dict) -> tuple[list[dict[str, str]], list[str], int]:
    """Up to 6 plain-English lines with severity + parallel string list (homepage)."""
    findings = result.get("findings") or []
    interpreted = result.get("interpreted_findings") or []
    merged: list[tuple[dict, str]] = []
    for idx, f in enumerate(findings):
        if not isinstance(f, dict):
            continue
        ir: dict | None = None
        if idx < len(interpreted) and isinstance(interpreted[idx], dict):
            ir = interpreted[idx]
        text = _finding_plain_english(f, ir)
        if text:
            merged.append((f, text))
    merged.sort(key=lambda x: _severity_rank(x[0].get("severity")))
    issues = sum(1 for f, _ in merged if (f.get("severity") or "").lower() != "ok")

    preview: list[dict[str, str]] = []
    seen: set[str] = set()

    def _push(f: dict, text: str, severity: str) -> None:
        if text in seen:
            return
        seen.add(text)
        preview.append({"text": text, "severity": severity})

    for f, text in merged:
        if (f.get("severity") or "").lower() == "ok":
            continue
        sev = (f.get("severity") or "medium").lower()
        if sev not in ("critical", "high", "medium", "warning", "low", "info"):
            sev = "medium"
        _push(f, text, sev)
        if len(preview) >= _HOMEPAGE_PREVIEW_MAX:
            break

    if len(preview) < _HOMEPAGE_PREVIEW_MAX:
        for f, text in merged:
            if (f.get("severity") or "").lower() != "ok":
                continue
            _push(f, text, "ok")
            if len(preview) >= _HOMEPAGE_PREVIEW_MAX:
                break

    fillers = [
        "Automated criminal tooling probes this exact public surface 24/7 — what you see above is only what answered immediately.",
        "Ransomware affiliates and cred-stuffing bots start from the same DNS, mail, and TLS signals we just evaluated.",
        "Insurers and enterprise clients increasingly ask for continuous evidence — not a one-time PDF that was green last quarter.",
        "Shield runs deeper template coverage, lookalike monitoring, and scheduled re-tests so drift gets caught before an incident.",
        "Most SMB breaches start from small, internet-visible misconfigurations — prioritized above so you can fix what attackers enumerate first.",
        "Enter your work email below and we will send the expanded report with remediation steps you can hand to IT or your MSP.",
    ]
    i = 0
    while len(preview) < _HOMEPAGE_PREVIEW_MAX:
        preview.append({"text": fillers[i % len(fillers)], "severity": "info"})
        i += 1

    plain = [p["text"] for p in preview[:_HOMEPAGE_PREVIEW_MAX]]
    return preview[:_HOMEPAGE_PREVIEW_MAX], plain, issues


def _public_risk_extras(result: dict) -> dict:
    """Small, factual urgency fields for marketing homepage (no fabricated findings)."""
    out: dict[str, object] = {}
    ap = result.get("attack_paths") or []
    if isinstance(ap, list):
        out["attack_paths_count"] = len(ap)
        if ap and isinstance(ap[0], dict):
            name = (ap[0].get("name") or ap[0].get("title") or "").strip()
            if name:
                out["top_attack_path"] = name[:200]
    bce = result.get("breach_cost_estimate") or {}
    if isinstance(bce, dict):
        if bce.get("baseline_usd") is not None:
            try:
                out["breach_baseline_usd"] = int(bce["baseline_usd"])
            except (TypeError, ValueError):
                pass
        summ = bce.get("summary")
        if isinstance(summ, str) and summ.strip():
            out["breach_cost_summary"] = summ.strip()[:500]
    return out


def _normalize_domain(domain: str) -> str:
    d = domain.lower().strip()
    if re.match(r'^(https?|ftp)://', d):
        d = d.split("//", 1)[1].split("/")[0]
    elif d.startswith("//"):
        d = d[2:].split("/")[0]
    # Strip port number
    d = re.sub(r':\d+$', '', d)
    if d.startswith("www."):
        d = d[4:]
    return d


def _scan_to_item(scan: Scan) -> dict:
    return {
        "id": scan.id,
        "domain_id": scan.domain_id,
        "user_id": scan.user_id,
        "status": scan.status,
        "score": scan.score,
        "grade": scan.grade,
        "started_at": scan.started_at.isoformat() if scan.started_at else None,
        "completed_at": scan.completed_at.isoformat() if scan.completed_at else None,
    }


@router.post("/api/scan/public")
def start_scan_public(req: ScanStartRequest, request: Request):
    """Run a real scan without auth. Slim JSON by default; set full_result=true for CRM-sized payload."""
    client_ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
                 or (request.client.host if request.client else "unknown"))
    if not _public_scan_limiter.check(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again in a minute.")
    domain_clean = _normalize_domain(req.domain)
    if not domain_clean:
        raise HTTPException(status_code=400, detail="Invalid domain")
    depth = (req.scan_depth or "full").strip().lower()
    if depth not in ("fast", "full"):
        depth = "full"
    try:
        result = run_scan(domain_clean, scan_id=None, scan_depth=depth, trust_level="public")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Scanner error: {e}") from e
    if req.full_result:
        return result
    preview, plain, issues_count = _public_scan_findings_preview(result)
    risk = _public_risk_extras(result)
    return {
        "domain": result.get("domain", domain_clean),
        "status": result.get("status", "completed"),
        "score": result.get("score"),
        "grade": result.get("grade"),
        "findings_count": len(result.get("findings", [])),
        "issues_count": issues_count,
        "findings_plain": plain,
        "findings_preview": preview,
        "scan_version": result.get("scan_version"),
        **risk,
    }


@router.post("/api/scan/enqueue")
def scan_enqueue(req: ScanEnqueueRequest, request: Request):
    """Queue async scan on hawk-scanner-v2 (Redis/arq). Returns job_id for polling."""
    client_ip = (request.headers.get("x-forwarded-for", "").split(",")[0].strip()
                 or (request.client.host if request.client else "unknown"))
    if not _public_scan_limiter.check(client_ip):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again in a minute.")
    domain_clean = _normalize_domain(req.domain)
    if not domain_clean:
        raise HTTPException(status_code=400, detail="Invalid domain")
    try:
        job_id = enqueue_async_scan(
            domain_clean,
            req.industry,
            req.company_name,
            scan_depth=req.scan_depth or "full",
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Scanner enqueue error: {e}") from e
    return {"job_id": job_id}


@router.get("/api/scan/job/{job_id}")
def scan_job_status(job_id: str):
    """Proxy job status/result from scanner worker."""
    try:
        return get_async_job(job_id)
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=e.response.text[:800]) from e
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Scanner job error: {e}") from e


@router.post("/api/scan")
def start_scan(
    req: ScanStartRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Start a scan for the given domain. Returns scan_id and result (saved to DB)."""
    domain_clean = _normalize_domain(req.domain)

    scan_id = str(uuid4())
    scan = Scan(
        id=scan_id,
        user_id=user.id,
        domain_id=None,
        scanned_domain=domain_clean,
        triggered_by="user",
        status="pending",
    )
    db.add(scan)
    db.commit()

    depth = (req.scan_depth or "full").strip().lower()
    if depth not in ("fast", "full"):
        depth = "full"
    trust = scanner_trust_level(
        db,
        user,
        domain_clean,
        remediation_acknowledged=bool(req.remediation_acknowledged),
    )
    try:
        result = run_scan(domain_clean, scan_id=scan_id, scan_depth=depth, trust_level=trust)
    except Exception as e:
        scan.status = "failed"
        db.commit()
        raise HTTPException(status_code=502, detail=f"Scanner error: {e}") from e

    scan.status = result.get("status", "completed")
    scan.score = result.get("score")
    scan.grade = result.get("grade")
    scan.findings_json = json.dumps(result.get("findings", []))
    scan.started_at = datetime.fromisoformat(result["started_at"].replace("Z", "+00:00")) if result.get("started_at") else datetime.now(timezone.utc)
    scan.completed_at = datetime.fromisoformat(result["completed_at"].replace("Z", "+00:00")) if result.get("completed_at") else datetime.now(timezone.utc)
    db.commit()
    _maybe_alert_critical(user, domain_clean, scan_id, result.get("findings", []))

    return {"scan_id": scan_id, "domain": domain_clean, "status": scan.status, "score": scan.score, "grade": scan.grade}


@router.get("/api/scan/{scan_id}")
def get_scan(
    scan_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    scan = db.query(Scan).filter(Scan.id == scan_id, Scan.user_id == user.id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    return {
        "id": scan.id,
        "domain_id": scan.domain_id,
        "user_id": scan.user_id,
        "triggered_by": scan.triggered_by,
        "status": scan.status,
        "score": scan.score,
        "grade": scan.grade,
        "findings_json": scan.findings_json,
        "started_at": scan.started_at.isoformat() if scan.started_at else None,
        "completed_at": scan.completed_at.isoformat() if scan.completed_at else None,
    }


@router.get("/api/scans")
def list_scans(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    scans = db.query(Scan).filter(Scan.user_id == user.id).order_by(desc(Scan.started_at)).limit(100).all()
    return {"scans": [_scan_to_item(s) for s in scans]}


@router.post("/api/scan/{scan_id}/rescan")
def rescan(
    scan_id: str,
    remediation_acknowledged: bool = Query(
        False,
        description="If true, use certified scoring tier (paid + domain + attestation).",
    ),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    scan = db.query(Scan).filter(Scan.id == scan_id, Scan.user_id == user.id).first()
    if not scan:
        raise HTTPException(status_code=404, detail="Scan not found")
    domain_str = scan.scanned_domain
    if not domain_str and scan.domain_id:
        dom = db.query(Domain).filter(Domain.id == scan.domain_id).first()
        domain_str = dom.domain if dom else None
    if not domain_str and scan.findings_json:
        try:
            findings = json.loads(scan.findings_json)
            for f in findings:
                if f.get("affected_asset"):
                    domain_str = f["affected_asset"].split("(")[-1].rstrip(")").strip() or f.get("affected_asset", "").split()[-1]
                    break
        except Exception:
            pass
    if not domain_str:
        raise HTTPException(status_code=400, detail="Cannot determine domain to rescan")
    new_id = str(uuid4())
    new_scan = Scan(id=new_id, user_id=user.id, domain_id=scan.domain_id, scanned_domain=domain_str, triggered_by="user", status="pending")
    db.add(new_scan)
    db.commit()
    trust = scanner_trust_level(
        db,
        user,
        domain_str,
        remediation_acknowledged=bool(remediation_acknowledged),
    )
    try:
        result = run_scan(domain_str, scan_id=new_id, trust_level=trust)
    except Exception as e:
        new_scan.status = "failed"
        db.commit()
        raise HTTPException(status_code=502, detail=f"Scanner error: {e}") from e
    new_scan.status = result.get("status", "completed")
    new_scan.score = result.get("score")
    new_scan.grade = result.get("grade")
    new_scan.findings_json = json.dumps(result.get("findings", []))
    new_scan.started_at = datetime.fromisoformat(result["started_at"].replace("Z", "+00:00")) if result.get("started_at") else datetime.now(timezone.utc)
    new_scan.completed_at = datetime.fromisoformat(result["completed_at"].replace("Z", "+00:00")) if result.get("completed_at") else datetime.now(timezone.utc)
    db.commit()
    _maybe_alert_critical(user, domain_str, new_id, result.get("findings", []))
    return {"scan_id": new_id, "domain": domain_str, "status": new_scan.status, "score": new_scan.score, "grade": new_scan.grade}


def _cron_verified(x_cron_secret: str | None = Header(None)):
    if not CRON_SECRET or not x_cron_secret or not secrets.compare_digest(x_cron_secret, CRON_SECRET):
        raise HTTPException(status_code=403, detail="Invalid or missing cron secret")
    return True


def _maybe_alert_critical(user: User, domain: str, scan_id: str, findings: list) -> None:
    critical = [f for f in findings if f.get("severity") == "critical"]
    if not critical:
        return
    to = user.email
    critical_finding_alert(to=to, domain=domain, scan_id=scan_id, critical_count=len(critical), titles=[f.get("title", "") for f in critical[:5]])


@router.post("/api/cron/scheduled-scans")
def run_scheduled_scans(
    x_cron_secret: str | None = Header(None),
    db: Session = Depends(get_db),
    _: bool = Depends(_cron_verified),
):
    """Call from cron. Runs scans for domains with weekly/daily frequency when due."""
    now = datetime.now(timezone.utc)
    def _utc(d):
        if d is None:
            return None
        return d if getattr(d, "tzinfo", None) else d.replace(tzinfo=timezone.utc)

    domains = db.query(Domain).filter(Domain.scan_frequency.in_(["weekly", "daily"])).all()
    triggered = []
    for dom in domains:
        last = db.query(Scan).filter(Scan.domain_id == dom.id).order_by(desc(Scan.completed_at)).first()
        due = False
        if not last or not last.completed_at:
            due = True
        else:
            completed = _utc(last.completed_at)
            if completed and dom.scan_frequency == "daily" and (now - completed) > timedelta(days=1):
                due = True
            elif completed and dom.scan_frequency == "weekly" and (now - completed) > timedelta(days=7):
                due = True
        if not due:
            continue
        scan_id = str(uuid4())
        scan = Scan(id=scan_id, user_id=dom.user_id, domain_id=dom.id, scanned_domain=dom.domain, triggered_by="schedule", status="pending")
        db.add(scan)
        db.commit()
        user = db.query(User).filter(User.id == dom.user_id).first()
        trust = scanner_trust_level(
            db,
            user,
            dom.domain,
            remediation_acknowledged=False,
        )
        try:
            result = run_scan(dom.domain, scan_id=scan_id, trust_level=trust)
        except Exception:
            scan.status = "failed"
            db.commit()
            continue
        scan.status = result.get("status", "completed")
        scan.score = result.get("score")
        scan.grade = result.get("grade")
        scan.findings_json = json.dumps(result.get("findings", []))
        scan.started_at = datetime.fromisoformat(result["started_at"].replace("Z", "+00:00")) if result.get("started_at") else now
        scan.completed_at = datetime.fromisoformat(result["completed_at"].replace("Z", "+00:00")) if result.get("completed_at") else now
        db.commit()
        if user:
            _maybe_alert_critical(user, dom.domain, scan_id, result.get("findings", []))
        triggered.append({"domain": dom.domain, "scan_id": scan_id})
    return {"triggered": len(triggered), "scans": triggered}


@router.post("/api/cron/trial-expiry")
def run_trial_expiry_emails(
    x_cron_secret: str | None = Header(None),
    _: bool = Depends(_cron_verified),
):
    """Legacy cron hook: product trials are not offered — no emails sent."""
    return {"sent": 0, "skipped": True, "reason": "trial_expiry_emails_disabled"}


@router.post("/api/cron/weekly-digest")
def run_weekly_digest(
    x_cron_secret: str | None = Header(None),
    db: Session = Depends(get_db),
    _: bool = Depends(_cron_verified),
):
    """Call weekly from cron. Sends digest to users who had scans in the last 7 days."""
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=7)
    # Get users who have scans in the last 7 days
    scan_subq = db.query(Scan.user_id).filter(Scan.completed_at >= since).distinct()
    user_ids = [r[0] for r in scan_subq.all()]
    sent = 0
    for uid in user_ids:
        user = db.query(User).filter(User.id == uid).first()
        if not user:
            continue
        scans = db.query(Scan).filter(Scan.user_id == uid, Scan.completed_at >= since).all()
        if not scans:
            continue
        critical_total = 0
        domains_seen = set()
        for s in scans:
            domains_seen.add(s.scanned_domain or "")
            try:
                findings = json.loads(s.findings_json or "[]")
                critical_total += sum(1 for f in findings if f.get("severity") == "critical")
            except Exception:
                pass
        domains_seen.discard("")
        domains_list = sorted(domains_seen)[:20]
        if weekly_digest_email(user.email, len(scans), critical_total, domains_list, user.first_name):
            sent += 1
    return {"sent": sent, "users_contacted": sent}


@router.post("/api/cron/monthly-report")
def run_monthly_report_emails(
    x_cron_secret: str | None = Header(None),
    db: Session = Depends(get_db),
    _: bool = Depends(_cron_verified),
):
    """Call monthly from cron. Sends 'report ready' email to users who have at least one report in the past 30 days."""
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=30)
    user_ids = db.query(Report.user_id).filter(Report.created_at >= since).distinct().all()
    user_ids = [r[0] for r in user_ids]
    sent = 0
    for uid in user_ids:
        user = db.query(User).filter(User.id == uid).first()
        if user and monthly_report_ready_email(user.email, user.first_name):
            sent += 1
    return {"sent": sent}
