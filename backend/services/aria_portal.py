"""ARIA Phase 16 — Client-facing ARIA in the securedbyhawk.com client portal.

Limited to client-specific data and actions. Uses a client-friendly system prompt
and restricts access to only the authenticated client's own data.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()


def _sb() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def _build_client_system_prompt(client_data: dict[str, Any]) -> str:
    """Build a client-facing ARIA system prompt limited to their own data."""
    company = client_data.get("company_name", "your company")
    domain = client_data.get("domain", "")
    plan = client_data.get("plan", "")
    score = client_data.get("hawk_score")
    health = client_data.get("health_score")

    return f"""You are ARIA, the AI security advisor for {company} through the Hawk Security client portal.

**Your role**: Help {company} understand their security posture, explain findings, provide remediation guidance, and answer questions about their Hawk Security services.

**Client context**:
- Company: {company}
- Domain: {domain}
- Plan: {plan}
- Latest HAWK Score: {score}/100
- Health Score: {health}
- Today: {datetime.now(timezone.utc).strftime('%B %d, %Y')}

**Rules**:
- Only discuss this client's own data. Never reference other clients or internal Hawk operations.
- Be helpful, professional, and security-focused.
- Explain technical findings in plain language.
- Reference the US regulatory angle appropriate to the client's vertical when relevant: HIPAA Security Rule + OCR breach notification (dental / medical), FTC Safeguards Rule + May 2024 breach-notification amendment (CPA / tax), ABA Formal Opinion 24-514 (legal). Do not reference PIPEDA, CASL, or Canadian-only regulators.
- If asked about pricing or upgrades, mention (USD): HAWK Core $249/mo, HAWK Guard $449/mo, HAWK Sentinel $799/mo. Core includes the Breach Response Guarantee ($250K), Guard raises it to $1M, Sentinel to $2.5M.
- For urgent security issues, recommend contacting Hawk support directly.
- Never share internal Hawk processes, VA team details, or pipeline information.
- Be concise and actionable. Prefer numbered steps for remediation."""


def get_client_context(portal_user_id: str) -> dict[str, Any] | None:
    """Load client context from portal user ID."""
    if not SUPABASE_URL or not SERVICE_KEY:
        return None

    # Get client portal profile
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_portal_profiles",
        headers=_sb(),
        params={
            "user_id": f"eq.{portal_user_id}",
            "select": "client_id,company_name,domain,email",
            "limit": "1",
        },
        timeout=20.0,
    )
    cpp = (r.json() or [None])[0] if r.status_code < 400 else None
    if not cpp:
        return None

    client_id = cpp["client_id"]

    # Get client record
    cr = httpx.get(
        f"{SUPABASE_URL}/rest/v1/clients",
        headers=_sb(),
        params={
            "id": f"eq.{client_id}",
            "select": "id,prospect_id,plan,mrr_cents,hawk_readiness_score,guarantee_status,status",
            "limit": "1",
        },
        timeout=20.0,
    )
    client = (cr.json() or [None])[0] if cr.status_code < 400 else None

    # Get latest scan
    scan = None
    pid = client.get("prospect_id") if client else None
    if pid:
        sr = httpx.get(
            f"{SUPABASE_URL}/rest/v1/crm_prospect_scans",
            headers=_sb(),
            params={
                "prospect_id": f"eq.{pid}",
                "select": "hawk_score,grade,findings,created_at",
                "order": "created_at.desc",
                "limit": "1",
            },
            timeout=20.0,
        )
        scan = (sr.json() or [None])[0] if sr.status_code < 400 else None

    # Get health score
    health = None
    if client_id:
        hr = httpx.get(
            f"{SUPABASE_URL}/rest/v1/aria_client_health_scores",
            headers=_sb(),
            params={
                "client_id": f"eq.{client_id}",
                "select": "score,factors,at_risk",
                "order": "updated_at.desc",
                "limit": "1",
            },
            timeout=20.0,
        )
        health = (hr.json() or [None])[0] if hr.status_code < 400 else None

    return {
        "client_id": client_id,
        "company_name": cpp.get("company_name", ""),
        "domain": cpp.get("domain", ""),
        "email": cpp.get("email", ""),
        "plan": client.get("plan", "") if client else "",
        "hawk_score": scan.get("hawk_score") if scan else None,
        "health_score": health.get("score") if health else None,
        "scan": scan,
        "health": health,
    }


def portal_aria_chat(
    portal_user_id: str,
    message: str,
    conversation_history: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Handle a chat message from a portal client."""
    if not OPENAI_API_KEY:
        return {"reply": "ARIA is not configured yet. Please contact Hawk Security support."}

    client_data = get_client_context(portal_user_id)
    if not client_data:
        return {"reply": "I couldn't find your account. Please contact Hawk Security support."}

    system_prompt = _build_client_system_prompt(client_data)

    # Add scan findings context if available
    scan = client_data.get("scan")
    if scan and scan.get("findings"):
        findings = scan["findings"]
        if isinstance(findings, dict):
            fl = findings.get("findings", [])
            if isinstance(fl, list) and fl:
                finding_lines = []
                for f in fl[:20]:
                    if isinstance(f, dict):
                        sev = f.get("severity", "")
                        title = f.get("title", "")
                        finding_lines.append(f"- [{sev}] {title}")
                if finding_lines:
                    system_prompt += f"\n\n**Current findings on {client_data['domain']}**:\n" + "\n".join(finding_lines)

    try:
        from services.openai_chat import chat_text_sync

        user_messages: list[dict[str, str]] = []

        for h in (conversation_history or [])[-10:]:
            role = h.get("role", "user")
            if role in ("user", "assistant"):
                user_messages.append({"role": role, "content": h.get("content", "")})

        user_messages.append({"role": "user", "content": message})

        reply = chat_text_sync(
            api_key=OPENAI_API_KEY,
            system=system_prompt,
            user_messages=user_messages,
            max_tokens=1500,
        )
        return {"reply": reply, "client_id": client_data["client_id"]}
    except Exception as exc:
        logger.exception("Portal ARIA chat failed: %s", exc)
        return {"reply": "I'm having trouble right now. Please try again in a moment."}
