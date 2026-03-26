"""
CRM Stripe Webhooks Router
Keeps client billing status, commissions, and clawbacks in sync with Stripe events.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Request

from backend.services.supabase_crm import (
    supabase_available,
    get_supabase,
    get_client_by_stripe_id,
    update_client,
    insert_commission,
    log_activity,
    write_audit_log,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/crm/webhooks", tags=["crm-stripe"])

STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")
CLAWBACK_WINDOW_DAYS = int(os.getenv("CLAWBACK_WINDOW_DAYS", "90"))

PLAN_MRR = {"starter": 99, "shield": 199, "enterprise": 399}

# Map Stripe price metadata → plan names (configure in Stripe dashboard)
STRIPE_PRICE_TO_PLAN = {
    os.getenv("STRIPE_PRICE_STARTER", ""): "starter",
    os.getenv("STRIPE_PRICE_SHIELD", os.getenv("STRIPE_PRICE_PRO", "")): "shield",
    os.getenv("STRIPE_PRICE_ENTERPRISE", os.getenv("STRIPE_PRICE_AGENCY", "")): "enterprise",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _month_year() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _verify_signature(payload: bytes, sig_header: str) -> dict:
    """Verify Stripe webhook signature and return parsed event."""
    if STRIPE_WEBHOOK_SECRET:
        try:
            import stripe
            event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET)
            return dict(event)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Webhook signature invalid: {exc}") from exc
    # No secret configured — parse raw JSON (dev mode only)
    try:
        return json.loads(payload)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")


# ─── Main webhook endpoint ────────────────────────────────────────────────────

@router.post("/stripe")
async def stripe_crm_webhook(request: Request):
    """
    Stripe webhook receiver for CRM client lifecycle events.
    Separate from the billing router which handles subscription management for HAWK itself.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    event = _verify_signature(payload, sig_header)

    event_type: str = event.get("type", "")
    data: dict = event.get("data", {}).get("object", {})

    handlers = {
        "checkout.session.completed": _handle_checkout_completed,
        "invoice.payment_succeeded": _handle_payment_succeeded,
        "invoice.payment_failed": _handle_payment_failed,
        "customer.subscription.updated": _handle_subscription_updated,
        "customer.subscription.deleted": _handle_subscription_deleted,
    }

    handler = handlers.get(event_type)
    if handler:
        try:
            await handler(data)
        except Exception as exc:
            logger.error("CRM Stripe handler %s failed: %s", event_type, exc)
            # Return 200 to Stripe — log the failure, don't retry indefinitely
    else:
        logger.debug("CRM Stripe: unhandled event type %s", event_type)

    return {"received": True, "event_type": event_type}


# ─── Event handlers ───────────────────────────────────────────────────────────

async def _handle_checkout_completed(data: dict):
    """
    New HAWK client signed up via Stripe Checkout.
    - Creates client record (links to prospect via stripe_customer_id in metadata)
    - Logs close_won activity
    - Calculates and records closing commission
    - Sets 60/90-day clawback deadline
    """
    if not supabase_available():
        logger.warning("Supabase not configured — checkout.session.completed not persisted")
        return

    customer_id = data.get("customer")
    subscription_id = data.get("subscription")
    metadata = data.get("metadata", {})  # Set by frontend: prospect_id, rep_id, plan

    prospect_id = metadata.get("prospect_id")
    rep_id = metadata.get("rep_id")
    plan = metadata.get("plan", "starter")
    mrr = PLAN_MRR.get(plan, 99)

    now = _now()
    clawback_deadline = (
        datetime.now(timezone.utc) + timedelta(days=CLAWBACK_WINDOW_DAYS)
    ).isoformat()

    sb = get_supabase()

    # Create client record
    client_data = {
        "prospect_id": prospect_id,
        "plan": plan,
        "mrr": mrr,
        "stripe_customer_id": customer_id,
        "stripe_subscription_id": subscription_id,
        "closing_rep_id": rep_id,
        "status": "active",
        "close_date": now,
        "clawback_deadline": clawback_deadline,
        "churn_risk_score": "low",
    }
    res = sb.table("clients").insert(client_data).execute()
    if not res.data:
        logger.error("Failed to create client for customer %s", customer_id)
        return

    client = res.data[0]
    client_id = client["id"]

    # Log close_won activity on prospect
    if prospect_id:
        log_activity({
            "prospect_id": prospect_id,
            "client_id": client_id,
            "type": "close_won",
            "metadata": {
                "plan": plan,
                "mrr": mrr,
                "stripe_customer_id": customer_id,
            },
        })
        # Move prospect to closed_won stage
        sb.table("prospects").update({
            "stage": "closed_won",
            "last_activity_at": now,
        }).eq("id", prospect_id).execute()

    # Calculate closing commission (30% of first month for rep)
    if rep_id:
        closing_commission = round(mrr * 0.30, 2)
        insert_commission({
            "rep_id": rep_id,
            "type": "closing",
            "amount": closing_commission,
            "client_id": client_id,
            "month_year": _month_year(),
            "status": "pending",
        })
        logger.info(
            "Closing commission $%.2f calculated for rep %s on client %s",
            closing_commission, rep_id, client_id
        )

    write_audit_log({
        "action": "client_created",
        "record_type": "client",
        "record_id": client_id,
        "new_value": client_data,
    })
    logger.info("Client created for customer %s (plan: %s, MRR: $%s)", customer_id, plan, mrr)


async def _handle_payment_succeeded(data: dict):
    """Invoice paid — update billing status and calculate monthly residuals."""
    if not supabase_available():
        return

    customer_id = data.get("customer")
    client = get_client_by_stripe_id(customer_id)
    if not client:
        logger.warning("payment_succeeded: no client found for customer %s", customer_id)
        return

    update_client(client["id"], {"status": "active"})

    # Calculate residual commission for closing rep (10% of MRR monthly)
    closing_rep_id = client.get("closing_rep_id")
    mrr = client.get("mrr", 0)
    if closing_rep_id and mrr:
        residual = round(mrr * 0.10, 2)
        insert_commission({
            "rep_id": closing_rep_id,
            "type": "residual",
            "amount": residual,
            "client_id": client["id"],
            "month_year": _month_year(),
            "status": "pending",
        })
        logger.info("Residual commission $%.2f for rep %s", residual, closing_rep_id)


async def _handle_payment_failed(data: dict):
    """Invoice failed — set past_due, create urgent task."""
    if not supabase_available():
        return

    customer_id = data.get("customer")
    client = get_client_by_stripe_id(customer_id)
    if not client:
        return

    update_client(client["id"], {"status": "past_due"})

    # Log urgent activity for rep
    log_activity({
        "client_id": client["id"],
        "type": "note_added",
        "notes": "⚠️ Client payment failed — contact today to resolve billing.",
        "metadata": {"urgent": True, "type": "payment_failed"},
    })
    logger.warning("Payment failed for customer %s — client %s set to past_due", customer_id, client["id"])


async def _handle_subscription_updated(data: dict):
    """Plan upgrade/downgrade — update MRR and recalculate residuals."""
    if not supabase_available():
        return

    customer_id = data.get("customer")
    client = get_client_by_stripe_id(customer_id)
    if not client:
        return

    items = data.get("items", {}).get("data", [])
    if not items:
        return

    price_id = items[0].get("price", {}).get("id", "")
    new_plan = STRIPE_PRICE_TO_PLAN.get(price_id)
    new_mrr = items[0].get("price", {}).get("unit_amount", 0) / 100

    update_data: dict = {}
    if new_plan:
        update_data["plan"] = new_plan
    if new_mrr:
        update_data["mrr"] = new_mrr

    if update_data:
        update_client(client["id"], update_data)
        logger.info("Client %s plan updated: %s → $%.2f/mo", client["id"], new_plan, new_mrr)


async def _handle_subscription_deleted(data: dict):
    """Subscription cancelled — churn client, check clawback window."""
    if not supabase_available():
        return

    customer_id = data.get("customer")
    client = get_client_by_stripe_id(customer_id)
    if not client:
        return

    update_client(client["id"], {"status": "churned"})
    log_activity({
        "client_id": client["id"],
        "type": "stage_changed",
        "metadata": {"status": "churned"},
    })

    # Check clawback window
    clawback_deadline_str = client.get("clawback_deadline")
    if clawback_deadline_str and client.get("closing_rep_id"):
        try:
            deadline = datetime.fromisoformat(clawback_deadline_str.replace("Z", "+00:00"))
            if datetime.now(timezone.utc) <= deadline:
                mrr = client.get("mrr", 0)
                clawback_amount = round(mrr * 0.30, 2)
                insert_commission({
                    "rep_id": client["closing_rep_id"],
                    "type": "clawback",
                    "amount": -clawback_amount,  # Negative = deduction
                    "client_id": client["id"],
                    "month_year": _month_year(),
                    "status": "clawback",
                })
                logger.warning(
                    "Clawback $%.2f applied for rep %s (client churned within %d days)",
                    clawback_amount, client["closing_rep_id"], CLAWBACK_WINDOW_DAYS
                )
        except (ValueError, TypeError) as exc:
            logger.error("Clawback window parse error: %s", exc)

    write_audit_log({
        "action": "client_churned",
        "record_type": "client",
        "record_id": client["id"],
        "new_value": {"status": "churned", "stripe_customer_id": customer_id},
    })
    logger.info("Client %s marked as churned", client["id"])
