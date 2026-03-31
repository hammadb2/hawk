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

# whatweb + libpcap for naabu at runtime
RUN apt-get update && apt-get install -y --no-install-recommends whatweb ca-certificates libpcap0.8 && \
    rm -rf /var/lib/apt/lists/*

COPY --from=pd-tools /go/bin/subfinder /go/bin/naabu /go/bin/httpx /go/bin/nuclei /usr/local/bin/
RUN chmod +x /usr/local/bin/subfinder /usr/local/bin/naabu /usr/local/bin/httpx /usr/local/bin/nuclei

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY scripts ./scripts

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
