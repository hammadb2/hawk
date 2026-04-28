#!/usr/bin/env bash
# nuclei_update_cron.sh — Daily Nuclei template auto-update.
#
# Install on Hetzner (or any scanner host) via crontab:
#   0 0 * * * /opt/hawk/scripts/nuclei_update_cron.sh >> /var/log/nuclei-update.log 2>&1
#
# Ensures the scanner always runs the latest community + custom templates.

set -euo pipefail

LOG_PREFIX="[nuclei-update $(date -u +%Y-%m-%dT%H:%M:%SZ)]"

echo "${LOG_PREFIX} Starting Nuclei template update..."

# Update community templates
if command -v nuclei &>/dev/null; then
    nuclei -update-templates 2>&1 | tail -5
    echo "${LOG_PREFIX} Community templates updated."
else
    echo "${LOG_PREFIX} ERROR: nuclei not found in PATH."
    exit 1
fi

# Verify template count
TEMPLATE_COUNT=$(nuclei -tl 2>/dev/null | wc -l || echo "0")
echo "${LOG_PREFIX} Total templates available: ${TEMPLATE_COUNT}"

# Update nuclei binary if a newer version is available
if command -v nuclei &>/dev/null; then
    CURRENT_VERSION=$(nuclei -version 2>&1 | head -1 || echo "unknown")
    echo "${LOG_PREFIX} Current nuclei version: ${CURRENT_VERSION}"
    nuclei -update 2>&1 | tail -3 || true
fi

# If custom templates directory exists, pull latest
CUSTOM_TEMPLATES_DIR="${HAWK_CUSTOM_TEMPLATES_DIR:-/opt/hawk/nuclei-templates-custom}"
if [ -d "${CUSTOM_TEMPLATES_DIR}/.git" ]; then
    echo "${LOG_PREFIX} Pulling custom templates from ${CUSTOM_TEMPLATES_DIR}..."
    cd "${CUSTOM_TEMPLATES_DIR}"
    git pull --ff-only 2>&1 | tail -3 || echo "${LOG_PREFIX} WARN: custom templates git pull failed"
fi

echo "${LOG_PREFIX} Nuclei template update complete."
