# HAWK Scanner 2.0 — Python API + worker (same image; Railway sets start command per service)

FROM python:3.12-slim-bookworm

# Install Go and ProjectDiscovery tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    golang-go whatweb ca-certificates git && \
    go install -v github.com/projectdiscovery/subfinder/v2/cmd/subfinder@latest && \
    go install -v github.com/projectdiscovery/naabu/v2/cmd/naabu@latest && \
    go install -v github.com/projectdiscovery/httpx/cmd/httpx@latest && \
    go install -v github.com/projectdiscovery/nuclei/v3/cmd/nuclei@latest && \
    cp /root/go/bin/subfinder /usr/local/bin/ && \
    cp /root/go/bin/naabu /usr/local/bin/ && \
    cp /root/go/bin/httpx /usr/local/bin/ && \
    cp /root/go/bin/nuclei /usr/local/bin/ && \
    chmod +x /usr/local/bin/subfinder /usr/local/bin/naabu /usr/local/bin/httpx /usr/local/bin/nuclei && \
    apt-get remove -y golang-go git && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/* /root/go/pkg /root/go/src

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY scripts ./scripts

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
