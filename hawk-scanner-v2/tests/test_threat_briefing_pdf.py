"""Unit tests for the weekly threat briefing PDF renderer (priority list #37).

The renderer is the input to two callers: (a) the weekly cron that
attaches it to the Resend email, and (b) the
``GET /api/portal/threat-briefing/latest.pdf`` endpoint that lets clients
download it on-demand. Both paths must succeed for any briefing the AI
produces — even when the markdown is empty, the title contains HTML
escapables, or reportlab is unavailable. These tests pin that contract.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_BACKEND = _REPO_ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# ---------- briefing_filename -------------------------------------------


def test_briefing_filename_sanitizes_company_name() -> None:
    from services.threat_briefing_pdf import briefing_filename

    f = briefing_filename(company="Smith & Associates, P.C.", week_start="2026-01-12")
    assert f == "hawk-weekly-threat-briefing-Smith-Associates-P-C-2026-01-12.pdf"


def test_briefing_filename_handles_empty_company() -> None:
    from services.threat_briefing_pdf import briefing_filename

    f = briefing_filename(company="", week_start="2026-01-12")
    assert f.endswith("-2026-01-12.pdf")
    assert ".." not in f


def test_briefing_filename_handles_unicode_and_quotes() -> None:
    """Filename must be filesystem-safe even for non-ASCII / quoted names."""
    from services.threat_briefing_pdf import briefing_filename

    f = briefing_filename(company='"Müller & Söhne"', week_start="2026-01-12")
    # Non-ASCII collapses to dashes via the regex; result is plain ASCII.
    assert f.startswith("hawk-weekly-threat-briefing-")
    assert all(ord(c) < 128 for c in f)
    # No path traversal characters.
    assert "/" not in f and "\\" not in f and ".." not in f


# ---------- render_weekly_briefing_pdf ----------------------------------


def test_render_weekly_briefing_pdf_returns_pdf_bytes() -> None:
    from services.threat_briefing_pdf import render_weekly_briefing_pdf

    pdf = render_weekly_briefing_pdf(
        company="Acme Dental",
        title="Weekly briefing — Acme Dental",
        body_md=(
            "## This week\n\n"
            "Ransomware activity targeting US dental clinics continues. "
            "**Action:** patch your VPN concentrator before Friday.\n\n"
            "- Two new IOCs published by HHS\n"
            "- Third-party billing portal showed credential reuse\n"
        ),
        industry="dental",
        week_start="2026-01-12",
    )
    assert pdf, "expected non-empty PDF bytes"
    assert pdf[:4] == b"%PDF", "output must start with the PDF magic header"


def test_render_weekly_briefing_pdf_handles_empty_body() -> None:
    """Empty body still produces a valid PDF (header + footer + title only)."""
    from services.threat_briefing_pdf import render_weekly_briefing_pdf

    pdf = render_weekly_briefing_pdf(
        company="Acme Dental",
        title="",
        body_md="",
    )
    assert pdf and pdf[:4] == b"%PDF"


def test_render_weekly_briefing_pdf_escapes_angle_brackets() -> None:
    """A stray ``<script>`` in the AI body must not break Paragraph parsing."""
    from services.threat_briefing_pdf import render_weekly_briefing_pdf

    pdf = render_weekly_briefing_pdf(
        company="Acme",
        title="Test",
        body_md="An <evil> tag and a 5 < 10 comparison and >>arrow<< chars.",
    )
    assert pdf and pdf[:4] == b"%PDF"


def test_render_weekly_briefing_pdf_handles_ampersand_in_company_name() -> None:
    """Reportlab Paragraph parses XML; bare ``&`` in a company name must
    be escaped before interpolation or the meta line throws and the PDF
    silently degrades to empty bytes (caught by the outer try/except).
    """
    from services.threat_briefing_pdf import render_weekly_briefing_pdf

    pdf = render_weekly_briefing_pdf(
        company="Smith & Associates, P.C.",
        title="Test",
        body_md="hi",
        industry="legal & advisory",
        week_start="2026-01-12",
    )
    assert pdf and pdf[:4] == b"%PDF"


def test_render_weekly_briefing_pdf_renders_markdown_emphasis() -> None:
    """``**bold**`` and ``*italic*`` must produce a valid PDF (no raw stars)."""
    from services.threat_briefing_pdf import render_weekly_briefing_pdf

    pdf = render_weekly_briefing_pdf(
        company="Acme",
        title="Test",
        body_md="Make sure **this is bold** and *this italic* both render.",
    )
    assert pdf and pdf[:4] == b"%PDF"


def test_render_weekly_briefing_pdf_returns_empty_when_reportlab_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Graceful degrade — returns ``b""`` so the email cron still sends."""
    import builtins
    from services import threat_briefing_pdf as mod

    real_import = builtins.__import__

    def boom(name: str, *args, **kwargs):
        if name.startswith("reportlab"):
            raise ImportError(name)
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", boom)

    out = mod.render_weekly_briefing_pdf(
        company="Acme", title="Test", body_md="hi"
    )
    assert out == b""
