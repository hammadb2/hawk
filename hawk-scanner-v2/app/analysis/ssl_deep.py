"""TLS version, chain presence, HSTS hint (socket + ssl)."""
from __future__ import annotations

import socket
import ssl
import uuid
from typing import Any


def _check_tls(host: str, port: int = 443, timeout: float = 10.0) -> dict[str, Any]:
    ctx = ssl.create_default_context()
    raw_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    raw_sock.settimeout(timeout)
    try:
        raw_sock.connect((host, port))
    except OSError as e:
        return {"ok": False, "error": str(e)}
    try:
        ssock = ctx.wrap_socket(raw_sock, server_hostname=host)
    except ssl.SSLError as e:
        raw_sock.close()
        return {"ok": False, "error": str(e)}
    try:
        ver = ssock.version() or ""
        cipher = ssock.cipher()
        cert = ssock.getpeercert()
        return {
            "ok": True,
            "tls_version": ver,
            "cipher": cipher,
            "cert_subject": dict(x[0] for x in cert.get("subject", ())) if cert else {},
            "cert_issuer": dict(x[0] for x in cert.get("issuer", ())) if cert else {},
        }
    finally:
        try:
            ssock.close()
        except Exception:
            pass


async def analyze(domain: str) -> list[dict[str, Any]]:
    import asyncio

    host = domain.lower().strip().lstrip("*.") if domain else ""
    if host.startswith("www."):
        host = host[4:]
    info = await asyncio.to_thread(_check_tls, host, 443)
    findings: list[dict[str, Any]] = []
    if not info.get("ok"):
        findings.append(
            {
                "id": str(uuid.uuid4()),
                "severity": "high",
                "category": "SSL/TLS",
                "title": "HTTPS handshake failed",
                "description": "Could not complete TLS to port 443.",
                "technical_detail": info.get("error", "")[:1000],
                "affected_asset": f"{host}:443",
                "remediation": "Fix certificate or firewall; ensure TLS 1.2+ on edge.",
                "layer": "ssl_deep",
            }
        )
        return findings

    ver = (info.get("tls_version") or "").upper()
    sev = "low"
    desc = f"TLS version: {ver}"
    if "TLSV1" in ver and "1.2" not in ver and "1.3" not in ver:
        sev = "high"
        desc = f"Legacy TLS ({ver}) — prefer TLS 1.2+."
    elif "1.0" in ver or "1.1" in ver:
        sev = "high"
        desc = f"Weak TLS protocol ({ver})."

    cipher = info.get("cipher") or ()
    cipher_txt = f"{cipher[0]} {cipher[1]} {cipher[2]}" if cipher else ""
    if cipher and isinstance(cipher, tuple):
        name = str(cipher[0] or "")
        if any(x in name.upper() for x in ("RC4", "DES", "NULL", "EXPORT", "MD5")):
            sev = "critical"
            desc += " Weak cipher suite detected."

    findings.append(
        {
            "id": str(uuid.uuid4()),
            "severity": sev,
            "category": "SSL/TLS",
            "title": "TLS configuration",
            "description": desc,
            "technical_detail": f"{ver} | {cipher_txt}",
            "affected_asset": f"{host}:443",
            "remediation": "Disable TLS 1.0/1.1 and weak ciphers at CDN or origin.",
            "layer": "ssl_deep",
        }
    )

    return findings
