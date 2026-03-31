# HAWK Frontend

Next.js 14 (App Router), Tailwind, shadcn-style components, Framer Motion. Connects to the HAWK API for auth, scans, findings, reports, and billing.

## Run

```bash
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Set `NEXT_PUBLIC_API_URL` to your backend (default `http://localhost:8000`).

## Deploy (Vercel)

Set **Root Directory** to **`frontend`** (Project → Settings → General). The old `crm/` folder no longer exists; CRM routes are `frontend/app/crm/*`.

## Build

```bash
npm run build
npm start
```

## Pages

- **/** — Gate: domain scan input, animated terminal, lead capture modal
- **/login** — Log in / Sign up (query `?register=1`)
- **/forgot-password** — Password reset request
- **/onboarding** — 5-step flow: welcome → profile → domain → plan → done
- **/dashboard** — Overview (score, stats, recent activity)
- **/dashboard/findings** — Load scan by ID, filter by severity
- **/dashboard/history** — Scan history table
- **/dashboard/reports** — Generate PDF, list and download
- **/dashboard/domains** — Add/remove domains
- **/dashboard/hawk** — Ask HAWK: chat with scan context, DeepSeek R1 (trial: 5 messages)
- **/dashboard/compliance** — PIPEDA §4.7, Bill C-26 S.7, NIST mapping (Pro+)
- **/dashboard/agency** — Client list, ROI calculator, white-label report (Agency)
- **/dashboard/notifications** — Inbox, mark all read
- **/dashboard/settings** — Account, billing portal, upgrade buttons

## Design

- Background: `#07060C`, surfaces `#0D0B14`–`#1A1727`, accent `#7B5CF5`
- Fonts: DM Sans (stand-in for Cabinet Grotesk), JetBrains Mono for code
- Dark, minimal, sharp borders; micro-animations via Framer Motion
