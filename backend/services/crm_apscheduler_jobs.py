"""Internal CRM / ARIA cron job entrypoints for APScheduler (no HTTP, no X-Cron-Secret)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

MST = ZoneInfo("America/Edmonton")


async def run_nightly_pipeline_job() -> None:
    try:
        from services.aria_lead_inventory import run_nightly_pipeline

        # Off the asyncio event loop (same pattern as avoiding asyncio.run inside FastAPI's loop).
        result = await asyncio.to_thread(lambda: asyncio.run(run_nightly_pipeline()))
        logger.info("scheduler job run_nightly_pipeline_job ok: %s", result)
    except Exception as e:
        logger.exception("scheduler job run_nightly_pipeline_job failed")
        try:
            from services.crm_openphone import send_ceo_sms

            send_ceo_sms(f"ARIA nightly pipeline failed: {e!s}"[:1500])
        except Exception:
            pass


async def run_morning_dispatch_job() -> None:
    try:
        from services.aria_morning_dispatch import run_morning_dispatch

        result = await asyncio.to_thread(run_morning_dispatch)
        logger.info("scheduler job run_morning_dispatch_job ok: %s", result)
    except Exception as e:
        logger.exception("scheduler job run_morning_dispatch_job failed")
        try:
            from services.crm_openphone import send_ceo_sms

            send_ceo_sms(f"ARIA morning dispatch failed: {e!s}"[:1500])
        except Exception:
            pass


async def run_inbox_health_job() -> None:
    try:
        from services.aria_inbox_health import run_inbox_health_check

        include_blacklist = datetime.now(MST).weekday() == 0
        result = await asyncio.to_thread(run_inbox_health_check, include_blacklist=include_blacklist)
        logger.info("scheduler job run_inbox_health_job ok: %s", result)
    except Exception:
        logger.exception("scheduler job run_inbox_health_job failed")


async def run_aging_job() -> None:
    try:
        from routers.crm_cron import run_aging_cron_internal

        result = await asyncio.to_thread(run_aging_cron_internal)
        logger.info("scheduler job run_aging_job ok: %s", result)
    except Exception:
        logger.exception("scheduler job run_aging_job failed")


async def run_stale_pipeline_job() -> None:
    try:
        from routers.crm_cron import run_stale_pipeline_cron_internal

        result = await asyncio.to_thread(run_stale_pipeline_cron_internal)
        logger.info("scheduler job run_stale_pipeline_job ok: %s", result)
    except Exception:
        logger.exception("scheduler job run_stale_pipeline_job failed")


async def run_onboarding_drip_job() -> None:
    try:
        from services.crm_portal_sequence_worker import process_due_onboarding_sequences

        result = await asyncio.to_thread(process_due_onboarding_sequences)
        logger.info("scheduler job run_onboarding_drip_job ok: %s", result)
    except Exception:
        logger.exception("scheduler job run_onboarding_drip_job failed")


async def run_shield_rescan_job() -> None:
    try:
        from services.crm_shield_daily import run_daily_shield_rescans

        result = await asyncio.to_thread(run_daily_shield_rescans)
        logger.info("scheduler job run_shield_rescan_job ok: %s", result)
    except Exception:
        logger.exception("scheduler job run_shield_rescan_job failed")


async def run_dnstwist_job() -> None:
    try:
        from services.crm_dnstwist_daily import run_daily_dnstwist_monitoring

        result = await asyncio.to_thread(run_daily_dnstwist_monitoring)
        logger.info("scheduler job run_dnstwist_job ok: %s", result)
    except Exception:
        logger.exception("scheduler job run_dnstwist_job failed")


async def run_portal_milestones_job() -> None:
    try:
        from routers.crm_cron import run_portal_milestones_cron_internal

        result = await asyncio.to_thread(run_portal_milestones_cron_internal)
        logger.info("scheduler job run_portal_milestones_job ok: %s", result)
    except Exception:
        logger.exception("scheduler job run_portal_milestones_job failed")


async def run_rep_health_job() -> None:
    try:
        from services.crm_rep_health import run_rep_health_scores

        result = await asyncio.to_thread(run_rep_health_scores)
        logger.info("scheduler job run_rep_health_job ok: %s", result)
    except Exception:
        logger.exception("scheduler job run_rep_health_job failed")


async def run_enterprise_scans_job() -> None:
    try:
        from services.crm_enterprise_domain_scans import run_enterprise_domain_scans

        result = await asyncio.to_thread(run_enterprise_domain_scans)
        logger.info("scheduler job run_enterprise_scans_job ok: %s", result)
    except Exception:
        logger.exception("scheduler job run_enterprise_scans_job failed")


async def run_monthly_reports_job() -> None:
    try:
        from services.crm_monthly_reports import run_monthly_client_reports

        result = await asyncio.to_thread(run_monthly_client_reports)
        logger.info("scheduler job run_monthly_reports_job ok: %s", result)
    except Exception:
        logger.exception("scheduler job run_monthly_reports_job failed")


async def run_weekly_threat_job() -> None:
    try:
        from routers.portal_phase2 import run_weekly_threat_briefings_for_all_clients

        result = await asyncio.to_thread(run_weekly_threat_briefings_for_all_clients)
        logger.info("scheduler job run_weekly_threat_job ok: %s", result)
    except Exception:
        logger.exception("scheduler job run_weekly_threat_job failed")


async def run_attacker_sim_job() -> None:
    try:
        from services.crm_attacker_simulation import run_weekly_attacker_simulations

        result = await asyncio.to_thread(run_weekly_attacker_simulations)
        logger.info("scheduler job run_attacker_sim_job ok: %s", result)
    except Exception:
        logger.exception("scheduler job run_attacker_sim_job failed")


async def run_monday_briefing_job() -> None:
    try:
        from services.aria_briefing import run_monday_briefing

        result = await asyncio.to_thread(run_monday_briefing)
        logger.info("scheduler job run_monday_briefing_job ok: %s", result)
    except Exception:
        logger.exception("scheduler job run_monday_briefing_job failed")


async def run_competitive_brief_job() -> None:
    try:
        from services.aria_briefing import run_competitive_brief

        result = await asyncio.to_thread(run_competitive_brief)
        logger.info("scheduler job run_competitive_brief_job ok: %s", result)
    except Exception:
        logger.exception("scheduler job run_competitive_brief_job failed")


async def run_scheduled_ai_actions_job() -> None:
    try:
        from routers.crm_cron import run_scheduled_ai_actions_cron_internal

        result = await asyncio.to_thread(run_scheduled_ai_actions_cron_internal)
        logger.info("scheduler job run_scheduled_ai_actions_job ok: %s", result)
    except Exception:
        logger.exception("scheduler job run_scheduled_ai_actions_job failed")


async def run_aria_memory_job() -> None:
    try:
        from services.aria_memory import run_memory_ingestion

        result = await asyncio.to_thread(run_memory_ingestion)
        logger.info("scheduler job run_aria_memory_job ok: %s", result)
    except Exception:
        logger.exception("scheduler job run_aria_memory_job failed")


async def run_aria_client_health_job() -> None:
    try:
        from services.aria_client_health import run_client_health_scores

        result = await asyncio.to_thread(run_client_health_scores)
        logger.info("scheduler job run_aria_client_health_job ok: %s", result)
    except Exception:
        logger.exception("scheduler job run_aria_client_health_job failed")
