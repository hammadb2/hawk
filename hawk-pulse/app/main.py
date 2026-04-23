"""
HAWK Pulse Engine — Event-Driven Continuous Threat Exposure Management.

FastAPI application with:
- Certificate Transparency listener (certstream)
- Micro-scan orchestrator (naabu + httpx)
- State diffing engine (PostgreSQL JSONB)
- Real-time WebSocket alert push
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_engine, get_session, get_session_factory
from app.engine.state_diff import (
    get_all_monitored_domains,
    get_monitored_domain,
    process_scan_results,
)
from app.listeners.certstream import start_ct_listener
from app.models import Alert, Asset, Base, MonitoredDomain, ScanEvent
from app.scanner.microscan import micro_scan
from app.ws.manager import ConnectionManager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

ws_manager = ConnectionManager()
_ct_listener = None
_scan_semaphore: asyncio.Semaphore | None = None


async def _on_ct_match(root_domain: str, cert_domains: list[str]) -> None:
    """Callback fired by the CT listener when a monitored domain gets a new cert."""
    logger.info("CT event for %s — cert domains: %s", root_domain, cert_domains[:5])

    new_hosts = [d for d in cert_domains if d.endswith(f".{root_domain}") or d == root_domain]

    if _scan_semaphore:
        async with _scan_semaphore:
            result = await micro_scan(root_domain, hosts=new_hosts or [root_domain])
    else:
        result = await micro_scan(root_domain, hosts=new_hosts or [root_domain])

    factory = get_session_factory()
    async with factory() as session:
        alerts = await process_scan_results(
            session,
            root_domain,
            result,
            trigger="certstream",
            trigger_detail={"cert_domains": cert_domains[:20]},
        )

    for alert in alerts:
        await ws_manager.broadcast_alert(root_domain, _alert_to_dict(alert))


def _alert_to_dict(alert: Alert) -> dict[str, Any]:
    return {
        "id": str(alert.id),
        "domain_id": str(alert.domain_id),
        "alert_type": alert.alert_type,
        "severity": alert.severity,
        "title": alert.title,
        "detail": alert.detail,
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _ct_listener, _scan_semaphore
    settings = get_settings()
    _scan_semaphore = asyncio.Semaphore(settings.microscan_workers)

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables ensured")

    factory = get_session_factory()
    async with factory() as session:
        domains = await get_all_monitored_domains(session)

    if domains:
        _ct_listener = await start_ct_listener(
            set(domains), _on_ct_match, settings.certstream_url
        )
        logger.info("CT listener started for %d domain(s)", len(domains))
    else:
        logger.warning("No monitored domains — CT listener not started. Add domains via POST /api/domains.")

    yield

    if _ct_listener:
        _ct_listener.stop()
    await engine.dispose()


app = FastAPI(
    title="HAWK Pulse Engine",
    description="Event-driven CTEM: certstream listener -> micro-scan -> state diff -> WebSocket alerts.",
    version="3.0.0-poc",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "hawk-pulse",
        "version": "3.0.0-poc",
        "ws_connections": ws_manager.active_connections,
        "ct_listener_active": _ct_listener is not None and _ct_listener._running,
    }


# ---------------------------------------------------------------------------
# Domain management
# ---------------------------------------------------------------------------

class DomainCreate(BaseModel):
    domain: str = Field(..., min_length=1, description="Root domain to monitor (e.g. example.com)")
    owner_email: str | None = None


class DomainResponse(BaseModel):
    id: str
    domain: str
    owner_email: str | None
    active: bool
    created_at: str


@app.post("/api/domains", response_model=DomainResponse, status_code=201)
async def add_domain(body: DomainCreate, session: AsyncSession = Depends(get_session)):
    global _ct_listener
    domain = body.domain.lower().strip()
    existing = await get_monitored_domain(session, domain)

    if existing and existing.active:
        raise HTTPException(status_code=409, detail=f"Domain {domain} already monitored")
    if existing and not existing.active:
        existing.active = True
        existing.owner_email = body.owner_email or existing.owner_email
        await session.commit()
        await session.refresh(existing)
        md = existing
    else:
        md = MonitoredDomain(domain=domain, owner_email=body.owner_email)
        session.add(md)
        await session.commit()
        await session.refresh(md)

    if _ct_listener:
        _ct_listener.update_domains(
            _ct_listener._monitored | {domain}
        )
    else:
        settings = get_settings()
        _ct_listener = await start_ct_listener({domain}, _on_ct_match, settings.certstream_url)
        logger.info("CT listener lazily started for first domain: %s", domain)

    logger.info("Domain added for monitoring: %s", domain)
    return DomainResponse(
        id=str(md.id), domain=md.domain, owner_email=md.owner_email,
        active=md.active, created_at=md.created_at.isoformat(),
    )


@app.get("/api/domains")
async def list_domains(session: AsyncSession = Depends(get_session)):
    result = await session.execute(
        select(MonitoredDomain).where(MonitoredDomain.active.is_(True))
    )
    domains = result.scalars().all()
    return [
        {
            "id": str(d.id), "domain": d.domain, "owner_email": d.owner_email,
            "active": d.active, "created_at": d.created_at.isoformat(),
        }
        for d in domains
    ]


@app.delete("/api/domains/{domain}")
async def remove_domain(domain: str, session: AsyncSession = Depends(get_session)):
    md = await get_monitored_domain(session, domain)
    if not md:
        raise HTTPException(status_code=404, detail="Domain not found")
    md.active = False
    await session.commit()

    if _ct_listener:
        _ct_listener.update_domains(
            _ct_listener._monitored - {domain.lower().strip()}
        )
    return {"status": "deactivated", "domain": domain}


# ---------------------------------------------------------------------------
# Manual scan trigger
# ---------------------------------------------------------------------------

class ScanTriggerRequest(BaseModel):
    domain: str = Field(..., min_length=1)
    hosts: list[str] | None = None


@app.post("/api/scan")
async def trigger_scan(body: ScanTriggerRequest, session: AsyncSession = Depends(get_session)):
    """Manually trigger a micro-scan and run state diffing."""
    domain = body.domain.lower().strip()
    md = await get_monitored_domain(session, domain)
    if not md:
        raise HTTPException(status_code=404, detail=f"Domain {domain} not monitored. Add it first via POST /api/domains.")

    result = await micro_scan(domain, hosts=body.hosts)

    alerts = await process_scan_results(
        session, domain, result,
        trigger="manual",
        trigger_detail={"hosts": body.hosts},
    )

    for alert in alerts:
        await ws_manager.broadcast_alert(domain, _alert_to_dict(alert))

    return {
        "domain": domain,
        "scan_result": {
            "ports_found": len(result.get("ports", [])),
            "http_services_found": len(result.get("http_services", [])),
        },
        "alerts": [_alert_to_dict(a) for a in alerts],
    }


# ---------------------------------------------------------------------------
# Alerts API
# ---------------------------------------------------------------------------

@app.get("/api/alerts/{domain}")
async def get_alerts(
    domain: str,
    limit: int = 50,
    unacknowledged_only: bool = False,
    session: AsyncSession = Depends(get_session),
):
    md = await get_monitored_domain(session, domain)
    if not md:
        raise HTTPException(status_code=404, detail="Domain not found")

    q = select(Alert).where(Alert.domain_id == md.id)
    if unacknowledged_only:
        q = q.where(Alert.acknowledged.is_(False))
    q = q.order_by(Alert.created_at.desc()).limit(limit)
    result = await session.execute(q)
    alerts = result.scalars().all()
    return [_alert_to_dict(a) for a in alerts]


@app.patch("/api/alerts/{alert_id}/ack")
async def acknowledge_alert(alert_id: str, session: AsyncSession = Depends(get_session)):
    import uuid as _uuid
    result = await session.execute(select(Alert).where(Alert.id == _uuid.UUID(alert_id)))
    alert = result.scalar_one_or_none()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    alert.acknowledged = True
    await session.commit()
    return {"status": "acknowledged", "alert_id": alert_id}


# ---------------------------------------------------------------------------
# Assets API
# ---------------------------------------------------------------------------

@app.get("/api/assets/{domain}")
async def get_assets(
    domain: str,
    asset_type: str | None = None,
    session: AsyncSession = Depends(get_session),
):
    md = await get_monitored_domain(session, domain)
    if not md:
        raise HTTPException(status_code=404, detail="Domain not found")

    q = select(Asset).where(Asset.domain_id == md.id)
    if asset_type:
        q = q.where(Asset.asset_type == asset_type)
    q = q.order_by(Asset.last_seen.desc())
    result = await session.execute(q)
    assets = result.scalars().all()
    return [
        {
            "id": str(a.id),
            "asset_type": a.asset_type,
            "asset_key": a.asset_key,
            "metadata": a.metadata_,
            "first_seen": a.first_seen.isoformat(),
            "last_seen": a.last_seen.isoformat(),
            "is_new": a.is_new,
        }
        for a in assets
    ]


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

@app.websocket("/ws/alerts/{domain}")
async def websocket_alerts(websocket: WebSocket, domain: str):
    """
    Real-time alert stream. Connect to /ws/alerts/example.com to receive
    push notifications whenever a state change is detected for that domain.
    """
    await ws_manager.connect(websocket, domain)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket, domain)


# ---------------------------------------------------------------------------
# Scan events (audit log)
# ---------------------------------------------------------------------------

@app.get("/api/events/{domain}")
async def get_scan_events(
    domain: str, limit: int = 20, session: AsyncSession = Depends(get_session)
):
    md = await get_monitored_domain(session, domain)
    if not md:
        raise HTTPException(status_code=404, detail="Domain not found")
    result = await session.execute(
        select(ScanEvent)
        .where(ScanEvent.domain_id == md.id)
        .order_by(ScanEvent.started_at.desc())
        .limit(limit)
    )
    events = result.scalars().all()
    return [
        {
            "id": str(e.id),
            "trigger": e.trigger,
            "status": e.status,
            "result_summary": e.result_summary,
            "started_at": e.started_at.isoformat() if e.started_at else None,
            "completed_at": e.completed_at.isoformat() if e.completed_at else None,
        }
        for e in events
    ]
