# HAWK

B2B cybersecurity SaaS for Canadian SMBs. External attack-surface scans, findings dashboard, Ask HAWK (AI), compliance mapping, and billing.

**Domain:** hawk.akbstudios.com · **Company:** [AKB Studios](https://akbstudios.com)

---

## Repo layout

| Path | Purpose |
|------|--------|
| **specter/** | Scanner engine (runs on Specter 10.0.0.2:8002). DNS, SSL, ports, headers, subdomains, grade. |
| **ghost/** | Scanner relay (runs on Ghost 178.104.27.211:8002). Forwards scan requests to Specter. |
| **backend/** | Core API (FastAPI). Auth, scans, findings, domains, reports, billing, Ask HAWK, agency, notifications. |
| **frontend/** | Next.js 14 app. Gate, onboarding, dashboard, settings. |

---

## Run locally (dev)

### 1. Specter scanner (optional if using Ghost relay to real Specter)

```bash
cd specter
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn specter_scanner:app --host 0.0.0.0 --port 8002
```

### 2. Scanner relay (Ghost)

Only needed if you’re not on Ghost. Point it at Specter (e.g. `HAWK_SPECTER_URL=http://10.0.0.2:8002` or `http://localhost:8002` for local Specter).

```bash
cd ghost
pip install -r requirements.txt
uvicorn scanner_relay:app --host 0.0.0.0 --port 8002
```

### 3. Backend API

```bash
cd backend
cp .env.example .env   # edit with real keys
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

Database: SQLite at `./hawk.db` by default. Set `DATABASE_URL` for PostgreSQL.

### 4. Frontend

```bash
cd frontend
cp .env.example .env.local
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" >> .env.local
npm install && npm run dev
```

Open http://localhost:3000.

---

## Cron (production)

Call these with **header** `X-Cron-Secret: <HAWK_CRON_SECRET>`.

| Endpoint | Schedule | Purpose |
|----------|----------|--------|
| `POST /api/cron/scheduled-scans` | e.g. daily | Run weekly/daily scans for domains that are due. |
| `POST /api/cron/trial-expiry` | daily | Email users whose trial ends tomorrow. |
| `POST /api/cron/weekly-digest` | weekly | Email digest (scan count, criticals) to users with recent scans. |
| `POST /api/cron/monthly-report` | monthly | Email "report ready" to users who have reports in the past 30 days. |

Example:

```bash
curl -X POST -H "X-Cron-Secret: YOUR_SECRET" https://your-api/api/cron/scheduled-scans
```

---

## Key env (backend)

See **backend/.env.example**. Main ones:

- `HAWK_SECRET_KEY` — JWT
- `DATABASE_URL` — SQLite or PostgreSQL
- `HAWK_SCANNER_RELAY_URL` — Ghost relay (default 178.104.27.211:8002)
- `STRIPE_*` — Billing
- `DEEPSEEK_API_KEY` — Ask HAWK
- `CHARLOTTE_*` — Transactional email (Revenue-Ops)
- `HAWK_CRON_SECRET` — Cron endpoints

---

## Plans

| Plan | Domains | Ask HAWK | PDFs | Notes |
|------|---------|----------|------|--------|
| Trial | 1 | 5 msgs | 0 | 7 days |
| Starter | 1 | unlimited | 1/mo | Weekly scans |
| Pro | 3 | unlimited | unlimited | Daily, PIPEDA/C-26 |
| Agency | 10 | unlimited | unlimited | White-label, client report, API |

---

## Auth

- **Forgot password:** User requests reset → backend creates 1h token, Charlotte sends email with link to `/reset-password?token=...` → user sets new password via `POST /api/auth/reset-password`.
- **Dashboard/onboarding** are protected by middleware (cookie `hawk_auth`). Login/register set the cookie; logout clears it.
