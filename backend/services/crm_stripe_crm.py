"""Stripe: verify recent payment for CRM close-won; fulfill deferred commissions from webhooks."""

from __future__ import annotations

import logging
import os
import time
from typing import Any

logger = logging.getLogger(__name__)

STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "").strip()


def _stripe():
    if not STRIPE_SECRET_KEY:
        return None
    try:
        import stripe

        stripe.api_key = STRIPE_SECRET_KEY
        return stripe
    except ImportError:
        return None


def verify_payment_recent(
    *,
    domain: str,
    mrr_cents: int,
    stripe_customer_id: str | None,
) -> bool:
    """
    True if checkout.session.completed or invoice.payment_succeeded in the last 24h
    matches this deal (customer id and/or email domain vs prospect domain).
    """
    s = _stripe()
    if not s:
        return False

    domain_l = domain.strip().lower()
    now = int(time.time())
    since = now - 86400

    try:
        events = s.Event.list(limit=100, types=["checkout.session.completed", "invoice.payment_succeeded"])
    except Exception as e:
        logger.exception("stripe event list failed: %s", e)
        return False

    for ev in events.data:
        if getattr(ev, "created", 0) < since:
            continue
        obj = ev.data.object
        if not obj:
            continue
        cust_id = getattr(obj, "customer", None)
        if stripe_customer_id and cust_id and cust_id == stripe_customer_id:
            amt = _amount_cents_from_obj(ev.type, obj)
            if amt and abs(amt - mrr_cents) <= max(500, int(mrr_cents * 0.15)):
                return True
            if not amt:
                return True

        # Match by customer email domain
        email = _extract_customer_email(s, getattr(obj, "customer", None))
        if email and domain_l and email.split("@")[-1].lower() == domain_l:
            amt = _amount_cents_from_obj(ev.type, obj)
            if amt and abs(amt - mrr_cents) <= max(500, int(mrr_cents * 0.15)):
                return True
            if not amt:
                return True

        md = getattr(obj, "metadata", None) or {}
        if isinstance(md, dict) and md.get("crm_domain", "").lower() == domain_l:
            return True

    return False


def _amount_cents_from_obj(event_type: str, obj: Any) -> int | None:
    try:
        if event_type == "checkout.session.completed":
            return int(getattr(obj, "amount_total", None) or 0) or None
        if event_type == "invoice.payment_succeeded":
            return int(getattr(obj, "amount_paid", None) or 0) or None
    except (TypeError, ValueError):
        return None
    return None


def _extract_customer_email(stripe_mod: Any, customer_id: str | None) -> str | None:
    if not customer_id or not isinstance(customer_id, str):
        return None
    try:
        c = stripe_mod.Customer.retrieve(customer_id)
        return (getattr(c, "email", None) or "").strip().lower() or None
    except Exception:
        return None


def fulfill_deferred_commission_for_stripe_event(event: dict) -> bool:
    """
    If Stripe event indicates a paid invoice/session, create crm_commissions row for matching
    clients with commission_deferred=true. Returns True if at least one row was written.
    """
    import httpx

    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not supabase_url or not key:
        return False

    et = event.get("type")
    obj = (event.get("data") or {}).get("object") or {}
    if et not in ("checkout.session.completed", "invoice.payment_succeeded"):
        return False

    customer_id = obj.get("customer")
    if isinstance(customer_id, dict):
        customer_id = customer_id.get("id")
    if not customer_id:
        return False

    email = _extract_customer_email(_stripe(), customer_id)
    domain_from_email = email.split("@")[-1].lower() if email and "@" in email else None
    meta = obj.get("metadata") or {}
    meta_domain = (meta.get("crm_domain") or meta.get("domain") or "").strip().lower() or None
    target_domain = meta_domain or domain_from_email
    if not target_domain:
        return False

    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=30.0) as client:
        r = client.get(
            f"{supabase_url}/rest/v1/clients",
            headers=headers,
            params={
                "commission_deferred": "eq.true",
                "domain": f"eq.{target_domain}",
                "select": "id,closing_rep_id,mrr_cents",
            },
        )
        r.raise_for_status()
        rows = r.json()
        if not rows:
            # try ilike company match — skip for v1
            return False

        did = False
        for row in rows:
            cid = row["id"]
            rep = row["closing_rep_id"]
            mrr = int(row["mrr_cents"])
            if not rep:
                continue
            chk = client.get(
                f"{supabase_url}/rest/v1/crm_commissions",
                headers=headers,
                params={"client_id": f"eq.{cid}", "select": "id", "limit": "1"},
                timeout=20.0,
            )
            chk.raise_for_status()
            if chk.json():
                client.patch(
                    f"{supabase_url}/rest/v1/clients",
                    headers=headers,
                    params={"id": f"eq.{cid}"},
                    json={"commission_deferred": False},
                    timeout=20.0,
                )
                did = True
                continue
            amt = (mrr * 30) // 100
            ins = client.post(
                f"{supabase_url}/rest/v1/crm_commissions",
                headers=headers,
                json={
                    "client_id": cid,
                    "rep_id": rep,
                    "basis_mrr_cents": mrr,
                    "amount_cents": amt,
                    "rate": 0.30,
                    "status": "pending",
                },
                timeout=20.0,
            )
            if ins.status_code not in (200, 201):
                logger.warning("commission insert failed: %s %s", ins.status_code, ins.text)
                continue
            patch = client.patch(
                f"{supabase_url}/rest/v1/clients",
                headers=headers,
                params={"id": f"eq.{cid}"},
                json={"commission_deferred": False},
                timeout=20.0,
            )
            patch.raise_for_status()
            did = True
        return did
