"""Shared generic-email filter for the enrichment pipeline.

Role-based / unaddressed mailboxes (info@, contact@, hello@, admin@, etc.)
burn sender-domain reputation and tank reply rates.  Every enrichment path
— Prospeo, Apollo, Google-Places extraction — must treat these as "no result"
and either fall through to the next source or suppress the lead.

Centralised here so ``aria_apify_scraper``, ``aria_post_scan_pipeline``, and
``crm_charlotte_run`` share exactly the same set.
"""
from __future__ import annotations

GENERIC_EMAIL_PREFIXES: frozenset[str] = frozenset({
    "info", "contact", "hello", "hi", "support", "help", "office", "team",
    "admin", "administrator", "mail", "email", "enquiries", "enquiry",
    "inquiries", "inquiry", "sales", "marketing", "hr", "careers", "jobs",
    "billing", "accounts", "accounting", "finance", "legal", "press",
    "media", "webmaster", "postmaster", "noreply", "no-reply", "donotreply",
    "do-not-reply", "general", "frontdesk", "front-desk", "reception",
    "receptionist", "appointments", "scheduling", "booking", "service",
})


def is_generic_email(email: str) -> bool:
    """True when an email's local-part is a role-based / unaddressed mailbox.

    Matches case-insensitively and ignores ``+suffix`` aliases.
    """
    if not email or "@" not in email:
        return False
    local = email.split("@", 1)[0].strip().lower()
    if not local:
        return False
    base = local.split("+", 1)[0]
    return base in GENERIC_EMAIL_PREFIXES
