"""HAWK backend configuration from environment."""
from __future__ import annotations

import os

# App
SECRET_KEY = os.environ.get("HAWK_SECRET_KEY", "")
if not SECRET_KEY:
    import warnings
    warnings.warn(
        "HAWK_SECRET_KEY is not set — using an insecure random key. "
        "Set HAWK_SECRET_KEY in your environment for production.",
        stacklevel=1,
    )
    import secrets as _secrets
    SECRET_KEY = _secrets.token_urlsafe(64)
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

# Shield onboarding — booking link in WhatsApp / email (Cal.com or similar)
CAL_COM_BOOKING_URL = os.environ.get("CAL_COM_BOOKING_URL", "https://cal.com").strip().rstrip("/")

# OpenAI — portal AI, Charlotte emails, attacker simulation, Ask HAWK, scanner interpretation (when wired to API)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o").strip() or "gpt-4o"

# Legacy DeepSeek (optional; Ask HAWK uses OpenAI when OPENAI_API_KEY is set)
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_CHAT_MODEL = "deepseek-chat"
DEEPSEEK_REASONER_MODEL = "deepseek-reasoner"

# Charlotte (Revenue-Ops) for emails
CHARLOTTE_URL = os.environ.get("CHARLOTTE_URL", "http://46.225.168.75:8001/agent/charlotte")
CHARLOTTE_API_KEY = os.environ.get("CHARLOTTE_API_KEY", "")

# Frontend / marketing site (Stripe redirects, email links — same host as Next.js when unified)
DEFAULT_PUBLIC_SITE_URL = "https://securedbyhawk.com"
BASE_URL = os.environ.get("HAWK_BASE_URL", DEFAULT_PUBLIC_SITE_URL).strip().rstrip("/")

# HaveIBeenPwned (breach check)
HIBP_API_KEY = os.environ.get("HIBP_API_KEY", "")

# Optional — CRM integrations
SMARTLEAD_API_KEY = os.environ.get("SMARTLEAD_API_KEY", "")

# ARIA Pipeline — outbound automation API keys
APOLLO_API_KEY = os.environ.get("APOLLO_API_KEY", "").strip()
CLAY_API_KEY = os.environ.get("CLAY_API_KEY", "").strip()
ZEROBOUNCE_API_KEY = os.environ.get("ZEROBOUNCE_API_KEY", "").strip()

# Unified pipeline — nightly build + morning dispatch
GOOGLE_PLACES_API_KEY = os.environ.get("GOOGLE_PLACES_API_KEY", "").strip()
PROSPEO_API_KEY = os.environ.get("PROSPEO_API_KEY", "").strip()
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

# CRM public URL for WhatsApp deep links (no trailing slash)
CRM_PUBLIC_BASE_URL = (
    os.environ.get("CRM_PUBLIC_BASE_URL", os.environ.get("HAWK_CRM_PUBLIC_URL", "")).strip().rstrip("/")
    or DEFAULT_PUBLIC_SITE_URL
)

# Monitor self-check: public API base (e.g. https://api.example.com) — defaults to localhost PORT in health_monitor
MONITOR_API_BASE_URL = os.environ.get("MONITOR_API_BASE_URL", "").strip().rstrip("/")

# CEO SMS (OpenPhone) — E.164, e.g. +15551234567
CRM_CEO_PHONE_E164 = os.environ.get("CRM_CEO_PHONE_E164", "").strip()

# Client portal — welcome / drip (Phase 2B)
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "").strip()
# Client-facing mail — verify securedbyhawk.com in Resend; Railway: RESEND_FROM_EMAIL=noreply@securedbyhawk.com
RESEND_FROM_EMAIL = os.environ.get("RESEND_FROM_EMAIL", "HAWK Security <noreply@securedbyhawk.com>").strip()
# Optional override; defaults to RESEND_FROM_EMAIL when empty
RESEND_GUARANTEE_FROM = os.environ.get("RESEND_GUARANTEE_FROM", "").strip() or RESEND_FROM_EMAIL

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
