"""Certificate Transparency log listener via certstream."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Coroutine

import certstream

logger = logging.getLogger(__name__)


def _extract_domains(message: dict[str, Any]) -> list[str]:
    """Pull SAN domains from a certstream message."""
    data = message.get("data") or {}
    leaf = data.get("leaf_cert") or {}
    all_domains = leaf.get("all_domains") or []
    return [d.lower().strip().lstrip("*.") for d in all_domains if d and isinstance(d, str)]


class CTListener:
    """
    Connects to the Certificate Transparency log stream and fires a callback
    whenever a certificate is issued for a monitored domain.
    """

    def __init__(
        self,
        monitored_domains: set[str],
        on_match: Callable[[str, list[str]], Coroutine],
        certstream_url: str = "wss://certstream.calidog.io/",
    ):
        self._monitored = monitored_domains
        self._on_match = on_match
        self._url = certstream_url
        self._running = False

    def update_domains(self, domains: set[str]) -> None:
        self._monitored = {d.lower().strip() for d in domains}

    def _matches(self, cert_domain: str) -> str | None:
        """Check if cert_domain matches or is a subdomain of any monitored domain."""
        cert_domain = cert_domain.lower().strip()
        for md in self._monitored:
            if cert_domain == md or cert_domain.endswith(f".{md}"):
                return md
        return None

    def start(self) -> None:
        """Start the certstream listener in a background thread (blocking internally via certstream lib)."""
        self._running = True
        logger.info("CT listener starting — monitoring %d domain(s)", len(self._monitored))

        def _callback(message: dict, context: Any) -> None:
            if not self._running:
                return
            if message.get("message_type") != "certificate_update":
                return
            cert_domains = _extract_domains(message)
            for cd in cert_domains:
                matched_root = self._matches(cd)
                if matched_root:
                    logger.info("CT match: %s (root: %s)", cd, matched_root)
                    asyncio.get_event_loop().create_task(
                        self._on_match(matched_root, cert_domains)
                    )
                    break

        certstream.listen_for_events(_callback, url=self._url)

    def stop(self) -> None:
        self._running = False


async def start_ct_listener(
    monitored_domains: set[str],
    on_match: Callable[[str, list[str]], Coroutine],
    certstream_url: str = "wss://certstream.calidog.io/",
) -> CTListener:
    """Create and start a CT listener in a background thread."""
    listener = CTListener(monitored_domains, on_match, certstream_url)
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, listener.start)
    return listener
