"""Resend — client portal emails. All client-facing mail uses branded HTML + noreply@securedbyhawk.com."""

from __future__ import annotations

import html as html_module
import logging
from typing import Any

import httpx

from config import RESEND_API_KEY, RESEND_FROM_EMAIL, RESEND_GUARANTEE_FROM

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Master wrapper (dark theme, green bar, logo) — BODY inserted at __BODY_CONTENT__
# ---------------------------------------------------------------------------
_MASTER_HTML = """<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0;padding:0;background:#f4f4f8;font-family:Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0"
         style="background:#f4f4f8;min-height:100vh;">
    <tr>
      <td align="center" style="padding:60px 20px;">
        <table width="520" cellpadding="0" cellspacing="0"
               style="background:#1a1a2e;border-radius:12px;overflow:hidden;">

          <tr>
            <td style="background:#00C48C;height:4px;font-size:0;">&nbsp;</td>
          </tr>

          <tr>
            <td align="center" style="padding:40px 48px 32px;">
              <img src="https://securedbyhawk.com/hawk-logo.png"
                   alt="HAWK Security"
                   width="120"
                   style="display:block;margin:0 auto 12px;max-width:120px;" />
              <div style="font-size:11px;letter-spacing:4px;color:#9090A8;
                          text-transform:uppercase;">Security Platform</div>
            </td>
          </tr>

          <tr>
            <td style="padding:0 48px;">
              <div style="height:1px;background:#2a2a40;"></div>
            </td>
          </tr>

          __BODY_CONTENT__

          <tr>
            <td style="padding:0 48px;">
              <div style="height:1px;background:#2a2a40;"></div>
            </td>
          </tr>

          <tr>
            <td align="center" style="padding:24px 48px 40px;">
              <p style="margin:0 0 4px;font-size:12px;color:#4a4a6a;">
                HAWK Security
              </p>
              <p style="margin:0;font-size:12px;">
                <a href="https://securedbyhawk.com"
                   style="color:#00C48C;text-decoration:none;">
                  securedbyhawk.com
                </a>
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""


def _esc(s: str | int | float | None) -> str:
    if s is None:
        return ""
    return html_module.escape(str(s), quote=True)


def _wrap(body_inner_rows: str) -> str:
    """Wrap inner <tr>...</tr> rows (tbody content) inside the master card."""
    return _MASTER_HTML.replace("__BODY_CONTENT__", body_inner_rows)


def _security_notice_block() -> str:
    return """
          <tr>
            <td style="padding:0 48px 0 48px;">
              <table cellpadding="0" cellspacing="0" width="100%" style="margin-top:0;">
                <tr>
                  <td style="background:#0F0E17;border:1px solid #2a2a40;
                             border-left:3px solid #00C48C;border-radius:6px;
                             padding:14px 16px;">
                    <p style="margin:0;font-size:12px;color:#9090A8;line-height:1.6;">
                      <strong style="color:#00C48C;">Security notice:</strong>
                      If you did not expect this email you can safely ignore it.
                      Contact us at hello@securedbyhawk.com if you have any questions.
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
"""


def _fallback_url_line(url: str) -> str:
    u = _esc(url)
    return f"""
            <p style="margin:28px 0 0;font-size:12px;color:#4a4a6a;line-height:1.6;">
              If the button does not work copy and paste this link:<br>
              <span style="color:#00C48C;">{u}</span>
            </p>
"""


def _default_from() -> str:
    raw = (RESEND_FROM_EMAIL or "").strip()
    if "@" in raw and "<" not in raw:
        return f"HAWK Security <{raw}>"
    return raw or "HAWK Security <noreply@securedbyhawk.com>"


def _guarantee_from() -> str:
    g = (RESEND_GUARANTEE_FROM or "").strip()
    if g:
        if "@" in g and "<" not in g:
            return f"HAWK Security <{g}>"
        return g
    return _default_from()


def send_resend(
    *,
    to_email: str,
    subject: str,
    html: str,
    tags: list[dict[str, str]] | None = None,
    from_email: str | None = None,
) -> dict[str, Any]:
    """POST https://api.resend.com/emails — returns JSON or raises."""
    if not RESEND_API_KEY:
        logger.info("RESEND_API_KEY not set — skip email to %s: %s", to_email, subject)
        return {"skipped": True}

    frm = from_email or _default_from()
    body: dict[str, Any] = {
        "from": frm,
        "to": [to_email],
        "subject": subject,
        "html": html,
    }
    if tags:
        body["tags"] = tags

    r = httpx.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
        json=body,
        timeout=30.0,
    )
    r.raise_for_status()
    return r.json()


def welcome_portal_email(*, to_email: str, company_name: str, portal_url: str) -> dict[str, Any]:
    esc = _esc
    inner = f"""
          <tr>
            <td style="padding:40px 48px 32px;">
              <p style="margin:0 0 8px;font-size:22px;font-weight:700;color:#ffffff;line-height:1.3;">
                Welcome, {esc(company_name)}.
              </p>
              <p style="margin:0 0 24px;font-size:15px;color:#9090A8;line-height:1.6;">
                Your HAWK client portal is ready. Sign in with this email — we&apos;ll send you a secure magic link.
              </p>
              <table cellpadding="0" cellspacing="0" width="100%">
                <tr>
                  <td align="center">
                    <a href="{esc(portal_url)}"
                       style="display:inline-block;background:#00C48C;color:#ffffff;
                              font-size:15px;font-weight:700;text-decoration:none;
                              padding:16px 48px;border-radius:8px;letter-spacing:0.3px;">
                      Login to HAWK Security
                    </a>
                  </td>
                </tr>
              </table>
              {_fallback_url_line(portal_url)}
            </td>
          </tr>
"""
    return send_resend(
        to_email=to_email,
        subject="Welcome to your HAWK security portal",
        html=_wrap(inner + _security_notice_block()),
        tags=[{"name": "category", "value": "portal_welcome"}],
    )


def shield_day0_welcome_email(
    *,
    to_email: str,
    first_name: str,
    domain: str,
    cal_url: str,
) -> dict[str, Any]:
    """EMAIL 1 — immediately after Shield payment (Stripe)."""
    esc = _esc
    fn = (first_name or "").strip() or "there"
    dom = (domain or "").strip() or "your domain"
    portal = "https://securedbyhawk.com/portal"
    inner = f"""
          <tr>
            <td style="padding:40px 48px 32px;">
              <p style="margin:0 0 8px;font-size:22px;font-weight:700;
                        color:#ffffff;line-height:1.3;">
                Welcome, {esc(fn)}.
              </p>
              <p style="margin:0 0 32px;font-size:15px;color:#9090A8;line-height:1.6;">
                Your HAWK Shield subscription is confirmed and your breach
                response guarantee is now active.
              </p>

              <p style="margin:0 0 16px;font-size:15px;color:#ffffff;
                        font-weight:600;">
                Here is what happens next:
              </p>

              <p style="margin:0 0 8px;font-size:14px;color:#9090A8;line-height:1.6;">
                We are running your first security scan on
                <strong style="color:#00C48C;">{esc(dom)}</strong> right now.
                Your full report will be ready shortly.
              </p>

              <p style="margin:0 0 32px;font-size:14px;color:#9090A8;line-height:1.6;">
                Your 90 day path to HAWK Certified starts today.
              </p>

              <table cellpadding="0" cellspacing="0" width="100%"
                     style="margin-bottom:16px;">
                <tr>
                  <td style="background:#0F0E17;border:1px solid #2a2a40;
                             border-left:3px solid #00C48C;border-radius:6px;
                             padding:14px 16px;">
                    <p style="margin:0 0 4px;font-size:13px;font-weight:700;
                              color:#00C48C;">Step 1</p>
                    <p style="margin:0;font-size:13px;color:#ffffff;">
                      Book your onboarding call — we will walk you through
                      everything we found and how to fix it.
                    </p>
                  </td>
                </tr>
              </table>

              <table cellpadding="0" cellspacing="0" width="100%"
                     style="margin-bottom:24px;">
                <tr>
                  <td align="center">
                    <a href="{esc(cal_url)}"
                       style="display:inline-block;background:#00C48C;color:#ffffff;
                              font-size:15px;font-weight:700;text-decoration:none;
                              padding:16px 48px;border-radius:8px;">
                      Book My Onboarding Call
                    </a>
                  </td>
                </tr>
              </table>
              {_fallback_url_line(cal_url)}

              <table cellpadding="0" cellspacing="0" width="100%"
                     style="margin-bottom:16px;margin-top:24px;">
                <tr>
                  <td style="background:#0F0E17;border:1px solid #2a2a40;
                             border-left:3px solid #00C48C;border-radius:6px;
                             padding:14px 16px;">
                    <p style="margin:0 0 4px;font-size:13px;font-weight:700;
                              color:#00C48C;">Step 2</p>
                    <p style="margin:0;font-size:13px;color:#ffffff;">
                      Access your security dashboard to see your findings,
                      your readiness score, and your guarantee status.
                    </p>
                  </td>
                </tr>
              </table>

              <table cellpadding="0" cellspacing="0" width="100%"
                     style="margin-bottom:32px;">
                <tr>
                  <td align="center">
                    <a href="{esc(portal)}"
                       style="display:inline-block;background:#1a1a2e;
                              color:#00C48C;font-size:15px;font-weight:700;
                              text-decoration:none;padding:14px 48px;
                              border-radius:8px;border:2px solid #00C48C;">
                      Access My Dashboard
                    </a>
                  </td>
                </tr>
              </table>
              {_fallback_url_line(portal)}

              <table cellpadding="0" cellspacing="0" width="100%">
                <tr>
                  <td style="background:#0F0E17;border:1px solid #2a2a40;
                             border-left:3px solid #00C48C;border-radius:6px;
                             padding:14px 16px;">
                    <p style="margin:0;font-size:12px;color:#9090A8;line-height:1.6;">
                      <strong style="color:#00C48C;">Questions?</strong>
                      Reply to this email or contact us at
                      hello@securedbyhawk.com anytime.
                    </p>
                  </td>
                </tr>
              </table>

              <p style="margin:28px 0 0;font-size:12px;color:#4a4a6a;line-height:1.6;">
                The HAWK Team · securedbyhawk.com
              </p>
            </td>
          </tr>
"""
    return send_resend(
        to_email=to_email,
        subject="Welcome to HAWK Security — your protection starts now",
        html=_wrap(inner),
        tags=[{"name": "category", "value": "shield_day0_welcome"}],
    )


def shield_day1_findings_email(
    *,
    to_email: str,
    first_name: str,
    domain: str,
    cal_url: str,
    top_findings: list[tuple[str, str]],
) -> dict[str, Any]:
    """EMAIL 2 — Day 1 after onboarded_at (24h) if onboarding call not booked."""
    esc = _esc
    fn = (first_name or "").strip() or "there"
    dom = (domain or "").strip() or "your domain"

    def line(n: int, label: str, color: str, border: str) -> str:
        if len(top_findings) > n:
            t, pl = top_findings[n][0], top_findings[n][1]
            text = pl.strip() or t
        else:
            text = "See your full report in the portal."
        return f"""
              <table cellpadding="0" cellspacing="0" width="100%"
                     style="margin-bottom:12px;">
                <tr>
                  <td style="background:#0F0E17;border:1px solid #2a2a40;
                             border-left:3px solid {border};border-radius:6px;
                             padding:14px 16px;">
                    <p style="margin:0 0 4px;font-size:11px;font-weight:700;
                              color:{color};text-transform:uppercase;
                              letter-spacing:1px;">{label}</p>
                    <p style="margin:0;font-size:13px;color:#ffffff;line-height:1.5;">
                      {esc(text)}
                    </p>
                  </td>
                </tr>
              </table>
"""

    blocks = line(0, "Critical", "#FF4444", "#FF4444") + line(1, "High", "#FF8C00", "#FF8C00") + line(
        2, "Medium", "#FFC107", "#FFC107"
    )

    inner = f"""
          <tr>
            <td style="padding:40px 48px 32px;">
              <p style="margin:0 0 8px;font-size:22px;font-weight:700;
                        color:#ffffff;line-height:1.3;">
                Hi {esc(fn)}, here is what we found.
              </p>
              <p style="margin:0 0 32px;font-size:15px;color:#9090A8;line-height:1.6;">
                We completed your first scan on
                <strong style="color:#00C48C;">{esc(dom)}</strong>.
                Here are your top findings.
              </p>
              {blocks}
              <p style="margin:0 0 32px;font-size:14px;color:#9090A8;line-height:1.6;">
                Your onboarding call is not booked yet. Book it now and we will
                walk you through every finding and show you exactly how to fix
                each one step by step.
              </p>

              <table cellpadding="0" cellspacing="0" width="100%"
                     style="margin-bottom:32px;">
                <tr>
                  <td align="center">
                    <a href="{esc(cal_url)}"
                       style="display:inline-block;background:#00C48C;color:#ffffff;
                              font-size:15px;font-weight:700;text-decoration:none;
                              padding:16px 48px;border-radius:8px;">
                      Book My Onboarding Call
                    </a>
                  </td>
                </tr>
              </table>
              {_fallback_url_line(cal_url)}

              <table cellpadding="0" cellspacing="0" width="100%">
                <tr>
                  <td style="background:#0F0E17;border:1px solid #2a2a40;
                             border-left:3px solid #00C48C;border-radius:6px;
                             padding:14px 16px;">
                    <p style="margin:0;font-size:12px;color:#9090A8;line-height:1.6;">
                      <strong style="color:#00C48C;">Remember:</strong>
                      Critical findings must be resolved within 24 hours
                      to maintain your guarantee coverage. Login to see
                      your fix guides.
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
"""
    return send_resend(
        to_email=to_email,
        subject="Your HAWK security findings — action required",
        html=_wrap(inner + _security_notice_block()),
        tags=[{"name": "category", "value": "shield_day1_findings"}],
    )


def shield_day3_update_email(
    *,
    to_email: str,
    first_name: str,
    company_name: str,
    findings_resolved: bool,
    findings_fixed: int,
    score_start: int,
    score_current: int,
    days_until_certified: int,
    portal_url: str,
) -> dict[str, Any]:
    """EMAIL 3 — Day 3 (72h after onboarded_at)."""
    esc = _esc
    fn = (first_name or "").strip() or "there"
    co = _esc(company_name)
    if findings_resolved:
        mid = f"""
      Great work. You have resolved {esc(findings_fixed)} findings.
      Your score improved from
      <strong style="color:#FF4444;">{esc(score_start)}/100</strong> to
      <strong style="color:#00C48C;">{esc(score_current)}/100</strong>.
"""
    else:
        mid = """
      We noticed your critical findings have not been resolved yet.
      Your guarantee requires fixes within 24 to 48 hours.
      Need help? Reply to this email and our team will assist you.
"""

    inner = f"""
          <tr>
            <td style="padding:40px 48px 32px;">
              <p style="margin:0 0 8px;font-size:22px;font-weight:700;
                        color:#ffffff;line-height:1.3;">
                Day 3 update, {esc(fn)}.
              </p>
              <p style="margin:0 0 32px;font-size:15px;color:#9090A8;line-height:1.6;">
                {mid}
              </p>

              <table cellpadding="0" cellspacing="0" width="100%"
                     style="margin-bottom:32px;">
                <tr>
                  <td style="background:#0F0E17;border:1px solid #2a2a40;
                             border-radius:6px;padding:20px 16px;text-align:center;">
                    <p style="margin:0 0 4px;font-size:13px;color:#9090A8;">
                      Current readiness score
                    </p>
                    <p style="margin:0;font-size:48px;font-weight:900;
                              color:#00C48C;line-height:1;">
                      {esc(score_current)}
                    </p>
                    <p style="margin:4px 0 0;font-size:13px;color:#9090A8;">
                      out of 100
                    </p>
                  </td>
                </tr>
              </table>

              <p style="margin:0 0 32px;font-size:14px;color:#9090A8;line-height:1.6;">
                {esc(days_until_certified)} days until HAWK Certified for {co}.
                Keep resolving findings to stay on track.
              </p>

              <table cellpadding="0" cellspacing="0" width="100%"
                     style="margin-bottom:32px;">
                <tr>
                  <td align="center">
                    <a href="{esc(portal_url)}"
                       style="display:inline-block;background:#00C48C;color:#ffffff;
                              font-size:15px;font-weight:700;text-decoration:none;
                              padding:16px 48px;border-radius:8px;">
                      View My Dashboard
                    </a>
                  </td>
                </tr>
              </table>
              {_fallback_url_line(portal_url)}
            </td>
          </tr>
"""
    return send_resend(
        to_email=to_email,
        subject=f"{company_name} security update — Day 3",
        html=_wrap(inner + _security_notice_block()),
        tags=[{"name": "category", "value": "shield_day3_update"}],
    )


def shield_day7_week_summary_email(
    *,
    to_email: str,
    company_name: str,
    domain: str,
    portal_url: str,
    score_now: int,
    findings_fixed: int,
    days_until_certified: int,
    progress_pct: int,
) -> dict[str, Any]:
    """EMAIL 4 — Day 7 week one summary."""
    esc = _esc
    pct = max(0, min(100, int(progress_pct)))
    dom = (domain or company_name or "your domain").strip()
    inner = f"""
          <tr>
            <td style="padding:40px 48px 32px;">
              <p style="margin:0 0 8px;font-size:22px;font-weight:700;
                        color:#ffffff;line-height:1.3;">
                Week one complete.
              </p>
              <p style="margin:0 0 32px;font-size:15px;color:#9090A8;line-height:1.6;">
                Here is everything HAWK did for
                <strong style="color:#00C48C;">{esc(dom)}</strong> this week.
              </p>

              <table cellpadding="0" cellspacing="0" width="100%"
                     style="margin-bottom:32px;">
                <tr>
                  <td width="33%" style="text-align:center;padding:16px 8px;
                                         background:#0F0E17;border-radius:8px 0 0 8px;
                                         border:1px solid #2a2a40;">
                    <p style="margin:0;font-size:28px;font-weight:900;color:#00C48C;">
                      7
                    </p>
                    <p style="margin:4px 0 0;font-size:11px;color:#9090A8;">
                      Days monitored
                    </p>
                  </td>
                  <td width="33%" style="text-align:center;padding:16px 8px;
                                         background:#0F0E17;
                                         border-top:1px solid #2a2a40;
                                         border-bottom:1px solid #2a2a40;">
                    <p style="margin:0;font-size:28px;font-weight:900;color:#00C48C;">
                      {esc(findings_fixed)}
                    </p>
                    <p style="margin:4px 0 0;font-size:11px;color:#9090A8;">
                      Issues fixed
                    </p>
                  </td>
                  <td width="33%" style="text-align:center;padding:16px 8px;
                                         background:#0F0E17;border-radius:0 8px 8px 0;
                                         border:1px solid #2a2a40;">
                    <p style="margin:0;font-size:28px;font-weight:900;color:#00C48C;">
                      {esc(score_now)}
                    </p>
                    <p style="margin:4px 0 0;font-size:11px;color:#9090A8;">
                      Security score
                    </p>
                  </td>
                </tr>
              </table>

              <table cellpadding="0" cellspacing="0" width="100%"
                     style="margin-bottom:24px;">
                <tr>
                  <td style="background:#0F0E17;border:1px solid #2a2a40;
                             border-left:3px solid #00C48C;border-radius:6px;
                             padding:14px 16px;">
                    <p style="margin:0 0 4px;font-size:13px;font-weight:700;
                              color:#00C48C;">Guarantee status</p>
                    <p style="margin:0;font-size:13px;color:#ffffff;">
                      ACTIVE — You are covered.
                    </p>
                  </td>
                </tr>
              </table>

              <table cellpadding="0" cellspacing="0" width="100%"
                     style="margin-bottom:32px;">
                <tr>
                  <td style="background:#0F0E17;border:1px solid #2a2a40;
                             border-left:3px solid #00C48C;border-radius:6px;
                             padding:14px 16px;">
                    <p style="margin:0 0 4px;font-size:13px;font-weight:700;
                              color:#00C48C;">HAWK Certified</p>
                    <p style="margin:0 0 8px;font-size:13px;color:#ffffff;">
                      {esc(days_until_certified)} days remaining
                    </p>
                    <table cellpadding="0" cellspacing="0" width="100%">
                      <tr>
                        <td style="background:#2a2a40;border-radius:4px;height:8px;">
                          <div style="background:#00C48C;border-radius:4px;
                                      height:8px;width:{esc(pct)}%;max-width:100%;">
                          </div>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>
              </table>

              <table cellpadding="0" cellspacing="0" width="100%"
                     style="margin-bottom:32px;">
                <tr>
                  <td align="center">
                    <a href="{esc(portal_url)}"
                       style="display:inline-block;background:#00C48C;color:#ffffff;
                              font-size:15px;font-weight:700;text-decoration:none;
                              padding:16px 48px;border-radius:8px;">
                      View My Security Dashboard
                    </a>
                  </td>
                </tr>
              </table>
              {_fallback_url_line(portal_url)}

              <table cellpadding="0" cellspacing="0" width="100%">
                <tr>
                  <td style="background:#0F0E17;border:1px solid #2a2a40;
                             border-left:3px solid #00C48C;border-radius:6px;
                             padding:14px 16px;">
                    <p style="margin:0;font-size:12px;color:#9090A8;line-height:1.6;">
                      <strong style="color:#00C48C;">Keep going.</strong>
                      Every finding you resolve brings you closer to
                      HAWK Certified and keeps your guarantee active.
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
"""
    return send_resend(
        to_email=to_email,
        subject="Your first week with HAWK — here is what happened",
        html=_wrap(inner + _security_notice_block()),
        tags=[{"name": "category", "value": "shield_day7_summary"}],
    )


def shield_guarantee_at_risk_email(
    *,
    to_email: str,
    first_name: str,
    domain: str,
    critical_finding: str,
    portal_url: str,
) -> dict[str, Any]:
    """EMAIL 5 — critical SLA window (e.g. ~20h): fix within hours to maintain coverage."""
    esc = _esc
    fn = (first_name or "").strip() or "there"
    dom = (domain or "").strip() or "your domain"
    inner = f"""
          <tr>
            <td style="padding:40px 48px 32px;">
              <p style="margin:0 0 8px;font-size:22px;font-weight:700;
                        color:#FF4444;line-height:1.3;">
                Your guarantee is at risk.
              </p>
              <p style="margin:0 0 32px;font-size:15px;color:#9090A8;line-height:1.6;">
                Hi {esc(fn)}, you have an unresolved critical finding on
                <strong style="color:#00C48C;">{esc(dom)}</strong> that must
                be fixed within 4 hours to maintain your coverage.
              </p>

              <table cellpadding="0" cellspacing="0" width="100%"
                     style="margin-bottom:32px;">
                <tr>
                  <td style="background:#0F0E17;border:1px solid #2a2a40;
                             border-left:3px solid #FF4444;border-radius:6px;
                             padding:14px 16px;">
                    <p style="margin:0 0 4px;font-size:11px;font-weight:700;
                              color:#FF4444;text-transform:uppercase;
                              letter-spacing:1px;">Critical — fix now</p>
                    <p style="margin:0;font-size:13px;color:#ffffff;line-height:1.5;">
                      {esc(critical_finding)}
                    </p>
                  </td>
                </tr>
              </table>

              <table cellpadding="0" cellspacing="0" width="100%"
                     style="margin-bottom:32px;">
                <tr>
                  <td align="center">
                    <a href="{esc(portal_url)}"
                       style="display:inline-block;background:#FF4444;color:#ffffff;
                              font-size:15px;font-weight:700;text-decoration:none;
                              padding:16px 48px;border-radius:8px;">
                      Fix This Now
                    </a>
                  </td>
                </tr>
              </table>
              {_fallback_url_line(portal_url)}

              <table cellpadding="0" cellspacing="0" width="100%">
                <tr>
                  <td style="background:#0F0E17;border:1px solid #2a2a40;
                             border-left:3px solid #FF4444;border-radius:6px;
                             padding:14px 16px;">
                    <p style="margin:0;font-size:12px;color:#9090A8;line-height:1.6;">
                      <strong style="color:#FF4444;">Need help?</strong>
                      Reply to this email or WhatsApp us at +18259458282
                      and our team will assist you immediately.
                    </p>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
"""
    return send_resend(
        to_email=to_email,
        subject="Action required — your HAWK guarantee is at risk",
        html=_wrap(inner + _security_notice_block()),
        tags=[{"name": "category", "value": "guarantee_at_risk"}],
    )


def send_homepage_scan_followup_email(
    *,
    to_email: str,
    domain: str,
    hawk_score: int | None,
    grade: str | None,
    findings_plain: list[str],
) -> dict[str, Any]:
    """Homepage capture — full report promise."""
    esc = _esc
    d = esc(domain)
    score_s = f"{hawk_score}/100" if hawk_score is not None else "—"
    grade_s = esc(grade) if grade else "—"
    bullets = ""
    for line in findings_plain[:5]:
        if line.strip():
            bullets += f"<li style=\"color:#9090A8;font-size:14px;\">{esc(line)}</li>"
    if not bullets:
        bullets = "<li style=\"color:#9090A8;font-size:14px;\">Your personalized report is being prepared.</li>"

    inner = f"""
          <tr>
            <td style="padding:40px 48px 32px;">
              <p style="margin:0 0 16px;font-size:22px;font-weight:700;color:#ffffff;line-height:1.3;">
                Thanks for scanning with HAWK
              </p>
              <p style="margin:0 0 24px;font-size:15px;color:#9090A8;line-height:1.6;">
                Quick scan snapshot for <strong style="color:#00C48C;">{d}</strong>:
                Grade <strong style="color:#ffffff;">{grade_s}</strong>,
                score <strong style="color:#ffffff;">{score_s}</strong>
              </p>
              <p style="margin:0 0 12px;font-size:14px;color:#9090A8;">What we flagged (plain English):</p>
              <ul style="margin:0;padding-left:20px;">{bullets}</ul>
              <p style="margin:24px 0 0;font-size:14px;color:#9090A8;line-height:1.6;">
                Your <strong style="color:#ffffff;">full analysis</strong> is running. We will follow up with the complete report and fix priorities shortly.
              </p>
              <p style="margin:16px 0 0;font-size:13px;color:#9090A8;">
                Questions: <a href="mailto:hello@securedbyhawk.com" style="color:#00C48C;text-decoration:none;">hello@securedbyhawk.com</a>
              </p>
            </td>
          </tr>
"""
    return send_resend(
        to_email=to_email,
        subject=f"Your HAWK security report — {domain}",
        html=_wrap(inner + _security_notice_block()),
        tags=[{"name": "category", "value": "homepage_scan_followup"}],
    )


def send_free_scan_ack_email(
    *,
    to_email: str,
    domain: str,
    first_name: str | None = None,
) -> dict[str, Any]:
    """Ack email for securedbyhawk.com/free-scan submissions.

    Sets the 24-hour expectation so the recipient doesn't bounce if the full
    scan + report hasn't landed yet. Deliberately spare — no marketing fluff.
    """
    esc = _esc
    d = esc(domain)
    hello = esc((first_name or "").strip()) or "there"
    inner = f"""
          <tr>
            <td style="padding:40px 48px 32px;">
              <p style="margin:0 0 16px;font-size:22px;font-weight:700;color:#ffffff;line-height:1.3;">
                Scan requested — report coming within 24 hours
              </p>
              <p style="margin:0 0 18px;font-size:15px;color:#9090A8;line-height:1.6;">
                Hi {hello}, we kicked off an external attack-surface scan on
                <strong style="color:#00C48C;">{d}</strong> the moment you hit submit.
              </p>
              <p style="margin:0 0 18px;font-size:15px;color:#9090A8;line-height:1.6;">
                Within <strong style="color:#ffffff;">24 hours</strong> you&apos;ll get a
                plain-English report with the <strong style="color:#ffffff;">3 highest-priority
                findings</strong> on your external surface — the same signals ransomware crews and
                credential-stuffing bots harvest before they ever contact you.
              </p>
              <p style="margin:0 0 0;font-size:14px;color:#9090A8;line-height:1.6;">
                No credit card. No sales call required to see the report. If anything in it needs
                fixing urgently we&apos;ll flag it at the top.
              </p>
              <p style="margin:24px 0 0;font-size:13px;color:#5C5876;">
                Questions: <a href="mailto:hello@securedbyhawk.com" style="color:#00C48C;text-decoration:none;">hello@securedbyhawk.com</a>
              </p>
            </td>
          </tr>
"""
    return send_resend(
        to_email=to_email,
        subject=f"Your HAWK free scan — report for {domain} in 24 hours",
        html=_wrap(inner + _security_notice_block()),
        tags=[{"name": "category", "value": "free_scan_ack"}],
    )


def send_free_scan_report_email(
    *,
    to_email: str,
    domain: str,
    first_name: str | None,
    hawk_score: int | None,
    grade: str | None,
    findings: list[dict[str, str]],
    industry: str | None = None,
) -> dict[str, Any]:
    """3-finding report for a free-scan lead. ``findings`` is a list of
    ``{text, severity, title}`` from ``pick_top_findings``.
    """
    import os as _os

    booking_url = (
        _os.environ.get("CAL_COM_BOOKING_URL")
        or "https://cal.com/hawksecurity/15min"
    ).strip()

    esc = _esc
    d = esc(domain)
    hello = esc((first_name or "").strip()) or "there"
    score_s = f"{hawk_score}/100" if hawk_score is not None else "—"
    grade_s = esc(grade) if grade else "—"

    sev_color = {
        "critical": "#FF4D4D",
        "high": "#FF8C42",
        "medium": "#E8B54A",
        "warning": "#E8B54A",
        "low": "#3BA7FF",
        "info": "#9090A8",
    }

    items = ""
    for i, f in enumerate(findings[:3], start=1):
        sev = (f.get("severity") or "medium").lower()
        color = sev_color.get(sev, "#9090A8")
        text = esc(f.get("text") or "")
        items += f"""
              <tr>
                <td style="padding:16px 0;border-top:1px solid #2a2a40;">
                  <p style="margin:0 0 6px;font-size:12px;letter-spacing:0.08em;text-transform:uppercase;color:{color};font-weight:700;">
                    Finding {i} · {esc(sev)}
                  </p>
                  <p style="margin:0;font-size:14px;color:#d6d6e8;line-height:1.55;">{text}</p>
                </td>
              </tr>"""

    # Vertical-specific regulatory angle, mirrors EMAIL_SYSTEM_PROMPT
    angles = {
        "dental": "Under the HIPAA Security Rule and HHS OCR 60-day breach-notification rule, exposures like these can become a reportable incident if an attacker gets to PHI.",
        "legal": "ABA Formal Opinion 24-514 and Model Rules 1.1, 1.4, 1.6 obligate you to take reasonable technical safeguards and notify affected clients if this surface is exploited.",
        "accounting": "Under the FTC Safeguards Rule (and the May 2024 breach-notification amendment) any unauthorized access to client data triggers a 30-day FTC notification obligation.",
    }
    angle = angles.get((industry or "").lower(), "")
    angle_block = (
        f"""
          <tr>
            <td style="padding:0 48px 18px;">
              <p style="margin:0;font-size:13px;color:#9090A8;line-height:1.6;">
                {esc(angle)}
              </p>
            </td>
          </tr>
"""
        if angle
        else ""
    )

    inner = f"""
          <tr>
            <td style="padding:40px 48px 16px;">
              <p style="margin:0 0 8px;font-size:22px;font-weight:700;color:#ffffff;line-height:1.3;">
                Your 3-finding security report — {d}
              </p>
              <p style="margin:0 0 16px;font-size:14px;color:#9090A8;line-height:1.6;">
                Hi {hello}, here&apos;s what attackers can see on your external surface today.
              </p>
              <p style="margin:0 0 0;font-size:14px;color:#9090A8;line-height:1.6;">
                Grade <strong style="color:#ffffff;">{grade_s}</strong> · score <strong style="color:#ffffff;">{score_s}</strong>
              </p>
            </td>
          </tr>
          <tr>
            <td style="padding:0 48px 16px;">
              <table cellpadding="0" cellspacing="0" width="100%">{items}
              </table>
            </td>
          </tr>
{angle_block}
          <tr>
            <td align="center" style="padding:8px 48px 32px;">
              <a href="{esc(booking_url)}"
                 style="display:inline-block;padding:14px 28px;border-radius:8px;background:#00C48C;color:#0B0B12;font-weight:700;font-size:14px;text-decoration:none;">
                Book a 15-min walkthrough
              </a>
              <p style="margin:16px 0 0;font-size:12px;color:#5C5876;line-height:1.6;">
                We&apos;ll walk through how to fix each finding above. No pitch deck, no obligation.
              </p>
            </td>
          </tr>
"""
    return send_resend(
        to_email=to_email,
        subject=f"Your 3-finding HAWK report — {domain}",
        html=_wrap(inner + _security_notice_block()),
        tags=[{"name": "category", "value": "free_scan_report"}],
    )


def send_guarantee_verification_code_email(*, to_email: str, code: str, full_name: str) -> dict[str, Any]:
    """6-digit code for Breach Response Guarantee PDF — same visual system."""
    esc = _esc
    name = esc(full_name.strip() or "there")
    inner = f"""
          <tr>
            <td style="padding:40px 48px 32px;">
              <p style="margin:0 0 8px;font-size:22px;font-weight:700;color:#ffffff;">
                Verify your email
              </p>
              <p style="margin:0 0 28px;font-size:14px;color:#9090A8;line-height:1.6;">
                Hi {name}, use this code to view the <strong style="color:#ffffff;">Breach Response Guarantee</strong> document on securedbyhawk.com.
              </p>
              <table cellpadding="0" cellspacing="0" width="100%" style="margin-bottom:24px;">
                <tr>
                  <td align="center">
                    <div style="display:inline-block;padding:16px 28px;border-radius:10px;background:#0F0E17;border:1px solid #2a2a40;">
                      <p style="margin:0;font-size:11px;color:#5C5876;letter-spacing:0.06em;">YOUR CODE</p>
                      <p style="margin:8px 0 0 0;font-size:32px;font-weight:800;letter-spacing:0.25em;color:#00C48C;font-family:ui-monospace,SFMono-Regular,Menlo,Monaco,Consolas,monospace">{esc(code)}</p>
                    </div>
                  </td>
                </tr>
              </table>
              <p style="margin:0;font-size:12px;color:#5C5876;text-align:center;">
                Expires in 15 minutes. If you did not request this, you can ignore this email.
              </p>
            </td>
          </tr>
"""
    return send_resend(
        to_email=to_email,
        subject="Your HAWK verification code",
        html=_wrap(inner + _security_notice_block()),
        tags=[{"name": "category", "value": "guarantee_doc_verify"}],
        from_email=_guarantee_from(),
    )
