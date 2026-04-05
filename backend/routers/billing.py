from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import User
from schemas import CheckoutRequest, PublicCheckoutRequest
import logging

from config import (
    STRIPE_SECRET_KEY,
    STRIPE_SECRET_KEY_TEST,
    STRIPE_WEBHOOK_SECRET,
    STRIPE_WEBHOOK_SECRET_TEST,
    STRIPE_PRICE_STARTER,
    STRIPE_PRICE_STARTER_TEST,
    STRIPE_PRICE_PRO,
    STRIPE_PRICE_AGENCY,
    STRIPE_PRICE_SHIELD,
    STRIPE_PRICE_SHIELD_TEST,
    BASE_URL,
    DEFAULT_PUBLIC_SITE_URL,
)

logger = logging.getLogger(__name__)


def _stripe_event_to_dict(event) -> dict:
    """Stripe SDK returns StripeObject; CRM helpers expect plain dicts."""
    if isinstance(event, dict):
        return event
    to_d = getattr(event, "to_dict", None)
    if callable(to_d):
        return to_d()
    try:
        return dict(event)
    except Exception:
        return {"type": getattr(event, "type", None), "data": getattr(event, "data", None)}

# Map Stripe price ID -> plan name for webhook
def _plan_from_subscription(sub) -> str | None:
    items = sub.get("items") or {}
    data = items.get("data") or []
    if not data:
        return None
    price = data[0].get("price") or {}
    pid = price.get("id")
    if pid == STRIPE_PRICE_STARTER or (STRIPE_PRICE_STARTER_TEST and pid == STRIPE_PRICE_STARTER_TEST):
        return "starter"
    if pid == STRIPE_PRICE_PRO:
        return "pro"
    if pid == STRIPE_PRICE_AGENCY:
        return "agency"
    return None

router = APIRouter(prefix="/api/billing", tags=["billing"])

# Public marketing checkout (no JWT) — success/cancel on securedbyhawk.com
_SITE = BASE_URL or DEFAULT_PUBLIC_SITE_URL

stripe = None


def _stripe():
    global stripe
    if stripe is None:
        try:
            import stripe as s
            stripe = s
            stripe.api_key = STRIPE_SECRET_KEY
        except ImportError:
            pass
    return stripe


def _checkout_public_session_url(
    *,
    api_key: str,
    price_id: str,
    hawk_product: str,
    site: str,
    extra_meta: dict[str, str] | None = None,
) -> str:
    """Create a Stripe Checkout Session; StripeClient isolates live vs test API keys (SDK v8+)."""
    from stripe import StripeClient

    meta: dict[str, str] = {"hawk_product": hawk_product}
    sub_meta: dict[str, str] = {"hawk_product": hawk_product}
    if extra_meta:
        meta.update(extra_meta)
        sub_meta.update(extra_meta)
    success_url = f"{site}/portal?welcome=1"
    if extra_meta and extra_meta.get("hawk_checkout_mode") == "test":
        success_url = f"{site}/portal?welcome=1&test_checkout=1"
    cancel_url = f"{site}/#pricing"
    client = StripeClient(api_key)
    session = client.v1.checkout.sessions.create(
        {
            "mode": "subscription",
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata": meta,
            "subscription_data": {"metadata": sub_meta},
            "allow_promotion_codes": True,
        }
    )
    return session.url


@router.post("/checkout-public")
def checkout_public(req: PublicCheckoutRequest):
    """Stripe Checkout for homepage pricing — no account. Metadata hawk_product for webhook (live mode)."""
    s = _stripe()
    if not s or not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Billing not configured")
    if req.hawk_product == "starter":
        price_id = STRIPE_PRICE_STARTER
    else:
        price_id = STRIPE_PRICE_SHIELD
    if not price_id:
        raise HTTPException(status_code=503, detail="Shield price not configured")
    hp = req.hawk_product
    site = _SITE.rstrip("/")
    try:
        url = _checkout_public_session_url(api_key=STRIPE_SECRET_KEY, price_id=price_id, hawk_product=hp, site=site)
    except Exception as e:
        logger.exception("checkout-public Stripe error")
        raise HTTPException(status_code=502, detail=str(e)[:200]) from e
    return {"url": url}


@router.post("/checkout-public-test")
def checkout_public_test(req: PublicCheckoutRequest):
    """
    Same as checkout-public but uses Stripe test API key and test price IDs.
    Configure STRIPE_SECRET_KEY_TEST, STRIPE_PRICE_STARTER_TEST, STRIPE_PRICE_SHIELD_TEST (Dashboard test mode).
    Webhook: add a test-mode endpoint in Stripe pointing to the same URL, or use STRIPE_WEBHOOK_SECRET_TEST
    with stripe listen / Stripe CLI.
    """
    s = _stripe()
    if not s:
        raise HTTPException(status_code=503, detail="Stripe SDK not available")
    if not STRIPE_SECRET_KEY_TEST:
        raise HTTPException(status_code=503, detail="Test checkout not configured (STRIPE_SECRET_KEY_TEST)")
    if req.hawk_product == "starter":
        price_id = STRIPE_PRICE_STARTER_TEST
    else:
        price_id = STRIPE_PRICE_SHIELD_TEST
    if not price_id:
        raise HTTPException(
            status_code=503,
            detail="Test price IDs not configured (STRIPE_PRICE_STARTER_TEST / STRIPE_PRICE_SHIELD_TEST)",
        )
    hp = req.hawk_product
    site = _SITE.rstrip("/")
    extra = {"hawk_checkout_mode": "test"}
    try:
        url = _checkout_public_session_url(
            api_key=STRIPE_SECRET_KEY_TEST,
            price_id=price_id,
            hawk_product=hp,
            site=site,
            extra_meta=extra,
        )
    except Exception as e:
        logger.exception("checkout-public-test Stripe error")
        raise HTTPException(status_code=502, detail=str(e)[:200]) from e
    return {"url": url, "mode": "test"}


@router.post("/checkout")
def checkout(
    req: CheckoutRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    s = _stripe()
    if not s or not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Billing not configured")
    price_map = {"starter": STRIPE_PRICE_STARTER, "pro": STRIPE_PRICE_PRO, "agency": STRIPE_PRICE_AGENCY}
    price_id = price_map.get(req.plan)
    if not price_id:
        raise HTTPException(status_code=400, detail="Invalid plan")
    customer_id = user.stripe_customer_id
    if not customer_id:
        cust = s.Customer.create(email=user.email, name=f"{user.first_name or ''} {user.last_name or ''}".strip() or None)
        customer_id = cust.id
        user.stripe_customer_id = customer_id
        db.commit()
    session = s.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{BASE_URL}/dashboard/settings?billing=success",
        cancel_url=f"{BASE_URL}/dashboard/settings?billing=cancel",
        metadata={"user_id": user.id, "plan": req.plan},
    )
    return {"url": session.url}


@router.post("/portal")
def portal(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    s = _stripe()
    if not s or not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Billing not configured")
    if not user.stripe_customer_id:
        raise HTTPException(status_code=400, detail="No billing account")
    session = s.billing_portal.Session.create(
        customer=user.stripe_customer_id,
        return_url=f"{BASE_URL}/dashboard/settings",
    )
    return {"url": session.url}


@router.post("/webhook")
async def webhook(
    request: Request,
    stripe_signature: str | None = Header(None, alias="Stripe-Signature"),
    db: Session = Depends(get_db),
):
    if not STRIPE_WEBHOOK_SECRET and not STRIPE_WEBHOOK_SECRET_TEST:
        raise HTTPException(status_code=503, detail="Webhook not configured (live and/or test signing secret)")
    payload = await request.body()
    s = _stripe()
    if not s:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    event = None
    last_err: Exception | None = None
    for secret in (STRIPE_WEBHOOK_SECRET, STRIPE_WEBHOOK_SECRET_TEST):
        if not (secret or "").strip():
            continue
        try:
            event = s.Webhook.construct_event(payload, stripe_signature or "", secret)
            break
        except Exception as e:
            last_err = e
    if event is None:
        raise HTTPException(
            status_code=400,
            detail=f"Webhook signature invalid (neither live nor test secret matched): {last_err}",
        ) from last_err
    if event["type"] == "customer.subscription.updated":
        sub = event["data"]["object"]
        cust_id = sub.get("customer")
        user = db.query(User).filter(User.stripe_customer_id == cust_id).first()
        if user:
            user.stripe_subscription_id = sub.get("id")
            plan = _plan_from_subscription(sub)
            if plan:
                user.plan = plan
            db.commit()
    elif event["type"] == "customer.subscription.deleted":
        sub = event["data"]["object"]
        user = db.query(User).filter(User.stripe_customer_id == sub.get("customer")).first()
        if user:
            user.stripe_subscription_id = None
            user.plan = "starter"
            db.commit()
    elif event["type"] == "checkout.session.completed":
        evd = _stripe_event_to_dict(event)
        # CRM Shield Day 0: portal, deep scan, WhatsApp, Resend — see services.crm_portal_stripe
        try:
            from services.crm_portal_stripe import provision_portal_from_checkout

            provision_portal_from_checkout(evd)
        except Exception:
            logger.exception("checkout.session.completed CRM provision failed")
        try:
            from services.crm_stripe_crm import fulfill_deferred_commission_for_stripe_event

            fulfill_deferred_commission_for_stripe_event(evd)
        except Exception:
            logger.exception("checkout.session.completed commission fulfill failed")
    return {"received": True}


@router.get("/invoices")
def invoices(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    s = _stripe()
    if not s or not user.stripe_customer_id:
        return {"invoices": []}
    invs = s.Invoice.list(customer=user.stripe_customer_id, limit=10)
    out = []
    for i in invs.get("data", []):
        out.append({
            "id": i.id,
            "amount_due": i.amount_due,
            "amount_paid": i.amount_paid,
            "status": i.status,
            "created": i.created,
            "pdf_url": i.invoice_pdf,
        })
    return {"invoices": out}
