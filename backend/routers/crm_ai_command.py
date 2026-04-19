"""CRM — AI Command Center API endpoints (function calling + chat persistence)."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from config import SUPABASE_URL, OPENAI_API_KEY, OPENAI_MODEL, RESEND_API_KEY
from routers.crm_auth import require_supabase_uid
from services.crm_portal_email import send_resend, _wrap, _esc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/crm/ai", tags=["crm-ai-command"])

SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def _get_profile(uid: str) -> dict[str, Any] | None:
    if not SUPABASE_URL or not SERVICE_KEY:
        return None
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=_sb_headers(),
        params={"id": f"eq.{uid}", "select": "*", "limit": "1"},
        timeout=20.0,
    )
    r.raise_for_status()
    rows = r.json()
    return rows[0] if rows else None


# ── Role-based access ─────────────────────────────────────────────────────

ALLOWED_ROLES = {"ceo", "hos", "team_lead"}
ALLOWED_ROLE_TYPES = {"ceo", "va_manager"}


def _require_ai_access(uid: str) -> dict[str, Any]:
    """Ensure user has access to AI Command Center. Returns profile."""
    prof = _get_profile(uid)
    if not prof:
        raise HTTPException(status_code=403, detail="Profile not found")
    role = prof.get("role", "")
    role_type = prof.get("role_type", "")
    if role not in ALLOWED_ROLES and role_type not in ALLOWED_ROLE_TYPES:
        raise HTTPException(status_code=403, detail="AI Command Center access denied")
    return prof


# ── Data access levels per role ───────────────────────────────────────────

def _get_role_permissions(profile: dict[str, Any]) -> dict[str, bool]:
    role = profile.get("role", "")
    role_type = profile.get("role_type", "")

    if role == "ceo":
        return {
            "va_data": True, "prospect_data": True, "client_data": True,
            "financials": True, "reports": True, "team_data": True,
            "onboarding": True, "send_email": True, "manage_team": True,
            "generate_docs": True, "schedule_actions": True,
        }
    elif role in ("hos", "team_lead"):
        return {
            "va_data": False, "prospect_data": True, "client_data": True,
            "financials": False, "reports": True, "team_data": True,
            "onboarding": False, "send_email": True, "manage_team": False,
            "generate_docs": True, "schedule_actions": True,
        }
    elif role_type == "va_manager":
        return {
            "va_data": True, "prospect_data": False, "client_data": False,
            "financials": False, "reports": True, "team_data": True,
            "onboarding": False, "send_email": True, "manage_team": True,
            "generate_docs": True, "schedule_actions": True,
        }
    else:
        return {
            "va_data": False, "prospect_data": False, "client_data": False,
            "financials": False, "reports": False, "team_data": False,
            "onboarding": False, "send_email": False, "manage_team": False,
            "generate_docs": False, "schedule_actions": False,
        }


# ── OpenAI function definitions ───────────────────────────────────────────

FUNCTION_DEFINITIONS = [
    {
        "name": "get_va_performance_report",
        "description": "Pull VA performance data for a given week. Optionally filter by VA ID.",
        "parameters": {
            "type": "object",
            "properties": {
                "week": {"type": "string", "description": "ISO week string, e.g. '2026-W15'"},
                "va_id": {"type": "string", "description": "Optional specific VA profile ID"},
            },
            "required": ["week"],
        },
    },
    {
        "name": "send_email",
        "description": "Send an email to a team member or prospect via the HAWK email system.",
        "parameters": {
            "type": "object",
            "properties": {
                "to": {"type": "string", "description": "Email address"},
                "subject": {"type": "string", "description": "Email subject"},
                "body": {"type": "string", "description": "Email body in plain text"},
            },
            "required": ["to", "subject", "body"],
        },
    },
    {
        "name": "schedule_action",
        "description": "Schedule an action to be executed at a future time.",
        "parameters": {
            "type": "object",
            "properties": {
                "action_type": {"type": "string", "description": "Type of action: send_email, send_reminder"},
                "payload": {"type": "object", "description": "Action payload data"},
                "scheduled_for": {"type": "string", "description": "ISO timestamp for execution"},
            },
            "required": ["action_type", "payload", "scheduled_for"],
        },
    },
    {
        "name": "generate_document",
        "description": "Generate a document (PDF) such as a report, PIP, coaching note, or contract.",
        "parameters": {
            "type": "object",
            "properties": {
                "type": {"type": "string", "description": "Document type: report, pip, coaching_note, weekly_summary, contract"},
                "data": {"type": "object", "description": "Data for the document"},
            },
            "required": ["type", "data"],
        },
    },
    {
        "name": "get_pipeline_summary",
        "description": "Get current pipeline health summary with stage counts and projected MRR.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "approve_onboarding",
        "description": "Approve a pending onboarding submission.",
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {"type": "string", "description": "Onboarding session ID"},
            },
            "required": ["session_id"],
        },
    },
    {
        "name": "flag_va_for_pip",
        "description": "Flag a VA for a Performance Improvement Plan with a reason.",
        "parameters": {
            "type": "object",
            "properties": {
                "va_id": {"type": "string", "description": "VA profile ID"},
                "reason": {"type": "string", "description": "Reason for the PIP"},
            },
            "required": ["va_id", "reason"],
        },
    },
    {
        "name": "get_client_mrr_summary",
        "description": "Get total MRR, client count, and breakdown by plan.",
        "parameters": {"type": "object", "properties": {}},
    },
    # ── Phase 1: Outbound pipeline ────────────────────────────────────────
    {
        "name": "run_outbound_pipeline",
        "description": "Run the full ARIA outbound pipeline: Apollo lead pull, Clay enrichment, ZeroBounce verification, Hawk domain scan, personalized email generation, and Smartlead loading. Requires vertical and location.",
        "parameters": {
            "type": "object",
            "properties": {
                "vertical": {"type": "string", "description": "Target vertical: dental, legal, or accounting"},
                "location": {"type": "string", "description": "Geographic location, e.g. 'Toronto, Canada' or 'Ontario'"},
                "batch_size": {"type": "integer", "description": "Number of leads to pull (default 50)"},
            },
            "required": ["vertical", "location"],
        },
    },
    {
        "name": "get_pipeline_run_status",
        "description": "Get live status of a running or completed pipeline run.",
        "parameters": {
            "type": "object",
            "properties": {
                "run_id": {"type": "string", "description": "Pipeline run ID"},
            },
            "required": ["run_id"],
        },
    },
    # ── Phase 9: Pattern learning ─────────────────────────────────────────
    {
        "name": "detect_business_patterns",
        "description": "Analyze CRM data to detect business patterns, trends, and insights. Returns actionable patterns with confidence scores.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_recent_patterns",
        "description": "Get recently detected business patterns and insights.",
        "parameters": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Max patterns to return (default 10)"},
            },
        },
    },
    # ── Phase 10: A/B testing ─────────────────────────────────────────────
    {
        "name": "create_ab_experiment",
        "description": "Create an A/B test experiment for email campaigns with two subject/body variants.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Experiment name"},
                "variant_a_subject": {"type": "string", "description": "Subject line for variant A"},
                "variant_b_subject": {"type": "string", "description": "Subject line for variant B"},
                "variant_a_body": {"type": "string", "description": "Email body for variant A"},
                "variant_b_body": {"type": "string", "description": "Email body for variant B"},
                "campaign_id": {"type": "string", "description": "Optional Smartlead campaign ID"},
            },
            "required": ["name", "variant_a_subject", "variant_b_subject", "variant_a_body", "variant_b_body"],
        },
    },
    {
        "name": "generate_ab_variants",
        "description": "Use AI to generate A/B test variants from an original email.",
        "parameters": {
            "type": "object",
            "properties": {
                "original_subject": {"type": "string", "description": "Original email subject"},
                "original_body": {"type": "string", "description": "Original email body"},
                "test_element": {"type": "string", "description": "Element to test: subject, body, cta, tone"},
            },
            "required": ["original_subject", "original_body"],
        },
    },
    {
        "name": "list_ab_experiments",
        "description": "List recent A/B test experiments and their status.",
        "parameters": {"type": "object", "properties": {}},
    },
    # ── Phase 11: Competitive intelligence ────────────────────────────────
    {
        "name": "research_competitors",
        "description": "Research competitors and market landscape for Hawk Security. Provides pricing analysis, strengths/weaknesses, and opportunities.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Optional specific research question"},
            },
        },
    },
    {
        "name": "analyze_competitor_pricing",
        "description": "Analyze competitor pricing for a specific vertical (dental, legal, accounting).",
        "parameters": {
            "type": "object",
            "properties": {
                "vertical": {"type": "string", "description": "Target vertical: dental, legal, or accounting"},
            },
            "required": ["vertical"],
        },
    },
    # ── Phase 12: File/image intelligence ─────────────────────────────────
    {
        "name": "analyze_document",
        "description": "Analyze a document's text content. Supports contracts, compliance docs, reports, and email threads.",
        "parameters": {
            "type": "object",
            "properties": {
                "text_content": {"type": "string", "description": "The document text to analyze"},
                "doc_type": {"type": "string", "description": "Type: general, contract, compliance, report, email_thread"},
                "prompt": {"type": "string", "description": "Optional specific analysis prompt"},
            },
            "required": ["text_content"],
        },
    },
    # ── Phase 14: Sales playbook ──────────────────────────────────────────
    {
        "name": "build_sales_playbook",
        "description": "Analyze won/lost deals, activities, and replies to build a comprehensive sales playbook with ICP, objection handlers, and email templates.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "get_objection_handler",
        "description": "Get a ready-to-use response for a specific prospect objection using the sales playbook.",
        "parameters": {
            "type": "object",
            "properties": {
                "objection": {"type": "string", "description": "The prospect's objection text"},
            },
            "required": ["objection"],
        },
    },
    # ── Phase 15: CEO Dashboard ───────────────────────────────────────────
    {
        "name": "get_ceo_dashboard",
        "description": "Get the God Mode CEO dashboard with all KPIs: revenue, pipeline, activity, client health, and team metrics with AI narration.",
        "parameters": {"type": "object", "properties": {}},
    },
    # ── Phase 19: Onboarding trainer ──────────────────────────────────────
    {
        "name": "start_training_session",
        "description": "Start an interactive sales training roleplay session. Scenarios: cold_call, objection_handling, discovery_call, product_demo, upsell, product_knowledge.",
        "parameters": {
            "type": "object",
            "properties": {
                "scenario_type": {"type": "string", "description": "Type of scenario: cold_call, objection_handling, discovery_call, product_demo, upsell, product_knowledge"},
            },
            "required": ["scenario_type"],
        },
    },
    {
        "name": "list_training_scenarios",
        "description": "List available training roleplay scenarios.",
        "parameters": {"type": "object", "properties": {}},
    },
]


def _filter_functions_for_role(permissions: dict[str, bool]) -> list[dict]:
    """Filter available functions based on role permissions."""
    available = []
    for fn in FUNCTION_DEFINITIONS:
        name = fn["name"]
        if name == "get_va_performance_report" and not permissions.get("va_data"):
            continue
        if name == "send_email" and not permissions.get("send_email"):
            continue
        if name == "schedule_action" and not permissions.get("schedule_actions"):
            continue
        if name == "generate_document" and not permissions.get("generate_docs"):
            continue
        if name == "get_pipeline_summary" and not permissions.get("prospect_data"):
            continue
        if name == "approve_onboarding" and not permissions.get("onboarding"):
            continue
        if name == "flag_va_for_pip" and not permissions.get("manage_team"):
            continue
        if name == "get_client_mrr_summary" and not permissions.get("financials"):
            continue
        # Phase 9: patterns require reports permission
        if name in ("detect_business_patterns", "get_recent_patterns") and not permissions.get("reports"):
            continue
        # Phase 1: pipeline requires prospect_data
        if name in ("run_outbound_pipeline", "get_pipeline_run_status") and not permissions.get("prospect_data"):
            continue
        # Phase 10: A/B testing requires prospect_data
        if name in ("create_ab_experiment", "generate_ab_variants", "list_ab_experiments") and not permissions.get("prospect_data"):
            continue
        # Phase 11: competitive intel requires reports
        if name in ("research_competitors", "analyze_competitor_pricing") and not permissions.get("reports"):
            continue
        # Phase 12: document analysis requires reports
        if name == "analyze_document" and not permissions.get("reports"):
            continue
        # Phase 14: playbook requires prospect_data
        if name in ("build_sales_playbook", "get_objection_handler") and not permissions.get("prospect_data"):
            continue
        # Phase 15: CEO dashboard requires financials
        if name == "get_ceo_dashboard" and not permissions.get("financials"):
            continue
        # Phase 19: training available to all with AI access
        available.append(fn)
    return available


# ── Function execution ────────────────────────────────────────────────────

def _execute_function(
    name: str, args: dict[str, Any], uid: str, permissions: dict[str, bool]
) -> str:
    """Execute an AI function and return the result as a string."""
    headers = _sb_headers()

    try:
        if name == "get_va_performance_report":
            return _fn_get_va_performance(args, headers)
        elif name == "send_email":
            return _fn_send_email(args, uid)
        elif name == "schedule_action":
            return _fn_schedule_action(args, uid, headers)
        elif name == "generate_document":
            return _fn_generate_document(args)
        elif name == "get_pipeline_summary":
            return _fn_get_pipeline_summary(headers)
        elif name == "approve_onboarding":
            return _fn_approve_onboarding(args, uid, headers)
        elif name == "flag_va_for_pip":
            return _fn_flag_va_for_pip(args, uid, headers)
        elif name == "get_client_mrr_summary":
            return _fn_get_client_mrr_summary(headers)
        # ── Phase 1: Outbound pipeline ────────────────────────────────
        elif name == "run_outbound_pipeline":
            from services.aria_apify_scraper import canonical_vertical
            from services.aria_pipeline import run_outbound_pipeline as _run_pipeline

            vertical = canonical_vertical(str(args.get("vertical", "dental")))
            location = args.get("location", "")
            batch_size = args.get("batch_size", 50)
            # Create the pipeline run record first
            run_payload = {
                "triggered_by": uid,
                "vertical": vertical,
                "location": location,
                "status": "running",
                "current_step": "initializing",
                "started_at": datetime.now(timezone.utc).isoformat(),
            }
            r = httpx.post(
                f"{SUPABASE_URL}/rest/v1/aria_pipeline_runs",
                headers={**headers, "Prefer": "return=representation"},
                json=run_payload,
                timeout=20.0,
            )
            if r.status_code >= 400:
                return json.dumps({"error": "Failed to create pipeline run", "detail": r.text[:300]})
            run_row = r.json()[0] if isinstance(r.json(), list) else r.json()
            run_id = run_row["id"]
            result = _run_pipeline(run_id, vertical, location, batch_size)
            return json.dumps(result)
        elif name == "get_pipeline_run_status":
            from services.aria_pipeline import _build_summary
            return json.dumps(_build_summary(args.get("run_id", "")))
        # ── Phase 9: Pattern learning ────────────────────────────────
        elif name == "detect_business_patterns":
            from services.aria_patterns import run_pattern_detection
            return json.dumps(run_pattern_detection())
        elif name == "get_recent_patterns":
            from services.aria_patterns import get_recent_patterns
            limit = args.get("limit", 10)
            return json.dumps(get_recent_patterns(limit=limit))
        # ── Phase 10: A/B testing ────────────────────────────────────
        elif name == "create_ab_experiment":
            from services.aria_ab_testing import create_ab_experiment
            return json.dumps(create_ab_experiment(
                name=args.get("name", ""),
                variant_a_subject=args.get("variant_a_subject", ""),
                variant_b_subject=args.get("variant_b_subject", ""),
                variant_a_body=args.get("variant_a_body", ""),
                variant_b_body=args.get("variant_b_body", ""),
                campaign_id=args.get("campaign_id"),
            ))
        elif name == "generate_ab_variants":
            from services.aria_ab_testing import generate_variants
            return json.dumps(generate_variants(
                original_subject=args.get("original_subject", ""),
                original_body=args.get("original_body", ""),
                test_element=args.get("test_element", "subject"),
            ))
        elif name == "list_ab_experiments":
            from services.aria_ab_testing import list_experiments
            return json.dumps(list_experiments())
        # ── Phase 11: Competitive intelligence ───────────────────────
        elif name == "research_competitors":
            from services.aria_competitive_intel import research_competitors
            return json.dumps(research_competitors(query=args.get("query")))
        elif name == "analyze_competitor_pricing":
            from services.aria_competitive_intel import analyze_competitor_pricing
            return json.dumps(analyze_competitor_pricing(vertical=args.get("vertical", "dental")))
        # ── Phase 12: Document analysis ──────────────────────────────
        elif name == "analyze_document":
            from services.aria_vision import analyze_document_text
            return json.dumps(analyze_document_text(
                text_content=args.get("text_content", ""),
                doc_type=args.get("doc_type", "general"),
                prompt=args.get("prompt"),
            ))
        # ── Phase 14: Sales playbook ─────────────────────────────────
        elif name == "build_sales_playbook":
            from services.aria_playbook import build_playbook_from_deals
            return json.dumps(build_playbook_from_deals())
        elif name == "get_objection_handler":
            from services.aria_playbook import get_objection_handler
            return json.dumps(get_objection_handler(objection=args.get("objection", "")))
        # ── Phase 15: CEO Dashboard ──────────────────────────────────
        elif name == "get_ceo_dashboard":
            from services.aria_ceo_dashboard import get_dashboard_data, generate_narration
            data = get_dashboard_data()
            narration = generate_narration(data)
            return json.dumps({"dashboard": data, "narration": narration})
        # ── Phase 19: Training ───────────────────────────────────────
        elif name == "start_training_session":
            from services.aria_onboarding_trainer import start_training_session
            return json.dumps(start_training_session(
                user_id=uid,
                scenario_type=args.get("scenario_type", "cold_call"),
            ))
        elif name == "list_training_scenarios":
            from services.aria_onboarding_trainer import list_scenarios
            return json.dumps(list_scenarios())
        else:
            return json.dumps({"error": f"Unknown function: {name}"})
    except Exception as exc:
        logger.exception("Function execution failed: %s", exc)
        return json.dumps({"error": str(exc)})


def _fn_get_va_performance(args: dict[str, Any], headers: dict[str, str]) -> str:
    params: dict[str, str] = {
        "select": "id,full_name,email,role_type,health_score,status",
        "role_type": "eq.va_outreach",
        "limit": "50",
    }
    va_id = args.get("va_id")
    if va_id:
        params["id"] = f"eq.{va_id}"

    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=headers,
        params=params,
        timeout=20.0,
    )
    r.raise_for_status()
    return json.dumps({"week": args.get("week"), "vas": r.json()})


def _fn_send_email(args: dict[str, Any], uid: str) -> str:
    to = args.get("to", "")
    subject = args.get("subject", "")
    body_text = args.get("body", "")

    if not to or not subject:
        return json.dumps({"error": "Missing 'to' or 'subject'"})

    inner = f"""
      <tr>
        <td style="padding:40px 48px 32px;">
          <p style="margin:0 0 24px;font-size:15px;color:#9090A8;line-height:1.6;">
            {_esc(body_text)}
          </p>
        </td>
      </tr>
"""
    result = send_resend(
        to_email=to,
        subject=subject,
        html=_wrap(inner),
        tags=[{"name": "category", "value": "ai_command_email"}],
    )

    # Log the action
    _log_action(uid, "send_email", args, "sent")

    return json.dumps({"sent": True, "to": to})


def _fn_schedule_action(args: dict[str, Any], uid: str, headers: dict[str, str]) -> str:
    payload = {
        "triggered_by": uid,
        "action_type": args.get("action_type", ""),
        "action_payload": args.get("payload", {}),
        "scheduled_for": args.get("scheduled_for", ""),
    }
    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/aria_scheduled_actions",
        headers={**headers, "Prefer": "return=representation"},
        json=payload,
        timeout=20.0,
    )
    if r.status_code >= 400:
        return json.dumps({"error": r.text[:300]})

    _log_action(uid, "schedule_action", args, "scheduled")
    return json.dumps({"scheduled": True, "scheduled_for": args.get("scheduled_for")})


def _fn_generate_document(args: dict[str, Any]) -> str:
    doc_type = args.get("type", "report")
    data = args.get("data", {})
    # For now, return a summary — PDF generation will be added as a separate download endpoint
    return json.dumps({
        "generated": True,
        "type": doc_type,
        "note": f"Document of type '{doc_type}' has been prepared. Use the download button to get the PDF.",
        "data_summary": str(data)[:500],
    })


def _fn_get_pipeline_summary(headers: dict[str, str]) -> str:
    stages = ["new", "scanned", "loom_sent", "replied", "call_booked", "proposal_sent", "closed_won", "lost"]
    result: dict[str, Any] = {"stages": {}, "total": 0}

    for stage in stages:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers={**headers, "Prefer": "count=exact"},
            params={"stage": f"eq.{stage}", "select": "id", "limit": "0"},
            timeout=15.0,
        )
        count = 0
        content_range = r.headers.get("content-range", "")
        if "/" in content_range:
            try:
                count = int(content_range.split("/")[1])
            except (ValueError, IndexError):
                pass
        result["stages"][stage] = count
        result["total"] += count

    return json.dumps(result)


def _fn_approve_onboarding(args: dict[str, Any], uid: str, headers: dict[str, str]) -> str:
    session_id = args.get("session_id", "")
    if not session_id:
        return json.dumps({"error": "session_id required"})

    now = datetime.now(timezone.utc).isoformat()
    # Get session
    sr = httpx.get(
        f"{SUPABASE_URL}/rest/v1/onboarding_sessions",
        headers=headers,
        params={"id": f"eq.{session_id}", "select": "id,profile_id,status", "limit": "1"},
        timeout=20.0,
    )
    sessions = sr.json() if sr.status_code == 200 else []
    if not sessions:
        return json.dumps({"error": "Session not found"})
    session = sessions[0]

    if session["status"] != "pending_review":
        return json.dumps({"error": "Session is not pending review"})

    httpx.patch(
        f"{SUPABASE_URL}/rest/v1/onboarding_sessions",
        headers=headers,
        params={"id": f"eq.{session_id}"},
        json={"status": "approved", "approved_by": uid, "approved_at": now},
        timeout=20.0,
    ).raise_for_status()

    httpx.patch(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=headers,
        params={"id": f"eq.{session['profile_id']}"},
        json={"onboarding_status": "approved", "status": "active"},
        timeout=20.0,
    ).raise_for_status()

    _log_action(uid, "approve_onboarding", args, "approved")
    return json.dumps({"approved": True, "session_id": session_id})


def _fn_flag_va_for_pip(args: dict[str, Any], uid: str, headers: dict[str, str]) -> str:
    va_id = args.get("va_id", "")
    reason = args.get("reason", "")
    if not va_id:
        return json.dumps({"error": "va_id required"})

    # Check VA exists
    vr = httpx.get(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=headers,
        params={"id": f"eq.{va_id}", "select": "id,full_name,role_type", "limit": "1"},
        timeout=20.0,
    )
    vas = vr.json() if vr.status_code == 200 else []
    if not vas:
        return json.dumps({"error": "VA not found"})

    # Flag as at_risk
    httpx.patch(
        f"{SUPABASE_URL}/rest/v1/profiles",
        headers=headers,
        params={"id": f"eq.{va_id}"},
        json={"status": "at_risk"},
        timeout=20.0,
    )

    _log_action(uid, "flag_va_for_pip", args, f"flagged: {reason}")
    return json.dumps({"flagged": True, "va_id": va_id, "va_name": vas[0].get("full_name", "")})


def _fn_get_client_mrr_summary(headers: dict[str, str]) -> str:
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/clients",
        headers=headers,
        params={"status": "eq.active", "select": "id,plan,mrr_cents", "limit": "500"},
        timeout=20.0,
    )
    r.raise_for_status()
    clients = r.json()

    total_mrr = sum(c.get("mrr_cents", 0) for c in clients)
    by_plan: dict[str, int] = {}
    for c in clients:
        plan = c.get("plan") or "unknown"
        by_plan[plan] = by_plan.get(plan, 0) + 1

    return json.dumps({
        "total_clients": len(clients),
        "total_mrr_cents": total_mrr,
        "total_mrr_dollars": total_mrr / 100,
        "by_plan": by_plan,
    })


def _log_action(uid: str, action_type: str, payload: dict, result: str) -> None:
    """Log AI action to aria_action_log."""
    try:
        httpx.post(
            f"{SUPABASE_URL}/rest/v1/aria_action_log",
            headers=_sb_headers(),
            json={
                "triggered_by": uid,
                "action_type": action_type,
                "action_payload": payload,
                "action_result": result,
            },
            timeout=15.0,
        )
    except Exception as exc:
        logger.exception("Failed to log AI action: %s", exc)


# ── Chat endpoints ────────────────────────────────────────────────────────

class CreateConversationBody(BaseModel):
    title: str | None = None


@router.post("/conversations")
def create_conversation(body: CreateConversationBody, uid: str = Depends(require_supabase_uid)):
    """Create a new AI Command Center conversation."""
    prof = _require_ai_access(uid)
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    headers = _sb_headers()
    payload = {
        "user_id": uid,
        "title": body.title or "New conversation",
    }
    r = httpx.post(
        f"{SUPABASE_URL}/rest/v1/aria_conversations",
        headers={**headers, "Prefer": "return=representation"},
        json=payload,
        timeout=20.0,
    )
    if r.status_code >= 400:
        raise HTTPException(status_code=400, detail=r.text[:500])
    created = r.json()
    return created[0] if isinstance(created, list) else created


@router.get("/conversations")
def list_conversations(uid: str = Depends(require_supabase_uid)):
    """List user's AI Command Center conversations."""
    _require_ai_access(uid)
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/aria_conversations",
        headers=_sb_headers(),
        params={
            "user_id": f"eq.{uid}",
            "select": "id,title,created_at,updated_at",
            "order": "updated_at.desc",
            "limit": "50",
        },
        timeout=20.0,
    )
    r.raise_for_status()
    return r.json()


@router.get("/conversations/{conversation_id}/messages")
def get_messages(conversation_id: str, uid: str = Depends(require_supabase_uid)):
    """Get messages for a conversation."""
    _require_ai_access(uid)
    if not SUPABASE_URL or not SERVICE_KEY:
        raise HTTPException(status_code=503, detail="Supabase not configured")

    # Verify ownership
    headers = _sb_headers()
    cr = httpx.get(
        f"{SUPABASE_URL}/rest/v1/aria_conversations",
        headers=headers,
        params={"id": f"eq.{conversation_id}", "user_id": f"eq.{uid}", "select": "id", "limit": "1"},
        timeout=20.0,
    )
    if not cr.json():
        raise HTTPException(status_code=404, detail="Conversation not found")

    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/aria_messages",
        headers=headers,
        params={
            "conversation_id": f"eq.{conversation_id}",
            "select": "*",
            "order": "created_at.asc",
            "limit": "200",
        },
        timeout=20.0,
    )
    r.raise_for_status()
    return r.json()


# ── Briefing endpoints ────────────────────────────────────────────────────


@router.get("/briefings/unread")
def get_unread_briefings(uid: str = Depends(require_supabase_uid)):
    """Return unread proactive briefings for the authenticated user."""
    _require_ai_access(uid)
    headers = _sb_headers()
    r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/aria_proactive_briefings",
        headers=headers,
        params={
            "user_id": f"eq.{uid}",
            "read": "eq.false",
            "select": "id,briefing_date,content,created_at",
            "order": "created_at.desc",
            "limit": "10",
        },
        timeout=15.0,
    )
    if r.status_code >= 400:
        return []
    return r.json()


@router.post("/briefings/{briefing_id}/read")
def mark_briefing_read(briefing_id: str, uid: str = Depends(require_supabase_uid)):
    """Mark a briefing as read for the authenticated user."""
    _require_ai_access(uid)
    headers = _sb_headers()
    r = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/aria_proactive_briefings",
        headers=headers,
        params={
            "id": f"eq.{briefing_id}",
            "user_id": f"eq.{uid}",
        },
        json={"read": True},
        timeout=15.0,
    )
    if r.status_code >= 400:
        raise HTTPException(status_code=400, detail="Failed to mark briefing as read")
    return {"ok": True}


@router.get("/dashboard")
def get_ceo_dashboard(uid: str = Depends(require_supabase_uid)):
    """Dedicated CEO dashboard endpoint — returns structured KPI data + narration."""
    prof = _require_ai_access(uid)
    role = prof.get("role", "")
    if role != "ceo":
        raise HTTPException(status_code=403, detail="CEO-only endpoint")

    from services.aria_ceo_dashboard import get_dashboard_data, generate_narration

    dashboard = get_dashboard_data()
    if "error" in dashboard:
        raise HTTPException(status_code=503, detail=dashboard["error"])

    narration = generate_narration(dashboard)
    return {"dashboard": dashboard, "narration": narration}


class AnalyzeFileBody(BaseModel):
    content: str
    image_data: str | None = None


@router.post("/analyze-file")
def analyze_file(body: AnalyzeFileBody, uid: str = Depends(require_supabase_uid)):
    """Dedicated file/image analysis endpoint — no conversation required."""
    _require_ai_access(uid)

    from services.aria_vision import analyze_image, analyze_document_text

    if body.image_data:
        # image_data is a data URL like "data:image/png;base64,..."
        import base64 as b64mod

        try:
            header, encoded = body.image_data.split(",", 1)
            mime = header.split(":")[1].split(";")[0] if ":" in header else "image/png"
            raw = b64mod.b64decode(encoded)
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid image data")

        result = analyze_image(raw, prompt=body.content, mime_type=mime)
    else:
        # Text/CSV document analysis
        doc_type = "report" if "report" in body.content.lower() or "csv" in body.content.lower() else "general"
        result = analyze_document_text(body.content, doc_type=doc_type)

    if "error" in result:
        raise HTTPException(status_code=503, detail=result["error"])

    return {"reply": result.get("analysis", "Analysis complete.")}


class SendMessageBody(BaseModel):
    conversation_id: str
    content: str


@router.post("/chat")
def ai_command_chat(body: SendMessageBody, uid: str = Depends(require_supabase_uid)):
    """Send a message to the AI Command Center and get a response."""
    if not OPENAI_API_KEY:
        raise HTTPException(status_code=503, detail="OpenAI not configured")

    prof = _require_ai_access(uid)
    permissions = _get_role_permissions(prof)
    headers = _sb_headers()

    # Verify conversation ownership
    cr = httpx.get(
        f"{SUPABASE_URL}/rest/v1/aria_conversations",
        headers=headers,
        params={"id": f"eq.{body.conversation_id}", "user_id": f"eq.{uid}", "select": "id", "limit": "1"},
        timeout=20.0,
    )
    if not cr.json():
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Save user message
    httpx.post(
        f"{SUPABASE_URL}/rest/v1/aria_messages",
        headers=headers,
        json={
            "conversation_id": body.conversation_id,
            "role": "user",
            "content": body.content,
        },
        timeout=20.0,
    )

    # Get conversation history
    hist_r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/aria_messages",
        headers=headers,
        params={
            "conversation_id": f"eq.{body.conversation_id}",
            "select": "role,content,function_name,function_result",
            "order": "created_at.asc",
            "limit": "50",
        },
        timeout=20.0,
    )
    history = hist_r.json() if hist_r.status_code == 200 else []

    # Build messages for OpenAI
    role_name = prof.get("role", "")
    role_type = prof.get("role_type", "")
    user_name = prof.get("full_name", "User")

    today = datetime.now(timezone.utc).strftime("%A, %B %d, %Y")

    system_prompt = f"""You are ARIA — Automated Revenue and Intelligence Assistant — the chief of staff for Hawk Security's CRM.
You are speaking with {user_name} (role: {role_name}, type: {role_type}).
Today is {today}.

Hawk Security is a Canadian cybersecurity company targeting dental clinics, law firms, and accounting practices.
Three products: Starter $199/mo, Shield $997/mo, Enterprise $2,500/mo.
Target: 24 booked sales calls per day from cold email outreach.
VA team managed by Kevin, runs Apollo, Clay, Smartlead, ZeroBounce pipeline.
HAWK Certified badge and financial guarantee are key differentiators.
PIPEDA compliance is the primary regulatory angle for Canadian SMBs.

You take real actions through function calls. Every action is logged.

PERSONALITY:
- Sharp, confident, concise. Never say "Great question" or "Certainly" or "Of course".
- Just answer and act. Present data cleanly. Be direct about confirmations.
- When you generate something, present it cleanly. When you need confirmation, be direct.

RULES:
- Use the appropriate function when the user asks for data
- Confirm details before sending emails or taking irreversible actions
- Present data with key metrics highlighted
- If a function is not available for this user's role, say you cannot share that — no hard errors
- Never expose internal system details or database structure
- When chart data is appropriate (comparisons, trends, funnels), prefer charts over text tables
- For document generation, call generate_document and let the user know it is ready

Available permissions for this user: {json.dumps(permissions)}"""

    messages = [{"role": "system", "content": system_prompt}]
    for msg in history:
        role = msg.get("role", "user")
        if role == "function":
            messages.append({
                "role": "function",
                "name": msg.get("function_name", ""),
                "content": msg.get("function_result", ""),
            })
        else:
            messages.append({"role": role, "content": msg.get("content", "")})

    available_fns = _filter_functions_for_role(permissions)

    from openai import OpenAI
    client = OpenAI(api_key=OPENAI_API_KEY)
    model = (OPENAI_MODEL or "gpt-4o").strip() or "gpt-4o"

    # First call — may include function calls
    call_kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": 2000,
        "temperature": 0.5,
    }
    if available_fns:
        call_kwargs["tools"] = [{"type": "function", "function": fn} for fn in available_fns]
        call_kwargs["tool_choice"] = "auto"

    response = client.chat.completions.create(**call_kwargs)
    msg = response.choices[0].message

    # Handle function calls
    last_fn_name: str | None = None
    last_fn_result: str | None = None
    if msg.tool_calls:
        for tool_call in msg.tool_calls:
            fn_name = tool_call.function.name
            try:
                fn_args = json.loads(tool_call.function.arguments)
            except json.JSONDecodeError:
                fn_args = {}

            # Check permission before executing
            fn_allowed = True
            for fn_def in FUNCTION_DEFINITIONS:
                if fn_def["name"] == fn_name:
                    # Re-check using filter
                    if fn_def not in available_fns:
                        fn_allowed = False
                    break

            if fn_allowed:
                fn_result = _execute_function(fn_name, fn_args, uid, permissions)
            else:
                fn_result = json.dumps({"error": "This action is not available for your access level."})

            last_fn_name = fn_name
            last_fn_result = fn_result

            # Save function call message
            httpx.post(
                f"{SUPABASE_URL}/rest/v1/aria_messages",
                headers=headers,
                json={
                    "conversation_id": body.conversation_id,
                    "role": "assistant",
                    "content": msg.content or "",
                    "function_name": fn_name,
                    "function_args": fn_args,
                },
                timeout=20.0,
            )

            # Save function result
            httpx.post(
                f"{SUPABASE_URL}/rest/v1/aria_messages",
                headers=headers,
                json={
                    "conversation_id": body.conversation_id,
                    "role": "function",
                    "content": "",
                    "function_name": fn_name,
                    "function_result": fn_result,
                },
                timeout=20.0,
            )

            # Add to messages for follow-up
            messages.append({"role": "assistant", "content": msg.content or "", "tool_calls": [
                {"id": tool_call.id, "type": "function", "function": {"name": fn_name, "arguments": json.dumps(fn_args)}}
            ]})
            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": fn_result})

        # Second call to get natural language response
        response2 = client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=2000,
            temperature=0.5,
        )
        final_content = (response2.choices[0].message.content or "").strip()
    else:
        final_content = (msg.content or "").strip()

    # Save assistant response
    httpx.post(
        f"{SUPABASE_URL}/rest/v1/aria_messages",
        headers=headers,
        json={
            "conversation_id": body.conversation_id,
            "role": "assistant",
            "content": final_content,
        },
        timeout=20.0,
    )

    # Update conversation timestamp — and auto-generate a title on the first message
    patch_payload: dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}

    # If this is the first exchange (history only had the user message we just saved),
    # generate a short descriptive title from the user's message.
    is_first_message = len([m for m in history if m.get("role") == "user"]) <= 1
    if is_first_message:
        try:
            title_resp = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Generate a short conversation title (max 6 words) that summarizes the user's request. "
                            "No quotes, no punctuation at the end. Just the title."
                        ),
                    },
                    {"role": "user", "content": body.content},
                ],
                max_tokens=20,
                temperature=0.3,
            )
            auto_title = (title_resp.choices[0].message.content or "").strip().strip('"').strip("'")
            if auto_title:
                patch_payload["title"] = auto_title
        except Exception:
            pass  # Non-critical — keep the default title

    httpx.patch(
        f"{SUPABASE_URL}/rest/v1/aria_conversations",
        headers=headers,
        params={"id": f"eq.{body.conversation_id}"},
        json=patch_payload,
        timeout=20.0,
    )

    result: dict[str, Any] = {"reply": final_content}

    # Attach function metadata so the frontend can render inline components
    if last_fn_name:
        result["function_called"] = last_fn_name
        if last_fn_result:
            try:
                parsed = json.loads(last_fn_result)
                # Pass chart_data through if the function returned it
                if isinstance(parsed, dict) and "chart_data" in parsed:
                    result["chart_data"] = parsed["chart_data"]
                result["function_result"] = parsed
            except (json.JSONDecodeError, TypeError):
                pass

    return result
