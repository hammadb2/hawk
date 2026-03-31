from __future__ import annotations

import json
import logging

from app.pipeline import tools
from app.settings import Settings

logger = logging.getLogger(__name__)


async def run(domain: str, settings: Settings) -> dict:
    bin_path = tools.which_or_configured("dnstwist", settings.dnstwist_bin)
    code, out, err = await tools.run_tool(
        [bin_path, domain, "--registered", "--format", "json"],
        timeout=float(settings.layer_timeout_sec) * 1.5,
    )
    if code != 0 and not out.strip():
        return {"tool": "dnstwist", "exit_code": code, "registered": [], "stderr_tail": err[-800:]}
    try:
        data = json.loads(out) if out.strip() else []
    except json.JSONDecodeError:
        data = []
    return {"tool": "dnstwist", "exit_code": code, "registered": data[:100], "stderr_tail": err[-800:]}
