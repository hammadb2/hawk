"""Micro-scan orchestrator — lightweight, targeted scans triggered by events."""
from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import uuid
from typing import Any

from app.config import Settings, get_settings
from app.scanner.tools import parse_jsonl, run_tool, which_or_configured

logger = logging.getLogger(__name__)


async def run_naabu(hosts: list[str], settings: Settings | None = None) -> list[dict[str, str]]:
    """Port-scan a small set of hosts. Returns [{host, port}, ...]."""
    settings = settings or get_settings()
    if not hosts:
        return []
    bin_path = which_or_configured("naabu", settings.naabu_bin)
    fd = tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt")
    try:
        for h in hosts[:20]:
            fd.write(h.strip() + "\n")
        fd.close()
        code, out, err = await run_tool(
            [bin_path, "-list", fd.name, "-p", settings.naabu_ports, "-silent"],
            timeout=settings.layer_timeout_sec,
        )
    finally:
        try:
            os.unlink(fd.name)
        except OSError:
            pass
    parsed: list[dict[str, str]] = []
    for ln in out.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        if ":" in ln:
            h, p = ln.rsplit(":", 1)
            parsed.append({"host": h.strip(), "port": p.strip()})
        else:
            parsed.append({"host": ln, "port": ""})
    return parsed


async def run_httpx(targets: list[str], settings: Settings | None = None) -> list[dict[str, Any]]:
    """HTTP-probe a list of URLs. Returns parsed JSONL rows."""
    settings = settings or get_settings()
    if not targets:
        return []
    bin_path = which_or_configured("httpx", settings.httpx_bin)
    code, out, err = await run_tool(
        [bin_path, "-silent", "-json", "-timeout", "10", "-u", ",".join(targets[:40])],
        timeout=settings.layer_timeout_sec,
    )
    return parse_jsonl(out)


async def micro_scan(
    domain: str,
    hosts: list[str] | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """
    Run a lightweight micro-scan on a domain or specific hosts.
    Returns a dict of discovered assets: {ports: [...], http_services: [...]}.
    """
    settings = settings or get_settings()
    scan_hosts = hosts or [domain]

    naabu_results = await run_naabu(scan_hosts, settings)

    urls: list[str] = []
    for row in naabu_results:
        h = row.get("host", "")
        p = row.get("port", "")
        if not h:
            continue
        if p in ("443", "8443", "4443"):
            urls.append(f"https://{h}" if p == "443" else f"https://{h}:{p}")
        elif p in ("80", ""):
            urls.append(f"http://{h}")
        else:
            urls.append(f"http://{h}:{p}")
    if not urls:
        urls = [f"https://{domain}", f"http://{domain}"]

    httpx_results = await run_httpx(urls, settings)

    return {
        "scan_id": str(uuid.uuid4()),
        "domain": domain,
        "hosts_scanned": scan_hosts,
        "ports": naabu_results,
        "http_services": httpx_results,
    }
