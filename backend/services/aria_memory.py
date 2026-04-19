"""ARIA Phase 4 — Semantic memory ingestion and retrieval.

Ingests significant CRM events (prospect stage changes, client onboarding,
scans, emails, deals, notes) into aria_memories with pgvector embeddings.
Provides semantic search for ARIA context injection.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from services.aria_embedding import (
    format_embedding_for_pgvector,
    get_embedding,
    get_embeddings_batch,
)

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def _sb() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }


# ---------------------------------------------------------------------------
# Event ingestion helpers
# ---------------------------------------------------------------------------

def _already_ingested(headers: dict[str, str], event_id: str) -> bool:
    """Check if an event has already been stored in aria_memories."""
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/aria_memories",
        headers=headers,
        params={"event_id": f"eq.{event_id}", "select": "id", "limit": "1"},
        timeout=10.0,
    )
    return bool(r.status_code < 400 and r.json())


def _store_memory(
    headers: dict[str, str],
    *,
    event_type: str,
    event_id: str | None,
    source_table: str,
    actor_id: str | None,
    subject_id: str | None,
    subject_type: str | None,
    summary: str,
    detail: str,
    metadata: dict[str, Any],
    embedding: list[float] | None,
) -> bool:
    """Insert a single memory row into aria_memories."""
    payload: dict[str, Any] = {
        "event_type": event_type,
        "event_id": event_id,
        "source_table": source_table,
        "actor_id": actor_id,
        "subject_id": subject_id,
        "subject_type": subject_type,
        "summary": summary,
        "detail": detail,
        "metadata": metadata,
    }
    if embedding:
        payload["embedding"] = format_embedding_for_pgvector(embedding)

    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/aria_memories",
        headers={**headers, "Prefer": "return=minimal"},
        json=payload,
        timeout=15.0,
    )
    if r.status_code >= 400:
        logger.warning("memory store failed: %s", r.text[:300])
        return False
    return True


# ---------------------------------------------------------------------------
# Event collectors — each returns a list of (summary, detail, metadata) tuples
# ---------------------------------------------------------------------------

def _collect_activities(headers: dict[str, str], since: str) -> list[dict[str, Any]]:
    """Collect recent CRM activities (stage changes, notes, emails)."""
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/activities",
        headers=headers,
        params={
            "select": "id,type,prospect_id,client_id,user_id,description,created_at",
            "created_at": f"gte.{since}",
            "order": "created_at.desc",
            "limit": "200",
        },
        timeout=30.0,
    )
    if r.status_code >= 400:
        return []
    return r.json() or []


def _collect_prospect_changes(headers: dict[str, str], since: str) -> list[dict[str, Any]]:
    """Collect prospects updated recently (stage changes, new prospects)."""
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/prospects",
        headers=headers,
        params={
            "select": "id,company_name,domain,stage,email,hawk_score,updated_at",
            "updated_at": f"gte.{since}",
            "order": "updated_at.desc",
            "limit": "200",
        },
        timeout=30.0,
    )
    if r.status_code >= 400:
        return []
    return r.json() or []


def _collect_client_events(headers: dict[str, str], since: str) -> list[dict[str, Any]]:
    """Collect recent client updates (new clients, status changes)."""
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/clients",
        headers=headers,
        params={
            "select": "id,company_name,domain,plan,mrr_cents,status,updated_at",
            "updated_at": f"gte.{since}",
            "order": "updated_at.desc",
            "limit": "100",
        },
        timeout=30.0,
    )
    if r.status_code >= 400:
        return []
    return r.json() or []


def _collect_scan_events(headers: dict[str, str], since: str) -> list[dict[str, Any]]:
    """Collect recent prospect scans."""
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/prospect_scans",
        headers=headers,
        params={
            "select": "id,prospect_id,domain,hawk_score,critical,high,medium,low,created_at",
            "created_at": f"gte.{since}",
            "order": "created_at.desc",
            "limit": "100",
        },
        timeout=30.0,
    )
    if r.status_code >= 400:
        return []
    return r.json() or []


# ---------------------------------------------------------------------------
# Build memory records from raw events
# ---------------------------------------------------------------------------

def _build_activity_memories(activities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Transform activities into memory records."""
    memories: list[dict[str, Any]] = []
    for act in activities:
        event_id = f"activity-{act.get('id', '')}"
        act_type = act.get("type", "unknown")
        desc = act.get("description", "") or ""

        summary = f"Activity: {act_type}"
        if desc:
            summary = f"{act_type}: {desc[:120]}"

        detail = f"CRM activity of type '{act_type}'"
        if act.get("prospect_id"):
            detail += f" on prospect {act['prospect_id']}"
        if act.get("client_id"):
            detail += f" on client {act['client_id']}"
        if desc:
            detail += f". {desc}"

        memories.append({
            "event_type": f"activity_{act_type}",
            "event_id": event_id,
            "source_table": "activities",
            "actor_id": act.get("user_id"),
            "subject_id": act.get("prospect_id") or act.get("client_id"),
            "subject_type": "prospect" if act.get("prospect_id") else "client" if act.get("client_id") else None,
            "summary": summary,
            "detail": detail,
            "metadata": {"activity_type": act_type, "created_at": act.get("created_at")},
        })
    return memories


def _build_prospect_memories(prospects: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Transform prospect updates into memory records."""
    memories: list[dict[str, Any]] = []
    for p in prospects:
        event_id = f"prospect-update-{p.get('id', '')}-{p.get('updated_at', '')}"
        company = p.get("company_name") or p.get("domain") or "Unknown"
        stage = p.get("stage", "unknown")
        hawk_score = p.get("hawk_score")

        summary = f"Prospect {company} is at stage '{stage}'"
        if hawk_score is not None:
            summary += f" with hawk score {hawk_score}"

        detail = f"Prospect {company} (domain: {p.get('domain', 'N/A')}) "
        detail += f"is in pipeline stage '{stage}'. "
        if hawk_score is not None:
            detail += f"Hawk security score: {hawk_score}/100. "
        if p.get("email"):
            detail += f"Contact email: {p['email']}. "

        memories.append({
            "event_type": "prospect_update",
            "event_id": event_id,
            "source_table": "prospects",
            "actor_id": None,
            "subject_id": p.get("id"),
            "subject_type": "prospect",
            "summary": summary,
            "detail": detail,
            "metadata": {"stage": stage, "hawk_score": hawk_score, "company": company},
        })
    return memories


def _build_client_memories(clients: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Transform client updates into memory records."""
    memories: list[dict[str, Any]] = []
    for c in clients:
        event_id = f"client-update-{c.get('id', '')}-{c.get('updated_at', '')}"
        company = c.get("company_name") or c.get("domain") or "Unknown"
        plan = c.get("plan", "unknown")
        mrr = (c.get("mrr_cents", 0) or 0) / 100
        status = c.get("status", "unknown")

        summary = f"Client {company} on {plan} plan (${mrr:,.0f}/mo) — status: {status}"

        detail = f"Client {company} (domain: {c.get('domain', 'N/A')}) "
        detail += f"is on the {plan} plan at ${mrr:,.0f}/mo MRR. "
        detail += f"Current status: {status}."

        memories.append({
            "event_type": "client_update",
            "event_id": event_id,
            "source_table": "clients",
            "actor_id": None,
            "subject_id": c.get("id"),
            "subject_type": "client",
            "summary": summary,
            "detail": detail,
            "metadata": {"plan": plan, "mrr_cents": c.get("mrr_cents"), "status": status, "company": company},
        })
    return memories


def _build_scan_memories(scans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Transform scan results into memory records."""
    memories: list[dict[str, Any]] = []
    for s in scans:
        event_id = f"scan-{s.get('id', '')}"
        domain = s.get("domain", "unknown")
        score = s.get("hawk_score", 0) or 0
        crit = s.get("critical", 0) or 0
        high = s.get("high", 0) or 0
        med = s.get("medium", 0) or 0
        low = s.get("low", 0) or 0

        summary = f"Security scan on {domain}: score {score}/100, {crit}C/{high}H/{med}M/{low}L findings"

        detail = f"Hawk security scan completed for domain {domain}. "
        detail += f"Overall hawk score: {score}/100. "
        detail += f"Findings: {crit} critical, {high} high, {med} medium, {low} low."

        memories.append({
            "event_type": "scan_completed",
            "event_id": event_id,
            "source_table": "prospect_scans",
            "actor_id": None,
            "subject_id": s.get("prospect_id"),
            "subject_type": "prospect",
            "summary": summary,
            "detail": detail,
            "metadata": {
                "domain": domain,
                "hawk_score": score,
                "critical": crit,
                "high": high,
                "medium": med,
                "low": low,
            },
        })
    return memories


# ---------------------------------------------------------------------------
# Main ingestion function (called by cron)
# ---------------------------------------------------------------------------

def run_memory_ingestion(lookback_minutes: int = 20) -> dict[str, Any]:
    """Ingest recent CRM events into aria_memories with embeddings.

    Called every 15 minutes by cron. Looks back *lookback_minutes* to
    catch events since the last run (with overlap buffer).
    """
    if not SUPABASE_URL or not SERVICE_KEY:
        return {"ok": False, "error": "supabase not configured"}

    headers = _sb()
    since = (datetime.now(timezone.utc) - timedelta(minutes=lookback_minutes)).isoformat()

    # Collect events from various sources
    activities = _collect_activities(headers, since)
    prospects = _collect_prospect_changes(headers, since)
    clients = _collect_client_events(headers, since)
    scans = _collect_scan_events(headers, since)

    # Build memory records
    all_memories: list[dict[str, Any]] = []
    all_memories.extend(_build_activity_memories(activities))
    all_memories.extend(_build_prospect_memories(prospects))
    all_memories.extend(_build_client_memories(clients))
    all_memories.extend(_build_scan_memories(scans))

    if not all_memories:
        return {"ok": True, "ingested": 0, "skipped": 0, "message": "no new events"}

    # Dedup — skip events already ingested
    new_memories: list[dict[str, Any]] = []
    skipped = 0
    for mem in all_memories:
        eid = mem.get("event_id")
        if eid and _already_ingested(headers, eid):
            skipped += 1
            continue
        new_memories.append(mem)

    if not new_memories:
        return {"ok": True, "ingested": 0, "skipped": skipped, "message": "all events already ingested"}

    # Generate embeddings in batch
    texts_to_embed = [f"{m['summary']}\n{m['detail']}" for m in new_memories]
    embeddings = get_embeddings_batch(texts_to_embed)

    # Store each memory (skip if embedding is None — will retry next cron run)
    ingested = 0
    embed_failures = 0
    for mem, emb in zip(new_memories, embeddings):
        if emb is None:
            embed_failures += 1
            continue
        ok = _store_memory(
            headers,
            event_type=mem["event_type"],
            event_id=mem.get("event_id"),
            source_table=mem["source_table"],
            actor_id=mem.get("actor_id"),
            subject_id=mem.get("subject_id"),
            subject_type=mem.get("subject_type"),
            summary=mem["summary"],
            detail=mem["detail"],
            metadata=mem.get("metadata", {}),
            embedding=emb,
        )
        if ok:
            ingested += 1

    if embed_failures:
        logger.warning("memory ingestion: %d events skipped due to embedding failures (will retry)", embed_failures)

    return {
        "ok": True,
        "ingested": ingested,
        "skipped": skipped,
        "embed_failures": embed_failures,
        "total_events": len(all_memories),
    }


# ---------------------------------------------------------------------------
# Semantic retrieval (called during ARIA chat)
# ---------------------------------------------------------------------------

def search_memories(
    query: str,
    *,
    match_count: int = 8,
    similarity_threshold: float = 0.7,
    filter_event_type: str | None = None,
    filter_subject_type: str | None = None,
    filter_subject_id: str | None = None,
) -> list[dict[str, Any]]:
    """Search aria_memories semantically using pgvector cosine similarity.

    Uses the Supabase RPC function `aria_memory_search` defined in the migration.
    Returns a list of matching memory records sorted by relevance.
    """
    if not SUPABASE_URL or not SERVICE_KEY:
        return []

    embedding = get_embedding(query)
    if not embedding:
        return []

    headers = _sb()
    rpc_params: dict[str, Any] = {
        "query_embedding": format_embedding_for_pgvector(embedding),
        "match_count": match_count,
        "similarity_threshold": similarity_threshold,
    }
    if filter_event_type:
        rpc_params["filter_event_type"] = filter_event_type
    if filter_subject_type:
        rpc_params["filter_subject_type"] = filter_subject_type
    if filter_subject_id:
        rpc_params["filter_subject_id"] = filter_subject_id

    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/rpc/aria_memory_search",
        headers=headers,
        json=rpc_params,
        timeout=20.0,
    )
    if r.status_code >= 400:
        logger.warning("memory search failed: %s", r.text[:300])
        return []

    return r.json() or []


def build_memory_context(query: str, max_tokens_budget: int = 1500) -> str:
    """Build a context string from relevant memories for injection into ARIA's system prompt.

    Retrieves semantically similar memories and formats them as a concise
    context block that ARIA can reference when responding.
    """
    memories = search_memories(query, match_count=8, similarity_threshold=0.65)
    if not memories:
        return ""

    lines: list[str] = ["RELEVANT CONTEXT FROM CRM MEMORY:"]
    char_budget = max_tokens_budget * 4  # rough chars-per-token estimate

    for mem in memories:
        line = f"- [{mem.get('event_type', '')}] {mem.get('summary', '')}"
        detail = mem.get("detail", "")
        if detail and len(line) + len(detail) < 300:
            line += f" | {detail}"
        lines.append(line)
        char_budget -= len(line)
        if char_budget <= 0:
            break

    return "\n".join(lines)
