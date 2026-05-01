"""Static fix-guide registry — plain-English, step-by-step remediation
for every finding category the HAWK scanner produces (priority list #39).

When the OpenAI interpretation layer returns a ``fix_guide`` for a finding,
that takes precedence. This module provides the fallback for findings that
were not LLM-interpreted (e.g. OpenAI key not configured, rate-limited, or
the finding was added after interpretation ran).

Guides are keyed by **(category, title-substring)** so that a single entry
can cover all variants of a title (e.g. "SPF policy" covers both the
passing and failing SPF finding). A category-only fallback catches any
title not explicitly mapped.

All text is written for a non-technical audience: dental office managers,
law firm administrators, CPA practice owners. No jargon, exact DNS records
or step-by-step CLI instructions where applicable.
"""

from __future__ import annotations

from typing import Any


# ------------------------------------------------------------------
# Registry: (category_lower, title_substring_lower | None) → guide
# None as the title key = category-level fallback.
# ------------------------------------------------------------------

_GUIDES: list[tuple[str, str | None, str]] = [
    # ── Email Security ───────────────────────────────────────────
    (
        "email security",
        "spf",
        (
            "1. Log in to your DNS provider (GoDaddy, Cloudflare, Namecheap, etc.).\n"
            "2. Find the TXT record for your root domain that starts with 'v=spf1'.\n"
            "3. If it does not exist, add a new TXT record:\n"
            "   Name: @   Value: v=spf1 include:_spf.google.com ~all\n"
            "   (Replace _spf.google.com with your email provider's SPF include.)\n"
            "4. If it exists but ends with '~all' (soft fail), change it to '-all' (hard fail)\n"
            "   once you have confirmed all legitimate senders are listed.\n"
            "5. Save and wait up to 48 hours for DNS propagation.\n"
            "6. Verify with: nslookup -type=TXT yourdomain.com"
        ),
    ),
    (
        "email security",
        "dmarc",
        (
            "1. Log in to your DNS provider.\n"
            "2. Add a TXT record:\n"
            "   Name: _dmarc   Value: v=DMARC1; p=quarantine; rua=mailto:dmarc@yourdomain.com\n"
            "3. Start with p=quarantine so suspicious emails go to spam rather than being silently rejected.\n"
            "4. After 2–4 weeks of monitoring DMARC reports (sent to the rua address),\n"
            "   switch to p=reject to fully block spoofed email from your domain.\n"
            "5. Save and wait for DNS propagation (usually under 1 hour).\n"
            "6. Verify with: nslookup -type=TXT _dmarc.yourdomain.com"
        ),
    ),
    (
        "email security",
        "dkim",
        (
            "1. DKIM is configured through your email provider (Google Workspace, Microsoft 365, etc.).\n"
            "2. In Google Workspace: Admin Console → Apps → Gmail → Authenticate email → Generate new record.\n"
            "   In Microsoft 365: Defender portal → Email authentication → DKIM → Enable.\n"
            "3. Copy the CNAME or TXT record your provider gives you.\n"
            "4. Add it to your DNS as instructed (usually a CNAME for the selector subdomain).\n"
            "5. Return to your email provider and click 'Start authenticating' / 'Enable'.\n"
            "6. Verify by sending a test email to mail-tester.com or check-auth@verifier.port25.com."
        ),
    ),
    (
        "email security",
        None,
        (
            "1. Review your domain's email authentication records (SPF, DKIM, DMARC).\n"
            "2. Ensure SPF lists all services that send email on your behalf.\n"
            "3. Enable DKIM signing through your email provider.\n"
            "4. Set a DMARC policy of at least p=quarantine.\n"
            "5. Monitor DMARC aggregate reports for 2–4 weeks before tightening to p=reject."
        ),
    ),
    # ── SSL/TLS ──────────────────────────────────────────────────
    (
        "ssl/tls",
        "handshake",
        (
            "1. Check that your web host or CDN has a valid SSL certificate installed.\n"
            "2. In Cloudflare: SSL/TLS → Overview → set mode to 'Full (strict)'.\n"
            "3. If self-hosting: install a free certificate from Let's Encrypt:\n"
            "   sudo certbot --nginx -d yourdomain.com\n"
            "4. Ensure port 443 is open in your firewall.\n"
            "5. Test at ssllabs.com/ssltest — aim for grade A."
        ),
    ),
    (
        "ssl/tls",
        "tls configuration",
        (
            "1. Disable old TLS versions (TLS 1.0 and 1.1 are insecure).\n"
            "   In Nginx: ssl_protocols TLSv1.2 TLSv1.3;\n"
            "   In Apache: SSLProtocol all -SSLv3 -TLSv1 -TLSv1.1\n"
            "2. Use strong cipher suites — your hosting provider may have a recommended config.\n"
            "3. Enable HSTS by adding this header:\n"
            "   Strict-Transport-Security: max-age=31536000; includeSubDomains\n"
            "4. Renew certificates before expiry (Let's Encrypt auto-renews with certbot).\n"
            "5. Re-test at ssllabs.com/ssltest after changes."
        ),
    ),
    (
        "ssl/tls",
        None,
        (
            "1. Ensure all public-facing services use TLS 1.2 or higher.\n"
            "2. Install a valid SSL certificate from a trusted certificate authority.\n"
            "3. Disable TLS 1.0 and 1.1 in your web server configuration.\n"
            "4. Add HSTS headers to prevent downgrade attacks.\n"
            "5. Test your configuration at ssllabs.com/ssltest."
        ),
    ),
    # ── Access control / MFA ─────────────────────────────────────
    (
        "access control",
        "no mfa",
        (
            "1. Identify every login page found by the scan (listed in the finding details).\n"
            "2. Enable multi-factor authentication (MFA/2FA) on each one:\n"
            "   - Google Workspace: Admin → Security → 2-Step Verification → Enforce.\n"
            "   - Microsoft 365: Azure AD → Security → MFA → Enable.\n"
            "   - Practice management software: check Settings → Security for a 2FA option.\n"
            "3. Require all staff to enroll — use an authenticator app (Google Authenticator,\n"
            "   Microsoft Authenticator, or Authy), not SMS if possible.\n"
            "4. Store backup codes in a safe place (locked file cabinet or password manager).\n"
            "5. Re-run the HAWK scan to verify MFA is now detected."
        ),
    ),
    (
        "access control",
        None,
        (
            "1. Enable multi-factor authentication on all internet-facing login portals.\n"
            "2. Use strong, unique passwords for each system (use a password manager).\n"
            "3. Remove or restrict access for unused accounts.\n"
            "4. Review access logs for any unfamiliar login activity."
        ),
    ),
    # ── Attack surface ───────────────────────────────────────────
    (
        "attack surface",
        "login",
        (
            "1. Review each URL listed in the finding — determine if it needs to be public.\n"
            "2. For admin panels (wp-admin, cpanel, webmail):\n"
            "   - Restrict access by IP allowlist in your web server or hosting control panel.\n"
            "   - Add rate limiting to prevent brute-force attempts.\n"
            "3. Enable MFA on every login form.\n"
            "4. Use a Web Application Firewall (Cloudflare, Sucuri) to block automated scanners.\n"
            "5. Consider moving admin paths behind a VPN if they don't need public access."
        ),
    ),
    (
        "attack surface",
        "subdomain",
        (
            "1. Review the list of subdomains found by the scan.\n"
            "2. For any subdomain you don't recognize:\n"
            "   - Check if it points to an active service. If not, remove the DNS record.\n"
            "   - Dangling DNS records can be hijacked (subdomain takeover).\n"
            "3. Consolidate services where possible to reduce your attack surface.\n"
            "4. Set up monitoring for new subdomain registrations on your domain."
        ),
    ),
    (
        "attack surface",
        None,
        (
            "1. Audit all public-facing services and remove anything that is unused.\n"
            "2. Restrict admin interfaces to authorized IP addresses.\n"
            "3. Enable MFA on all authentication endpoints.\n"
            "4. Use a CDN or WAF to shield your origin servers."
        ),
    ),
    # ── Transport security ───────────────────────────────────────
    (
        "transport security",
        None,
        (
            "1. Set up an automatic HTTP-to-HTTPS redirect on your web server:\n"
            "   Nginx: server { listen 80; return 301 https://$host$request_uri; }\n"
            "   Apache: RewriteEngine On / RewriteRule ^(.*)$ https://%{HTTP_HOST}/$1 [R=301,L]\n"
            "2. In Cloudflare: SSL/TLS → Edge Certificates → toggle 'Always Use HTTPS'.\n"
            "3. Add an HSTS header once you confirm HTTPS works everywhere:\n"
            "   Strict-Transport-Security: max-age=31536000; includeSubDomains\n"
            "4. Test by visiting http://yourdomain.com — it should immediately redirect to https://."
        ),
    ),
    # ── Network exposure ─────────────────────────────────────────
    (
        "network exposure",
        None,
        (
            "1. Review the list of open ports found by the scan.\n"
            "2. For each non-standard port (anything besides 80 and 443):\n"
            "   - Identify what service is listening. If it's unused, shut it down.\n"
            "   - If it's intentional (e.g. a staging server), restrict it with a firewall rule\n"
            "     to only allow your office IP.\n"
            "3. Use your hosting provider's firewall or security group settings:\n"
            "   AWS: Security Groups → edit inbound rules.\n"
            "   DigitalOcean: Networking → Firewalls.\n"
            "4. Re-scan to confirm the ports are no longer visible."
        ),
    ),
    # ── Internet exposure (InternetDB) ───────────────────────────
    (
        "internet exposure",
        "cve",
        (
            "1. The scan found known vulnerabilities (CVEs) associated with your public IP.\n"
            "2. Identify the affected software from the finding details.\n"
            "3. Update or patch the software to the latest version:\n"
            "   - Web servers: apt update && apt upgrade (Linux) or Windows Update.\n"
            "   - CMS plugins: update through the admin dashboard.\n"
            "4. If the software is end-of-life, migrate to a supported alternative.\n"
            "5. Re-scan after patching to confirm the CVE no longer appears."
        ),
    ),
    (
        "internet exposure",
        None,
        (
            "1. Review what services are exposed on your public IP addresses.\n"
            "2. Close or firewall any ports that don't need to be public.\n"
            "3. Keep all internet-facing software up to date.\n"
            "4. Consider placing services behind a reverse proxy or CDN."
        ),
    ),
    # ── Lookalike domains ────────────────────────────────────────
    (
        "lookalike domains",
        None,
        (
            "1. Review the list of lookalike domains found by the scan.\n"
            "2. Check if any are actively being used to impersonate your practice:\n"
            "   - Visit each domain in a browser (use caution — don't enter any credentials).\n"
            "3. Register the most obvious typos of your domain defensively\n"
            "   (e.g. if you own smithdental.com, register smthdental.com, smithdentel.com).\n"
            "4. Report malicious lookalike domains to your domain registrar for takedown.\n"
            "5. Warn staff about phishing emails that might use these lookalike domains.\n"
            "6. DMARC (p=reject) prevents attackers from sending email *as* your domain,\n"
            "   but does not stop them from using a lookalike domain — vigilance is key."
        ),
    ),
    # ── Supply chain (NVD CVEs) ──────────────────────────────────
    (
        "supply chain",
        None,
        (
            "1. The scan detected outdated software with known security vulnerabilities.\n"
            "2. Check the CVE ID(s) listed in the finding details at nvd.nist.gov.\n"
            "3. Update the affected software to the patch version listed in the finding.\n"
            "   - For web frameworks: follow the vendor's upgrade guide.\n"
            "   - For CMS platforms (WordPress, Joomla): update via the admin panel.\n"
            "4. If the software cannot be updated immediately:\n"
            "   - Apply any available hotfixes or workarounds from the vendor.\n"
            "   - Use a WAF rule to block the specific attack vector if documented.\n"
            "5. Set up automatic security updates where possible to prevent future gaps."
        ),
    ),
    # ── Breach monitoring ────────────────────────────────────────
    (
        "breach monitoring",
        None,
        (
            "1. One or more email addresses on your domain appeared in a data breach.\n"
            "2. Immediately reset passwords for all affected accounts.\n"
            "3. Enable MFA on every account that was in the breach.\n"
            "4. Check if the same passwords were reused on other services — change those too.\n"
            "5. Notify affected staff that their credentials were exposed and instruct them\n"
            "   to use unique passwords going forward (recommend a password manager like\n"
            "   1Password, Bitwarden, or LastPass).\n"
            "6. Monitor for suspicious login activity on your systems over the next 30 days."
        ),
    ),
    # ── Breach Exposure (HIBP) ───────────────────────────────────
    (
        "breach exposure",
        None,
        (
            "1. Domain email addresses were found in known breach databases.\n"
            "2. Force a password reset for all affected accounts.\n"
            "3. Enable MFA (multi-factor authentication) on all accounts.\n"
            "4. Instruct staff to never reuse passwords across services.\n"
            "5. Use a password manager to generate and store strong, unique passwords.\n"
            "6. Consider enrolling in a breach monitoring service for ongoing alerts."
        ),
    ),
    # ── Stealer exposure (Breachsense) ───────────────────────────
    (
        "stealer exposure",
        None,
        (
            "1. URGENT: Credentials associated with your domain were found in info-stealer logs.\n"
            "   This means malware on a device captured real login credentials.\n"
            "2. Immediately reset the password for every affected account.\n"
            "3. Enable MFA on all accounts — this is critical because the attacker has\n"
            "   the actual password, not a hash.\n"
            "4. Run antivirus/anti-malware scans on all devices used by affected staff.\n"
            "5. Check for unauthorized access: review login history, sent emails,\n"
            "   financial transactions, and patient/client records.\n"
            "6. If patient data may have been accessed, consult your compliance officer\n"
            "   about HIPAA breach notification requirements (45 CFR 164.408)."
        ),
    ),
    # ── Secrets exposure (GitHub) ────────────────────────────────
    (
        "secrets exposure",
        None,
        (
            "1. Public code repositories may contain credentials tied to your domain.\n"
            "2. Search GitHub for your domain: github.com/search?q=yourdomain.com&type=code\n"
            "3. If you find exposed API keys, passwords, or tokens:\n"
            "   - Revoke and rotate them immediately.\n"
            "   - Remove or overwrite the sensitive code from the repository.\n"
            "   - Note: deleting a file from Git doesn't remove it from history.\n"
            "     Use 'git filter-repo' or contact GitHub support for full scrubbing.\n"
            "4. Use .gitignore to prevent committing credentials in the future.\n"
            "5. Consider using a secrets manager (AWS Secrets Manager, HashiCorp Vault,\n"
            "   or environment variables) instead of hard-coding credentials."
        ),
    ),
    # ── Ransomware intelligence ──────────────────────────────────
    (
        "ransomware intelligence",
        None,
        (
            "1. Active ransomware groups are targeting businesses in your industry and state.\n"
            "2. Ensure you have offline backups that are tested regularly:\n"
            "   - Use the 3-2-1 rule: 3 copies, 2 different media, 1 offsite.\n"
            "   - Test restoring from backup at least quarterly.\n"
            "3. Patch all systems — most ransomware exploits known vulnerabilities.\n"
            "4. Enable MFA on all remote access (VPN, RDP, email).\n"
            "5. Train staff to recognize phishing emails — this is the #1 entry point.\n"
            "6. Disable RDP on any internet-facing system. Use a VPN instead.\n"
            "7. Consider a ransomware-specific insurance rider if not already covered."
        ),
    ),
    # ── Exposure evidence (screenshots) ──────────────────────────
    (
        "exposure evidence",
        None,
        (
            "1. The scan captured a live screenshot of a publicly accessible login or admin page.\n"
            "2. Determine whether this page needs to be public:\n"
            "   - Patient/client portals: should be public but protected with MFA.\n"
            "   - Admin panels: should NOT be public. Restrict by IP or place behind a VPN.\n"
            "3. Remove any version numbers, server banners, or error messages visible on the page.\n"
            "4. Ensure the login page uses HTTPS and has rate limiting enabled."
        ),
    ),
    # ── Vertical software exposure ───────────────────────────────
    (
        "software exposure",
        "dentrix",
        (
            "1. Dentrix (Henry Schein) was detected on your public-facing infrastructure.\n"
            "2. Ensure Dentrix is NOT directly accessible from the internet:\n"
            "   - The Dentrix server should only be reachable from your office network.\n"
            "   - If remote access is needed, use a VPN — never expose Dentrix directly.\n"
            "3. Apply the latest Dentrix security patches from Henry Schein.\n"
            "4. Enable the built-in audit trail in Dentrix for HIPAA compliance.\n"
            "5. Restrict user permissions to the minimum needed for each role."
        ),
    ),
    (
        "software exposure",
        "eaglesoft",
        (
            "1. Eaglesoft (Patterson Dental) was detected on your public-facing infrastructure.\n"
            "2. Ensure the Eaglesoft server is behind a firewall and not internet-accessible.\n"
            "3. If you use Eaglesoft's cloud or remote access features, ensure MFA is enabled.\n"
            "4. Keep Eaglesoft updated to the latest version via Patterson's update service.\n"
            "5. Enable encryption at rest for the Eaglesoft database."
        ),
    ),
    (
        "software exposure",
        "carestream",
        (
            "1. Carestream Dental imaging software was detected on your perimeter.\n"
            "2. Imaging servers should never be directly accessible from the internet.\n"
            "3. Place the Carestream server behind your office firewall.\n"
            "4. Use a VPN for any remote access to imaging data.\n"
            "5. Apply all vendor security patches promptly."
        ),
    ),
    (
        "software exposure",
        "clio",
        (
            "1. Clio (legal practice management) was detected.\n"
            "2. Enable MFA in Clio: Settings → Security → Two-Factor Authentication.\n"
            "3. Review user access — remove inactive accounts and limit permissions.\n"
            "4. Ensure your Clio data is encrypted and that you're using their latest security features.\n"
            "5. Review Clio's trust page (trust.clio.com) for any active advisories."
        ),
    ),
    (
        "software exposure",
        "mycase",
        (
            "1. MyCase (legal practice management) was detected.\n"
            "2. Enable two-factor authentication for all MyCase users.\n"
            "3. Review connected integrations and revoke any you don't actively use.\n"
            "4. Ensure client portal links use HTTPS.\n"
            "5. Keep your MyCase subscription current to receive security patches."
        ),
    ),
    (
        "software exposure",
        None,
        (
            "1. Practice management or industry-specific software was detected on your perimeter.\n"
            "2. Ensure the software is NOT directly accessible from the internet unless designed for it.\n"
            "3. Place internal applications behind a firewall or VPN.\n"
            "4. Apply all vendor security patches and updates.\n"
            "5. Enable MFA if the software supports it.\n"
            "6. Review the vendor's security documentation for hardening recommendations."
        ),
    ),
]


def _normalize(s: str) -> str:
    return (s or "").strip().lower()


def get_fix_guide(category: str, title: str) -> str | None:
    """Return the best-matching static fix guide for a finding.

    Matching priority:
    1. Exact category + title substring match
    2. Category-only fallback (title key is None)
    3. None if no match at all
    """
    cat = _normalize(category)
    ttl = _normalize(title)

    category_fallback: str | None = None

    for guide_cat, guide_title, guide_text in _GUIDES:
        if guide_cat != cat and guide_cat not in cat:
            continue
        if guide_title is None:
            if category_fallback is None:
                category_fallback = guide_text
            continue
        if guide_title in ttl:
            return guide_text

    return category_fallback


def apply_fallback_guides(findings: list[dict[str, Any]]) -> int:
    """Fill in ``fix_guide`` on findings that lack one. Returns count of guides added."""
    count = 0
    for f in findings:
        if f.get("fix_guide"):
            continue
        guide = get_fix_guide(f.get("category", ""), f.get("title", ""))
        if guide:
            f["fix_guide"] = guide
            count += 1
    return count
