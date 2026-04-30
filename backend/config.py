"""HAWK backend configuration from environment."""
from __future__ import annotations

import os

# App
#
# HAWK_SECRET_KEY signs every JWT we issue. In production it MUST be set to a
# stable, high-entropy value — otherwise tokens issued before a process restart
# stop validating, and a process-local random key is trivially recoverable.
#
# Hard rule: production refuses to start without it. Dev / test / CI fall back
# to a process-local random key (with a warning) so the app still imports.
SECRET_KEY = os.environ.get("HAWK_SECRET_KEY", "").strip()
_HAWK_ENV = (
    os.environ.get("HAWK_ENV")
    or os.environ.get("RAILWAY_ENVIRONMENT")
    or os.environ.get("ENVIRONMENT")
    or "development"
).strip().lower()
_IS_PRODUCTION = _HAWK_ENV in {"production", "prod"}
if not SECRET_KEY:
    if _IS_PRODUCTION:
        raise RuntimeError(
            "HAWK_SECRET_KEY is not set. Refusing to start in production "
            "with an insecure random key. Set HAWK_SECRET_KEY to a stable "
            "64+ character secret (e.g. `python -c 'import secrets; "
            "print(secrets.token_urlsafe(64))'`) in the Railway / host env."
        )
    import warnings
    warnings.warn(
        f"HAWK_SECRET_KEY is not set (HAWK_ENV={_HAWK_ENV!r}) — using an "
        "insecure random key for this process only. JWTs will not survive "
        "restarts. Set HAWK_SECRET_KEY for any non-dev environment.",
        stacklevel=1,
    )
    import secrets as _secrets
    SECRET_KEY = _secrets.token_urlsafe(64)
elif len(SECRET_KEY) < 32:
    if _IS_PRODUCTION:
        raise RuntimeError(
            f"HAWK_SECRET_KEY is too short ({len(SECRET_KEY)} chars). "
            "Production requires at least 32 characters of entropy; aim for 64."
        )
    import warnings
    warnings.warn(
        f"HAWK_SECRET_KEY is only {len(SECRET_KEY)} characters — set at "
        "least 32 (64 recommended) before deploying to production.",
        stacklevel=1,
    )
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# Database
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite:///./hawk.db",
)
# Railway / Heroku often use postgres:// — SQLAlchemy expects postgresql://
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://") :]

_d = DATABASE_URL.lower()
# SQLite needs connect_args for foreign keys; Postgres needs connect_timeout so startup cannot hang forever
if _d.startswith("postgresql"):
    CONNECT_ARGS = {"connect_timeout": 10}
else:
    CONNECT_ARGS = {"check_same_thread": False}

# Scanner relay (Ghost)
SCANNER_RELAY_URL = os.environ.get("HAWK_SCANNER_RELAY_URL", "")
# Must be >= longest expected hawk-scanner-v2 sync run (Vercel CRM calls wait up to ~295s)
SCANNER_TIMEOUT = float(os.environ.get("HAWK_SCANNER_TIMEOUT", "300"))

# Stripe (live / default)
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_STARTER = os.environ.get("STRIPE_PRICE_STARTER", "price_starter")
STRIPE_PRICE_PRO = os.environ.get("STRIPE_PRICE_PRO", "price_pro")
STRIPE_PRICE_AGENCY = os.environ.get("STRIPE_PRICE_AGENCY", "price_agency")
# HAWK Shield — $997/mo (set in Stripe Dashboard; override via env in production)
STRIPE_PRICE_SHIELD = os.environ.get(
    "STRIPE_PRICE_SHIELD",
    "price_1THYpWRVvrqiS5j4rFdQclsd",
).strip()

# Stripe test mode — separate Dashboard products/prices; webhook signing secret from test-mode endpoint
STRIPE_SECRET_KEY_TEST = os.environ.get("STRIPE_SECRET_KEY_TEST", "").strip()
STRIPE_WEBHOOK_SECRET_TEST = os.environ.get("STRIPE_WEBHOOK_SECRET_TEST", "").strip()
STRIPE_PRICE_STARTER_TEST = os.environ.get("STRIPE_PRICE_STARTER_TEST", "").strip()
STRIPE_PRICE_SHIELD_TEST = os.environ.get("STRIPE_PRICE_SHIELD_TEST", "").strip()

# Booking link used in every outbound + reply email (Cal.com or similar). Leave
# empty by default so downstream ``CAL_COM_BOOKING_URL or "<fallback>"`` guards
# actually hit their fallback; a prior default of ``"https://cal.com"`` was
# non-empty-truthy which silently shadowed every callsite's real fallback URL
# and caused reply emails to go out with a bare "https://cal.com" CTA when the
# env var wasn't set in prod.
CAL_COM_BOOKING_URL = os.environ.get("CAL_COM_BOOKING_URL", "").strip().rstrip("/")

# OpenAI — portal AI, ARIA email drafts, attacker simulation, Ask HAWK, scanner interpretation
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o").strip() or "gpt-4o"

# Legacy DeepSeek (optional; Ask HAWK uses OpenAI when OPENAI_API_KEY is set)
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_CHAT_MODEL = "deepseek-chat"
DEEPSEEK_REASONER_MODEL = "deepseek-reasoner"

# Frontend / marketing site (Stripe redirects, email links — same host as Next.js when unified)
DEFAULT_PUBLIC_SITE_URL = "https://securedbyhawk.com"
BASE_URL = os.environ.get("HAWK_BASE_URL", DEFAULT_PUBLIC_SITE_URL).strip().rstrip("/")

# HaveIBeenPwned (breach check)
HIBP_API_KEY = os.environ.get("HIBP_API_KEY", "")

# Optional — CRM integrations
SMARTLEAD_API_KEY = os.environ.get("SMARTLEAD_API_KEY", "")

# ARIA Pipeline — outbound automation API keys
APOLLO_API_KEY = os.environ.get("APOLLO_API_KEY", "").strip()
PROSPEO_API_KEY = os.environ.get("PROSPEO_API_KEY", "").strip()
CLAY_API_KEY = os.environ.get("CLAY_API_KEY", "").strip()
ZEROBOUNCE_API_KEY = os.environ.get("ZEROBOUNCE_API_KEY", "").strip()

# Unified pipeline — nightly build + morning dispatch
APIFY_API_KEY = os.environ.get("APIFY_API_KEY", "").strip()
MXTOOLBOX_API_KEY = os.environ.get("MXTOOLBOX_API_KEY", "").strip()
CRM_SMARTLEAD_WEBHOOK_SECRET = os.environ.get("CRM_SMARTLEAD_WEBHOOK_SECRET", "").strip()

# ARIA Phase 18 — WhatsApp Business Cloud API
WHATSAPP_ACCESS_TOKEN = os.environ.get("WHATSAPP_ACCESS_TOKEN", "").strip()
WHATSAPP_PHONE_NUMBER_ID = os.environ.get("WHATSAPP_PHONE_NUMBER_ID", "").strip()
WHATSAPP_VERIFY_TOKEN = os.environ.get("WHATSAPP_VERIFY_TOKEN", "aria-hawk-verify").strip()
WHATSAPP_APP_SECRET = os.environ.get("WHATSAPP_APP_SECRET", "").strip()

# CRM (Supabase Auth JWT for FastAPI — same as Dashboard > Settings > API > JWT Secret)
SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "").strip()
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
# Server-side REST (portal bootstrap, JWT fallback via /auth/v1/user)
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
# Public anon key — required for PostgREST calls that enforce RLS with the user JWT (e.g. CRM KPI aggregation).
SUPABASE_ANON_KEY = (
    os.environ.get("SUPABASE_ANON_KEY", "").strip()
    or os.environ.get("NEXT_PUBLIC_SUPABASE_ANON_KEY", "").strip()
)

# CRM public URL for WhatsApp deep links (no trailing slash)
CRM_PUBLIC_BASE_URL = (
    os.environ.get("CRM_PUBLIC_BASE_URL", os.environ.get("HAWK_CRM_PUBLIC_URL", "")).strip().rstrip("/")
    or DEFAULT_PUBLIC_SITE_URL
)

# Monitor self-check: public API base (e.g. https://api.example.com) — defaults to localhost PORT in health_monitor
MONITOR_API_BASE_URL = os.environ.get("MONITOR_API_BASE_URL", "").strip().rstrip("/")

# CEO SMS (OpenPhone) — E.164, e.g. +15551234567
CRM_CEO_PHONE_E164 = os.environ.get("CRM_CEO_PHONE_E164", "").strip()

# Closer (Kevin) SMS number for booking alerts — E.164. Falls back to the
# ``kevin_sms_number`` row in ``crm_settings`` when this env var is empty so
# the CEO can rotate it from the UI without a redeploy.
KEVIN_SMS_NUMBER = os.environ.get("KEVIN_SMS_NUMBER", "").strip()

# Auto-reply kill switch (env var override for crm_settings.autonomous_reply_enabled).
# Leave empty to defer to the DB setting; set to "false" to force-disable.
ARIA_AUTONOMOUS_REPLY_ENABLED = os.environ.get("ARIA_AUTONOMOUS_REPLY_ENABLED", "").strip()

# Human-checkpoint threshold — any deal at or above this monthly-recurring
# value bypasses auto-send and routes to the VA queue + SMS alert.
ARIA_HUMAN_CHECKPOINT_USD = int(os.environ.get("ARIA_HUMAN_CHECKPOINT_USD", "5000") or "5000")

# Client portal — welcome / drip (Phase 2B)
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
# Client-facing mail — verify securedbyhawk.com in Resend; Railway: RESEND_FROM_EMAIL=noreply@securedbyhawk.com
RESEND_FROM_EMAIL = os.environ.get("RESEND_FROM_EMAIL", "HAWK Security <noreply@securedbyhawk.com>").strip()
# Optional override; defaults to RESEND_FROM_EMAIL when empty
RESEND_GUARANTEE_FROM = os.environ.get("RESEND_GUARANTEE_FROM", "").strip() or RESEND_FROM_EMAIL

# Mailbox-native cold-outbound dispatcher (replaces Smartlead).
# Fernet key (urlsafe base64, 32 bytes) used to encrypt per-mailbox SMTP/IMAP
# passwords at rest. MUST be set in production; the backend will refuse to
# decrypt stored credentials without it. Generate with:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
MAILBOX_ENCRYPTION_KEY = os.environ.get("MAILBOX_ENCRYPTION_KEY", "").strip()

# Cron (scheduled scans) — set to a secret; cron calls with X-Cron-Secret
# Railway often uses CRON_SECRET; we accept that as an alias for HAWK_CRON_SECRET.
CRON_SECRET = (
    os.environ.get("HAWK_CRON_SECRET", "").strip()
    or os.environ.get("CRON_SECRET", "").strip()
)

# Plan limits
PLAN_DOMAINS = {"trial": 1, "starter": 1, "pro": 3, "agency": 10}
PLAN_ASK_HAWK_LIMIT = {"trial": 5, "starter": -1, "pro": -1, "agency": -1}  # -1 = unlimited
PLAN_PDF_PER_MONTH = {"trial": 2, "starter": 3, "pro": -1, "agency": -1}
TRIAL_DAYS = 7
