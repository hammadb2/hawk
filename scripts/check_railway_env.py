#!/usr/bin/env python3
"""Audit which environment variables are present, missing, or empty on Railway
(or any other host running ``backend/``).

Run on a Railway service — or against any shell — like this::

    python scripts/check_railway_env.py
    python scripts/check_railway_env.py --json
    python scripts/check_railway_env.py --strict   # exit 1 if any REQUIRED is missing

Tiers
-----

REQUIRED — production will not start, refuse to come up, or silently corrupt
data without these. The script exits non-zero in ``--strict`` mode if any of
these are missing **and** ``HAWK_ENV`` (or ``RAILWAY_ENVIRONMENT`` /
``ENVIRONMENT``) is set to a production-like value.

RECOMMENDED — major paid features are completely disabled when these are
missing (Stripe checkout, OpenAI-powered features, Supabase service-role
operations, transactional email, scanner relay). The app boots, but big
parts of it no-op.

OPTIONAL — auxiliary integrations (WhatsApp, OpenPhone SMS, Cal.com hooks,
HIBP, Apollo / Prospeo / ZeroBounce / Smartlead / Apify / MXToolbox).
Missing means the corresponding feature degrades gracefully or is skipped.

Each entry below also records *what feature* the variable gates, so when the
audit prints a missing one you can see immediately what's offline.

This script imports nothing from ``backend/`` — it only reads ``os.environ`` —
so it can run in a stripped Railway shell that doesn't have project deps
installed.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class EnvVar:
    name: str
    tier: str  # "required" | "recommended" | "optional"
    feature: str
    aliases: tuple[str, ...] = field(default_factory=tuple)
    notes: str = ""

    def resolve(self) -> tuple[str, str | None]:
        """Return (resolved_name, value). ``resolved_name`` is whichever alias
        actually had a non-empty value, or ``self.name`` if none did. ``value``
        is ``None`` when truly unset/empty."""
        for n in (self.name, *self.aliases):
            v = os.environ.get(n, "").strip()
            if v:
                return n, v
        return self.name, None


# ── Catalog ─────────────────────────────────────────────────────────────

REQUIRED: list[EnvVar] = [
    EnvVar(
        "HAWK_SECRET_KEY",
        tier="required",
        feature="JWT signing — production refuses to start without ≥32 chars",
        notes="Generate with `python -c 'import secrets; print(secrets.token_urlsafe(64))'`",
    ),
    EnvVar(
        "DATABASE_URL",
        tier="required",
        feature="Postgres / SQLAlchemy connection (postgres:// auto-rewritten to postgresql://)",
        notes="Without this the API silently falls back to ./hawk.db (SQLite) which is wrong on Railway",
    ),
]

RECOMMENDED: list[EnvVar] = [
    # Supabase — portal bootstrap, RLS, JWT verification, all CRM writes
    EnvVar("SUPABASE_URL", "recommended", "Supabase REST host for portal + CRM"),
    EnvVar(
        "SUPABASE_SERVICE_ROLE_KEY",
        tier="recommended",
        feature="Service-role writes (portal bootstrap, incident reports, support tickets, RLS bypass)",
    ),
    EnvVar(
        "SUPABASE_ANON_KEY",
        tier="recommended",
        feature="PostgREST calls that enforce RLS with the user JWT",
        aliases=("NEXT_PUBLIC_SUPABASE_ANON_KEY",),
    ),
    EnvVar(
        "SUPABASE_JWT_SECRET",
        tier="recommended",
        feature="Local HS256 verify for Bearer tokens (falls back to /auth/v1/user when missing)",
    ),
    # Scanner
    EnvVar(
        "HAWK_SCANNER_RELAY_URL",
        tier="recommended",
        feature="hawk-scanner-v2 relay base URL — every domain scan / homepage widget / portal scan calls this",
    ),
    # Stripe
    EnvVar("STRIPE_SECRET_KEY", "recommended", "Stripe live secret — checkout, subscriptions"),
    EnvVar("STRIPE_WEBHOOK_SECRET", "recommended", "Stripe live webhook signature verification"),
    EnvVar("STRIPE_PRICE_STARTER", "recommended", "Stripe Starter plan price id"),
    EnvVar("STRIPE_PRICE_PRO", "recommended", "Stripe Pro plan price id"),
    EnvVar("STRIPE_PRICE_AGENCY", "recommended", "Stripe Agency plan price id"),
    EnvVar("STRIPE_PRICE_SHIELD", "recommended", "HAWK Shield $997/mo subscription price id"),
    # OpenAI
    EnvVar(
        "OPENAI_API_KEY",
        tier="recommended",
        feature="Ask HAWK, portal advisor, ARIA outbound emails, threat briefings, attacker simulation",
    ),
    # Email
    EnvVar(
        "RESEND_API_KEY",
        tier="recommended",
        feature="Transactional email — incident-report receipts, welcome, password reset, drip sequences",
    ),
    # Mailbox-native cold-outbound dispatcher (was Smartlead)
    EnvVar(
        "MAILBOX_ENCRYPTION_KEY",
        tier="recommended",
        feature="Fernet key encrypting per-mailbox SMTP/IMAP creds; backend refuses to decrypt without it",
        notes="Generate with `python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'`",
    ),
    # Cron
    EnvVar(
        "HAWK_CRON_SECRET",
        tier="recommended",
        feature="X-Cron-Secret header for /api/crm/cron/* — onboarding sequences, nightly pipeline, SLA scans",
        aliases=("CRON_SECRET",),
    ),
    EnvVar("HAWK_BASE_URL", "recommended", "Public site URL for Stripe redirects + email links"),
]

OPTIONAL: list[EnvVar] = [
    # Lead enrichment
    EnvVar(
        "PROSPEO_API_KEY",
        tier="optional",
        feature="Primary contact enrichment (priority list #17 — Prospeo first-pass)",
    ),
    EnvVar(
        "APOLLO_API_KEY",
        tier="optional",
        feature="Apollo enrichment fallback when Prospeo misses; people-topup discovery",
    ),
    EnvVar(
        "ZEROBOUNCE_API_KEY",
        tier="optional",
        feature="Pre-send email validation in nightly pipeline",
    ),
    EnvVar(
        "CLAY_API_KEY",
        tier="optional",
        feature="Clay CRM enrichment (legacy / rarely used)",
    ),
    EnvVar(
        "APIFY_API_KEY",
        tier="optional",
        feature="Google-Places-based domain discovery (Actor 1)",
    ),
    EnvVar(
        "MXTOOLBOX_API_KEY",
        tier="optional",
        feature="DMARC / SPF / DKIM lookup enrichment",
    ),
    EnvVar(
        "SMARTLEAD_API_KEY",
        tier="optional",
        feature="Smartlead campaign push (legacy; mailbox-native dispatcher is primary)",
    ),
    EnvVar(
        "CRM_SMARTLEAD_WEBHOOK_SECRET",
        tier="optional",
        feature="Smartlead reply webhook signature verification",
    ),
    # Stripe test mode
    EnvVar("STRIPE_SECRET_KEY_TEST", "optional", "Stripe test-mode secret (embedded /checkout)"),
    EnvVar("STRIPE_WEBHOOK_SECRET_TEST", "optional", "Stripe test-mode webhook signature"),
    EnvVar("STRIPE_PRICE_SHIELD_TEST", "optional", "Stripe test-mode Shield price id"),
    EnvVar("STRIPE_PRICE_STARTER_TEST", "optional", "Stripe test-mode Starter price id"),
    # SMS / OpenPhone
    EnvVar(
        "OPENPHONE_API_KEY",
        tier="optional",
        feature="SMS alerts — ARIA replies, Shield onboarding, pipeline failures, incident report → CEO",
    ),
    EnvVar("OPENPHONE_FROM_NUMBER", "optional", "OpenPhone sender E.164"),
    EnvVar(
        "CRM_CEO_PHONE_E164",
        tier="optional",
        feature="CEO phone for SMS escalation; HAWK_CEO_PHONE is the newer name",
        aliases=("HAWK_CEO_PHONE",),
    ),
    EnvVar(
        "HAWK_CEO_EMAIL",
        tier="optional",
        feature="CEO email for incident-report escalation receipts",
    ),
    EnvVar(
        "VA_PHONE_NUMBER",
        tier="optional",
        feature="VA team SMS for ARIA reply routing",
    ),
    EnvVar(
        "KEVIN_SMS_NUMBER",
        tier="optional",
        feature="Closer (Kevin) SMS for booking alerts; falls back to crm_settings.kevin_sms_number",
    ),
    # WhatsApp
    EnvVar("WHATSAPP_ACCESS_TOKEN", "optional", "WhatsApp Business Cloud API token"),
    EnvVar("WHATSAPP_PHONE_NUMBER_ID", "optional", "WhatsApp Business phone number id"),
    EnvVar("WHATSAPP_VERIFY_TOKEN", "optional", "WhatsApp webhook verify token"),
    EnvVar("WHATSAPP_APP_SECRET", "optional", "WhatsApp webhook signature verification"),
    # Webhooks
    EnvVar(
        "CAL_COM_BOOKING_URL",
        tier="optional",
        feature="Cal.com booking link in every outbound + reply email",
    ),
    EnvVar(
        "CAL_WEBHOOK_SECRET",
        tier="optional",
        feature="Cal.com webhook signature verification",
    ),
    EnvVar(
        "CRM_EMAIL_WEBHOOK_SECRET",
        tier="optional",
        feature="X-CRM-Webhook-Secret for /api/crm/webhooks/email-events",
    ),
    # Misc integrations
    EnvVar("HIBP_API_KEY", "optional", "HaveIBeenPwned breach check"),
    EnvVar(
        "GOOGLE_SAFE_BROWSING_API_KEY",
        tier="optional",
        feature="Guardian Chrome extension URL safety lookups",
    ),
    EnvVar(
        "GUARDIAN_EXTENSION_SECRET",
        tier="optional",
        feature="Shared secret for Guardian extension → /api/guardian/log-event",
    ),
    EnvVar("REDIS_URL", "optional", "Scanner queue depth health"),
    EnvVar(
        "TRANSACTIONAL_EMAIL_WEBHOOK_URL",
        tier="optional",
        feature="Optional generic email relay webhook (when Resend isn't enough)",
    ),
    EnvVar("TRANSACTIONAL_EMAIL_API_KEY", "optional", "Auth for the generic email relay webhook"),
    EnvVar("MONITOR_API_BASE_URL", "optional", "Public API base URL for monitor self-check"),
    EnvVar(
        "DEEPSEEK_API_KEY",
        tier="optional",
        feature="Legacy DeepSeek; OpenAI is primary when OPENAI_API_KEY is set",
    ),
    EnvVar("RESEND_FROM_EMAIL", "optional", "Resend sender — defaults to noreply@securedbyhawk.com"),
    EnvVar(
        "RESEND_GUARANTEE_FROM",
        tier="optional",
        feature="Resend guarantee-team sender override; falls back to RESEND_FROM_EMAIL",
    ),
    EnvVar(
        "ARIA_AUTONOMOUS_REPLY_ENABLED",
        tier="optional",
        feature="Kill switch for ARIA auto-reply (env override of crm_settings.autonomous_reply_enabled)",
    ),
    EnvVar(
        "HAWK_INCIDENT_SLA_MINUTES",
        tier="optional",
        feature="Incident-report SLA clock (default 60 minutes)",
    ),
]


# ── Helpers ─────────────────────────────────────────────────────────────


def _is_production() -> bool:
    val = (
        os.environ.get("HAWK_ENV")
        or os.environ.get("RAILWAY_ENVIRONMENT")
        or os.environ.get("ENVIRONMENT")
        or "development"
    ).strip().lower()
    return val in {"production", "prod"}


def _audit(catalog: Iterable[EnvVar]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for var in catalog:
        resolved_name, value = var.resolve()
        rows.append({
            "name": var.name,
            "tier": var.tier,
            "feature": var.feature,
            "set": value is not None,
            "resolved_name": resolved_name if value is not None else None,
            "aliases": list(var.aliases),
            "notes": var.notes,
        })
    return rows


def _print_section(title: str, rows: list[dict[str, object]]) -> tuple[int, int]:
    set_count = sum(1 for r in rows if r["set"])
    missing_count = len(rows) - set_count
    print(f"\n══ {title}  ({set_count}/{len(rows)} set, {missing_count} missing) " + "═" * 4)
    width = max(len(r["name"]) for r in rows) if rows else 0  # type: ignore[arg-type]
    for r in rows:
        status = "OK   " if r["set"] else "MISS "
        name_field = str(r["name"]).ljust(width)
        line = f"  [{status}] {name_field}  {r['feature']}"
        if not r["set"] and r["aliases"]:
            line += f"  (aliases: {', '.join(str(a) for a in r['aliases'])})"  # type: ignore[arg-type]
        print(line)
        if not r["set"] and r["notes"]:
            print(" " * (width + 12) + f"↳ {r['notes']}")
    return set_count, missing_count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else "")
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON instead of human report")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 if any REQUIRED variable is missing (regardless of HAWK_ENV)",
    )
    args = parser.parse_args(argv)

    required_rows = _audit(REQUIRED)
    recommended_rows = _audit(RECOMMENDED)
    optional_rows = _audit(OPTIONAL)
    is_prod = _is_production()

    missing_required = [r for r in required_rows if not r["set"]]
    missing_recommended = [r for r in recommended_rows if not r["set"]]
    missing_optional = [r for r in optional_rows if not r["set"]]

    if args.json:
        print(json.dumps({
            "production": is_prod,
            "required": required_rows,
            "recommended": recommended_rows,
            "optional": optional_rows,
            "summary": {
                "missing_required": len(missing_required),
                "missing_recommended": len(missing_recommended),
                "missing_optional": len(missing_optional),
            },
        }, indent=2, default=str))
    else:
        print("HAWK environment audit")
        print(f"  HAWK_ENV          = {os.environ.get('HAWK_ENV', '(unset)')!r}")
        print(f"  RAILWAY_ENVIRONMENT = {os.environ.get('RAILWAY_ENVIRONMENT', '(unset)')!r}")
        print(f"  ENVIRONMENT       = {os.environ.get('ENVIRONMENT', '(unset)')!r}")
        print(f"  is_production     = {is_prod}")
        _print_section("REQUIRED (production refuses to start without these)", required_rows)
        _print_section("RECOMMENDED (key features off when missing)", recommended_rows)
        _print_section("OPTIONAL (graceful degradation)", optional_rows)
        print()
        if missing_required:
            print(f"!! {len(missing_required)} REQUIRED missing:")
            for r in missing_required:
                print(f"   - {r['name']}  ({r['feature']})")
        if missing_recommended:
            print(f"-- {len(missing_recommended)} RECOMMENDED missing — feature impact:")
            for r in missing_recommended:
                print(f"   - {r['name']}: {r['feature']}")

    if (args.strict or is_prod) and missing_required:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
