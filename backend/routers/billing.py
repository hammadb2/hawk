from __future__ import annotations

import logging
import os
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.orm import Session

from auth import get_current_user
from database import get_db
from models import User
from schemas import (
    CheckoutRequest,
    CheckoutCompleteRequest,
    CreatePaymentIntentRequest,
    CreatePaymentIntentPortalRequest,
    PublicCheckoutRequest,
)
from routers.crm_auth import require_supabase_uid_and_email
from services.portal_bootstrap import (
    bootstrap_portal_account,
    ensure_portal_crm_client_id_for_email,
    get_client_id_for_portal_user,
)

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
    CRM_PUBLIC_BASE_URL,
    DEFAULT_PUBLIC_SITE_URL,
    SUPABASE_URL,
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
# Test-mode Shield checkout always returns here (not HAWK_BASE_URL / preview hosts)
MARKETING_PUBLIC_SITE = DEFAULT_PUBLIC_SITE_URL.rstrip("/")

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
    success_url_override: str | None = None,
) -> str:
    """Create a Stripe Checkout Session; StripeClient isolates live vs test API keys (SDK v8+)."""
    from stripe import StripeClient

    meta: dict[str, str] = {"hawk_product": hawk_product}
    sub_meta: dict[str, str] = {"hawk_product": hawk_product}
    if extra_meta:
        meta.update(extra_meta)
        sub_meta.update(extra_meta)
    if success_url_override:
        success_url = success_url_override
    else:
        # Stripe replaces {CHECKOUT_SESSION_ID}; /portal/return exchanges session server-side → Supabase session
        success_url = site + "/portal/return?session_id={CHECKOUT_SESSION_ID}&welcome=1"
        if extra_meta and extra_meta.get("hawk_checkout_mode") == "test":
            success_url = site + "/portal/return?session_id={CHECKOUT_SESSION_ID}&welcome=1&test_checkout=1"
    cancel_url = f"{site}/#pricing"
    client = StripeClient(api_key)
    session = client.v1.checkout.sessions.create(
        {
            "mode": "subscription",
            "line_items": [{"price": price_id, "quantity": 1}],
            "success_url": success_url,
            "cancel_url": cancel_url,
            "metadata": meta,
            # Omit trial_period_days — Stripe rejects 0 ("minimum is 1"). No key = use Price as configured
            # (set Shield/Starter prices to 0-day trial in Dashboard if you need no trial).
            "subscription_data": {"metadata": sub_meta},
            "allow_promotion_codes": False,
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
def checkout_public_test():
    """
    Stripe test mode — HAWK Shield only (no Starter on this route).

    Uses STRIPE_SECRET_KEY_TEST, STRIPE_PRICE_SHIELD_TEST; success redirect is always
    https://securedbyhawk.com/portal?welcome=1 (see MARKETING_PUBLIC_SITE).

    Webhook: POST /api/billing/webhook verifies signatures with STRIPE_WEBHOOK_SECRET_TEST
    (and live secret) — configure the test signing secret on Railway.
    """
    s = _stripe()
    if not s:
        raise HTTPException(status_code=503, detail="Stripe SDK not available")
    if not STRIPE_SECRET_KEY_TEST:
        raise HTTPException(status_code=503, detail="Test checkout not configured (STRIPE_SECRET_KEY_TEST)")
    price_id = STRIPE_PRICE_SHIELD_TEST
    if not price_id:
        raise HTTPException(status_code=503, detail="Test Shield price not configured (STRIPE_PRICE_SHIELD_TEST)")
    site = MARKETING_PUBLIC_SITE
    success_url = site + "/portal/return?session_id={CHECKOUT_SESSION_ID}&welcome=1&test_checkout=1"
    extra = {"hawk_checkout_mode": "test"}
    try:
        url = _checkout_public_session_url(
            api_key=STRIPE_SECRET_KEY_TEST,
            price_id=price_id,
            hawk_product="shield",
            site=site,
            extra_meta=extra,
            success_url_override=success_url,
        )
    except Exception as e:
        logger.exception("checkout-public-test Stripe error")
        raise HTTPException(status_code=502, detail=str(e)[:200]) from e
    return {"url": url, "mode": "test", "product": "shield"}


def _public_site_origin() -> str:
    return (CRM_PUBLIC_BASE_URL or DEFAULT_PUBLIC_SITE_URL).rstrip("/")


def _stripe_obj_to_dict(obj) -> dict:
    if isinstance(obj, dict):
        return obj
    to_d = getattr(obj, "to_dict", None)
    if callable(to_d):
        return to_d()
    raise HTTPException(status_code=502, detail="Could not read Stripe session")


def _retrieve_checkout_session_dict(session_id: str) -> dict:
    import stripe as stripe_mod

    last_err: Exception | None = None
    for api_key in (STRIPE_SECRET_KEY, STRIPE_SECRET_KEY_TEST):
        if not (api_key or "").strip():
            continue
        try:
            stripe_mod.api_key = api_key
            sess = stripe_mod.checkout.Session.retrieve(
                session_id,
                expand=["line_items.data.price", "customer"],
            )
            return _stripe_obj_to_dict(sess)
        except Exception as e:
            last_err = e
    logger.warning("Stripe retrieve session failed: %s", last_err)
    raise HTTPException(status_code=404, detail="Checkout session not found") from last_err


def _portal_next_path_from_session(session_obj: dict) -> str:
    meta = session_obj.get("metadata") or {}
    if str(meta.get("hawk_checkout_mode", "")).lower() == "test":
        return "/portal?welcome=1&test_checkout=1"
    return "/portal?welcome=1"


def _magic_link_redirect_url(email: str, next_path: str) -> str:
    """Supabase Admin: one-time magic link → /portal/auth/callback exchanges code for session."""
    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not SUPABASE_URL or not service_key:
        raise HTTPException(status_code=503, detail="Supabase not configured on API")

    origin = _public_site_origin()
    redirect_to = f"{origin}/portal/auth/callback?next={quote(next_path, safe='')}"

    r = httpx.post(
        f"{SUPABASE_URL}/auth/v1/admin/generate_link",
        headers={
            "apikey": service_key,
            "Authorization": f"Bearer {service_key}",
            "Content-Type": "application/json",
        },
        json={
            "type": "magiclink",
            "email": email.lower().strip(),
            "options": {"redirect_to": redirect_to},
        },
        timeout=30.0,
    )
    if r.status_code >= 400:
        logger.warning("generate_link failed: %s %s", r.status_code, r.text[:400])
        raise HTTPException(status_code=502, detail="Could not create portal sign-in link") from None

    data = r.json()
    props = data.get("properties") if isinstance(data, dict) else {}
    if not isinstance(props, dict):
        props = {}
    link = props.get("action_link") or (data.get("action_link") if isinstance(data, dict) else None)
    if not link:
        raise HTTPException(status_code=502, detail="Sign-in provider returned no action link")
    return str(link)


def _payment_intent_client_secret(stripe_mod, pi) -> str | None:
    """payment_intent on an Invoice may be a dict, a string id, or (rarely) missing until invoice is finalized."""
    if isinstance(pi, dict):
        return pi.get("client_secret")
    if isinstance(pi, str) and pi.startswith("pi_"):
        try:
            got = _stripe_obj_to_dict(stripe_mod.PaymentIntent.retrieve(pi))
            return got.get("client_secret")
        except Exception:
            logger.exception("retrieve PaymentIntent for client_secret")
            return None
    return None


def _invoice_expand_params() -> list[str]:
    """Fields needed to resolve a card-confirmable client_secret for subscription first invoices."""
    # confirmation_secret is the modern field; payment_intent is legacy; payments covers invoice-payments model.
    return ["confirmation_secret", "payment_intent", "payments"]


def _invoice_retrieve_embedded(stripe_mod, inv_id: str) -> dict:
    """Retrieve invoice; retry with simpler expand if Stripe rejects nested expand params."""
    expansions = (
        _invoice_expand_params(),
        ["confirmation_secret", "payment_intent"],
        ["payment_intent"],
        [],
    )
    last_err: Exception | None = None
    for exp in expansions:
        try:
            return _stripe_obj_to_dict(stripe_mod.Invoice.retrieve(inv_id, expand=exp))
        except Exception as e:
            last_err = e
            logger.warning("Invoice.retrieve %s expand=%s: %s", inv_id, exp, e)
    assert last_err is not None
    raise last_err


def _subscription_latest_invoice_expand() -> list[str]:
    """Nested expands on Subscription — avoid deep paths (e.g. payments.data...) that Stripe rejects."""
    return [
        "latest_invoice.confirmation_secret",
        "latest_invoice.payment_intent",
    ]


def _client_secret_from_invoice_dict(stripe_mod, inv: dict) -> str | None:
    """
    Stripe API: newer invoices expose confirmation_secret.client_secret; legacy uses payment_intent;
    some accounts populate invoice payments (payments.data[].payment.payment_intent) instead of top-level PI.
    """
    cs = inv.get("confirmation_secret")
    if isinstance(cs, dict):
        sec = cs.get("client_secret")
        if isinstance(sec, str) and sec.strip():
            return sec.strip()

    sec = _payment_intent_client_secret(stripe_mod, inv.get("payment_intent"))
    if sec:
        return sec

    payments = inv.get("payments")
    if isinstance(payments, dict):
        for row in payments.get("data") or []:
            if not isinstance(row, dict):
                continue
            pay = row.get("payment") or {}
            if pay.get("type") == "payment_intent":
                sec = _payment_intent_client_secret(stripe_mod, pay.get("payment_intent"))
                if sec:
                    return sec
    return None


def _embedded_checkout_client_secret(stripe_mod, subscription) -> str:
    """
    Resolve PaymentIntent client_secret for Subscription.create(payment_behavior=default_incomplete).
    Re-fetches with expand (create() response sometimes omits nested expansions), finalizes draft
    invoices when needed, and resolves string PaymentIntent ids.
    """
    sub_id = subscription.get("id") if isinstance(subscription, dict) else getattr(subscription, "id", None)
    if not sub_id:
        raise HTTPException(status_code=502, detail="Could not read subscription id")

    sub = stripe_mod.Subscription.retrieve(
        str(sub_id),
        expand=_subscription_latest_invoice_expand(),
    )
    sub_d = _stripe_obj_to_dict(sub)
    inv = sub_d.get("latest_invoice")

    if isinstance(inv, str):
        inv = _invoice_retrieve_embedded(stripe_mod, inv)
    elif isinstance(inv, dict):
        pass
    else:
        raise HTTPException(status_code=502, detail="No invoice on subscription")

    inv_id = inv.get("id")
    st = (inv.get("status") or "").lower()

    secret = _client_secret_from_invoice_dict(stripe_mod, inv)
    if secret:
        return secret

    # Full invoice read (confirmation_secret + payments; avoids relying on Subscription nested object)
    if inv_id:
        try:
            inv_full = _invoice_retrieve_embedded(stripe_mod, inv_id)
            secret = _client_secret_from_invoice_dict(stripe_mod, inv_full)
            if secret:
                return secret
            inv = inv_full
            st = (inv.get("status") or "").lower()
        except Exception:
            logger.exception("full invoice retrieve for embedded checkout")

    # Draft first invoice: confirmation_secret / PI may not exist until finalized
    if inv_id and st == "draft":
        try:
            finalized = None
            for exp in (_invoice_expand_params(), ["confirmation_secret", "payment_intent"], ["payment_intent"], None):
                try:
                    if exp is None:
                        finalized = stripe_mod.Invoice.finalize_invoice(inv_id)
                    else:
                        finalized = stripe_mod.Invoice.finalize_invoice(inv_id, expand=exp)
                    break
                except Exception as e:
                    logger.warning("finalize_invoice expand=%s: %s", exp, e)
            if finalized is not None:
                inv = _stripe_obj_to_dict(finalized)
                secret = _client_secret_from_invoice_dict(stripe_mod, inv)
        except Exception:
            logger.exception("finalize_invoice for embedded checkout")

    if secret:
        return secret

    # Retry full invoice fetch (payments / confirmation_secret sometimes only after finalize + second read)
    if inv_id:
        try:
            inv2 = _invoice_retrieve_embedded(stripe_mod, inv_id)
            secret = _client_secret_from_invoice_dict(stripe_mod, inv2)
        except Exception:
            logger.exception("invoice retrieve retry for client_secret")

    if secret:
        return secret

    logger.warning(
        "embedded checkout: still no client_secret sub=%s inv=%s status=%s keys=%s",
        sub_id,
        inv_id,
        st,
        list(inv.keys()) if isinstance(inv, dict) else None,
    )
    raise HTTPException(status_code=502, detail="Could not get payment client secret for subscription")


def _retrieve_subscription_dict(subscription_id: str) -> dict:
    import stripe as stripe_mod

    last_err: Exception | None = None
    for api_key in (STRIPE_SECRET_KEY, STRIPE_SECRET_KEY_TEST):
        if not (api_key or "").strip():
            continue
        try:
            stripe_mod.api_key = api_key
            sub = stripe_mod.Subscription.retrieve(
                subscription_id,
                expand=["latest_invoice.payment_intent", "items.data.price", "customer"],
            )
            return _stripe_obj_to_dict(sub)
        except Exception as e:
            last_err = e
    logger.warning("Stripe retrieve subscription failed: %s", last_err)
    raise HTTPException(status_code=404, detail="Subscription not found") from last_err


def _session_like_from_subscription(sub: dict, cust: dict, email: str, name: str, price_id: str) -> dict:
    """Minimal checkout Session-shaped dict for provision_portal_from_checkout (embedded Elements)."""
    meta = dict(sub.get("metadata") or {})
    for k, v in list(meta.items()):
        if v is not None and not isinstance(v, str):
            meta[k] = str(v)

    hp = str(meta.get("hawk_product", "")).lower()
    if hp not in ("starter", "shield"):
        if price_id and (price_id == STRIPE_PRICE_SHIELD or (STRIPE_PRICE_SHIELD_TEST and price_id == STRIPE_PRICE_SHIELD_TEST)):
            meta["hawk_product"] = "shield"
        elif price_id and (price_id == STRIPE_PRICE_STARTER or (STRIPE_PRICE_STARTER_TEST and price_id == STRIPE_PRICE_STARTER_TEST)):
            meta["hawk_product"] = "starter"

    hp2 = str(meta.get("hawk_product", "")).lower()
    inv = sub.get("latest_invoice")
    amt = 0
    if isinstance(inv, dict):
        try:
            amt = int(inv.get("amount_paid") or inv.get("amount_due") or 0)
        except (TypeError, ValueError):
            amt = 0
    if not amt:
        amt = 99700 if hp2 == "shield" else 19900

    return {
        "id": f"cs_embedded_{sub.get('id', 'unknown')}",
        "object": "checkout.session",
        "mode": "subscription",
        "status": "complete",
        "payment_status": "paid",
        "customer": cust.get("id"),
        "customer_email": email,
        "customer_details": {"email": email, "name": name},
        "metadata": meta,
        "amount_total": amt,
        "line_items": {"data": [{"price": {"id": price_id}}]},
    }


def _run_provision_and_magic_link(session_obj: dict, email: str, log_label: str) -> dict:
    ev = {"type": "checkout.session.completed", "data": {"object": session_obj}}
    try:
        from services.crm_portal_stripe import provision_portal_from_checkout

        ok, prov_reason = provision_portal_from_checkout(ev)
    except Exception:
        logger.exception("checkout-complete provision failed (%s)", log_label)
        raise HTTPException(status_code=502, detail="Could not finish account setup") from None

    if not ok:
        logger.error("checkout-complete: provision failed (%s): %s", log_label, prov_reason)
        raise HTTPException(
            status_code=502,
            detail=prov_reason
            or "Could not finish account setup. Try again shortly or contact hello@securedbyhawk.com.",
        )

    next_path = _portal_next_path_from_session(session_obj)
    try:
        redirect_url = _magic_link_redirect_url(email, next_path)
    except HTTPException:
        raise
    except Exception:
        logger.exception("checkout-complete magic link failed (%s)", log_label)
        raise HTTPException(status_code=502, detail="Could not create sign-in link") from None

    return {"redirect_url": redirect_url}


def _checkout_complete_session(session_id: str) -> dict:
    sid = session_id.strip()
    if not sid.startswith("cs_"):
        raise HTTPException(status_code=400, detail="Invalid session id")

    session_obj = _retrieve_checkout_session_dict(sid)

    if session_obj.get("status") != "complete":
        raise HTTPException(status_code=400, detail="Checkout session is not complete")

    payment_status = session_obj.get("payment_status")
    if payment_status not in ("paid", "no_payment_required"):
        raise HTTPException(status_code=400, detail="Payment not completed")

    email = (session_obj.get("customer_email") or "").strip().lower()
    if not email and session_obj.get("customer_details"):
        cd = session_obj["customer_details"]
        if isinstance(cd, dict):
            email = (cd.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="No customer email on checkout session")

    return _run_provision_and_magic_link(session_obj, email, sid)


def _checkout_complete_subscription(body: CheckoutCompleteRequest) -> dict:
    import time

    sub_id = (body.subscription_id or "").strip()
    if not sub_id.startswith("sub_"):
        raise HTTPException(status_code=400, detail="Invalid subscription id")

    sub = None
    for _ in range(12):
        sub = _retrieve_subscription_dict(sub_id)
        status = (sub.get("status") or "").lower()
        if status in ("active", "trialing"):
            break
        if status not in ("incomplete", "incomplete_expired", "past_due"):
            break
        time.sleep(0.5)

    if sub is None:
        raise HTTPException(status_code=502, detail="Could not load subscription")

    status = (sub.get("status") or "").lower()
    if status not in ("active", "trialing"):
        raise HTTPException(status_code=400, detail="Subscription is not active yet — complete payment first")

    cust = sub.get("customer")
    if isinstance(cust, str):
        raise HTTPException(status_code=502, detail="Expand customer on subscription retrieve failed")
    if not isinstance(cust, dict):
        raise HTTPException(status_code=502, detail="No customer on subscription")

    email = (cust.get("email") or "").strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="No email on Stripe customer")

    if body.email and body.email.strip().lower() != email:
        raise HTTPException(status_code=400, detail="Email does not match this subscription")

    name = (cust.get("name") or body.name or "").strip() or email.split("@", 1)[0]

    items = sub.get("items") or {}
    rows = items.get("data") or []
    price_id = ""
    if rows and isinstance(rows[0], dict):
        pr = rows[0].get("price") or {}
        if isinstance(pr, dict):
            price_id = str(pr.get("id") or "")

    if not price_id:
        raise HTTPException(status_code=502, detail="Could not read subscription price")

    session_like = _session_like_from_subscription(sub, cust, email, name, price_id)
    meta = dict(session_like.get("metadata") or {})
    if not meta.get("crm_client_id"):
        try:
            cid = ensure_portal_crm_client_id_for_email(email)
        except HTTPException:
            raise
        if cid:
            meta["crm_client_id"] = cid
            session_like["metadata"] = meta
    return _run_provision_and_magic_link(session_like, email, sub_id)


@router.post("/create-payment-intent")
def create_payment_intent(req: CreatePaymentIntentRequest):
    """
    Embedded checkout: create Customer + incomplete Subscription; return PaymentIntent client_secret.
    Client confirms card with Stripe.js — no hosted Checkout page.
    """
    import stripe as stripe_mod

    test = bool(req.test_mode)
    api_key = STRIPE_SECRET_KEY_TEST if test else STRIPE_SECRET_KEY
    if not api_key:
        raise HTTPException(status_code=503, detail="Stripe not configured")

    if req.hawk_product == "starter":
        price_id = STRIPE_PRICE_STARTER_TEST if test else STRIPE_PRICE_STARTER
    else:
        price_id = STRIPE_PRICE_SHIELD_TEST if test else STRIPE_PRICE_SHIELD
    if not price_id:
        raise HTTPException(status_code=503, detail="Stripe price not configured for this product")

    stripe_mod.api_key = api_key
    email = req.email.strip().lower()
    name = req.name.strip()

    existing = stripe_mod.Customer.list(email=email, limit=1)
    ex_data = getattr(existing, "data", None) or []
    if ex_data:
        customer_id = ex_data[0].id
        stripe_mod.Customer.modify(customer_id, metadata={"hawk_product": req.hawk_product})
    else:
        cust = stripe_mod.Customer.create(
            email=email,
            name=name,
            metadata={"hawk_product": req.hawk_product},
        )
        customer_id = cust.id

    meta: dict[str, str] = {"hawk_product": req.hawk_product}
    if test:
        meta["hawk_checkout_mode"] = "test"
    if req.crm_client_id:
        meta["crm_client_id"] = str(req.crm_client_id).strip()

    try:
        subscription = stripe_mod.Subscription.create(
            customer=customer_id,
            items=[{"price": price_id}],
            payment_behavior="default_incomplete",
            payment_settings={"save_default_payment_method": "on_subscription"},
            metadata=meta,
            expand=["latest_invoice.payment_intent"],
        )
    except Exception as e:
        logger.exception("create subscription for embedded checkout")
        raise HTTPException(status_code=502, detail=str(e)[:200]) from e

    sub_d = _stripe_obj_to_dict(subscription)
    try:
        secret = _embedded_checkout_client_secret(stripe_mod, subscription)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("embedded client secret resolution")
        raise HTTPException(status_code=502, detail=str(e)[:200]) from e

    return {
        "subscription_id": sub_d.get("id"),
        "client_secret": secret,
        "customer_id": customer_id,
    }


@router.post("/create-payment-intent-portal")
def create_payment_intent_portal(
    req: CreatePaymentIntentPortalRequest,
    auth: tuple[str, str] = Depends(require_supabase_uid_and_email),
):
    """
    Same as create-payment-intent, but email is taken from the Supabase access token (signed-in portal user).
    Tags Stripe subscription with crm_client_id so checkout-complete provisions the bootstrapped client
    (domain-only lookup fails for shared hosts like gmail.com).

    If the browser never finished client-side bootstrap, run bootstrap here so crm_client_id is always set.
    """
    uid, jwt_email = auth
    name = (req.name or "").strip() or jwt_email.split("@", 1)[0]
    crm_client_id = get_client_id_for_portal_user(uid)
    if not crm_client_id:
        try:
            bootstrap_portal_account(uid, jwt_email)
        except HTTPException:
            raise
        except Exception as e:
            logger.exception("bootstrap before payment intent failed uid=%s", uid)
            raise HTTPException(
                status_code=502,
                detail="Could not prepare your account for billing. Try again or contact support.",
            ) from e
        crm_client_id = get_client_id_for_portal_user(uid)
    if not crm_client_id:
        raise HTTPException(
            status_code=503,
            detail="CRM link missing after bootstrap — verify SUPABASE_SERVICE_ROLE_KEY and clients/client_portal_profiles tables.",
        )
    inner = CreatePaymentIntentRequest(
        email=jwt_email,
        name=name,
        hawk_product=req.hawk_product,
        test_mode=req.test_mode,
        crm_client_id=crm_client_id,
    )
    return create_payment_intent(inner)


@router.post("/checkout-complete")
def checkout_complete(body: CheckoutCompleteRequest):
    """
    Hosted: session_id from /portal/return. Embedded: subscription_id after confirmCardPayment succeeds.
    Provisions CRM + returns Supabase magic link for PKCE session.
    """
    if body.subscription_id:
        return _checkout_complete_subscription(body)
    return _checkout_complete_session(body.session_id or "")


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
        existing = s.Customer.list(email=user.email, limit=1)
        ex_data = getattr(existing, "data", None) or []
        if ex_data:
            customer_id = ex_data[0].id
        else:
            cust = s.Customer.create(
                email=user.email,
                name=f"{user.first_name or ''} {user.last_name or ''}".strip() or None,
            )
            customer_id = cust.id
        user.stripe_customer_id = customer_id
        db.commit()
    session = s.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=f"{BASE_URL}/dashboard/settings?billing=success",
        cancel_url=f"{BASE_URL}/dashboard/settings?billing=cancel",
        metadata={"user_id": str(user.id), "plan": req.plan},
        subscription_data={"metadata": {"user_id": str(user.id), "plan": req.plan}},
        allow_promotion_codes=False,
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
    # Try live secret first, then STRIPE_WEBHOOK_SECRET_TEST (Stripe CLI / test-mode endpoint).
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
        # No crm_client_id: create clients row, Supabase invite (magic link), profiles.role=client,
        # welcome email, CEO SMS, enqueue scan — see services.crm_portal_stripe.provision_portal_from_checkout
        try:
            from services.crm_portal_stripe import provision_portal_from_checkout

            _ok, prov_err = provision_portal_from_checkout(evd)
            if not _ok:
                logger.warning("checkout.session.completed CRM provision incomplete: %s", prov_err)
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
