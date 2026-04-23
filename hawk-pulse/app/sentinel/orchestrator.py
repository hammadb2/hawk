"""HAWK Sentinel — Audit Orchestrator.

Coordinates the full penetration test lifecycle:
  ROE Chat → Sandbox Spin-up → Agent Swarm → PDF Report → Teardown
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session_factory
from app.models import Asset, MonitoredDomain, SentinelAudit
from app.sentinel.agents import (
    run_ciso_report,
    run_cleanup,
    run_ghost_setup,
    run_operator,
    run_planner,
)
from app.sentinel.pdf_report import generate_pdf
from app.sentinel.sandbox import (
    create_sandbox,
    destroy_sandbox,
    setup_arsenal,
    write_scope_to_sandbox,
)
from app.ws.manager import ConnectionManager

logger = logging.getLogger(__name__)


async def _get_pulse_data(domain_id: str, domain: str) -> dict[str, Any]:
    """Gather reconnaissance data from HAWK Pulse for the target domain."""
    factory = get_session_factory()
    async with factory() as session:
        result = await session.execute(
            select(Asset).where(Asset.domain_id == uuid.UUID(domain_id))
        )
        assets = result.scalars().all()

    pulse_data: dict[str, Any] = {
        "domain": domain,
        "assets": [],
    }

    for asset in assets:
        pulse_data["assets"].append({
            "type": asset.asset_type,
            "key": asset.asset_key,
            "metadata": dict(asset.metadata_) if asset.metadata_ else {},
            "first_seen": asset.first_seen.isoformat() if asset.first_seen else None,
            "last_seen": asset.last_seen.isoformat() if asset.last_seen else None,
        })

    return pulse_data


async def _run_full_audit_inner(
    audit_id: str,
    ws_manager: ConnectionManager | None = None,
) -> None:
    """Inner implementation of the audit pipeline (called with a timeout wrapper)."""
    settings = get_settings()
    factory = get_session_factory()
    container_id: str | None = None

    try:
        # Load audit record
        async with factory() as session:
            result = await session.execute(
                select(SentinelAudit).where(
                    SentinelAudit.id == uuid.UUID(audit_id)
                )
            )
            audit = result.scalar_one_or_none()
            if not audit:
                logger.error("Audit %s not found", audit_id)
                return

            scope = dict(audit.scope_json)
            domain_id = str(audit.domain_id)
            audit.status = "provisioning"
            audit.started_at = datetime.now(timezone.utc)
            await session.commit()

        # Resolve domain name
        async with factory() as session:
            result = await session.execute(
                select(MonitoredDomain).where(
                    MonitoredDomain.id == uuid.UUID(domain_id)
                )
            )
            domain_row = result.scalar_one_or_none()
            domain = domain_row.domain if domain_row else "unknown"

        # Phase 1: Provision sandbox
        logger.info("Audit %s: provisioning sandbox", audit_id[:12])
        loop = asyncio.get_event_loop()
        container_id = await loop.run_in_executor(
            None, create_sandbox, audit_id, scope, settings
        )

        async with factory() as session:
            result = await session.execute(
                select(SentinelAudit).where(
                    SentinelAudit.id == uuid.UUID(audit_id)
                )
            )
            audit = result.scalar_one_or_none()
            if audit:
                audit.container_id = container_id
                await session.commit()

        # Write scope.json into container
        await loop.run_in_executor(
            None, write_scope_to_sandbox, container_id, scope
        )

        # Install arsenal
        logger.info("Audit %s: installing arsenal", audit_id[:12])
        await loop.run_in_executor(None, setup_arsenal, container_id)

        # Update status to scanning
        async with factory() as session:
            result = await session.execute(
                select(SentinelAudit).where(
                    SentinelAudit.id == uuid.UUID(audit_id)
                )
            )
            audit = result.scalar_one_or_none()
            if audit:
                audit.status = "scanning"
                await session.commit()

        # Phase 2: Get Pulse recon data
        pulse_data = await _get_pulse_data(domain_id, domain)

        # Phase 3: Agent Swarm
        logger.info("Audit %s: running planner agent", audit_id[:12])
        attack_plan = await run_planner(scope, pulse_data, settings)

        logger.info("Audit %s: running ghost/OPSEC agent", audit_id[:12])
        ghost_results = await run_ghost_setup(scope, attack_plan, container_id, settings)

        logger.info("Audit %s: running operator agent (%d steps)", audit_id[:12], len(attack_plan))
        findings = await run_operator(scope, attack_plan, container_id, settings)

        logger.info("Audit %s: running cleanup agent", audit_id[:12])
        cleanup_results = await run_cleanup(scope, container_id, settings)

        # Phase 4: CISO Report
        async with factory() as session:
            result = await session.execute(
                select(SentinelAudit).where(
                    SentinelAudit.id == uuid.UUID(audit_id)
                )
            )
            audit = result.scalar_one_or_none()
            if audit:
                audit.status = "reporting"
                audit.findings = findings
                audit.agent_log = [
                    {"phase": "ghost_setup", "results": ghost_results},
                    {"phase": "operator", "steps": len(attack_plan)},
                    {"phase": "cleanup", "results": cleanup_results},
                ]
                await session.commit()

        logger.info("Audit %s: generating CISO report", audit_id[:12])
        report_markdown = await run_ciso_report(scope, findings, domain, settings)

        # Generate PDF
        pdf_path = await loop.run_in_executor(
            None, generate_pdf, report_markdown, scope, domain, audit_id
        )

        # Phase 5: Finalize
        async with factory() as session:
            result = await session.execute(
                select(SentinelAudit).where(
                    SentinelAudit.id == uuid.UUID(audit_id)
                )
            )
            audit = result.scalar_one_or_none()
            if audit:
                audit.status = "complete"
                audit.report_markdown = report_markdown
                audit.report_url = pdf_path
                audit.completed_at = datetime.now(timezone.utc)
                await session.commit()

        # Teardown sandbox
        logger.info("Audit %s: destroying sandbox", audit_id[:12])
        await loop.run_in_executor(None, destroy_sandbox, container_id)
        container_id = None

        # Push WebSocket event (lazy-import ws_manager if not provided)
        if ws_manager is None:
            from app.main import ws_manager as _ws
            ws_manager = _ws
        if ws_manager:
            await ws_manager.broadcast_alert(domain, {
                "type": "AUDIT_COMPLETE",
                "audit_id": audit_id,
                "domain": domain,
                "report_url": pdf_path,
                "status": "complete",
            })

        logger.info("Audit %s: COMPLETE", audit_id[:12])

    except BaseException:
        logger.exception("Audit %s failed", audit_id[:12])

        # Mark as failed
        try:
            async with factory() as session:
                result = await session.execute(
                    select(SentinelAudit).where(
                        SentinelAudit.id == uuid.UUID(audit_id)
                    )
                )
                audit = result.scalar_one_or_none()
                if audit:
                    audit.status = "failed"
                    audit.completed_at = datetime.now(timezone.utc)
                    await session.commit()
        except Exception:
            logger.exception("Failed to mark audit %s as failed", audit_id[:12])

    finally:
        # Always teardown sandbox if it was created
        if container_id:
            try:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, destroy_sandbox, container_id)
            except Exception:
                logger.exception("Failed to destroy sandbox for audit %s", audit_id[:12])


async def run_full_audit(
    audit_id: str,
    ws_manager: ConnectionManager | None = None,
) -> None:
    """
    Run the complete Sentinel audit pipeline with an overall timeout.

    Uses sentinel_container_timeout from config as the wall-clock limit.
    If the timeout fires, the inner implementation's except block handles
    marking the audit as failed and destroying the sandbox.
    """
    settings = get_settings()
    try:
        await asyncio.wait_for(
            _run_full_audit_inner(audit_id, ws_manager),
            timeout=settings.sentinel_container_timeout,
        )
    except asyncio.TimeoutError:
        logger.error(
            "Audit %s exceeded %ds timeout — aborting",
            audit_id[:12], settings.sentinel_container_timeout,
        )
        factory = get_session_factory()
        try:
            async with factory() as session:
                result = await session.execute(
                    select(SentinelAudit).where(
                        SentinelAudit.id == uuid.UUID(audit_id)
                    )
                )
                audit = result.scalar_one_or_none()
                if audit:
                    audit.status = "failed"
                    audit.completed_at = datetime.now(timezone.utc)
                    if audit.container_id:
                        try:
                            loop = asyncio.get_event_loop()
                            await loop.run_in_executor(
                                None, destroy_sandbox, audit.container_id
                            )
                        except Exception:
                            logger.exception("Failed to destroy sandbox after timeout")
                    await session.commit()
        except Exception:
            logger.exception("Failed to mark timed-out audit %s as failed", audit_id[:12])
