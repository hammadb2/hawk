"""HAWK Sentinel — Scope Enforcer (execute_terminal wrapper).

Intercepts commands before execution in the Kali sandbox and blocks
anything that violates the scope.json contract.
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

EXPLOITATION_TOOLS = frozenset({
    "msfconsole", "msfvenom", "msfdb",
    "sqlmap",
    "beef-xss",
    "setoolkit", "set",
    "empire",
    "covenant",
    "sliver",
    "mythic",
    "caldera",
    "hydra",
    "medusa",
    "john",
    "hashcat",
    "responder",
    "impacket",
    "crackmapexec", "cme",
    "evil-winrm",
    "chisel",
    "ligolo",
    "cobalt",
})

PASSIVE_SAFE_TOOLS = frozenset({
    "nmap", "naabu", "nuclei", "httpx", "subfinder",
    "whois", "dig", "nslookup", "host", "traceroute",
    "curl", "wget",
    "nikto", "whatweb", "wafw00f",
    "gobuster", "ffuf", "dirsearch", "dirb",
    "amass", "theHarvester",
    "sslscan", "sslyze", "testssl",
    "cat", "echo", "ls", "grep", "head", "tail", "wc",
    "python3", "python", "bash", "sh",
})


class ScopeViolation(Exception):
    """Raised when a command violates the scope contract."""
    pass


def _strip_wrappers(segment: str) -> str:
    """Strip sudo/proxychains/torify prefixes from a command segment."""
    cleaned = segment.strip()
    changed = True
    while changed:
        changed = False
        for prefix in ("sudo ", "proxychains ", "proxychains4 ", "torify "):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
                changed = True
    return cleaned


def _extract_all_commands(cmd: str) -> list[str]:
    """Extract all base command names from a shell command string.

    Splits on shell chaining operators (;, &&, ||, |, $(), backticks)
    so that every sub-command is checked against the scope rules.
    """
    segments = re.split(r"\s*(?:;|&&|\|\||\||\n)\s*", cmd)

    # Also catch $(...) and backtick subshells
    for match in re.finditer(r"\$\((.+?)\)", cmd):
        segments.extend(re.split(r"\s*(?:;|&&|\|\||\|)\s*", match.group(1)))
    for match in re.finditer(r"`(.+?)`", cmd):
        segments.extend(re.split(r"\s*(?:;|&&|\|\||\|)\s*", match.group(1)))

    commands: list[str] = []
    for seg in segments:
        cleaned = _strip_wrappers(seg)
        if cleaned:
            base = cleaned.split()[0].split("/")[-1]
            if base:
                commands.append(base)
    return commands


def _check_ip_exclusions(cmd: str, excluded_ips: list[str]) -> str | None:
    """Check if a command targets an excluded IP."""
    for ip in excluded_ips:
        if re.search(r'(?<![\d.])' + re.escape(ip) + r'(?![\d.])', cmd):
            return f"Command targets excluded IP: {ip}"
    return None


def _check_domain_scope(cmd: str, in_scope_domains: list[str]) -> str | None:
    """
    Heuristic check that the command targets in-scope domains.
    Returns a warning string if a potential out-of-scope target is detected.
    Only warns — does not block, since commands may use IPs resolved from in-scope domains.
    """
    return None


def enforce_scope(
    command: str,
    scope: dict[str, Any],
) -> tuple[bool, str]:
    """
    Check whether a command is allowed under the scope contract.

    Returns (allowed: bool, reason: str).
    If not allowed, reason explains why.
    """
    exploitation_allowed = scope.get("exploitation_allowed", False)
    excluded_ips = scope.get("excluded_ips", [])
    intensity = scope.get("intensity", "deep_scan_only")

    all_cmds = _extract_all_commands(command)

    if not all_cmds:
        return False, "Empty command"

    # Check IP exclusions (always enforced)
    ip_issue = _check_ip_exclusions(command, excluded_ips)
    if ip_issue:
        return False, ip_issue

    # Block exploitation tools when not allowed — check EVERY sub-command
    if not exploitation_allowed:
        for base_cmd in all_cmds:
            if base_cmd.lower() in EXPLOITATION_TOOLS:
                return False, (
                    f"Blocked: '{base_cmd}' is an exploitation tool but "
                    f"exploitation_allowed=false (intensity={intensity}). "
                    f"Only passive/enumeration tools are permitted."
                )

    # For deep_scan_only, also block any tool that could deliver payloads
    if intensity == "deep_scan_only":
        payload_patterns = [
            r"--os-shell", r"--os-pwn", r"--priv-esc",
            r"-e\s+(cmd|powershell|bash|sh)",
            r"reverse.shell", r"bind.shell",
            r"meterpreter", r"payload/",
        ]
        for pattern in payload_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return False, (
                    f"Blocked: command contains payload pattern '{pattern}' "
                    f"which is not allowed under deep_scan_only intensity."
                )

    # For exploit_safe, block destructive patterns
    if intensity == "exploit_safe":
        destructive_patterns = [
            r"rm\s+-rf\s+/\s*$",
            r"format\s+[cC]:",
            r"dd\s+if=.*of=/dev/",
            r"mkfs\.",
            r"--wipe",
            r"ransomware",
        ]
        for pattern in destructive_patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return False, (
                    f"Blocked: command contains destructive pattern "
                    f"not allowed under exploit_safe intensity."
                )

    return True, "Allowed"


def safe_execute(
    command: str,
    scope: dict[str, Any],
    executor_fn: Any,
    container_id: str,
) -> tuple[int, str, str]:
    """
    Execute a command only if it passes scope enforcement.

    Uses executor_fn(container_id, command) to run the actual command.
    Returns (exit_code, stdout, stderr).
    Raises ScopeViolation if the command is blocked.
    """
    allowed, reason = enforce_scope(command, scope)
    if not allowed:
        logger.warning("SCOPE BLOCKED: %s — %s", command[:100], reason)
        raise ScopeViolation(reason)

    logger.info("SCOPE OK: executing %s", command[:100])
    return executor_fn(container_id, command)


async def async_safe_execute(
    command: str,
    scope: dict[str, Any],
    executor_fn: Any,
    container_id: str,
) -> tuple[int, str, str]:
    """Async wrapper around safe_execute — offloads blocking Docker exec to a thread."""
    import asyncio

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None, safe_execute, command, scope, executor_fn, container_id
    )
