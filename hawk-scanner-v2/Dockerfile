# HAWK Scanner 2.0 — Python API + worker (same image; Railway sets start command per service)
# Install ProjectDiscovery binaries (subfinder, naabu, httpx, nuclei) via your preferred method:
#   - Pin releases in CI from https://github.com/projectdiscovery (linux_amd64 zip → /usr/local/bin), or
#   - `go install github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest` (multi-stage with golang)
# This image installs WhatWeb from apt; dnstwist can be `pip install dnstwist` or apt if available.

FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates whatweb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY scripts ./scripts

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
