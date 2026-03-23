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
# SQLite needs connect_args for foreign keys
CONNECT_ARGS = {} if DATABASE_URL.startswith("postgresql") else {"check_same_thread": False}

# Scanner relay (Ghost)
SCANNER_RELAY_URL = os.environ.get("HAWK_SCANNER_RELAY_URL", "http://178.104.27.211:8002")
SCANNER_TIMEOUT = float(os.environ.get("HAWK_SCANNER_TIMEOUT", "120"))

# Stripe
STRIPE_SECRET_KEY = os.environ.get("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PRICE_STARTER = os.environ.get("STRIPE_PRICE_STARTER", "price_starter")
STRIPE_PRICE_PRO = os.environ.get("STRIPE_PRICE_PRO", "price_pro")
STRIPE_PRICE_AGENCY = os.environ.get("STRIPE_PRICE_AGENCY", "price_agency")

# DeepSeek (Ask HAWK)
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_CHAT_MODEL = "deepseek-chat"
DEEPSEEK_REASONER_MODEL = "deepseek-reasoner"

# Charlotte (Revenue-Ops) for emails
CHARLOTTE_URL = os.environ.get("CHARLOTTE_URL", "http://46.225.168.75:8001/agent/charlotte")
CHARLOTTE_API_KEY = os.environ.get("CHARLOTTE_API_KEY", "akb-revenue-ops-2026")

# Frontend base URL (for Stripe redirects)
BASE_URL = os.environ.get("HAWK_BASE_URL", "https://hawk.akbstudios.com")

# Cron (scheduled scans) — set to a secret; cron calls with X-Cron-Secret
CRON_SECRET = os.environ.get("HAWK_CRON_SECRET", "")

# Plan limits
PLAN_DOMAINS = {"trial": 1, "starter": 1, "pro": 3, "agency": 10}
PLAN_ASK_HAWK_LIMIT = {"trial": 5, "starter": -1, "pro": -1, "agency": -1}  # -1 = unlimited
PLAN_PDF_PER_MONTH = {"trial": 2, "starter": 3, "pro": -1, "agency": -1}
TRIAL_DAYS = 7
