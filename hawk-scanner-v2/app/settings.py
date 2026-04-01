"""Environment for HAWK Scanner 2.0 (Railway + Redis queue)."""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Core
    service_name: str = "hawk-scanner-v2"
    log_level: str = "INFO"

    # Redis — same broker pattern as BullMQ (Redis); workers use arq (Python)
    redis_url: str = "redis://localhost:6379/0"

    # API keys
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"
    hibp_api_key: str = ""
    breachsense_api_key: str = ""
    breachsense_base_url: str = ""
    # Breach monitoring stack (A–E + optional F Breachsense)
    dehashed_email: str = ""
    dehashed_api_key: str = ""
    oathnet_api_key: str = ""
    ransomwatch_api_token: str = ""
    github_token: str = ""

    # Optional: persist from worker
    supabase_url: str = ""
    supabase_service_role_key: str = ""

    # Tool paths (override if not on PATH)
    subfinder_bin: str = "subfinder"
    naabu_bin: str = "naabu"
    httpx_bin: str = "httpx"
    whatweb_bin: str = "whatweb"
    nuclei_bin: str = "nuclei"
    dnstwist_bin: str = "dnstwist"

    # Time budget (seconds) — target total wall clock ~3–5 min
    layer_timeout_sec: int = 90
    total_budget_sec: int = 300

    # Nuclei
    nuclei_templates_dir: str = ""  # empty = default template path in image


@lru_cache
def get_settings() -> Settings:
    return Settings()
