# HAWK Core API

FastAPI backend: auth, scans, findings, domains, reports, billing, Ask HAWK, agency, notifications.

## Run

```bash
# From repo root (Hawk/)
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
PYTHONPATH=. uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Or: `PYTHONPATH=. python backend/main.py` (reload on port 8000).

## Env

- `DATABASE_URL` — default `sqlite:///./hawk.db`; use PostgreSQL in prod.
- `HAWK_SECRET_KEY` — JWT signing key.
- `HAWK_SCANNER_RELAY_URL` — Ghost relay (default `http://178.104.27.211:8002`).
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_*` — Stripe.
- `DEEPSEEK_API_KEY`, `DEEPSEEK_BASE_URL` — Ask HAWK (DeepSeek R1).
- `HAWK_BASE_URL` — Frontend URL for Stripe redirects (default `https://hawk.akbstudios.com`).

## Endpoints

- **Auth:** `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me`, `POST /api/auth/forgot-password`
- **Scans:** `POST /api/scan`, `GET /api/scan/:id`, `GET /api/scans`, `POST /api/scan/:id/rescan`
- **Findings:** `GET /api/findings/:scan_id`, `POST /api/findings/:id/ignore`, `POST /api/findings/:id/fix`
- **Domains:** `GET/POST/PUT/DELETE /api/domains`
- **Reports:** `GET /api/reports`, `POST /api/reports/generate`, `GET /api/reports/:id/pdf`
- **Billing:** `POST /api/billing/checkout`, `POST /api/billing/portal`, `POST /api/billing/webhook`, `GET /api/billing/invoices`
- **Ask HAWK:** `POST /api/hawk/chat`
- **Agency:** `GET/POST/GET/DELETE /api/agency/clients`, `POST /api/agency/clients/:id/report`
- **Notifications:** `GET /api/notifications`, `POST /api/notifications/read-all`

Docs: `http://localhost:8000/docs`.
