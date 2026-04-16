"""
ARIA Pipeline Report — generate downloadable PDF summary of a pipeline run.

Uses ReportLab (already in requirements.txt) to produce a branded Hawk Security
pipeline run report with all key metrics and lead details.
"""

from __future__ import annotations

import io
import logging
import os
from datetime import datetime, timezone
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

import httpx

logger = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()

HAWK_GREEN = colors.HexColor("#059669")
HAWK_DARK = colors.HexColor("#0f172a")
HAWK_LIGHT_BG = colors.HexColor("#f8fafc")


def _sb_headers() -> dict[str, str]:
    return {
        "apikey": SERVICE_KEY,
        "Authorization": f"Bearer {SERVICE_KEY}",
        "Content-Type": "application/json",
    }


def _get_run(run_id: str) -> dict[str, Any] | None:
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/aria_pipeline_runs",
            headers=_sb_headers(),
            params={"id": f"eq.{run_id}", "select": "*", "limit": "1"},
            timeout=20.0,
        )
        r.raise_for_status()
        rows = r.json()
        return rows[0] if rows else None
    except Exception as exc:
        logger.exception("Failed to fetch run %s: %s", run_id, exc)
        return None


def _get_run_leads(run_id: str) -> list[dict[str, Any]]:
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/aria_pipeline_leads",
            headers=_sb_headers(),
            params={
                "run_id": f"eq.{run_id}",
                "select": "company_name,domain,contact_name,contact_email,vertical,vulnerability_found,email_sent,status,removed_reason",
                "order": "created_at.asc",
                "limit": "500",
            },
            timeout=30.0,
        )
        r.raise_for_status()
        return r.json() or []
    except Exception as exc:
        logger.exception("Failed to fetch leads for run %s: %s", run_id, exc)
        return []


def generate_pipeline_report_pdf(run_id: str) -> bytes | None:
    """Generate a PDF report for a completed pipeline run. Returns PDF bytes."""
    run = _get_run(run_id)
    if not run:
        return None

    leads = _get_run_leads(run_id)
    buf = io.BytesIO()

    doc = SimpleDocTemplate(
        buf,
        pagesize=letter,
        rightMargin=0.75 * inch,
        leftMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "ARIATitle",
        parent=styles["Title"],
        fontSize=22,
        textColor=HAWK_DARK,
        spaceAfter=6,
    )
    subtitle_style = ParagraphStyle(
        "ARIASubtitle",
        parent=styles["Normal"],
        fontSize=11,
        textColor=colors.gray,
        spaceAfter=20,
    )
    heading_style = ParagraphStyle(
        "ARIAHeading",
        parent=styles["Heading2"],
        fontSize=14,
        textColor=HAWK_GREEN,
        spaceBefore=16,
        spaceAfter=8,
    )
    body_style = ParagraphStyle(
        "ARIABody",
        parent=styles["Normal"],
        fontSize=10,
        textColor=HAWK_DARK,
        leading=14,
    )

    elements: list[Any] = []

    # Title
    elements.append(Paragraph("ARIA Pipeline Run Report", title_style))
    elements.append(Paragraph("Hawk Security — Automated Revenue and Intelligence Assistant", subtitle_style))

    # Run Info
    vertical = (run.get("vertical") or "").title()
    location = run.get("location", "N/A")
    status = (run.get("status") or "").title()
    started = run.get("started_at", "")
    completed = run.get("completed_at", "")

    if started:
        try:
            dt = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
            started = dt.strftime("%B %d, %Y at %I:%M %p UTC")
        except Exception:
            pass
    if completed:
        try:
            dt = datetime.fromisoformat(str(completed).replace("Z", "+00:00"))
            completed = dt.strftime("%B %d, %Y at %I:%M %p UTC")
        except Exception:
            pass

    elements.append(Paragraph("Run Details", heading_style))

    run_info = [
        ["Vertical", vertical],
        ["Location", location],
        ["Status", status],
        ["Started", str(started)],
        ["Completed", str(completed) if completed else "In progress"],
    ]
    run_table = Table(run_info, colWidths=[1.5 * inch, 4.5 * inch])
    run_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("TEXTCOLOR", (0, 0), (0, -1), HAWK_GREEN),
        ("TEXTCOLOR", (1, 0), (1, -1), HAWK_DARK),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(run_table)

    # Pipeline Metrics
    elements.append(Paragraph("Pipeline Metrics", heading_style))

    metrics = [
        ["Metric", "Count"],
        ["Leads Pulled (Apollo)", str(run.get("leads_pulled", 0))],
        ["Leads Enriched (Clay)", str(run.get("leads_enriched", 0))],
        ["Leads Verified (ZeroBounce)", str(run.get("leads_verified", 0))],
        ["Leads Scanned (Hawk)", str(run.get("leads_scanned", 0))],
        ["Vulnerabilities Found", str(run.get("vulnerabilities_found", 0))],
        ["Emails Generated", str(run.get("emails_generated", 0))],
        ["Emails Sent (Smartlead)", str(run.get("emails_sent", 0))],
    ]

    metrics_table = Table(metrics, colWidths=[3.5 * inch, 2.5 * inch])
    metrics_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HAWK_GREEN),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BACKGROUND", (0, 1), (-1, -1), HAWK_LIGHT_BG),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.append(metrics_table)

    # Funnel conversion
    pulled = run.get("leads_pulled", 0)
    sent = run.get("emails_sent", 0)
    if pulled > 0:
        conversion = f"{(sent / pulled * 100):.1f}%"
        elements.append(Spacer(1, 8))
        elements.append(Paragraph(
            f"<b>Pipeline Conversion:</b> {conversion} of pulled leads reached Smartlead",
            body_style,
        ))

    # Lead Details
    if leads:
        elements.append(Paragraph("Lead Details", heading_style))

        # Sent leads
        sent_leads = [l for l in leads if l.get("status") == "sent"]
        if sent_leads:
            elements.append(Paragraph(f"<b>Emails Sent ({len(sent_leads)})</b>", body_style))
            elements.append(Spacer(1, 4))

            lead_data = [["Company", "Domain", "Contact", "Vulnerability"]]
            for lead in sent_leads[:50]:  # Cap at 50 for readability
                vuln = lead.get("vulnerability_found") or "No finding"
                if len(vuln) > 60:
                    vuln = vuln[:57] + "..."
                lead_data.append([
                    (lead.get("company_name") or "")[:30],
                    (lead.get("domain") or "")[:30],
                    (lead.get("contact_name") or "")[:25],
                    vuln,
                ])

            lead_table = Table(lead_data, colWidths=[1.5 * inch, 1.5 * inch, 1.25 * inch, 2.25 * inch])
            lead_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), HAWK_DARK),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, HAWK_LIGHT_BG]),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]))
            elements.append(lead_table)

        # Removed leads
        removed_leads = [l for l in leads if l.get("status") == "removed"]
        if removed_leads:
            elements.append(Spacer(1, 12))
            elements.append(Paragraph(f"<b>Removed ({len(removed_leads)})</b>", body_style))
            reasons: dict[str, int] = {}
            for l in removed_leads:
                reason = l.get("removed_reason") or "unknown"
                reasons[reason] = reasons.get(reason, 0) + 1
            for reason, count in reasons.items():
                elements.append(Paragraph(f"  {reason}: {count}", body_style))

    # Error info
    error = run.get("error_message")
    if error:
        elements.append(Paragraph("Error", heading_style))
        elements.append(Paragraph(str(error)[:500], body_style))

    # Footer
    elements.append(Spacer(1, 24))
    footer_style = ParagraphStyle(
        "ARIAFooter",
        parent=styles["Normal"],
        fontSize=8,
        textColor=colors.gray,
        alignment=1,
    )
    now = datetime.now(timezone.utc).strftime("%B %d, %Y at %I:%M %p UTC")
    elements.append(Paragraph(
        f"Generated by ARIA — Hawk Security | {now}",
        footer_style,
    ))

    doc.build(elements)
    return buf.getvalue()


def upload_report_to_storage(run_id: str, pdf_bytes: bytes) -> str | None:
    """Upload PDF report to Supabase Storage and return a signed URL."""
    if not SUPABASE_URL or not SERVICE_KEY:
        return None

    filename = f"pipeline-reports/{run_id}/report.pdf"

    try:
        # Upload to storage
        r = httpx.post(
            f"{SUPABASE_URL}/storage/v1/object/aria-documents/{filename}",
            headers={
                "apikey": SERVICE_KEY,
                "Authorization": f"Bearer {SERVICE_KEY}",
                "Content-Type": "application/pdf",
            },
            content=pdf_bytes,
            timeout=30.0,
        )
        if r.status_code >= 400:
            logger.warning("Storage upload failed: %s", r.text[:300])
            # Try upsert if it already exists
            r = httpx.put(
                f"{SUPABASE_URL}/storage/v1/object/aria-documents/{filename}",
                headers={
                    "apikey": SERVICE_KEY,
                    "Authorization": f"Bearer {SERVICE_KEY}",
                    "Content-Type": "application/pdf",
                },
                content=pdf_bytes,
                timeout=30.0,
            )

        # Create signed URL (valid for 1 hour)
        r2 = httpx.post(
            f"{SUPABASE_URL}/storage/v1/object/sign/aria-documents/{filename}",
            headers={
                "apikey": SERVICE_KEY,
                "Authorization": f"Bearer {SERVICE_KEY}",
                "Content-Type": "application/json",
            },
            json={"expiresIn": 3600},
            timeout=20.0,
        )
        if r2.status_code < 300:
            data = r2.json()
            signed_url = data.get("signedURL", "")
            if signed_url and not signed_url.startswith("http"):
                signed_url = f"{SUPABASE_URL}/storage/v1{signed_url}"
            return signed_url

    except Exception as exc:
        logger.exception("Failed to upload pipeline report: %s", exc)

    return None
