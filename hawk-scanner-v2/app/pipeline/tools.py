"""Subprocess helpers for ProjectDiscovery / security CLIs."""
from __future__ import annotations

import asyncio
import json
import logging
import shutil
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def which_or_configured(name: str, configured: str) -> str:
    return configured if configured and Path(configured).exists() else (shutil.which(name) or name)


async def run_tool(
    argv: list[str],
    *,
    timeout: float,
    cwd: Path | None = None,
) -> tuple[int, str, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return 127, "", f"executable not found: {argv[0]}"
    try:
        out_b, err_b = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return 124, "", "timeout"
    code = proc.returncode or 0
    return code, (out_b or b"").decode(errors="replace"), (err_b or b"").decode(errors="replace")


def parse_jsonl_lines(blob: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in blob.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows
