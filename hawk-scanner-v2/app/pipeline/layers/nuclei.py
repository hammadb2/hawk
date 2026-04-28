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
    nuc_cap = max(5, min(35, settings.nuclei_max_target_urls))
    argv = [
        bin_path,
        "-u",
        ",".join(target_urls[:nuc_cap]),
        "-jsonl",
        "-silent",
        "-timeout",
        "6",
        "-rate-limit",
        "80",
    ]
    if settings.nuclei_templates_dir:
        argv.extend(["-templates", settings.nuclei_templates_dir])
    code, out, err = await tools.run_tool(argv, timeout=float(settings.layer_timeout_sec) * 1.5)
    rows = tools.parse_jsonl_lines(out)
    findings = _findings_from_jsonl(rows, domain)
    meta = {"tool": "nuclei", "exit_code": code, "raw_count": len(rows), "stderr_tail": err[-800:]}

    # Run custom vertical templates (dental/legal) as second pass
    custom_dir = (settings.nuclei_custom_templates_dir or "").strip()
    if custom_dir:
        custom_argv = [
            bin_path,
            "-u",
            ",".join(target_urls[:nuc_cap]),
            "-jsonl",
            "-silent",
            "-timeout",
            "6",
            "-rate-limit",
            "80",
            "-templates",
            custom_dir,
        ]
        c2, o2, e2 = await tools.run_tool(custom_argv, timeout=float(settings.layer_timeout_sec) * 1.5)
        custom_rows = tools.parse_jsonl_lines(o2)
        findings.extend(_findings_from_jsonl(custom_rows, domain))
        meta["custom_exit_code"] = c2
        meta["custom_raw_count"] = len(custom_rows)
        meta["custom_stderr_tail"] = e2[-400:]

    return meta, findings
