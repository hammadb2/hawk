"""Phase 2 — Portal AI Advisor + threat briefings + benchmark copy (Claude)."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, datetime, timedelta, timezone
from typing import Any

import anthropic
import httpx

from config import ANTHROPIC_API_KEY, SUPABASE_URL

logger = logging.getLogger(__name__)

SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
CLAUDE_MODEL = os.environ.get("HAWK_PORTAL_CLAUDE_MODEL", "claude-sonnet-4-20250514")

# Rough sector averages for benchmarking narrative (real competitor scans = later phase).
INDUSTRY_BENCHMARK_AVG: dict[str, dict[str, float]] = {
    "dental": {"avg": 58, "top_quartile": 74},
    "medical": {"avg": 55, "top_quartile": 72},
    "legal": {"avg": 52, "top_quartile": 70},
    "financial": {"avg": 60, "top_quartile": 76},
    "default": {"avg": 54, "top_quartile": 71},
}


def _sb() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def _industry_bucket(raw: str | None) -> str:
    t = (raw or "").lower()
    for key in ("dental", "medical", "health", "clinic"):
        if key in t:
            return "dental" if "dental" in t else "medical"
    if any(x in t for x in ("legal", "law", "attorney")):
        return "legal"
    if any(x in t for x in ("financial", "bank", "wealth", "mortgage", "cpa", "accounting")):
        return "financial"
    return "default"


def load_portal_client_bundle(uid: str) -> dict[str, Any] | None:
    """Portal user id → client, prospect, latest scan, readiness."""
    if not SUPABASE_URL or not SERVICE_KEY:
        return None
    cpp_r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_portal_profiles",
        headers=_sb(),
        params={"user_id": f"eq.{uid}", "select": "client_id,company_name,domain,email", "limit": "1"},
        timeout=20.0,
    )
    if cpp_r.status_code != 200:
        return None
    cpp = (cpp_r.json() or [None])[0]
    if not cpp:
        return None
    cid = cpp["client_id"]
    cl_r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/clients",
        headers=_sb(),
        params={
            "id": f"eq.{cid}",
            "select": "id,prospect_id,mrr_cents,hawk_readiness_score,guarantee_status,certified_at,plan",
            "limit": "1",
        },
        timeout=20.0,
    )
    cl_r.raise_for_status()
    client = (cl_r.json() or [None])[0]
    if not client:
        return None
    prospect = None
    pid = client.get("prospect_id")
    if pid:
        pr = httpx.get(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_sb(),
            params={
                "id": f"eq.{pid}",
                "select": "id,domain,company_name,industry,city,contact_email,phone",
                "limit": "1",
            },
            timeout=20.0,
        )
        if pr.status_code == 200 and pr.json():
            prospect = pr.json()[0]
    scan = None
    if pid:
        sc = httpx.get(
            f"{SUPABASE_URL}/rest/v1/crm_prospect_scans",
            headers=_sb(),
            params={
                "prospect_id": f"eq.{pid}",
                "select": "id,hawk_score,grade,findings,interpreted_findings,created_at,attack_paths,industry",
                "order": "created_at.desc",
                "limit": "1",
            },
            timeout=20.0,
        )
        if sc.status_code == 200 and sc.json():
            scan = sc.json()[0]
    return {"cpp": cpp, "client": client, "prospect": prospect, "scan": scan}


def load_portal_client_bundle_by_client_id(client_id: str) -> dict[str, Any] | None:
    """Same bundle shape as load_portal_client_bundle — for crons keyed by clients.id."""
    if not SUPABASE_URL or not SERVICE_KEY:
        return None
    cl_r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/clients",
        headers=_sb(),
        params={
            "id": f"eq.{client_id}",
            "select": "id,prospect_id,company_name,domain,mrr_cents,hawk_readiness_score,guarantee_status,certified_at,plan",
            "limit": "1",
        },
        timeout=20.0,
    )
    if cl_r.status_code != 200:
        return None
    client = (cl_r.json() or [None])[0]
    if not client:
        return None
    cpp_r = httpx.get(
        f"{SUPABASE_URL}/rest/v1/client_portal_profiles",
        headers=_sb(),
        params={
            "client_id": f"eq.{client_id}",
            "select": "client_id,company_name,domain,email",
            "limit": "1",
        },
        timeout=20.0,
    )
    cpp = (cpp_r.json() or [None])[0] if cpp_r.status_code == 200 else None
    if not cpp:
        return None
    prospect = None
    pid = client.get("prospect_id")
    if pid:
        pr = httpx.get(
            f"{SUPABASE_URL}/rest/v1/prospects",
            headers=_sb(),
            params={
                "id": f"eq.{pid}",
                "select": "id,domain,company_name,industry,city,contact_email,phone",
                "limit": "1",
            },
            timeout=20.0,
        )
        if pr.status_code == 200 and pr.json():
            prospect = pr.json()[0]
    scan = None
    if pid:
        sc = httpx.get(
            f"{SUPABASE_URL}/rest/v1/crm_prospect_scans",
            headers=_sb(),
            params={
                "prospect_id": f"eq.{pid}",
                "select": "id,hawk_score,grade,findings,interpreted_findings,created_at,attack_paths,industry",
                "order": "created_at.desc",
                "limit": "1",
            },
            timeout=20.0,
        )
        if sc.status_code == 200 and sc.json():
            scan = sc.json()[0]
    return {"cpp": cpp, "client": client, "prospect": prospect, "scan": scan}


def _findings_for_prompt(scan: dict[str, Any] | None) -> str:
    if not scan:
        return "(No scan on file yet.)"
    raw = scan.get("findings")
    if isinstance(raw, dict):
        fl = raw.get("findings")
        if isinstance(fl, list):
            lines = []
            for f in fl[:40]:
                if not isinstance(f, dict):
                    continue
                sev = f.get("severity", "")
                title = f.get("title", "")
                desc = (f.get("description") or f.get("interpretation") or "")[:400]
                lines.append(f"- [{sev}] {title}: {desc}")
            return "\n".join(lines) if lines else json.dumps(raw)[:8000]
    return json.dumps(raw)[:8000]


def build_advisor_system_prompt(bundle: dict[str, Any]) -> str:
    cpp = bundle["cpp"]
    prospect = bundle.get("prospect") or {}
    scan = bundle.get("scan") or {}
    client = bundle.get("client") or {}
    domain = str(prospect.get("domain") or cpp.get("domain") or "unknown")
    industry = str(prospect.get("industry") or scan.get("industry") or "General business")
    city = str(prospect.get("city") or "")
    score = scan.get("hawk_score")
    grade = scan.get("grade")
    readiness = client.get("hawk_readiness_score")
    guarantee = client.get("guarantee_status")
    findings_block = _findings_for_prompt(scan)
    ap = scan.get("attack_paths")
    ap_note = ""
    if isinstance(ap, list) and ap:
        ap_note = "\nAttack path narratives (use to explain chaining risk):\n" + json.dumps(ap[:3])[:4000]

    return f"""You are **HAWK AI Advisor**, a senior cybersecurity consultant focused on Canadian SMBs.

**Client context**
- Organization: {cpp.get("company_name") or domain}
- Domain: {domain}
- City/region: {city or "—"}
- Industry: {industry}
- Latest HAWK score: {score}/100 (grade {grade})
- Readiness index: {readiness}
- Guarantee status: {guarantee}

**Regulatory framing (when relevant)**
- Reference **PIPEDA** (federal private-sector privacy) for handling personal information.
- Mention **Bill C-26** (CCCS) when discussing critical infrastructure or incident reporting obligations where applicable.
- For health-related practices, note provincial health privacy laws (e.g. PHIPA in Ontario) briefly when it strengthens the story.
- Never invent legal citations; speak in practical compliance terms.

**Instructions**
- Ground every answer in the findings below. Quote severities and titles when useful.
- If data is missing, say what is unknown and what HAWK would check next.
- Be concise, confident, and actionable. Prefer numbered steps.
- Tone: dedicated analyst, not marketing fluff.

**Their latest scan findings (authoritative)**
{findings_block}
{ap_note}
"""


def _anthropic_text(msg: Any) -> str:
    parts: list[str] = []
    for block in msg.content:
        if block.type == "text":
            parts.append(block.text)
    return "".join(parts).strip()


def advisor_chat(*, system: str, user_message: str, conversation_history: list[dict[str, Any]]) -> str:
    if not ANTHROPIC_API_KEY:
        return "HAWK AI Advisor is not configured yet (missing ANTHROPIC_API_KEY on the API)."
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    messages: list[dict[str, Any]] = []
    for h in conversation_history[-8:]:
        role = h.get("role", "user")
        if role not in ("user", "assistant"):
            continue
        content = str(h.get("content") or "").strip()
        if not content:
            continue
        messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})
    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=system,
        messages=messages,
    )
    return _anthropic_text(msg)


def generate_weekly_threat_briefing_md(bundle: dict[str, Any]) -> tuple[str, str]:
    """Returns (title, markdown body) — three paragraphs + bullets."""
    prospect = bundle.get("prospect") or {}
    industry = str(prospect.get("industry") or "Canadian SMBs")
    domain = str((prospect.get("domain") or bundle["cpp"].get("domain") or "")).strip()
    company = str(bundle["cpp"].get("company_name") or domain)
    scan = bundle.get("scan") or {}
    top_layers = ""
    if isinstance(scan.get("findings"), dict):
        fl = scan["findings"].get("findings")
        if isinstance(fl, list) and fl:
            top_layers = ", ".join(
                str(x.get("layer") or x.get("title") or "") for x in fl[:5] if isinstance(x, dict)
            )

    if not ANTHROPIC_API_KEY:
        body = (
            f"### Weekly threat briefing\n\n"
            f"Week of {date.today().isoformat()} — **{company}** ({industry}).\n\n"
            f"HAWK is monitoring **{domain or 'your domain'}** for external exposure. "
            f"Configure ANTHROPIC_API_KEY on the API for full AI-generated sector intelligence.\n\n"
            f"**Action:** review open findings in your portal and patch critical items within 24–48 hours.\n"
        )
        return f"Weekly briefing — {company}", body

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = f"""Write a **weekly threat intelligence briefing** for a Canadian business.

Company: {company}
Industry vertical: {industry}
Primary domain monitored: {domain or "n/a"}
Surfaces we watch (from last scan): {top_layers or "general perimeter, email auth, TLS, exposed services"}

**Requirements**
1. Exactly **3 paragraphs** (no more): (a) What threat activity or campaigns mattered this week for similar organizations in this sector (generic but realistic — you may reference well-known attack types: ransomware, credential stuffing, invoice fraud, phishing, exposed RDP/VPN). (b) What HAWK is watching on their domain / attack surface in plain language. (c) **One** concrete, actionable recommendation they can do this week.
2. Mention Canadian context where natural (PIPEDA breach notification pressure, sector-specific risk).
3. Professional tone — like a dedicated analyst email. No hype emojis.
4. Markdown: use ## title line, then paragraphs. Optional short bullet list at the end with 2–3 items max.

Output ONLY the markdown."""

    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
    )
    text = _anthropic_text(msg)
    title_m = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    title = title_m.group(1).strip() if title_m else f"Weekly briefing — {company}"
    return title, text


def discover_competitor_domains(bundle: dict[str, Any], *, max_domains: int = 3) -> list[str]:
    """
    Suggest apex domains for silent peer scans (excludes the client's domain).
    Returns 0–max_domains entries; failures yield [] (caller falls back to sector stats only).
    """
    cpp = bundle.get("cpp") or {}
    prospect = bundle.get("prospect") or {}
    own = str(prospect.get("domain") or cpp.get("domain") or "").lower().strip()
    company = str(prospect.get("company_name") or cpp.get("company_name") or "")
    industry = str(prospect.get("industry") or "business")
    city = str(prospect.get("city") or "")
    if not ANTHROPIC_API_KEY:
        return []

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = f"""Suggest up to {max_domains} **plausible competitor website domains** for passive external security benchmarking.

Context (do not output this text verbatim):
- Client business label: {company}
- Client domain (must NEVER appear in output): {own}
- Industry: {industry}
- City/region: {city or "unspecified"}

Rules:
- Return **only** valid JSON: {{"domains": ["a.com","b.com"]}} with 0–{max_domains} apex domains (lowercase, no protocol/path).
- Domains must look like real registrable hostnames. If you cannot suggest plausible peers without inventing harmful false associations, return {{"domains": []}}.

JSON only, no markdown."""

    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}],
    )
    text = _anthropic_text(msg)
    try:
        m = re.search(r"\{[\s\S]*\}", text)
        if not m:
            return []
        data = json.loads(m.group(0))
        raw = data.get("domains") if isinstance(data, dict) else []
        out: list[str] = []
        if not isinstance(raw, list):
            return []
        for d in raw[:max_domains]:
            ds = str(d).lower().strip()
            for prefix in ("https://", "http://"):
                if ds.startswith(prefix):
                    ds = ds[len(prefix) :]
            ds = ds.split("/")[0]
            if ds.startswith("www."):
                ds = ds[4:]
            if ds and ds != own and "." in ds:
                out.append(ds)
        return list(dict.fromkeys(out))[:max_domains]
    except Exception:
        logger.exception("discover_competitor_domains parse failed")
        return []


def generate_competitor_benchmark(
    bundle: dict[str, Any],
    client_score: int | None,
    *,
    peer_scores: list[float] | None = None,
    peer_domains: list[str] | None = None,
) -> dict[str, Any]:
    """Build benchmark JSON + narrative; optional silent peer scan scores (anonymized in copy)."""
    prospect = bundle.get("prospect") or {}
    industry = str(prospect.get("industry") or "business")
    city = str(prospect.get("city") or "")
    bucket = _industry_bucket(industry)
    bench = INDUSTRY_BENCHMARK_AVG.get(bucket, INDUSTRY_BENCHMARK_AVG["default"])
    you = float(client_score or 0)
    avg = bench["avg"]
    topq = bench["top_quartile"]
    competitors = [round(avg + i * 2, 0) for i in (-1, 0, 1)]
    peer_scores = peer_scores or []
    peer_avg: float | None = None
    if peer_scores:
        peer_avg = round(sum(peer_scores) / len(peer_scores), 1)

    scores: dict[str, Any] = {
        "you": you,
        "industry_average": avg,
        "top_quartile": topq,
        "sample_competitor_scores": competitors,
        "region_note": city or "your region",
    }
    if peer_avg is not None:
        scores["peer_scan_average"] = peer_avg
        scores["peer_sample_size"] = len(peer_scores)
    if peer_scores:
        scores["peer_scores_anonymized"] = [round(x, 1) for x in peer_scores[:5]]

    internal_domains = list(peer_domains or [])

    if not ANTHROPIC_API_KEY:
        extra = ""
        if peer_avg is not None:
            extra = f" Anonymized peer scan average from similar local businesses: **{peer_avg:.1f}/100** (n={len(peer_scores)})."
        narrative = (
            f"Your HAWK score is **{you:.0f}/100**. For **{industry}** organizations in Canada, "
            f"our reference dataset suggests a typical peer score around **{avg:.0f}**, with top quartile near **{topq:.0f}**.{extra}"
        )
        return {"scores": scores, "narrative_md": narrative, "competitor_domains": internal_domains}

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    peer_line = ""
    if peer_avg is not None:
        peer_line = (
            f"Anonymized external scans of {len(peer_scores)} similar-market domains averaged **{peer_avg:.1f}/100** "
            f"(individual scores not attributed to named businesses)."
        )
    prompt = f"""You explain competitive security posture **without naming real third-party companies**.

Client vertical: {industry}
City/region: {city or "unspecified"}
Their HAWK score: {you:.0f}/100
Reference peer average (same vertical, anonymized dataset): {avg:.0f}
Top quartile reference: {topq:.0f}
{peer_line}

Write 2 short paragraphs of markdown:
1. How they compare to typical peers — and if peer_scan data exists, how they compare to that anonymized local sample — plus what top performers tend to do differently (MFA, patching, email auth, backups, vendor access).
2. One prioritized action to close the gap.

Never name specific competitor companies or their domains. Frame peer scans as anonymized market samples."""

    msg = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    narrative = _anthropic_text(msg)
    return {"scores": scores, "narrative_md": narrative, "competitor_domains": internal_domains}


def monday_week_start(today: date | None = None) -> date:
    d = today or datetime.now(timezone.utc).date()
    return d - timedelta(days=d.weekday())
