# HAWK Scanner 2.0 — Python API + worker (same image; Railway sets start command per service)

FROM python:3.12-slim-bookworm

# Install ProjectDiscovery tools + WhatWeb
RUN apt-get update && apt-get install -y --no-install-recommends wget unzip ca-certificates whatweb && \
    wget -qL https://github.com/projectdiscovery/subfinder/releases/latest/download/subfinder_linux_amd64.zip && \
    unzip subfinder_linux_amd64.zip && mv subfinder /usr/local/bin/ && \
    wget -qL https://github.com/projectdiscovery/naabu/releases/latest/download/naabu_linux_amd64.zip && \
    unzip naabu_linux_amd64.zip && mv naabu /usr/local/bin/ && \
    wget -qL https://github.com/projectdiscovery/httpx/releases/latest/download/httpx_linux_amd64.zip && \
    unzip httpx_linux_amd64.zip && mv httpx /usr/local/bin/ && \
    wget -qL https://github.com/projectdiscovery/nuclei/releases/latest/download/nuclei_linux_amd64.zip && \
    unzip nuclei_linux_amd64.zip && mv nuclei /usr/local/bin/ && \
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
