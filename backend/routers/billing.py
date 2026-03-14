from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.orm import Session

from backend.auth import get_current_user
from backend.database import get_db
from backend.models import User
from backend.schemas import CheckoutRequest
from backend.config import (
    STRIPE_SECRET_KEY,
    STRIPE_WEBHOOK_SECRET,
    STRIPE_PRICE_STARTER,
    STRIPE_PRICE_PRO,
    STRIPE_PRICE_AGENCY,
    BASE_URL,
)

# Map Stripe price ID -> plan name for webhook
def _plan_from_subscription(sub) -> str | None:
    items = sub.get("items") or {}
    data = items.get("data") or []
    if not data:
        return None
    price = data[0].get("price") or {}
    pid = price.get("id")
    if pid == STRIPE_PRICE_STARTER:
        return "starter"
    if pid == STRIPE_PRICE_PRO:
        return "pro"
    if pid == STRIPE_PRICE_AGENCY:
        return "agency"
    return None

router = APIRouter(prefix="/api/billing", tags=["billing"])

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
    if not STRIPE_WEBHOOK_SECRET:
        raise HTTPException(status_code=503, detail="Webhook not configured")
    payload = await request.body()
    s = _stripe()
    if not s:
        raise HTTPException(status_code=503, detail="Stripe not configured")
    try:
        event = s.Webhook.construct_event(payload, stripe_signature or "", STRIPE_WEBHOOK_SECRET)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook signature invalid: {e}") from e
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
            user.plan = "trial"
            db.commit()
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
