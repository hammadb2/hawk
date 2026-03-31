from __future__ import annotations

import json
import logging

from app.pipeline import tools
from app.settings import Settings

logger = logging.getLogger(__name__)


async def run_httpx(targets: list[str], settings: Settings) -> dict:
    if not targets:
        return {"tool": "httpx", "jsonl": []}
    bin_path = tools.which_or_configured("httpx", settings.httpx_bin)
    # httpx accepts -u list
    code, out, err = await tools.run_tool(
        [
            bin_path,
            "-silent",
            "-json",
            "-timeout",
            "10",
            "-u",
            ",".join(targets[:80]),
        ],
        timeout=float(settings.layer_timeout_sec),
    )
    rows = tools.parse_jsonl_lines(out)
    return {"tool": "httpx", "exit_code": code, "jsonl": rows[:500], "stderr_tail": err[-800:]}


async def run_whatweb(urls: list[str], settings: Settings) -> dict:
    if not urls:
        return {"tool": "whatweb", "lines": []}
    bin_path = tools.which_or_configured("whatweb", settings.whatweb_bin)
    code, out, err = await tools.run_tool(
        [bin_path, "--no-errors", "-q"] + urls[:25],
        timeout=min(120.0, float(settings.layer_timeout_sec) * 1.2),
    )
    return {"tool": "whatweb", "exit_code": code, "lines": out.splitlines()[:200], "stderr_tail": err[-800:]}
