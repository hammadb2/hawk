"""
Supabase service client for CRM backend operations.

Used by CRM webhook handlers (Smartlead, Stripe) and complex business logic
endpoints that need server-side DB access with the service role key.

Simple CRUD operations go through the frontend Supabase JS client (RLS enforced).
This backend client uses the service role key and bypasses RLS intentionally —
only used where the operation is legitimately server-side (webhooks, commission calc).
"""
from __future__ import annotations

import os
import logging
from functools import lru_cache
from typing import Optional

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")


@lru_cache(maxsize=1)
def get_supabase():
    """
    Returns a Supabase client with service role privileges.
    Cached — only one instance per process.
    Raises RuntimeError if env vars are not configured.
    """
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set for CRM backend operations."
        )
    try:
        from supabase import create_client, Client
        client: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
        return client
    except ImportError:
        raise RuntimeError("supabase package not installed. Run: pip install supabase>=2.7.0")


def supabase_available() -> bool:
    """Check if Supabase is configured without raising."""
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


# ─── Prospect helpers ─────────────────────────────────────────────────────────

def get_prospect_by_domain(domain: str) -> Optional[dict]:
    """Look up a prospect by domain. Returns first match or None."""
    try:
        sb = get_supabase()
        res = sb.table("prospects").select("*").eq("domain", domain).limit(1).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        logger.error("get_prospect_by_domain error: %s", e)
        return None


def create_prospect(data: dict) -> Optional[dict]:
    """Create a new prospect. Returns the created record or None."""
    try:
        sb = get_supabase()
        res = sb.table("prospects").insert(data).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        logger.error("create_prospect error: %s", e)
        return None


def update_prospect(prospect_id: str, updates: dict) -> Optional[dict]:
    """Update a prospect by ID."""
    try:
        sb = get_supabase()
        res = sb.table("prospects").update(updates).eq("id", prospect_id).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        logger.error("update_prospect error: %s", e)
        return None


# ─── Email event helpers ──────────────────────────────────────────────────────

def upsert_email_event(prospect_id: str, event_data: dict) -> Optional[dict]:
    """Insert or update an email_events record."""
    try:
        sb = get_supabase()
        res = sb.table("email_events").insert(
            {"prospect_id": prospect_id, **event_data}
        ).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        logger.error("upsert_email_event error: %s", e)
        return None


def update_email_event_by_prospect(prospect_id: str, updates: dict) -> None:
    """Update the latest email event for a prospect."""
    try:
        sb = get_supabase()
        # Get the latest email event for this prospect
        res = (
            sb.table("email_events")
            .select("id")
            .eq("prospect_id", prospect_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        if res.data:
            sb.table("email_events").update(updates).eq("id", res.data[0]["id"]).execute()
    except Exception as e:
        logger.error("update_email_event_by_prospect error: %s", e)


# ─── Activity helpers ─────────────────────────────────────────────────────────

def log_activity(activity_data: dict) -> Optional[dict]:
    """Create an activity record."""
    try:
        sb = get_supabase()
        res = sb.table("activities").insert(activity_data).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        logger.error("log_activity error: %s", e)
        return None


# ─── Suppression helpers ──────────────────────────────────────────────────────

def add_to_suppression_list(domain: str, email: str, reason: str) -> None:
    """Add a domain/email to the suppression list."""
    try:
        sb = get_supabase()
        sb.table("suppressions").insert({
            "domain": domain,
            "email": email,
            "reason": reason,
        }).execute()
    except Exception as e:
        logger.error("add_to_suppression_list error: %s", e)


def is_suppressed(domain: str) -> bool:
    """Check if a domain is on the suppression list."""
    try:
        sb = get_supabase()
        res = (
            sb.table("suppressions")
            .select("id")
            .eq("domain", domain)
            .limit(1)
            .execute()
        )
        return len(res.data) > 0
    except Exception as e:
        logger.error("is_suppressed error: %s", e)
        return False


# ─── Client helpers ───────────────────────────────────────────────────────────

def create_client_record(data: dict) -> Optional[dict]:
    """Create a new client record (called on Stripe checkout.session.completed)."""
    try:
        sb = get_supabase()
        res = sb.table("clients").insert(data).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        logger.error("create_client_record error: %s", e)
        return None


def get_client_by_stripe_id(stripe_customer_id: str) -> Optional[dict]:
    """Look up a client by Stripe customer ID."""
    try:
        sb = get_supabase()
        res = (
            sb.table("clients")
            .select("*")
            .eq("stripe_customer_id", stripe_customer_id)
            .limit(1)
            .execute()
        )
        return res.data[0] if res.data else None
    except Exception as e:
        logger.error("get_client_by_stripe_id error: %s", e)
        return None


def update_client(client_id: str, updates: dict) -> Optional[dict]:
    """Update a client record."""
    try:
        sb = get_supabase()
        res = sb.table("clients").update(updates).eq("id", client_id).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        logger.error("update_client error: %s", e)
        return None


# ─── Commission helpers ───────────────────────────────────────────────────────

def insert_commission(data: dict) -> Optional[dict]:
    """Insert a commission record."""
    try:
        sb = get_supabase()
        res = sb.table("commissions").insert(data).execute()
        return res.data[0] if res.data else None
    except Exception as e:
        logger.error("insert_commission error: %s", e)
        return None


def get_rep_role(rep_id: str) -> Optional[str]:
    """Get a user's role by ID."""
    try:
        sb = get_supabase()
        res = sb.table("users").select("role").eq("id", rep_id).single().execute()
        return res.data.get("role") if res.data else None
    except Exception as e:
        logger.error("get_rep_role error: %s", e)
        return None


# ─── Audit log ────────────────────────────────────────────────────────────────

def write_audit_log(entry: dict) -> None:
    """Write an immutable audit log entry (server-side only)."""
    try:
        sb = get_supabase()
        sb.table("audit_log").insert(entry).execute()
    except Exception as e:
        logger.error("write_audit_log error: %s", e)
