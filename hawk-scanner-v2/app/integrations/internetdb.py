"""Shodan InternetDB (no API key) — CVE / exposure hints from discovered hosts."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
import uuid
from typing import Any

import httpx

logger = logging.getLogger(__name__)

INTERNETDB = "https://internetdb.shodan.io"


def _is_ip(s: str) -> bool:
    try:
        ipaddress.ip_address(s.split("%")[0])
        return True
    except ValueError:
        return False


def _resolve_ipv4(host: str) -> str | None:
    try:
        infos = socket.getaddrinfo(host, None, socket.AF_INET)
        for inf in infos:
            return inf[4][0]
    except OSError:
        return None
    return None


async def _fetch_one(client: httpx.AsyncClient, ip: str) -> dict[str, Any] | None:
    try:
        r = await client.get(f"{INTERNETDB}/{ip}", timeout=12.0)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    except Exception:
        logger.debug("internetdb fetch failed for %s", ip, exc_info=True)
        return None


async def internetdb_findings(naabu_results: list[dict], domain: str) -> list[dict[str, Any]]:
    hosts: list[str] = []
    for row in naabu_results or []:
        h = (row.get("host") or "").strip()
        if h and h not in hosts:
            hosts.append(h)

    ips: list[str] = []
    for h in hosts[:30]:
        if _is_ip(h):
            ips.append(h.split("%")[0])
        else:
            ip = _resolve_ipv4(h)
            if ip:
                ips.append(ip)

    seen: set[str] = set()
    uniq: list[str] = []
    for ip in ips:
        if ip not in seen:
            seen.add(ip)
            uniq.append(ip)
    uniq = uniq[:8]

    if not uniq:
        return []

    async with httpx.AsyncClient() as client:
        rows = await asyncio.gather(*[_fetch_one(client, ip) for ip in uniq])

    out: list[dict[str, Any]] = []
    for ip, data in zip(uniq, rows):
        if not data or not isinstance(data, dict):
            continue
        vulns = data.get("vulns") or []
        ports = data.get("ports") or []
        tags = data.get("tags") or []
        if vulns:
            out.append(
                {
                    "id": str(uuid.uuid4()),
                    "severity": "medium",
                    "category": "Internet exposure",
                    "title": f"Internet-wide CVE references for {ip}",
                    "description": (
                        "Shodan InternetDB lists known CVE references associated with this address. "
                        "Validate whether these assets are yours, patch exposed services, and reduce unnecessary exposure."
                    ),
                    "technical_detail": str(vulns[:20])[:4000],
                    "affected_asset": domain,
                    "remediation": "Confirm ownership, patch or remove exposed services, and verify against your asset inventory.",
                    "layer": "internetdb",
                }
            )
        elif len(ports) > 15:
            out.append(
                {
                    "id": str(uuid.uuid4()),
                    "severity": "low",
                    "category": "Internet exposure",
                    "title": f"Broad port exposure on {ip}",
                    "description": (
                        f"InternetDB reports {len(ports)} open ports on this host. "
                        "Large listening surfaces increase attack surface."
                    ),
                    "technical_detail": str(ports[:40])[:4000],
                    "affected_asset": domain,
                    "remediation": "Close unused ports, use firewalls/WAFs, and document required services.",
                    "layer": "internetdb",
                }
            )
        elif tags and any(
            str(t).lower() in ("vpn", "remote-access", "database") for t in tags
        ):
            out.append(
                {
                    "id": str(uuid.uuid4()),
                    "severity": "info",
                    "category": "Internet exposure",
                    "title": f"InternetDB tags: {', '.join(str(t) for t in tags[:6])}",
                    "description": "Classification tags from Shodan InternetDB for this address — review exposure of VPN/remote/database surfaces.",
                    "technical_detail": str(tags)[:2000],
                    "affected_asset": domain,
                    "remediation": "Ensure remote access and databases are not unnecessarily exposed to the internet.",
                    "layer": "internetdb",
                }
            )
    return out
