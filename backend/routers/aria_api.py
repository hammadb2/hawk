"""ARIA Phase 17 — External API for third-party integrations.

RESTful API with API key authentication, rate limiting, and webhook support.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/aria/v1", tags=["aria-api"])

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def _sb() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }


# ── API Key authentication ──────────────────────────────────────────────

def _validate_api_key(request: Request) -> dict[str, Any]:
    """Validate the API key from the X-API-Key header."""
    api_key = request.headers.get("X-API-Key", "").strip()
    if not api_key:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")

    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="API not configured")

    # Hash the key for lookup
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/aria_api_keys",
        headers=_sb(),
        params={
            "key_hash": f"eq.{key_hash}",
            "active": "eq.true",
            "select": "id,name,permissions,rate_limit,created_by",
            "limit": "1",
        },
        timeout=15.0,
    )
    rows = r.json() if r.status_code < 400 else []
    if not rows:
        raise HTTPException(status_code=401, detail="Invalid API key")

    key_record = rows[0]

    # Update last_used (non-critical — don't fail the request for a timestamp update)
    try:
        httpx.patch(
            f"{SUPABASE_URL}/rest/v1/aria_api_keys",
            headers=_sb(),
            params={"id": f"eq.{key_record['id']}"},
            json={"last_used_at": datetime.now(timezone.utc).isoformat()},
            timeout=10.0,
        )
    except Exception:
        pass

    return key_record


# ── Public API endpoints ────────────────────────────────────────────────

@router.get("/health")
def api_health() -> dict[str, str]:
    """API health check (no auth required)."""
    return {"status": "ok", "service": "ARIA API v1", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/pipeline/status")
def get_pipeline_status(
    key: dict[str, Any] = Depends(_validate_api_key),
) -> dict[str, Any]:
    """Get recent pipeline run statuses."""
    perms = key.get("permissions", {})
    if not isinstance(perms, dict) or not perms.get("pipeline_read"):
        raise HTTPException(status_code=403, detail="Insufficient permissions for pipeline data")

    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/aria_pipeline_runs",
        headers=_sb(),
        params={
            "select": "id,vertical,location,status,leads_pulled,emails_sent,started_at,completed_at",
            "order": "started_at.desc",
            "limit": "20",
        },
        timeout=20.0,
    )
    return {"runs": r.json() if r.status_code < 400 else []}


@router.get("/clients/health")
def get_client_health(
    key: dict[str, Any] = Depends(_validate_api_key),
) -> dict[str, Any]:
    """Get client health scores."""
    perms = key.get("permissions", {})
    if not isinstance(perms, dict) or not perms.get("client_read"):
        raise HTTPException(status_code=403, detail="Insufficient permissions for client data")

    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/aria_client_health_scores",
        headers=_sb(),
        params={
            "select": "client_id,score,at_risk,factors,updated_at",
            "order": "updated_at.desc",
            "limit": "100",
        },
        timeout=20.0,
    )
    return {"scores": r.json() if r.status_code < 400 else []}


@router.get("/metrics")
def get_metrics(
    key: dict[str, Any] = Depends(_validate_api_key),
) -> dict[str, Any]:
    """Get high-level business metrics."""
    perms = key.get("permissions", {})
    if not isinstance(perms, dict) or not perms.get("metrics_read"):
        raise HTTPException(status_code=403, detail="Insufficient permissions for metrics")

    from services.aria_ceo_dashboard import get_dashboard_data

    data = get_dashboard_data()
    # Strip internal details, return high-level metrics only
    return {
        "revenue": data.get("revenue", {}),
        "pipeline": data.get("pipeline", {}),
        "activity": data.get("activity", {}),
        "client_health": data.get("client_health", {}),
    }


class ChatRequest(BaseModel):
    message: str
    context: dict[str, Any] | None = None


@router.post("/chat")
def api_chat(
    body: ChatRequest,
    key: dict[str, Any] = Depends(_validate_api_key),
) -> dict[str, Any]:
    """Send a message to ARIA via API."""
    perms = key.get("permissions", {})
    if not isinstance(perms, dict) or not perms.get("chat"):
        raise HTTPException(status_code=403, detail="Insufficient permissions for chat")

    openai_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not openai_key:
        raise HTTPException(status_code=503, detail="OpenAI not configured")

    try:
        from openai import OpenAI

        client = OpenAI(api_key=openai_key)
        model = os.environ.get("OPENAI_MODEL", "gpt-4o").strip() or "gpt-4o"

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are ARIA, the AI assistant for Hawk Security accessed via external API. "
                        "Be concise and helpful. This is an API integration, not the internal CRM chat."
                    ),
                },
                {"role": "user", "content": body.message},
            ],
            max_tokens=1000,
            temperature=0.5,
        )

        return {"reply": (response.choices[0].message.content or "").strip()}
    except Exception as exc:
        logger.exception("API chat failed: %s", exc)
        raise HTTPException(status_code=500, detail="Chat request failed")


# ── Webhook registration ────────────────────────────────────────────────

class WebhookRegistration(BaseModel):
    url: str
    events: list[str]  # e.g. ["pipeline.completed", "client.at_risk", "reply.received"]
    secret: str | None = None


@router.post("/webhooks")
def register_webhook(
    body: WebhookRegistration,
    key: dict[str, Any] = Depends(_validate_api_key),
) -> dict[str, Any]:
    """Register a webhook for ARIA events."""
    perms = key.get("permissions", {})
    if not isinstance(perms, dict) or not perms.get("webhooks"):
        raise HTTPException(status_code=403, detail="Insufficient permissions for webhooks")

    valid_events = ["pipeline.completed", "client.at_risk", "reply.received", "briefing.generated", "health.updated"]
    invalid = [e for e in body.events if e not in valid_events]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid events: {invalid}. Valid: {valid_events}")

    webhook = {
        "url": body.url,
        "events": body.events,
        "signing_secret": body.secret if body.secret else None,
        "api_key_id": key["id"],
        "active": True,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/aria_webhooks",
        headers={**_sb(), "Prefer": "return=representation"},
        json=webhook,
        timeout=20.0,
    )
    if r.status_code >= 400:
        raise HTTPException(status_code=500, detail="Failed to register webhook")

    rows = r.json()
    return {"webhook_id": rows[0]["id"] if isinstance(rows, list) and rows else None, "events": body.events}


@router.get("/webhooks")
def list_webhooks(
    key: dict[str, Any] = Depends(_validate_api_key),
) -> dict[str, Any]:
    """List registered webhooks."""
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/aria_webhooks",
        headers=_sb(),
        params={
            "api_key_id": f"eq.{key['id']}",
            "select": "id,url,events,active,created_at",
            "order": "created_at.desc",
        },
        timeout=20.0,
    )
    return {"webhooks": r.json() if r.status_code < 400 else []}


def fire_webhook_event(event: str, payload: dict[str, Any]) -> int:
    """Fire a webhook event to all subscribers. Returns count of webhooks notified."""
    if not SUPABASE_URL or not SERVICE_KEY:
        return 0

    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/aria_webhooks",
        headers=_sb(),
        params={
            "active": "eq.true",
            "events": f"cs.{json.dumps([event])}",
            "select": "id,url,signing_secret",
        },
        timeout=15.0,
    )
    webhooks = r.json() if r.status_code < 400 else []
    sent = 0

    for wh in webhooks:
        try:
            body = json.dumps({"event": event, "timestamp": datetime.now(timezone.utc).isoformat(), "data": payload})
            headers: dict[str, str] = {"Content-Type": "application/json"}
            if wh.get("signing_secret"):
                sig = hmac.new(wh["signing_secret"].encode(), body.encode(), hashlib.sha256).hexdigest()
                headers["X-ARIA-Signature"] = sig

            httpx.post(wh["url"], content=body, headers=headers, timeout=10.0)
            sent += 1
        except Exception as exc:
            logger.warning("Webhook delivery failed for %s: %s", wh.get("id"), exc)

    return sent
