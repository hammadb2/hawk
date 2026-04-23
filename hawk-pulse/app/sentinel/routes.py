"""HAWK Sentinel — FastAPI routes for the AI Red Team endpoints."""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models import MonitoredDomain, SentinelAudit
from app.sentinel.roe_chat import roe_chat_turn
from app.ws.manager import ConnectionManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sentinel", tags=["sentinel"])

_background_tasks: set[asyncio.Task] = set()


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------

class RoeChatMessage(BaseModel):
    role: str = Field(..., description="'user' or 'assistant'")
    content: str


class RoeChatRequest(BaseModel):
    domain_id: str = Field(..., description="UUID of the monitored domain")
    audit_id: str | None = Field(None, description="Existing audit ID to continue chat")
    messages: list[RoeChatMessage] = Field(default_factory=list, description="Chat history")
    user_message: str = Field(..., description="The new user message")


class RoeChatResponse(BaseModel):
    audit_id: str
    assistant_message: str
    scope_json: dict[str, Any] | None = None
    roe_finalized: bool = False


class AuditStatusResponse(BaseModel):
    audit_id: str
    status: str
    scope_json: dict[str, Any]
    container_id: str | None = None
    findings: list[Any] = []
    report_url: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


class StartAuditRequest(BaseModel):
    audit_id: str = Field(..., description="UUID of the audit with finalized ROE")


class StartAuditResponse(BaseModel):
    audit_id: str
    status: str
    message: str


class ContainerTestRequest(BaseModel):
    audit_id: str | None = None
    scope_json: dict[str, Any] = Field(
        default_factory=lambda: {
            "roe_agreed": True,
            "exploitation_allowed": False,
            "intensity": "deep_scan_only",
            "in_scope_domains": ["*.test.local"],
            "excluded_ips": [],
        }
    )


class ContainerTestResponse(BaseModel):
    container_id: str
    status: str
    arsenal_output: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/roe-chat", response_model=RoeChatResponse)
async def roe_chat_endpoint(
    req: RoeChatRequest,
    session: AsyncSession = Depends(get_session),
) -> RoeChatResponse:
    """Interactive ROE chat — negotiate the penetration test scope."""

    # Validate domain exists
    result = await session.execute(
        select(MonitoredDomain).where(
            MonitoredDomain.id == uuid.UUID(req.domain_id)
        )
    )
    domain = result.scalar_one_or_none()
    if not domain:
        raise HTTPException(status_code=404, detail="Domain not found")

    # Get or create audit
    audit: SentinelAudit | None = None
    if req.audit_id:
        result = await session.execute(
            select(SentinelAudit).where(
                SentinelAudit.id == uuid.UUID(req.audit_id)
            )
        )
        audit = result.scalar_one_or_none()
        if not audit:
            raise HTTPException(status_code=404, detail="Audit not found")
        if audit.status not in ("roe_pending",):
            raise HTTPException(
                status_code=400,
                detail=f"Audit is in '{audit.status}' state — ROE chat is closed",
            )

    if audit is None:
        audit = SentinelAudit(
            domain_id=uuid.UUID(req.domain_id),
            status="roe_pending",
            scope_json={},
            roe_chat_history=[],
        )
        session.add(audit)
        await session.flush()

    # Build chat history for LLM
    chat_history = [
        {"role": m.role, "content": m.content} for m in req.messages
    ]

    # Run one chat turn
    try:
        assistant_reply, scope = await roe_chat_turn(chat_history, req.user_message)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    # Update chat history
    updated_history = list(audit.roe_chat_history or [])
    updated_history.append({"role": "user", "content": req.user_message})
    updated_history.append({"role": "assistant", "content": assistant_reply})
    audit.roe_chat_history = updated_history

    roe_finalized = False
    if scope:
        audit.scope_json = scope
        audit.status = "roe_agreed"
        roe_finalized = True

    await session.commit()

    return RoeChatResponse(
        audit_id=str(audit.id),
        assistant_message=assistant_reply,
        scope_json=scope,
        roe_finalized=roe_finalized,
    )


@router.get("/audits/{audit_id}", response_model=AuditStatusResponse)
async def get_audit_status(
    audit_id: str,
    session: AsyncSession = Depends(get_session),
) -> AuditStatusResponse:
    """Get the current status of a Sentinel audit."""
    result = await session.execute(
        select(SentinelAudit).where(
            SentinelAudit.id == uuid.UUID(audit_id)
        )
    )
    audit = result.scalar_one_or_none()
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    return AuditStatusResponse(
        audit_id=str(audit.id),
        status=audit.status,
        scope_json=audit.scope_json,
        container_id=audit.container_id,
        findings=audit.findings if isinstance(audit.findings, list) else [],
        report_url=audit.report_url,
        started_at=audit.started_at.isoformat() if audit.started_at else None,
        completed_at=audit.completed_at.isoformat() if audit.completed_at else None,
    )


@router.post("/audits/start", response_model=StartAuditResponse)
async def start_audit(
    req: StartAuditRequest,
    session: AsyncSession = Depends(get_session),
) -> StartAuditResponse:
    """Start a full Sentinel audit (after ROE is finalized)."""
    from app.sentinel.orchestrator import run_full_audit

    result = await session.execute(
        select(SentinelAudit).where(
            SentinelAudit.id == uuid.UUID(req.audit_id)
        )
    )
    audit = result.scalar_one_or_none()
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    if audit.status != "roe_agreed":
        raise HTTPException(
            status_code=400,
            detail=f"Audit must be in 'roe_agreed' state to start (current: {audit.status})",
        )

    # Launch the full audit pipeline as a background task
    task = asyncio.create_task(run_full_audit(str(audit.id)))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)

    return StartAuditResponse(
        audit_id=str(audit.id),
        status="provisioning",
        message="Sentinel audit started. Monitor via GET /api/sentinel/audits/{audit_id}",
    )


@router.post("/test-container", response_model=ContainerTestResponse)
async def test_container(
    req: ContainerTestRequest,
) -> ContainerTestResponse:
    """
    PoC endpoint: spin up a Kali container with the open-source arsenal.
    For testing the sandbox infrastructure only.
    """
    from app.sentinel.sandbox import create_sandbox, setup_arsenal

    audit_id = req.audit_id or str(uuid.uuid4())

    loop = asyncio.get_event_loop()
    try:
        container_id = await loop.run_in_executor(
            None, create_sandbox, audit_id, req.scope_json
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    try:
        arsenal_output = await loop.run_in_executor(
            None, setup_arsenal, container_id
        )
    except RuntimeError as e:
        raise HTTPException(
            status_code=500,
            detail=f"Arsenal setup failed: {e}",
        ) from e

    return ContainerTestResponse(
        container_id=container_id,
        status="ready",
        arsenal_output=arsenal_output[:2000],
    )


@router.delete("/containers/{container_id}")
async def destroy_container(container_id: str) -> dict[str, str]:
    """Tear down a Sentinel sandbox container."""
    from app.sentinel.sandbox import destroy_sandbox

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, destroy_sandbox, container_id)
    return {"status": "destroyed", "container_id": container_id}
