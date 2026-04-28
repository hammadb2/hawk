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

    # API keys — pipeline LLM (interpretation + attack paths)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    hibp_api_key: str = ""
    breachsense_api_key: str = ""
    breachsense_base_url: str = ""
    # Breach monitoring stack (A–E + optional F Breachsense)
    dehashed_email: str = ""
    dehashed_api_key: str = ""
    oathnet_api_key: str = ""
    ransomwatch_api_token: str = ""
    github_token: str = ""
    nvd_api_key: str = ""

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

    # Time budget (seconds) — per subprocess layer; lower = fail faster under load
    layer_timeout_sec: int = 72
    total_budget_sec: int = 300

    # Breadth caps — lower values shorten wall clock (less host/url coverage)
    naabu_max_hosts: int = 28
    full_scan_target_url_cap: int = 55
    nuclei_max_target_urls: int = 22

    # Nuclei
    nuclei_templates_dir: str = ""  # empty = default template path in image
    nuclei_custom_templates_dir: str = ""  # additional vertical-specific templates (dental/legal)

    # Scoring trust tiers (see app.scoring.compute_score)
    strict_score_floor_public: float = 28.0  # min deduction × mult for anonymous / non-trusted scans
    strict_score_floor_subscriber: float = 13.0  # paid + domain on account, before remediation attestation


@lru_cache
def get_settings() -> Settings:
    return Settings()
