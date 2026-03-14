# HAWK Specter Scanner

Runs on **Specter** (10.0.0.2), reachable only via Ghost relay. Passive external attack-surface scanner.

## Run

```bash
cd specter
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
uvicorn specter_scanner:app --host 0.0.0.0 --port 8002
```

Or: `python specter_scanner.py`

## API

- **GET /health** — `{"status":"ok","service":"specter-scanner"}`
- **POST /scan** — Body: `{"domain": "example.com", "scan_id": "optional-uuid"}`  
  Returns: `ScanResponse` (score, grade, findings[]).

## Checks (7 categories)

1. **DNS** — SPF, DMARC, DKIM (default selector), MX, NS
2. **SSL/TLS** — Certificate validity/expiry, TLS 1.2+, no weak ciphers
3. **Network** — TCP connect on 21,22,23,25,3306,3389,5432,6379,8080,8443,27017 (22 = info; others warning/critical)
4. **Web** — HSTS, X-Frame-Options/CSP frame-ancestors, CSP, X-Content-Type-Options, Referrer-Policy
5. **Redirect** — HTTP → HTTPS
6. **Subdomains** — Passive lookup for www, mail, api, admin, etc.
7. **Grade** — 100 − (25×critical + 8×warning + 2×info); A=90+, B=75–89, C=55–74, D=35–54, F=0–34
