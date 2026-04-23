"""State diffing engine — compares micro-scan results against the asset DB."""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Alert, Asset, MonitoredDomain, ScanEvent

logger = logging.getLogger(__name__)

# Ports that warrant a critical alert when newly opened
CRITICAL_PORTS = frozenset({"21", "23", "3306", "3389", "5432", "6379", "27017"})
WARNING_PORTS = frozenset({"22", "25", "8080", "8443"})


def _port_severity(port: str) -> str:
    if port in CRITICAL_PORTS:
        return "critical"
    if port in WARNING_PORTS:
        return "warning"
    return "info"


async def get_monitored_domain(session: AsyncSession, domain: str) -> MonitoredDomain | None:
    result = await session.execute(
        select(MonitoredDomain).where(MonitoredDomain.domain == domain.lower().strip())
    )
    return result.scalar_one_or_none()


async def get_all_monitored_domains(session: AsyncSession) -> list[str]:
    result = await session.execute(
        select(MonitoredDomain.domain).where(MonitoredDomain.active.is_(True))
    )
    return [row[0] for row in result.all()]


async def process_scan_results(
    session: AsyncSession,
    domain: str,
    scan_result: dict[str, Any],
    trigger: str = "certstream",
    trigger_detail: dict | None = None,
) -> list[Alert]:
    """
    Compare scan results against known asset state.
    Returns list of new alerts generated (delta only).
    """
    md = await get_monitored_domain(session, domain)
    if not md:
        logger.warning("Domain %s not in monitored_domains, skipping", domain)
        return []

    now = datetime.now(timezone.utc)

    scan_event = ScanEvent(
        domain_id=md.id,
        trigger=trigger,
        trigger_detail=trigger_detail or {},
        status="processing",
        started_at=now,
    )
    session.add(scan_event)
    await session.flush()

    alerts: list[Alert] = []

    # --- Diff open ports ---
    ports = scan_result.get("ports") or []
    for port_row in ports:
        host = port_row.get("host", "")
        port = port_row.get("port", "")
        if not host:
            continue
        asset_key = f"{host}:{port}" if port else host

        existing = await session.execute(
            select(Asset).where(
                Asset.domain_id == md.id,
                Asset.asset_type == "open_port",
                Asset.asset_key == asset_key,
            )
        )
        existing_asset = existing.scalar_one_or_none()

        if existing_asset:
            existing_asset.last_seen = now
            existing_asset.is_new = False
            existing_asset.metadata_ = {**existing_asset.metadata_, **port_row}
        else:
            new_asset = Asset(
                domain_id=md.id,
                asset_type="open_port",
                asset_key=asset_key,
                metadata_=port_row,
                first_seen=now,
                last_seen=now,
                is_new=True,
            )
            session.add(new_asset)
            await session.flush()

            severity = _port_severity(port)
            alert = Alert(
                domain_id=md.id,
                alert_type="port_opened",
                severity=severity,
                title=f"New port detected: {asset_key}",
                detail={
                    "host": host,
                    "port": port,
                    "trigger": trigger,
                },
                asset_id=new_asset.id,
            )
            session.add(alert)
            alerts.append(alert)
            logger.info("ALERT [%s]: %s — %s", severity.upper(), domain, alert.title)

    # --- Diff HTTP services ---
    http_services = scan_result.get("http_services") or []
    for svc in http_services:
        url = svc.get("url") or svc.get("final_url") or ""
        if not url:
            continue
        asset_key = url.split("?")[0][:512]

        existing = await session.execute(
            select(Asset).where(
                Asset.domain_id == md.id,
                Asset.asset_type == "http_service",
                Asset.asset_key == asset_key,
            )
        )
        existing_asset = existing.scalar_one_or_none()

        if existing_asset:
            old_status = existing_asset.metadata_.get("status_code")
            new_status = svc.get("status_code") or svc.get("status-code")
            existing_asset.last_seen = now
            existing_asset.is_new = False
            existing_asset.metadata_ = {**existing_asset.metadata_, **_safe_svc_meta(svc)}

            if old_status != new_status and new_status:
                alert = Alert(
                    domain_id=md.id,
                    alert_type="service_changed",
                    severity="info",
                    title=f"HTTP status changed on {asset_key}: {old_status} -> {new_status}",
                    detail={"url": url, "old_status": old_status, "new_status": new_status},
                    asset_id=existing_asset.id,
                )
                session.add(alert)
                alerts.append(alert)
        else:
            new_asset = Asset(
                domain_id=md.id,
                asset_type="http_service",
                asset_key=asset_key,
                metadata_=_safe_svc_meta(svc),
                first_seen=now,
                last_seen=now,
                is_new=True,
            )
            session.add(new_asset)
            await session.flush()

            alert = Alert(
                domain_id=md.id,
                alert_type="new_asset",
                severity="warning",
                title=f"New HTTP service discovered: {asset_key}",
                detail={"url": url, "trigger": trigger},
                asset_id=new_asset.id,
            )
            session.add(alert)
            alerts.append(alert)

    # --- Diff subdomains (from hosts_scanned) ---
    hosts_scanned = scan_result.get("hosts_scanned") or []
    for host in hosts_scanned:
        host = host.lower().strip()
        if not host or host == domain:
            continue
        existing = await session.execute(
            select(Asset).where(
                Asset.domain_id == md.id,
                Asset.asset_type == "subdomain",
                Asset.asset_key == host,
            )
        )
        existing_asset = existing.scalar_one_or_none()
        if existing_asset:
            existing_asset.last_seen = now
            existing_asset.is_new = False
        else:
            new_asset = Asset(
                domain_id=md.id,
                asset_type="subdomain",
                asset_key=host,
                metadata_={"source": trigger},
                first_seen=now,
                last_seen=now,
                is_new=True,
            )
            session.add(new_asset)
            await session.flush()
            alert = Alert(
                domain_id=md.id,
                alert_type="new_asset",
                severity="info",
                title=f"New subdomain discovered: {host}",
                detail={"subdomain": host, "trigger": trigger},
                asset_id=new_asset.id,
            )
            session.add(alert)
            alerts.append(alert)

    scan_event.status = "completed"
    scan_event.completed_at = datetime.now(timezone.utc)
    scan_event.result_summary = {
        "ports_scanned": len(ports),
        "http_services_scanned": len(http_services),
        "alerts_generated": len(alerts),
    }

    await session.commit()
    return alerts


def _safe_svc_meta(svc: dict[str, Any]) -> dict[str, Any]:
    """Extract a small metadata dict from an httpx JSONL row."""
    keys = ("url", "final_url", "status_code", "status-code", "title", "webserver", "tech", "content_length")
    return {k: svc[k] for k in keys if k in svc}
