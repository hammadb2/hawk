# HAWK

B2B cybersecurity SaaS for US SMBs. External attack-surface scans, findings dashboard, Ask HAWK (AI), compliance mapping, and billing.

**Domain:** securedbyhawk.com · **Company:** [Hawk Security](https://securedbyhawk.com)

---

## Repo layout

| Path | Purpose |
|------|--------|
| **hawk-pulse/** | **HAWK 3.0 Pulse Engine (CTEM).** Event-driven continuous monitoring: certstream CT listener, micro-scanner, state diffing, WebSocket alerts. |
| **hawk-scanner-v2/** | Scanner v2 pipeline (subfinder, naabu, httpx, nuclei, breach monitoring). Core tool wrappers reused by Pulse. |
| **backend/** | Core API (FastAPI). Auth, scans, findings, domains, reports, billing, Ask HAWK, agency, notifications. |
| **frontend/** | Next.js app. Gate, onboarding, main dashboard, and **CRM** at `/crm/*`. |
| **supabase/** | SQL migrations for CRM (Supabase: prospects, RLS, commissions, scoreboard, tickets). |
| **_archive/** | Archived legacy scanner (Specter engine + Ghost relay). No longer maintained. |

### Vercel (frontend)

The Next.js app lives under **`frontend/`**, not `crm/`. In the Vercel project: **Settings → General → Root Directory** → set to **`frontend`** (remove `crm`). Save and redeploy.

---

## Run locally (dev)

### 1. HAWK Pulse Engine (v3.0 — CTEM)

```bash
cd hawk-pulse
docker compose up -d          # starts Postgres + Pulse on :8080
# OR run locally:
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

See `hawk-pulse/README.md` for full API docs and WebSocket usage.

### 2. Backend API

```bash
cd backend
cp .env.example .env   # edit with real keys
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

Database: SQLite at `./hawk.db` by default. Set `DATABASE_URL` for PostgreSQL.

### 3. Frontend

```bash
cd frontend
cp .env.example .env.local
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" >> .env.local
npm install && npm run dev
```

Open http://localhost:3000.

---

## Cron (production)

Call these with **header** `X-Cron-Secret: <secret>`. The secret is read from `HAWK_CRON_SECRET`, or **`CRON_SECRET`** (e.g. on Railway) if the former is unset.

| Endpoint | Schedule | Purpose |
|----------|----------|--------|
| `POST /api/cron/scheduled-scans` | e.g. daily | Run weekly/daily scans for domains that are due. |
| `POST /api/cron/trial-expiry` | daily | Legacy no-op — no expiry emails sent. |
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
- `HAWK_SCANNER_RELAY_URL` — Scanner v2 relay URL (Railway deployment)
- `STRIPE_*` — Billing
- `OPENAI_API_KEY`, `OPENAI_MODEL` — Ask HAWK, portal AI, ARIA drafts, scanner interpretation (when API hosts those features)
- `TRANSACTIONAL_EMAIL_WEBHOOK_URL`, `TRANSACTIONAL_EMAIL_API_KEY` — optional relay for welcome / password-reset / digest emails
- `HAWK_CRON_SECRET` or `CRON_SECRET` — Cron endpoints (same header value)
- `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `CRM_EMAIL_WEBHOOK_SECRET` — CRM webhooks (backend only)
- `SMARTLEAD_API_KEY` — optional; ARIA / Smartlead dispatch when enabled

---

## Plans

| Plan | Domains | Ask HAWK | PDFs | Notes |
|------|---------|----------|------|--------|
| Starter | 1 | unlimited | 1/mo | Weekly scans |
| Pro | 3 | unlimited | unlimited | Daily, HIPAA/FTC compliance |
| Agency | 10 | unlimited | unlimited | White-label, client report, API |

---

## Auth

- **Forgot password:** User requests reset → backend creates 1h token, transactional email relay (if configured) sends a link to `/reset-password?token=...` → user sets new password via `POST /api/auth/reset-password`.
- **Dashboard/onboarding** are protected by middleware (cookie `hawk_auth`). Login/register set the cookie; logout clears it.
