"""HAWK Sentinel — Ephemeral Docker Sandbox Manager.

Spins up an isolated Kali Linux container with the open-source arsenal
for the duration of an audit, and tears it down when complete.
"""
from __future__ import annotations

import logging
from typing import Any

import docker
from docker.errors import DockerException, NotFound

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

ARSENAL_SETUP_SCRIPT = r"""#!/bin/bash
set -e
export DEBIAN_FRONTEND=noninteractive

# Update and install core tools
apt-get update -qq
apt-get install -y -qq \
    nmap \
    proxychains4 \
    tor \
    curl \
    wget \
    git \
    python3 \
    python3-pip \
    net-tools \
    dnsutils \
    whois \
    tcpdump \
    2>/dev/null

# Install nuclei
curl -sL https://github.com/projectdiscovery/nuclei/releases/latest/download/nuclei_$(uname -s)_$(uname -m).zip -o /tmp/nuclei.zip \
    && unzip -o /tmp/nuclei.zip -d /usr/local/bin/ nuclei 2>/dev/null \
    && chmod +x /usr/local/bin/nuclei \
    && rm /tmp/nuclei.zip || true

# Install subfinder
curl -sL https://github.com/projectdiscovery/subfinder/releases/latest/download/subfinder_$(uname -s)_$(uname -m).zip -o /tmp/subfinder.zip \
    && unzip -o /tmp/subfinder.zip -d /usr/local/bin/ subfinder 2>/dev/null \
    && chmod +x /usr/local/bin/subfinder \
    && rm /tmp/subfinder.zip || true

# Install httpx
curl -sL https://github.com/projectdiscovery/httpx/releases/latest/download/httpx_$(uname -s)_$(uname -m).zip -o /tmp/httpx.zip \
    && unzip -o /tmp/httpx.zip -d /usr/local/bin/ httpx 2>/dev/null \
    && chmod +x /usr/local/bin/httpx \
    && rm /tmp/httpx.zip || true

# Install naabu
curl -sL https://github.com/projectdiscovery/naabu/releases/latest/download/naabu_$(uname -s)_$(uname -m).zip -o /tmp/naabu.zip \
    && unzip -o /tmp/naabu.zip -d /usr/local/bin/ naabu 2>/dev/null \
    && chmod +x /usr/local/bin/naabu \
    && rm /tmp/naabu.zip || true

echo "HAWK Sentinel arsenal ready."
"""


def get_docker_client() -> docker.DockerClient:
    """Get a Docker client from the environment."""
    try:
        return docker.from_env()
    except DockerException as e:
        logger.error("Failed to connect to Docker daemon: %s", e)
        raise RuntimeError(
            "Docker daemon not available. Ensure Docker is installed and running."
        ) from e


def create_sandbox(
    audit_id: str,
    scope_json: dict[str, Any],
    settings: Settings | None = None,
) -> str:
    """
    Spin up an ephemeral Kali Linux container for a Sentinel audit.

    Returns the container ID.
    """
    settings = settings or get_settings()
    client = get_docker_client()

    import json
    scope_str = json.dumps(scope_json)

    container_name = f"hawk-sentinel-{audit_id[:12]}"

    try:
        old = client.containers.get(container_name)
        old.remove(force=True)
        logger.info("Removed stale container: %s", container_name)
    except NotFound:
        pass

    container = client.containers.run(
        image=settings.sentinel_docker_image,
        name=container_name,
        detach=True,
        tty=True,
        stdin_open=True,
        network_mode="bridge",
        mem_limit="2g",
        cpu_quota=100000,
        environment={
            "HAWK_AUDIT_ID": audit_id,
            "HAWK_SCOPE": scope_str,
        },
        labels={
            "hawk.sentinel": "true",
            "hawk.audit_id": audit_id,
        },
        auto_remove=False,
    )

    logger.info(
        "Sentinel sandbox created: %s (image=%s, container=%s)",
        container_name, settings.sentinel_docker_image, container.short_id,
    )

    return container.id


def setup_arsenal(container_id: str) -> str:
    """Install the open-source toolkit inside the container."""
    client = get_docker_client()
    container = client.containers.get(container_id)

    exit_code, output = container.exec_run(
        cmd=["bash", "-c", ARSENAL_SETUP_SCRIPT],
        demux=True,
    )

    stdout = (output[0] or b"").decode(errors="replace")
    stderr = (output[1] or b"").decode(errors="replace")

    if exit_code != 0:
        logger.error("Arsenal setup failed (exit %d): %s", exit_code, stderr[:500])
        raise RuntimeError(f"Arsenal setup failed with exit code {exit_code}")

    logger.info("Arsenal setup complete in container %s", container_id[:12])
    return stdout


def exec_in_sandbox(container_id: str, command: str, timeout: int = 120) -> tuple[int, str, str]:
    """
    Execute a command inside the Sentinel sandbox.

    Returns (exit_code, stdout, stderr).
    """
    client = get_docker_client()
    container = client.containers.get(container_id)

    exit_code, output = container.exec_run(
        cmd=["bash", "-c", command],
        demux=True,
    )

    stdout = (output[0] or b"").decode(errors="replace")
    stderr = (output[1] or b"").decode(errors="replace")

    return exit_code, stdout, stderr


def destroy_sandbox(container_id: str) -> None:
    """Kill and remove the Sentinel sandbox container.

    Only destroys containers with the ``hawk.sentinel`` label to prevent
    accidental destruction of unrelated Docker containers.
    """
    try:
        client = get_docker_client()
        container = client.containers.get(container_id)

        if container.labels.get("hawk.sentinel") != "true":
            raise RuntimeError(
                f"Container {container_id[:12]} is not a HAWK Sentinel container"
            )

        container.kill()
        container.remove(force=True)
        logger.info("Sentinel sandbox destroyed: %s", container_id[:12])
    except NotFound:
        logger.warning("Container %s already removed", container_id[:12])
    except Exception:
        logger.exception("Failed to destroy container %s", container_id[:12])


def write_scope_to_sandbox(container_id: str, scope_json: dict[str, Any]) -> None:
    """Write the scope.json file into the container's /opt/hawk/ directory."""
    import io
    import json
    import tarfile

    client = get_docker_client()
    container = client.containers.get(container_id)

    container.exec_run(cmd=["mkdir", "-p", "/opt/hawk"])

    scope_bytes = json.dumps(scope_json, indent=2).encode()
    tar_buf = io.BytesIO()
    with tarfile.open(fileobj=tar_buf, mode="w") as tar:
        info = tarfile.TarInfo(name="scope.json")
        info.size = len(scope_bytes)
        tar.addfile(info, io.BytesIO(scope_bytes))
    tar_buf.seek(0)

    container.put_archive("/opt/hawk", tar_buf)
    logger.info("scope.json written to container %s", container_id[:12])
