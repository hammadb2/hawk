"""
HAWK Specter Scanner — runs on Specter server (10.0.0.2:8002).
Passive external attack-surface checks: DNS, SSL/TLS, ports, headers, redirect, subdomains.
Returns structured findings JSON and grade.
"""

from __future__ import annotations

import concurrent.futures
import re
import socket
import ssl
import uuid
from datetime import datetime, timezone
from typing import Any

import dns.resolver
import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class ScanRequest(BaseModel):
    domain: str = Field(..., min_length=1, description="Domain to scan (e.g. example.com)")
    scan_id: str | None = Field(None, description="Optional scan ID for correlation")


class Finding(BaseModel):
    id: str
    severity: str  # critical | warning | info | ok
    category: str  # DNS | SSL | Network | Web | Subdomains
    title: str
    description: str
    technical_detail: str
    affected_asset: str
    remediation: str
    compliance: list[str] = Field(default_factory=list)


class ScanResponse(BaseModel):
    scan_id: str | None = None
    domain: str
    status: str = "completed"
    score: int = Field(..., ge=0, le=100)
    grade: str = Field(..., pattern=r"^[A-F]$")
    findings: list[Finding] = Field(default_factory=list)
    started_at: str = ""
    completed_at: str = ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# US framework tags attached to findings. Mapping is framework neutral at scan
# time because scans run before the prospect's vertical is confirmed. The
# downstream vertical aware compliance PDF in services/crm_compliance_report.py
# re-maps findings to HIPAA, FTC Safeguards, or ABA Formal Opinion 24-514 based
# on the client's vertical when the report is generated.
COMPLIANCE_TRANSMISSION = ["HIPAA 164.312(e)", "FTC 314.4(c)(3)"]
COMPLIANCE_RISK_MGMT = ["HIPAA 164.308(a)(1)", "FTC 314.4(b)"]
COMPLIANCE_EMAIL_AUTH = ["HIPAA 164.308(a)(5)", "FTC 314.4(d)", "ABA Rule 1.6(c)"]
COMPLIANCE_ACCESS = ["HIPAA 164.312(a)", "FTC 314.4(c)(1)"]
COMPLIANCE_AVAILABILITY = ["HIPAA 164.308(a)(7)", "FTC 314.4(h)"]

# Ports to scan; (port, "label", severity_if_open: warning | critical)
PORT_CHECKS = [
    (21, "FTP", "critical"),
    (22, "SSH", "info"),  # SSH expected
    (23, "Telnet", "critical"),
    (25, "SMTP", "warning"),
    (3306, "MySQL", "critical"),
    (3389, "RDP", "critical"),
    (5432, "PostgreSQL", "critical"),
    (6379, "Redis", "critical"),
    (8080, "HTTP-Alt", "warning"),
    (8443, "HTTPS-Alt", "warning"),
    (27017, "MongoDB", "critical"),
]

SUBDOMAIN_PREFIXES = [
    "www", "mail", "webmail", "smtp", "ftp", "dev", "staging",
    "api", "admin", "portal", "vpn", "remote", "autodiscover",
    "cpanel", "webdisk", "ns1", "ns2",
]

# Weak/insecure cipher patterns (no SSLv3, TLS 1.0/1.1; no export/null/RC4/DES)
WEAK_CIPHER_PATTERNS = [
    re.compile(r"NULL", re.I),
    re.compile(r"EXPORT", re.I),
    re.compile(r"RC4", re.I),
    re.compile(r"DES(-CBC|-EDE)?", re.I),
    re.compile(r"MD5", re.I),
    re.compile(r"anon", re.I),
]


def _make_finding(
    severity: str,
    category: str,
    title: str,
    description: str,
    technical_detail: str,
    affected_asset: str,
    remediation: str,
    compliance: list[str] | None = None,
) -> Finding:
    return Finding(
        id=str(uuid.uuid4()),
        severity=severity,
        category=category,
        title=title,
        description=description,
        technical_detail=technical_detail,
        affected_asset=affected_asset,
        remediation=remediation,
        compliance=compliance or [],
    )


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# 1. DNS Security
# ---------------------------------------------------------------------------


def _check_dns(domain: str) -> list[Finding]:
    findings: list[Finding] = []
    base_asset = f"DNS ({domain})"

    # Resolver with timeout
    resolver = dns.resolver.Resolver()
    resolver.timeout = 5
    resolver.lifetime = 10

    # SPF
    try:
        answers = resolver.resolve(domain, "TXT")
        spf_found = False
        spf_valid = False
        for rdata in answers:
            txt = rdata.to_text().strip('"')
            if "v=spf1" in txt:
                spf_found = True
                if "v=spf1" in txt and ("include:" in txt or "a:" in txt or "mx:" in txt or "ip4:" in txt or "all" in txt):
                    spf_valid = True
                break
        if not spf_found:
            findings.append(_make_finding(
                "critical",
                "DNS",
                "SPF record missing",
                "Your domain does not have an SPF (Sender Policy Framework) record. This allows attackers to send email that appears to come from your domain.",
                f"No TXT record containing v=spf1 found for {domain}",
                base_asset,
                f"Add a TXT record for {domain} with value similar to: v=spf1 include:_spf.google.com ~all (adjust for your mail provider).",
                COMPLIANCE_EMAIL_AUTH,
            ))
        elif not spf_valid:
            findings.append(_make_finding(
                "warning",
                "DNS",
                "SPF record may be incomplete",
                "An SPF record exists but may not correctly authorize your mail servers.",
                f"SPF record found for {domain} but structure may be invalid or too restrictive.",
                base_asset,
                "Ensure your SPF record includes all servers that send email for your domain (e.g. include: or ip4:).",
                COMPLIANCE_EMAIL_AUTH,
            ))
        else:
            findings.append(_make_finding(
                "ok",
                "DNS",
                "SPF record present and valid",
                "Your domain has a valid SPF record to help prevent email spoofing.",
                f"SPF record found for {domain}",
                base_asset,
                "No action required.",
                [],
            ))
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers, dns.exception.Timeout) as e:
        findings.append(_make_finding(
            "critical",
            "DNS",
            "SPF record missing or DNS unreachable",
            "We could not find an SPF record for your domain. This may be due to missing DNS or DNS resolution failure.",
            str(e),
            base_asset,
            "Add a TXT record with v=spf1 and ensure DNS is correctly configured.",
            COMPLIANCE_EMAIL_AUTH,
        ))

    # DMARC
    try:
        dmarc_domain = f"_dmarc.{domain}"
        answers = resolver.resolve(dmarc_domain, "TXT")
        dmarc_found = False
        policy_ok = False
        dmarc_raw = ""
        for rdata in answers:
            txt = rdata.to_text().strip('"')
            if "v=DMARC1" in txt or "v=DMARC1" in txt:
                dmarc_found = True
                dmarc_raw = txt
                if "p=reject" in txt or "p=quarantine" in txt:
                    policy_ok = True
                elif "p=none" in txt:
                    policy_ok = False
                break
        if not dmarc_found:
            findings.append(_make_finding(
                "critical",
                "DNS",
                "DMARC record missing",
                "Your domain has no DMARC record. Attackers can more easily send phishing email that appears to come from your domain.",
                f"No DMARC TXT record at {dmarc_domain}",
                base_asset,
                f"Add a TXT record for _dmarc.{domain} with at least: v=DMARC1; p=quarantine; (or p=reject for stronger protection).",
                COMPLIANCE_EMAIL_AUTH,
            ))
        elif not policy_ok:
            findings.append(_make_finding(
                "warning",
                "DNS",
                "DMARC policy is monitoring only (p=none)",
                "DMARC is set to p=none, which means no action is taken on failing messages. Your domain is still at risk of spoofing.",
                f"DMARC record: {dmarc_raw[:200]}",
                base_asset,
                "Change DMARC to p=quarantine or p=reject once you have validated SPF/DKIM.",
                COMPLIANCE_EMAIL_AUTH,
            ))
        else:
            findings.append(_make_finding(
                "ok",
                "DNS",
                "DMARC record present with enforcement",
                "Your domain has DMARC with a policy that enforces or quarantines failing messages.",
                f"DMARC: {dmarc_raw[:200]}",
                base_asset,
                "No action required.",
                [],
            ))
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers, dns.exception.Timeout) as e:
        findings.append(_make_finding(
            "critical",
            "DNS",
            "DMARC record missing",
            "We could not find a DMARC record for your domain.",
            str(e),
            base_asset,
            f"Add a TXT record for _dmarc.{domain} with v=DMARC1; p=quarantine;",
            COMPLIANCE_EMAIL_AUTH,
        ))

    # DKIM (default selector)
    try:
        dkim_domain = f"default._domainkey.{domain}"
        answers = resolver.resolve(dkim_domain, "TXT")
        dkim_found = False
        for rdata in answers:
            txt = rdata.to_text().strip('"')
            if "v=DKIM1" in txt or "DKIM1" in txt:
                dkim_found = True
                break
        if not dkim_found:
            findings.append(_make_finding(
                "warning",
                "DNS",
                "DKIM (default selector) not found",
                "No DKIM record was found for the default selector. Some receivers may treat unsigned mail from your domain with less trust.",
                f"No TXT record at {dkim_domain} containing DKIM1",
                base_asset,
                "If you use a different DKIM selector, ensure it is published. Otherwise add a TXT record at default._domainkey.{domain} with your mail provider's DKIM public key.",
                COMPLIANCE_EMAIL_AUTH,
            ))
        else:
            findings.append(_make_finding(
                "ok",
                "DNS",
                "DKIM selector exists",
                "A DKIM record was found for the default selector.",
                f"DKIM TXT found at {dkim_domain}",
                base_asset,
                "No action required.",
                [],
            ))
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers, dns.exception.Timeout):
        findings.append(_make_finding(
            "warning",
            "DNS",
            "DKIM (default selector) not found",
            "We could not find a DKIM record for the default selector. Your mail provider may use a different selector.",
            f"No TXT at default._domainkey.{domain}",
            base_asset,
            "Publish DKIM for the selector your mail server uses, or confirm default._domainkey is correct.",
            COMPLIANCE_EMAIL_AUTH,
        ))

    # MX records
    try:
        answers = resolver.resolve(domain, "MX")
        if not answers:
            findings.append(_make_finding(
                "warning",
                "DNS",
                "No MX records",
                "Your domain has no MX records. Incoming email cannot be delivered to this domain.",
                f"No MX records for {domain}",
                base_asset,
                "Add MX records pointing to your mail server(s) if you receive email at this domain.",
                [],
            ))
        else:
            mx_list = [str(r.exchange) for r in sorted(answers, key=lambda x: x.preference)]
            findings.append(_make_finding(
                "ok",
                "DNS",
                "MX records present",
                "Your domain has MX records configured for incoming email.",
                f"MX: {', '.join(mx_list[:5])}{'...' if len(mx_list) > 5 else ''}",
                base_asset,
                "No action required.",
                [],
            ))
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers, dns.exception.Timeout) as e:
        findings.append(_make_finding(
            "warning",
            "DNS",
            "MX records not found or DNS error",
            "We could not retrieve MX records for your domain.",
            str(e),
            base_asset,
            "Add MX records if you receive email at this domain.",
            [],
        ))

    # NS records
    try:
        answers = resolver.resolve(domain, "NS")
        if not answers:
            findings.append(_make_finding(
                "critical",
                "DNS",
                "No NS records",
                "Your domain has no nameserver records. DNS resolution may fail.",
                f"No NS records for {domain}",
                base_asset,
                "Configure nameservers at your domain registrar.",
                COMPLIANCE_AVAILABILITY,
            ))
        else:
            ns_list = [str(r) for r in answers]
            findings.append(_make_finding(
                "ok",
                "DNS",
                "NS records healthy",
                "Your domain has nameservers configured.",
                f"NS: {', '.join(ns_list[:5])}{'...' if len(ns_list) > 5 else ''}",
                base_asset,
                "No action required.",
                [],
            ))
    except (dns.resolver.NXDOMAIN, dns.resolver.NoNameservers, dns.exception.Timeout) as e:
        findings.append(_make_finding(
            "critical",
            "DNS",
            "NS records not found or DNS unreachable",
            "We could not retrieve nameservers for your domain. DNS may be misconfigured.",
            str(e),
            base_asset,
            "Ensure nameservers are set correctly at your registrar.",
            COMPLIANCE_AVAILABILITY,
        ))

    return findings


# ---------------------------------------------------------------------------
# 2. SSL/TLS
# ---------------------------------------------------------------------------


def _check_ssl(domain: str) -> list[Finding]:
    findings: list[Finding] = []
    host = domain if not domain.startswith("www.") else domain
    asset = f"https://{domain}"

    try:
        context = ssl.create_default_context()
        context.check_hostname = True
        context.verify_mode = ssl.CERT_REQUIRED
        with socket.create_connection((domain, 443), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()
                cipher = ssock.cipher()
                version = ssock.version()

                # Certificate expiry
                not_after = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z")
                not_after = not_after.replace(tzinfo=timezone.utc)
                now = datetime.now(timezone.utc)
                days_left = (not_after - now).days

                if days_left < 0:
                    findings.append(_make_finding(
                        "critical",
                        "SSL",
                        "SSL certificate expired",
                        "Your HTTPS certificate has expired. Browsers will show a security warning and visitors may not trust your site.",
                        f"Certificate expired {abs(days_left)} days ago. notAfter: {cert['notAfter']}",
                        asset,
                        "Renew your SSL certificate with your provider (e.g. Let's Encrypt, your hosting provider) and install it on your web server.",
                        COMPLIANCE_TRANSMISSION,
                    ))
                elif days_left <= 7:
                    findings.append(_make_finding(
                        "critical",
                        "SSL",
                        "SSL certificate expiring within 7 days",
                        "Your certificate will expire very soon. Renew it immediately to avoid downtime.",
                        f"Expires in {days_left} days. notAfter: {cert['notAfter']}",
                        asset,
                        "Renew your SSL certificate and deploy it before the expiry date.",
                        COMPLIANCE_TRANSMISSION,
                    ))
                elif days_left <= 30:
                    findings.append(_make_finding(
                        "warning",
                        "SSL",
                        "SSL certificate expiring within 30 days",
                        "Your certificate will expire in less than 30 days. Plan a renewal soon.",
                        f"Expires in {days_left} days. notAfter: {cert['notAfter']}",
                        asset,
                        "Renew your SSL certificate and deploy it before the expiry date.",
                        [],
                    ))
                else:
                    findings.append(_make_finding(
                        "ok",
                        "SSL",
                        "SSL certificate valid",
                        "Your certificate is valid and has sufficient time before expiry.",
                        f"Valid until {cert['notAfter']} ({days_left} days)",
                        asset,
                        "No action required.",
                        [],
                    ))

                # TLS version
                if version in ("SSLv2", "SSLv3", "TLSv1", "TLSv1.1"):
                    findings.append(_make_finding(
                        "critical",
                        "SSL",
                        "Outdated TLS version in use",
                        "Your server is using an old TLS version that is no longer considered secure. Modern browsers may block connections.",
                        f"Negotiated: {version}",
                        asset,
                        "Disable SSLv3, TLS 1.0, and TLS 1.1 on your web server. Use only TLS 1.2 and 1.3.",
                        COMPLIANCE_TRANSMISSION,
                    ))
                else:
                    findings.append(_make_finding(
                        "ok",
                        "SSL",
                        "TLS 1.2 or higher",
                        "Your server supports modern TLS versions.",
                        f"Negotiated: {version}",
                        asset,
                        "No action required.",
                        [],
                    ))

                # Cipher
                cipher_name = (cipher or ("", "", ""))[0]
                weak = any(pat.search(cipher_name) for pat in WEAK_CIPHER_PATTERNS)
                if weak:
                    findings.append(_make_finding(
                        "critical",
                        "SSL",
                        "Weak cipher suite in use",
                        "Your server is using a cipher suite that is considered weak or insecure.",
                        f"Cipher: {cipher_name}",
                        asset,
                        "Configure your web server to use only strong ciphers (e.g. AES-GCM, ChaCha20). Disable NULL, EXPORT, RC4, DES, and MD5 ciphers.",
                        COMPLIANCE_TRANSMISSION,
                    ))
                else:
                    findings.append(_make_finding(
                        "ok",
                        "SSL",
                        "Strong cipher suite",
                        "Your server is using an acceptable cipher suite.",
                        f"Cipher: {cipher_name}",
                        asset,
                        "No action required.",
                        [],
                    ))

    except ssl.SSLCertVerificationError as e:
        findings.append(_make_finding(
            "critical",
            "SSL",
            "SSL certificate invalid or self-signed",
            "Your certificate could not be verified. It may be self-signed, expired, or not match the domain.",
            str(e),
            asset,
            "Install a valid certificate from a trusted CA (e.g. Let's Encrypt) and ensure the certificate matches your domain name.",
            COMPLIANCE_TRANSMISSION,
        ))
    except (socket.timeout, socket.gaierror, OSError) as e:
        findings.append(_make_finding(
            "warning",
            "SSL",
            "Could not connect to HTTPS",
            "We could not establish an HTTPS connection to your domain. The site may be down or blocking our scanner.",
            str(e),
            asset,
            "Ensure port 443 is open and your web server is serving HTTPS. Allow our scanner IP if you use strict firewall rules.",
            [],
        ))

    return findings


# ---------------------------------------------------------------------------
# 3. Open Ports (TCP connect)
# ---------------------------------------------------------------------------


def _check_port(domain: str, port: int, label: str, severity_if_open: str) -> Finding | None:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        result = sock.connect_ex((domain, port))
        sock.close()
        if result == 0:
            if severity_if_open == "info":
                return _make_finding(
                    "info",
                    "Network",
                    f"Port {port} ({label}) is open",
                    "This port is commonly used for SSH. Ensure only authorized access is allowed.",
                    f"TCP {port} open on {domain}",
                    f"{domain}:{port}",
                    "Restrict SSH access with firewall rules and key-based authentication. Disable password auth if possible.",
                    [],
                )
            else:
                return _make_finding(
                    severity_if_open,
                    "Network",
                    f"Port {port} ({label}) is open",
                    f"Port {port} ({label}) is accessible from the internet. If this service is not intended to be public, it increases attack surface.",
                    f"TCP {port} open on {domain}",
                    f"{domain}:{port}",
                    f"Close port {port} on your firewall if {label} should not be publicly accessible. If it must be open, restrict by IP and use strong authentication.",
                    COMPLIANCE_ACCESS if severity_if_open == "critical" else [],
                )
    except (socket.gaierror, OSError):
        pass
    return None


def _check_ports(domain: str) -> list[Finding]:
    findings: list[Finding] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(12, len(PORT_CHECKS))) as ex:
        futures = {
            ex.submit(_check_port, domain, port, label, sev): (port, label, sev)
            for port, label, sev in PORT_CHECKS
        }
        for fut in concurrent.futures.as_completed(futures):
            finding = fut.result()
            if finding:
                findings.append(finding)
    return findings


# ---------------------------------------------------------------------------
# 4. HTTP Security Headers & 5. HTTPS Redirect
# ---------------------------------------------------------------------------


def _check_web_headers_and_redirect(domain: str) -> list[Finding]:
    findings: list[Finding] = []
    base_url_https = f"https://{domain}"
    base_url_http = f"http://{domain}"

    # HTTPS redirect
    try:
        r = requests.get(
            base_url_http,
            allow_redirects=True,
            timeout=10,
            headers={"User-Agent": "HAWK-Specter/1.0"},
        )
        if r.url.startswith("https://"):
            findings.append(_make_finding(
                "ok",
                "Web",
                "HTTP redirects to HTTPS",
                "Visitors typing http:// are correctly redirected to HTTPS.",
                f"GET {base_url_http} -> {r.url}",
                base_url_http,
                "No action required.",
                [],
            ))
        else:
            findings.append(_make_finding(
                "critical",
                "Web",
                "HTTP does not redirect to HTTPS",
                "Your site is not forcing HTTPS. Visitors may stay on an unencrypted connection.",
                f"GET {base_url_http} returned final URL: {r.url}",
                base_url_http,
                "Configure your web server to redirect HTTP to HTTPS (301 or 302). In Nginx: return 301 https://$host$request_uri;",
                COMPLIANCE_TRANSMISSION,
            ))
    except requests.RequestException as e:
        findings.append(_make_finding(
            "warning",
            "Web",
            "Could not check HTTP redirect",
            "We could not reach your site over HTTP. It may be down or blocking our scanner.",
            str(e),
            base_url_http,
            "Ensure HTTP redirects to HTTPS if you serve both.",
            [],
        ))

    # Security headers (from HTTPS response)
    try:
        r = requests.get(
            base_url_https,
            allow_redirects=True,
            timeout=10,
            headers={"User-Agent": "HAWK-Specter/1.0"},
        )
        headers = {k.lower(): v for k, v in r.headers.items()}

        # HSTS
        if "strict-transport-security" in headers:
            hsts = headers["strict-transport-security"]
            match = re.search(r"max-age=(\d+)", hsts)
            max_age = int(match.group(1)) if match else 0
            if max_age >= 31536000:
                findings.append(_make_finding(
                    "ok",
                    "Web",
                    "HSTS enabled with long max-age",
                    "Strict-Transport-Security is set, so browsers will use HTTPS only.",
                    f"Strict-Transport-Security: {hsts}",
                    base_url_https,
                    "No action required.",
                    [],
                ))
            else:
                findings.append(_make_finding(
                    "warning",
                    "Web",
                    "HSTS present but max-age too short",
                    "HSTS is set but we recommend max-age of at least 31536000 (1 year).",
                    f"Strict-Transport-Security: {hsts}",
                    base_url_https,
                    "Set Strict-Transport-Security: max-age=31536000; includeSubDomains; preload",
                    COMPLIANCE_TRANSMISSION,
                ))
        else:
            findings.append(_make_finding(
                "critical",
                "Web",
                "HSTS header missing",
                "Your site does not send Strict-Transport-Security. Browsers may allow a first request over HTTP.",
                "No Strict-Transport-Security header in response",
                base_url_https,
                "Add header: Strict-Transport-Security: max-age=31536000; includeSubDomains; preload",
                COMPLIANCE_TRANSMISSION,
            ))

        # X-Frame-Options or CSP frame-ancestors
        has_frame_protection = False
        if "x-frame-options" in headers:
            has_frame_protection = True
            findings.append(_make_finding(
                "ok",
                "Web",
                "Clickjacking protection (X-Frame-Options)",
                "Your site sends X-Frame-Options to prevent being embedded in frames.",
                f"X-Frame-Options: {headers['x-frame-options']}",
                base_url_https,
                "No action required.",
                [],
            ))
        if "content-security-policy" in headers:
            csp = headers["content-security-policy"]
            if "frame-ancestors" in csp:
                has_frame_protection = True
                if "x-frame-options" not in headers:
                    findings.append(_make_finding(
                        "ok",
                        "Web",
                        "Clickjacking protection (CSP frame-ancestors)",
                        "Your site uses CSP frame-ancestors to control framing.",
                        "CSP includes frame-ancestors",
                        base_url_https,
                        "No action required.",
                        [],
                    ))
        if not has_frame_protection:
            findings.append(_make_finding(
                "warning",
                "Web",
                "Missing clickjacking protection",
                "Your site does not send X-Frame-Options or CSP frame-ancestors. It could be embedded in a malicious iframe.",
                "No X-Frame-Options or CSP frame-ancestors",
                base_url_https,
                "Add X-Frame-Options: DENY or SAMEORIGIN, or add frame-ancestors to Content-Security-Policy.",
                COMPLIANCE_ACCESS,
            ))

        # Content-Security-Policy
        if "content-security-policy" in headers:
            findings.append(_make_finding(
                "ok",
                "Web",
                "Content-Security-Policy present",
                "Your site sends a Content-Security-Policy header to mitigate XSS and injection.",
                f"CSP: {headers['content-security-policy'][:150]}...",
                base_url_https,
                "No action required.",
                [],
            ))
        else:
            findings.append(_make_finding(
                "warning",
                "Web",
                "Content-Security-Policy missing",
                "Your site does not send a Content-Security-Policy header. XSS and data injection risks are higher.",
                "No Content-Security-Policy header",
                base_url_https,
                "Add a Content-Security-Policy header. Start with default-src 'self' and relax as needed.",
                COMPLIANCE_ACCESS,
            ))

        # X-Content-Type-Options
        if headers.get("x-content-type-options", "").lower() == "nosniff":
            findings.append(_make_finding(
                "ok",
                "Web",
                "X-Content-Type-Options: nosniff",
                "Browsers will not MIME-sniff content, reducing some XSS risks.",
                "X-Content-Type-Options: nosniff",
                base_url_https,
                "No action required.",
                [],
            ))
        else:
            findings.append(_make_finding(
                "warning",
                "Web",
                "X-Content-Type-Options missing",
                "Your site does not set X-Content-Type-Options: nosniff. Browsers may interpret content incorrectly.",
                f"Current: {headers.get('x-content-type-options', 'not set')}",
                base_url_https,
                "Add header: X-Content-Type-Options: nosniff",
                [],
            ))

        # Referrer-Policy
        if "referrer-policy" in headers:
            findings.append(_make_finding(
                "ok",
                "Web",
                "Referrer-Policy set",
                "Your site controls how much referrer information is sent to other sites.",
                f"Referrer-Policy: {headers['referrer-policy']}",
                base_url_https,
                "No action required.",
                [],
            ))
        else:
            findings.append(_make_finding(
                "info",
                "Web",
                "Referrer-Policy not set",
                "You may want to set Referrer-Policy to limit referrer leakage (e.g. strict-origin-when-cross-origin).",
                "No Referrer-Policy header",
                base_url_https,
                "Add header: Referrer-Policy: strict-origin-when-cross-origin",
                [],
            ))

    except requests.RequestException as e:
        findings.append(_make_finding(
            "warning",
            "Web",
            "Could not fetch HTTPS response for headers",
            "We could not retrieve your site's headers. The site may be down or blocking our scanner.",
            str(e),
            base_url_https,
            "Ensure your site is reachable over HTTPS and returns valid responses.",
            [],
        ))

    return findings


# ---------------------------------------------------------------------------
# 6. Subdomains (passive enumeration)
# ---------------------------------------------------------------------------


def _check_subdomain(domain: str, sub: str) -> Finding | None:
    host = f"{sub}.{domain}"
    try:
        resolver = dns.resolver.Resolver()
        resolver.timeout = 3
        resolver.lifetime = 5
        resolver.resolve(host, "A")
        return _make_finding(
            "info",
            "Subdomains",
            f"Subdomain found: {host}",
            f"The subdomain {host} resolves. Ensure it is intentionally exposed and secured.",
            f"{host} has A (and/or AAAA) record(s)",
            host,
            "Verify that this subdomain is required and that it has the same security controls as your main domain (HTTPS, headers, etc.).",
            [],
        )
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer, dns.resolver.NoNameservers, dns.exception.Timeout):
        return None


def _check_subdomains(domain: str) -> list[Finding]:
    findings: list[Finding] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(10, len(SUBDOMAIN_PREFIXES))) as ex:
        futures = {ex.submit(_check_subdomain, domain, sub): sub for sub in SUBDOMAIN_PREFIXES}
        for fut in concurrent.futures.as_completed(futures):
            f = fut.result()
            if f:
                findings.append(f)
    if not findings:
        findings.append(_make_finding(
            "ok",
            "Subdomains",
            "No common subdomains enumerated",
            "We did not find any of the common subdomains we checked. This may mean fewer exposed surfaces.",
            f"Checked: {', '.join(SUBDOMAIN_PREFIXES)}",
            domain,
            "No action required. Continue to monitor for unintended subdomains.",
            [],
        ))
    return findings


# ---------------------------------------------------------------------------
# 7. Grade calculation
# ---------------------------------------------------------------------------


def _compute_grade(findings: list[Finding]) -> tuple[int, str]:
    score = 100
    for f in findings:
        if f.severity == "critical":
            score -= 25
        elif f.severity == "warning":
            score -= 8
        elif f.severity == "info":
            score -= 2
        # ok: no deduction
    score = max(0, score)
    if score >= 90:
        grade = "A"
    elif score >= 75:
        grade = "B"
    elif score >= 55:
        grade = "C"
    elif score >= 35:
        grade = "D"
    else:
        grade = "F"
    return score, grade


# ---------------------------------------------------------------------------
# Run full scan
# ---------------------------------------------------------------------------


def run_scan(domain: str, scan_id: str | None = None) -> ScanResponse:
    """Run all 7 check categories and return structured response."""
    domain = domain.lower().strip()
    if domain.startswith("http://") or domain.startswith("https://"):
        domain = domain.replace("https://", "").replace("http://", "").split("/")[0]
    if domain.startswith("www."):
        domain = domain[4:]
    started_at = _iso_now()

    all_findings: list[Finding] = []

    # Run DNS, SSL, Ports, Web (headers+redirect), Subdomains
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        fut_dns = ex.submit(_check_dns, domain)
        fut_ssl = ex.submit(_check_ssl, domain)
        fut_ports = ex.submit(_check_ports, domain)
        fut_web = ex.submit(_check_web_headers_and_redirect, domain)
        fut_subs = ex.submit(_check_subdomains, domain)

        for fut in (fut_dns, fut_ssl, fut_ports, fut_web, fut_subs):
            all_findings.extend(fut.result())

    score, grade = _compute_grade(all_findings)
    completed_at = _iso_now()

    return ScanResponse(
        scan_id=scan_id,
        domain=domain,
        status="completed",
        score=score,
        grade=grade,
        findings=all_findings,
        started_at=started_at,
        completed_at=completed_at,
    )


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="HAWK Specter Scanner",
    description="Passive external attack-surface scanner for HAWK. Runs on Specter (internal).",
    version="1.0.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "specter-scanner"}


@app.post("/scan", response_model=ScanResponse)
def scan(req: ScanRequest) -> ScanResponse:
    """Run a full scan for the given domain. Returns findings and grade."""
    try:
        return run_scan(req.domain, req.scan_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Scan failed: {e}") from e


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
