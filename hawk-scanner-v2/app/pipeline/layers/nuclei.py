from __future__ import annotations

import logging
import uuid
from typing import Any

from app.pipeline import tools
from app.settings import Settings

logger = logging.getLogger(__name__)


def _findings_from_jsonl(rows: list[dict[str, Any]], domain: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        info = row.get("info") or {}
        name = info.get("name") or row.get("template-id") or "Nuclei finding"
        sev = (info.get("severity") or row.get("severity") or "medium").lower()
        matched = row.get("matched-at") or row.get("host") or domain
        out.append(
            {
                "id": str(uuid.uuid4()),
                "severity": sev,
                "category": "Vulnerability",
                "title": name,
                "description": info.get("description") or name,
                "technical_detail": str(row)[:4000],
                "affected_asset": str(matched),
                "remediation": "Review the matched template, patch or reconfigure the affected service, and restrict exposure where possible.",
                "layer": "nuclei",
            }
        )
    return out


async def run(target_urls: list[str], domain: str, settings: Settings) -> tuple[dict, list[dict[str, Any]]]:
    if not target_urls:
        return {"tool": "nuclei", "skipped": True}, []
    bin_path = tools.which_or_configured("nuclei", settings.nuclei_bin)
    argv = [
        bin_path,
        "-u",
        ",".join(target_urls[:30]),
        "-jsonl",
        "-silent",
        "-timeout",
        "8",
        "-rate-limit",
        "50",
    ]
    if settings.nuclei_templates_dir:
        argv.extend(["-templates", settings.nuclei_templates_dir])
    code, out, err = await tools.run_tool(argv, timeout=float(settings.layer_timeout_sec) * 1.5)
    rows = tools.parse_jsonl_lines(out)
    findings = _findings_from_jsonl(rows, domain)
    meta = {"tool": "nuclei", "exit_code": code, "raw_count": len(rows), "stderr_tail": err[-800:]}
    return meta, findings
