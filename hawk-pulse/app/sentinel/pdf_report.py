"""HAWK Sentinel — Boardroom PDF Report Generator.

Uses WeasyPrint + Jinja2 to generate a branded 20-page penetration test
report with the HAWK logo on every page.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader
from markdown import markdown

logger = logging.getLogger(__name__)

TEMPLATE_DIR = Path(__file__).parent / "templates"


def _get_jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=True,
    )


def render_report_html(
    report_markdown: str,
    scope: dict[str, Any],
    domain: str,
    audit_id: str,
) -> str:
    """Render the Markdown report into a branded HTML document."""
    env = _get_jinja_env()
    template = env.get_template("report.html")

    report_html_body = markdown(
        report_markdown,
        extensions=["tables", "fenced_code", "codehilite", "toc"],
    )

    return template.render(
        report_body=report_html_body,
        scope=scope,
        domain=domain,
        audit_id=audit_id,
    )


def generate_pdf(
    report_markdown: str,
    scope: dict[str, Any],
    domain: str,
    audit_id: str,
    output_path: str | None = None,
) -> str:
    """
    Generate a branded PDF from the Markdown report.

    Returns the path to the generated PDF file.
    """
    from weasyprint import HTML

    html_content = render_report_html(report_markdown, scope, domain, audit_id)

    if output_path is None:
        output_dir = Path("/tmp/hawk-reports")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(output_dir / f"hawk-sentinel-{audit_id[:12]}.pdf")

    HTML(string=html_content).write_pdf(output_path)

    logger.info("PDF report generated: %s", output_path)
    return output_path
