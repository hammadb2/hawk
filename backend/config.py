"""HAWK backend configuration from environment."""
from __future__ import annotations

import os

# App
SECRET_KEY = os.environ.get("HAWK_SECRET_KEY", "change-me-in-production")
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
SCANNER_RELAY_URL = os.environ.get("HAWK_SCANNER_RELAY_URL", "http://178.104.27.211:8002")
# Must be >= longest expected hawk-scanner-v2 sync run (Vercel CRM calls wait up to ~295s)
SCANNER_TIMEOUT = float(os.environ.get("HAWK_SCANNER_TIMEOUT", "300"))

# Stripe
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

# Shield onboarding — booking link in WhatsApp / email (Cal.com or similar)
CAL_COM_BOOKING_URL = os.environ.get("CAL_COM_BOOKING_URL", "https://cal.com").strip().rstrip("/")

# DeepSeek (Ask HAWK)
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_CHAT_MODEL = "deepseek-chat"
DEEPSEEK_REASONER_MODEL = "deepseek-reasoner"

# Charlotte (Revenue-Ops) for emails
CHARLOTTE_URL = os.environ.get("CHARLOTTE_URL", "http://46.225.168.75:8001/agent/charlotte")
CHARLOTTE_API_KEY = os.environ.get("CHARLOTTE_API_KEY", "akb-revenue-ops-2026")

# Frontend / marketing site (Stripe redirects, email links — same host as Next.js when unified)
DEFAULT_PUBLIC_SITE_URL = "https://securedbyhawk.com"
BASE_URL = os.environ.get("HAWK_BASE_URL", DEFAULT_PUBLIC_SITE_URL).strip().rstrip("/")

# HaveIBeenPwned (breach check)
HIBP_API_KEY = os.environ.get("HIBP_API_KEY", "")

# Optional — wire when used (CRM/AI integrations)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
SMARTLEAD_API_KEY = os.environ.get("SMARTLEAD_API_KEY", "")

# CRM (Supabase Auth JWT for FastAPI — same as Dashboard > Settings > API > JWT Secret)
SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET", "").strip()
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")

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
RESEND_FROM_EMAIL = os.environ.get("RESEND_FROM_EMAIL", "HAWK <onboarding@securedbyhawk.com>").strip()
# Gated guarantee document — must match verified domain in Resend (securedbyhawk.com)
RESEND_GUARANTEE_FROM = os.environ.get(
    "RESEND_GUARANTEE_FROM",
    "HAWK Security <noreply@securedbyhawk.com>",
).strip()

# Cron (scheduled scans) — set to a secret; cron calls with X-Cron-Secret
# Railway often uses CRON_SECRET; we accept that as an alias for HAWK_CRON_SECRET.
CRON_SECRET = (
    os.environ.get("HAWK_CRON_SECRET", "").strip()
    or os.environ.get("CRON_SECRET", "").strip()
)

# Plan limits
PLAN_DOMAINS = {"trial": 1, "starter": 1, "pro": 3, "agency": 10}
PLAN_ASK_HAWK_LIMIT = {"trial": 5, "starter": -1, "pro": -1, "agency": -1}  # -1 = unlimited
PLAN_PDF_PER_MONTH = {"trial": 0, "starter": 1, "pro": -1, "agency": -1}
TRIAL_DAYS = 7
