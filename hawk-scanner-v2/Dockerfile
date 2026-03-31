# HAWK Scanner 2.0 — Python API + worker (same image; Railway sets start command per service)

FROM python:3.12-slim-bookworm

# Install ProjectDiscovery tools + WhatWeb (pinned releases — avoid GitHub /latest redirect in CI)
RUN apt-get update && apt-get install -y --no-install-recommends wget unzip ca-certificates whatweb && \
    wget -q https://github.com/projectdiscovery/subfinder/releases/download/v2.6.6/subfinder_2.6.6_linux_amd64.zip && \
    unzip subfinder_2.6.6_linux_amd64.zip && mv subfinder /usr/local/bin/ && \
    wget -q https://github.com/projectdiscovery/naabu/releases/download/v2.3.1/naabu_2.3.1_linux_amd64.zip && \
    unzip naabu_2.3.1_linux_amd64.zip && mv naabu /usr/local/bin/ && \
    wget -q https://github.com/projectdiscovery/httpx/releases/download/v1.6.8/httpx_1.6.8_linux_amd64.zip && \
    unzip httpx_1.6.8_linux_amd64.zip && mv httpx /usr/local/bin/ && \
    wget -q https://github.com/projectdiscovery/nuclei/releases/download/v3.3.2/nuclei_3.3.2_linux_amd64.zip && \
    unzip nuclei_3.3.2_linux_amd64.zip && mv nuclei /usr/local/bin/ && \
    chmod +x /usr/local/bin/subfinder /usr/local/bin/naabu /usr/local/bin/httpx /usr/local/bin/nuclei && \
    rm -f *.zip && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY scripts ./scripts

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
