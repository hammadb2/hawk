from __future__ import annotations

import logging
from pathlib import Path

from app.pipeline import tools
from app.settings import Settings

logger = logging.getLogger(__name__)


async def run(domain: str, settings: Settings) -> dict:
    bin_path = tools.which_or_configured("subfinder", settings.subfinder_bin)
    code, out, err = await tools.run_tool(
        [bin_path, "-d", domain, "-silent", "-o", "-"],
        timeout=float(settings.layer_timeout_sec),
    )
    hosts = [h.strip() for h in out.splitlines() if h.strip()]
    if code not in (0,) and not hosts:
        logger.warning("subfinder exit %s: %s", code, err[:500])
    return {"tool": "subfinder", "exit_code": code, "hosts": hosts[:500], "stderr_tail": err[-800:]}
