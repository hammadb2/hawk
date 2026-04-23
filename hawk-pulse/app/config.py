"""HAWK Pulse Engine — configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Settings:
    database_url: str = field(
        default_factory=lambda: os.environ.get(
            "DATABASE_URL",
            "postgresql+asyncpg://hawk:hawk@localhost:5432/hawk_pulse",
        )
    )
    database_url_sync: str = field(
        default_factory=lambda: os.environ.get(
            "DATABASE_URL_SYNC",
            "postgresql://hawk:hawk@localhost:5432/hawk_pulse",
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


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
