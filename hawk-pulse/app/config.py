"""HAWK Pulse Engine — configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


def _to_asyncpg(url: str) -> str:
    """Ensure a PostgreSQL URL uses the asyncpg driver."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def _to_sync(url: str) -> str:
    """Ensure a PostgreSQL URL uses the sync (psycopg2) driver."""
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


@dataclass(frozen=True)
class Settings:
    database_url: str = field(
        default_factory=lambda: _to_asyncpg(
            os.environ.get(
                "DATABASE_URL",
                "postgresql+asyncpg://hawk:hawk@localhost:5432/hawk_pulse",
            )
        )
    )
    database_url_sync: str = field(
        default_factory=lambda: _to_sync(
            os.environ.get(
                "DATABASE_URL_SYNC",
                os.environ.get(
                    "DATABASE_URL",
                    "postgresql://hawk:hawk@localhost:5432/hawk_pulse",
                ),
            )
        )
    )

    # Scanner tool binary paths (empty = use $PATH)
    naabu_bin: str = field(default_factory=lambda: os.environ.get("NAABU_BIN", ""))
    httpx_bin: str = field(default_factory=lambda: os.environ.get("HTTPX_BIN", ""))
    nuclei_bin: str = field(default_factory=lambda: os.environ.get("NUCLEI_BIN", ""))

    # Scanner tunables
    naabu_ports: str = field(
        default_factory=lambda: os.environ.get("NAABU_PORTS", "80,443,8080,8443,3000,4443,22,21,3306,5432,6379,27017,3389")
    )
    layer_timeout_sec: float = field(
        default_factory=lambda: float(os.environ.get("LAYER_TIMEOUT_SEC", "60"))
    )

    # Certstream
    certstream_url: str = field(
        default_factory=lambda: os.environ.get(
            "CERTSTREAM_URL", "wss://certstream.calidog.io/"
        )
    )

    # Micro-scan concurrency
    microscan_workers: int = field(
        default_factory=lambda: int(os.environ.get("MICROSCAN_WORKERS", "4"))
    )

    # AI Remediation (HAWK Guard)
    openai_api_key: str = field(
        default_factory=lambda: os.environ.get("OPENAI_API_KEY", "")
    )
    openai_base_url: str = field(
        default_factory=lambda: os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    )
    openai_model: str = field(
        default_factory=lambda: os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    )
    remediation_timeout_sec: float = field(
        default_factory=lambda: float(os.environ.get("REMEDIATION_TIMEOUT_SEC", "60"))
    )
    remediation_enabled: bool = field(
        default_factory=lambda: os.environ.get("REMEDIATION_ENABLED", "true").lower() in ("true", "1", "yes")
    )

    # HAWK Sentinel (AI Red Team)
    sentinel_enabled: bool = field(
        default_factory=lambda: os.environ.get("SENTINEL_ENABLED", "true").lower() in ("true", "1", "yes")
    )
    sentinel_llm_api_key: str = field(
        default_factory=lambda: os.environ.get("SENTINEL_LLM_API_KEY", "")
    )
    sentinel_llm_base_url: str = field(
        default_factory=lambda: os.environ.get(
            "SENTINEL_LLM_BASE_URL", "https://api.openai.com/v1"
        )
    )
    sentinel_llm_model: str = field(
        default_factory=lambda: os.environ.get("SENTINEL_LLM_MODEL", "gpt-4o-mini")
    )
    sentinel_docker_image: str = field(
        default_factory=lambda: os.environ.get("SENTINEL_DOCKER_IMAGE", "kalilinux/kali-rolling")
    )
    sentinel_container_timeout: int = field(
        default_factory=lambda: int(os.environ.get("SENTINEL_CONTAINER_TIMEOUT", "3600"))
    )
    sentinel_max_concurrent: int = field(
        default_factory=lambda: int(os.environ.get("SENTINEL_MAX_CONCURRENT", "2"))
    )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
