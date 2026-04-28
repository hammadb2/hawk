# HAWK Scanner 2.0 — Python API + worker (same image; Railway sets start command per service)
#
# ProjectDiscovery @latest requires a modern Go (toolchain in go.mod). Debian's golang-go
# is too old; build tools in a golang image, then copy binaries into Python slim.

FROM golang:1.24-bookworm AS pd-tools

# httpx @latest can require a newer Go than the image (e.g. >= 1.25.7); download toolchain as needed
ENV GOTOOLCHAIN=auto

# naabu uses CGO + libpcap
RUN apt-get update && apt-get install -y --no-install-recommends libpcap-dev && \
    rm -rf /var/lib/apt/lists/*

ENV CGO_ENABLED=1

RUN go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest && \
    go install -v github.com/projectdiscovery/naabu/v2/cmd/naabu@latest && \
    go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest && \
    go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest

# --- runtime image ---

FROM python:3.12-slim-bookworm

# whatweb + libpcap for naabu; Playwright Chromium deps for exposure screenshots
RUN apt-get update && apt-get install -y --no-install-recommends \
    whatweb ca-certificates libpcap0.8 \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libdbus-1-3 \
    libxcb1 libxkbcommon0 libatspi2.0-0 libx11-6 libxcomposite1 libxdamage1 libxext6 \
    libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

COPY --from=pd-tools /go/bin/subfinder /go/bin/naabu /go/bin/httpx /go/bin/nuclei /usr/local/bin/
RUN chmod +x /usr/local/bin/subfinder /usr/local/bin/naabu /usr/local/bin/httpx /usr/local/bin/nuclei

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install chromium
COPY app ./app
COPY scripts ./scripts
COPY nuclei-templates-custom ./nuclei-templates-custom

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV NUCLEI_CUSTOM_TEMPLATES_DIR=/app/nuclei-templates-custom

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
