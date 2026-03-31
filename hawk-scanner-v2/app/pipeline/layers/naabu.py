from __future__ import annotations

import logging
import os
import tempfile

from app.pipeline import tools
from app.settings import Settings

logger = logging.getLogger(__name__)

DEFAULT_PORTS = "80,443,8080,8443,3000,4443"


async def run(hosts: list[str], settings: Settings) -> dict:
    if not hosts:
        return {"tool": "naabu", "results": [], "note": "no hosts"}
    bin_path = tools.which_or_configured("naabu", settings.naabu_bin)
    sample = hosts[:40]
    code, out, err = -1, "", ""
    path = tempfile.NamedTemporaryFile("w", delete=False, suffix=".txt")
    try:
        for h in sample:
            path.write(h.strip() + "\n")
        path.close()
        code, out, err = await tools.run_tool(
            [bin_path, "-list", path.name, "-p", DEFAULT_PORTS, "-silent"],
            timeout=float(settings.layer_timeout_sec),
        )
    finally:
        try:
            os.unlink(path.name)
        except OSError:
            pass
    lines = [ln.strip() for ln in out.splitlines() if ln.strip()]
    parsed: list[dict] = []
    for ln in lines:
        if ":" in ln:
            h, p = ln.rsplit(":", 1)
            parsed.append({"host": h.strip(), "port": p.strip()})
        else:
            parsed.append({"host": ln, "port": ""})
    return {"tool": "naabu", "exit_code": code, "results": parsed[:2000], "stderr_tail": err[-800:]}
