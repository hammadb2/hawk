"""HAWK Sentinel — 4-Agent Ghost Swarm + CISO Report Agent.

Orchestrates the automated penetration test using 4 LLM agents:
  Agent 1 (Planner):  Reads scope + Pulse data, writes attack plan
  Agent 2 (Ghost):    Configures OPSEC/evasion (proxychains, tunnels)
  Agent 3 (Operator): Executes attack commands in the Kali sandbox
  Agent 4 (Cleanup):  Removes artifacts, clears traces
  Agent 5 (CISO):     Writes the boardroom-grade report narrative
"""
from __future__ import annotations

import json
import logging
from typing import Any

from openai import AsyncOpenAI

from app.config import Settings, get_settings
from app.sentinel.sandbox import exec_in_sandbox
from app.sentinel.scope_enforcer import ScopeViolation, async_safe_execute, enforce_scope, safe_execute

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Agent System Prompts
# ---------------------------------------------------------------------------

PLANNER_PROMPT = """\
You are Agent 1 (The Planner) of HAWK Sentinel, an automated AI red team.

You are given:
- The scope.json contract defining what is allowed
- Passive reconnaissance data from HAWK Pulse (open ports, HTTP services, tech stack)
- The target domains

Your task: produce a JSON attack plan — an ordered array of objects, each with:
  {"step": 1, "tool": "nmap", "command": "nmap -sV -sC ...", "objective": "Service version detection"}

Rules:
- If exploitation_allowed is false, ONLY use passive/enumeration tools (nmap, nuclei, httpx, subfinder, nikto, gobuster, etc.)
- If exploitation_allowed is true, you MAY include exploitation tools (metasploit, sqlmap, etc.)
- NEVER target excluded_ips from scope.json
- Every command must target ONLY in_scope_domains
- Include thorough service enumeration, vulnerability scanning, and web application testing
- Output ONLY valid JSON — an array of step objects
- Aim for 10-20 steps for a comprehensive audit
"""

GHOST_PROMPT = """\
You are Agent 2 (The Ghost) of HAWK Sentinel. Your role is OPSEC & evasion.

You configure the network layer to route attack traffic through proxies so
the target's WAF/IDS doesn't immediately block the scanner IP.

Given the scope.json and attack plan, output shell commands to:
1. Configure proxychains4 with SOCKS5 proxies
2. Set up Tor if available
3. Randomize user agents and timing
4. Output a JSON array of setup commands to run before the attack plan

Output ONLY a JSON array of command strings.
"""

OPERATOR_PROMPT = """\
You are Agent 3 (The Operator) of HAWK Sentinel. You execute the attack plan.

For each step in the attack plan, you will be given the command to run.
After seeing the output, analyze it and produce a JSON findings object:

{
  "step": 1,
  "command": "the command that was run",
  "raw_output_summary": "brief summary of what was found",
  "findings": [
    {
      "type": "open_port | vulnerability | info_disclosure | misconfig | credential",
      "severity": "critical | high | medium | low | info",
      "title": "Short finding title",
      "detail": "Detailed description",
      "evidence": "Relevant output snippet"
    }
  ]
}

Rules:
- Be thorough — extract every finding from the output
- Classify severity accurately based on real-world impact
- Include raw evidence snippets (sanitized of any credentials found)
- Output ONLY valid JSON
"""

CLEANUP_PROMPT = """\
You are Agent 4 (The Cleanup Ghost) of HAWK Sentinel.

After the Operator finishes, you must clean up any traces left on the
target systems and the sandbox. Output a JSON array of cleanup commands:

1. Remove any test files that may have been uploaded to the target
2. Clear bash history in the sandbox
3. Remove temporary files from /tmp
4. Kill any lingering background processes

Output ONLY a JSON array of command strings.
"""

CISO_PROMPT = """\
You are Agent 5 (The CISO) of HAWK Sentinel. You write the executive report.

Given all findings from the automated penetration test, write a comprehensive
Markdown report suitable for a boardroom presentation. Structure:

# HAWK Sentinel — Penetration Test Report

## Executive Summary
(2-3 paragraph high-level overview for non-technical executives)

## Scope & Methodology
(What was tested, what tools were used, Rules of Engagement summary)

## Risk Score
(Overall risk score: Critical/High/Medium/Low with justification)

## Critical & High Findings
(Detailed writeup of each critical/high finding with:
- Description
- Impact
- Evidence
- Remediation steps)

## Medium & Low Findings
(Summary table of medium/low findings)

## Attack Narrative
(Chronological story of how an attacker could chain these vulnerabilities)

## Recommendations
(Prioritized remediation roadmap with timeline suggestions)

## Appendix: Full Scan Results
(Technical details for the security team)

Rules:
- Write for a C-suite audience in the Executive Summary
- Be extremely specific in findings — include exact ports, URLs, versions
- Provide actionable remediation steps (not generic advice)
- Include the risk score calculation methodology
- Format in clean Markdown
"""


async def _llm_call(
    system_prompt: str,
    user_content: str,
    settings: Settings,
) -> str:
    """Make an LLM call using the Sentinel-specific API config."""
    async with AsyncOpenAI(
        api_key=settings.sentinel_llm_api_key,
        base_url=settings.sentinel_llm_base_url,
        timeout=120,
    ) as client:
        response = await client.chat.completions.create(
            model=settings.sentinel_llm_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
            max_tokens=4000,
        )
    return (response.choices[0].message.content or "").strip()


def _parse_json_response(text: str) -> Any:
    """Extract JSON from an LLM response (handles ```json fences)."""
    import re
    match = re.search(r"```json\s*([\s\S]*?)\s*```", text)
    if match:
        return json.loads(match.group(1))
    text = text.strip()
    if text.startswith("[") or text.startswith("{"):
        return json.loads(text)
    raise ValueError(f"No valid JSON found in response: {text[:200]}")


# ---------------------------------------------------------------------------
# Agent Execution Functions
# ---------------------------------------------------------------------------

async def run_planner(
    scope: dict[str, Any],
    pulse_data: dict[str, Any],
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Agent 1: Generate the attack plan based on scope and recon data."""
    settings = settings or get_settings()

    user_content = (
        f"## Scope Contract\n```json\n{json.dumps(scope, indent=2)}\n```\n\n"
        f"## HAWK Pulse Reconnaissance Data\n```json\n{json.dumps(pulse_data, indent=2)}\n```\n\n"
        f"Generate the attack plan."
    )

    response = await _llm_call(PLANNER_PROMPT, user_content, settings)
    plan = _parse_json_response(response)

    if not isinstance(plan, list):
        raise ValueError("Planner must return a JSON array of steps")

    logger.info("Planner generated %d attack steps", len(plan))
    return plan


async def run_ghost_setup(
    scope: dict[str, Any],
    attack_plan: list[dict[str, Any]],
    container_id: str,
    settings: Settings | None = None,
) -> list[str]:
    """Agent 2: Configure OPSEC/evasion and run setup commands."""
    settings = settings or get_settings()

    user_content = (
        f"## Scope\n```json\n{json.dumps(scope, indent=2)}\n```\n\n"
        f"## Attack Plan\n```json\n{json.dumps(attack_plan, indent=2)}\n```\n\n"
        f"Generate OPSEC setup commands."
    )

    response = await _llm_call(GHOST_PROMPT, user_content, settings)
    commands = _parse_json_response(response)

    if not isinstance(commands, list):
        commands = []

    results = []
    for cmd in commands:
        if not isinstance(cmd, str):
            continue
        try:
            exit_code, stdout, stderr = await async_safe_execute(
                command=cmd, scope=scope,
                executor_fn=exec_in_sandbox, container_id=container_id,
            )
            results.append(f"[{exit_code}] {cmd}: {stdout[:200]}")
        except ScopeViolation as e:
            results.append(f"[SCOPE BLOCKED] {cmd}: {e}")
        except Exception as e:
            results.append(f"[ERR] {cmd}: {e}")

    logger.info("Ghost setup complete: %d commands", len(commands))
    return results


async def run_operator(
    scope: dict[str, Any],
    attack_plan: list[dict[str, Any]],
    container_id: str,
    settings: Settings | None = None,
) -> list[dict[str, Any]]:
    """Agent 3: Execute attack plan steps with scope enforcement."""
    settings = settings or get_settings()
    all_findings: list[dict[str, Any]] = []

    for step in attack_plan:
        command = step.get("command", "")
        step_num = step.get("step", "?")

        try:
            exit_code, stdout, stderr = await async_safe_execute(
                command=command,
                scope=scope,
                executor_fn=exec_in_sandbox,
                container_id=container_id,
            )
        except ScopeViolation as e:
            all_findings.append({
                "step": step_num,
                "command": command,
                "raw_output_summary": f"BLOCKED by scope enforcer: {e}",
                "findings": [],
            })
            continue

        output_text = stdout[:3000] + ("\n[stderr] " + stderr[:500] if stderr else "")

        user_content = (
            f"## Step {step_num}\n"
            f"Command: `{command}`\n"
            f"Exit code: {exit_code}\n\n"
            f"## Output\n```\n{output_text}\n```\n\n"
            f"Analyze the output and extract findings."
        )

        try:
            response = await _llm_call(OPERATOR_PROMPT, user_content, settings)
            step_result = _parse_json_response(response)
            if isinstance(step_result, dict):
                all_findings.append(step_result)
        except Exception:
            logger.exception("Operator failed to parse findings for step %s", step_num)
            all_findings.append({
                "step": step_num,
                "command": command,
                "raw_output_summary": output_text[:500],
                "findings": [],
            })

    logger.info("Operator complete: %d steps, findings extracted", len(attack_plan))
    return all_findings


async def run_cleanup(
    scope: dict[str, Any],
    container_id: str,
    settings: Settings | None = None,
) -> list[str]:
    """Agent 4: Run cleanup commands in the sandbox (scope-enforced)."""
    settings = settings or get_settings()

    response = await _llm_call(
        CLEANUP_PROMPT,
        "The penetration test is complete. Generate cleanup commands.",
        settings,
    )

    try:
        commands = _parse_json_response(response)
    except (ValueError, json.JSONDecodeError):
        commands = [
            "rm -rf /tmp/hawk-*",
            "history -c",
            "rm -f ~/.bash_history",
        ]

    results = []
    for cmd in commands:
        if not isinstance(cmd, str):
            continue
        try:
            exit_code, stdout, _ = await async_safe_execute(
                command=cmd, scope=scope,
                executor_fn=exec_in_sandbox, container_id=container_id,
            )
            results.append(f"[{exit_code}] {cmd}")
        except ScopeViolation as e:
            results.append(f"[SCOPE BLOCKED] {cmd}: {e}")
        except Exception as e:
            results.append(f"[ERR] {cmd}: {e}")

    logger.info("Cleanup complete: %d commands", len(commands))
    return results


async def run_ciso_report(
    scope: dict[str, Any],
    findings: list[dict[str, Any]],
    domain: str,
    settings: Settings | None = None,
) -> str:
    """Agent 5: Generate the boardroom-grade Markdown report."""
    settings = settings or get_settings()

    user_content = (
        f"## Target Domain\n{domain}\n\n"
        f"## Scope Contract\n```json\n{json.dumps(scope, indent=2)}\n```\n\n"
        f"## All Findings\n```json\n{json.dumps(findings, indent=2)}\n```\n\n"
        f"Write the complete penetration test report."
    )

    report = await _llm_call(CISO_PROMPT, user_content, settings)
    logger.info("CISO report generated: %d chars", len(report))
    return report
