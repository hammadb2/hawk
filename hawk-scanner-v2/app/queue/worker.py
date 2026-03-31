"""arq worker entrypoint: `arq app.queue.worker.WorkerSettings`"""
from __future__ import annotations

from arq.connections import RedisSettings

from app.queue.tasks import run_scan_task
from app.settings import get_settings


async def startup(ctx: dict) -> None:
    get_settings()


class WorkerSettings:
    functions = [run_scan_task]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    job_timeout = 600
    max_tries = 1
