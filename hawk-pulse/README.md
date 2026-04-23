# HAWK Pulse Engine (v3.0 PoC)

Event-driven Continuous Threat Exposure Management (CTEM). Replaces the legacy point-in-time scan architecture (Specter, Ghost, hawk-scanner-v2 async polling) with a reactive, real-time pipeline.

## Architecture

```
Certificate Transparency Logs
        │
        ▼
┌─────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  CT Listener    │────▶│  Micro-Scanner   │────▶│  State Diffing   │
│  (certstream)   │     │  (naabu + httpx) │     │  Engine (PG)     │
└─────────────────┘     └──────────────────┘     └────────┬─────────┘
                                                          │
                                                   Delta alerts only
                                                          │
                                                          ▼
                                                 ┌──────────────────┐
                                                 │  WebSocket Push  │
                                                 │  (FastAPI WS)    │
                                                 └──────────────────┘
                                                          │
                                                          ▼
                                                 React/Next.js Dashboard
```

### Flow

1. **CT Listener** subscribes to the global Certificate Transparency log stream via `certstream`.
2. When a certificate is issued for a **monitored domain** (e.g. `*.clientdomain.com`), the listener fires.
3. A **Micro-Scan** runs `naabu` (port scan) and `httpx` (HTTP probe) only on the newly discovered host(s).
4. The **State Diffing Engine** compares results against the PostgreSQL asset database:
   - **Known asset?** Update `last_seen` timestamp. No alert.
   - **New asset?** Insert into DB, generate a **delta alert** with severity.
5. The alert is pushed in real-time through the **WebSocket** to all connected dashboard clients.

## Quick Start

### Docker Compose (recommended)

```bash
cd hawk-pulse
docker compose up -d
```

This starts PostgreSQL and the Pulse engine on port 8080.

### Local Dev

```bash
cd hawk-pulse
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Start Postgres (or use docker compose up postgres)
# Then:
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

## API

### Domain Management

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/domains` | Add a domain for continuous monitoring |
| `GET` | `/api/domains` | List all monitored domains |
| `DELETE` | `/api/domains/{domain}` | Deactivate monitoring |

### Scanning

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/scan` | Manually trigger a micro-scan + state diff |

### Alerts

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/alerts/{domain}` | List alerts (optional `?unacknowledged_only=true`) |
| `PATCH` | `/api/alerts/{alert_id}/ack` | Acknowledge an alert |

### Assets

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/assets/{domain}` | List discovered assets (optional `?asset_type=open_port`) |

### Real-time

| Protocol | Endpoint | Description |
|----------|----------|-------------|
| WebSocket | `/ws/alerts/{domain}` | Live alert stream. Sends JSON on every state change. |

### Audit

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/events/{domain}` | Scan event audit log |

## Example: Register a domain and connect

```bash
# 1. Add a domain
curl -X POST http://localhost:8080/api/domains \
  -H "Content-Type: application/json" \
  -d '{"domain": "example.com", "owner_email": "admin@example.com"}'

# 2. Connect to the WebSocket (use wscat, websocat, or browser)
wscat -c ws://localhost:8080/ws/alerts/example.com

# 3. Trigger a manual scan (alerts push to WebSocket)
curl -X POST http://localhost:8080/api/scan \
  -H "Content-Type: application/json" \
  -d '{"domain": "example.com"}'
```

## Env

See `.env.example`. Key variables:

- `DATABASE_URL` — PostgreSQL async connection string
- `CERTSTREAM_URL` — CT log WebSocket (default: calidog.io)
- `NAABU_BIN`, `HTTPX_BIN` — paths to scanner binaries (empty = `$PATH`)
- `MICROSCAN_WORKERS` — max concurrent micro-scans

## Next Steps (Step 2 & 3)

- **HAWK Guard (Step 2):** AI remediation engine — auto-generate fix guides per finding, tailored to detected tech stack.
- **HAWK Sentinel (Step 3):** Ephemeral Kali Docker swarm for automated penetration testing with boardroom-grade reports.
