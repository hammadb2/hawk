# HAWK Scanner Relay (Ghost)

Runs on **Ghost** (178.104.27.211) port **8002**. Receives scan requests from the main HAWK API and forwards them to Specter (10.0.0.2:8002) over WireGuard.

## Run

```bash
cd ghost
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn scanner_relay:app --host 0.0.0.0 --port 8002
```

Or: `python scanner_relay.py`

## Env (optional)

- `HAWK_SPECTER_URL` — Specter base URL (default `http://10.0.0.2:8002`)
- `HAWK_SPECTER_TIMEOUT` — Request timeout in seconds (default `120`)

## API

- **GET /health** — `{"status":"ok","service":"scanner-relay"}`
- **POST /scan** — Body: `{"domain": "example.com", "scan_id": "optional-uuid"}`  
  Forwards to Specter and returns the same JSON (score, grade, findings, etc.).  
  Errors: 503 if Specter unreachable, 504 on timeout, or Specter’s status/details.
