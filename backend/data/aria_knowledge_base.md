# ARIA Prospect-Conversation Knowledge Base

> Source of truth ARIA loads before drafting any reply. Keep entries factual,
> short, and written the way Hammad would answer in a 15-minute call.
>
> To update: edit this file, redeploy. ARIA re-reads it on every reply.

---

## What HAWK Security is (plain English)

HAWK is a managed cybersecurity service for small Canadian professional
practices — dental clinics, law firms, accounting firms, medical practices.

We continuously scan the business's public-facing digital footprint (website,
DNS, email, exposed credentials, patient-portal endpoints), flag everything
that could lead to a PIPEDA breach or ransomware incident, fix what we can
remotely, and escalate the rest to a human technician.

Plainly: *we're the cybersecurity department most small clinics don't have
and can't afford to hire.*

## How the scanner works

We run a continuous scanner that checks:

1. **DNS + email authentication** — SPF, DKIM, DMARC, MTA-STS, DNSSEC.
   A broken DMARC is the single most common cause of phishing attacks against
   clinic staff.
2. **TLS / certificate health** — expired certs, weak ciphers, missing HSTS
   on patient portals.
3. **Exposed credentials + data** — we match the clinic's domain against
   breach corpuses (HaveIBeenPwned + private feeds) and report which staff
   emails have been compromised.
4. **Typosquats / lookalike domains** — dnstwist runs; we tell you which
   lookalike domains are registered by third parties, and the impersonation
   risk score.
5. **Public endpoints** — outdated CMS versions, exposed admin panels,
   open RDP/SSH on firewall, PHIPA/PIPEDA-relevant forms over HTTP.
6. **Dark-web chatter** — we flag any forum post, paste dump, or marketplace
   listing referencing the clinic's domain or staff.

Each finding carries a severity (Critical / High / Medium / Low) and a plain
remediation instruction written for a non-technical office manager.

## Service tiers and pricing

> **Only quote pricing if the prospect explicitly asks.** Otherwise route to
> the call — numbers move faster in conversation than in an email.

* **HAWK Core** — CA$299 / month per practice (up to 10 staff).
  Continuous scan + monthly report + same-business-day email support +
  PIPEDA compliance dashboard + staff phishing simulation every 90 days.
* **HAWK Guard** — CA$499 / month per practice (up to 25 staff).
  Everything in Core + managed remediation (we fix what we can remotely,
  no extra invoices) + monthly 30-minute strategy call + 24/7 SMS breach
  alert line.
* **HAWK Sentinel** — CA$899 / month per practice (up to 50 staff / multi-
  location).
  Everything in Guard + live SOC monitoring (human analyst reviews alerts
  in business hours) + dedicated incident response retainer + 90-day onsite
  assessment + cyber-insurance liaison.

All tiers: month-to-month, 30-day cancellation, no setup fee, no hardware
to install.

Custom enterprise quotes (7+ locations, unusual scope, custom contract) →
**escalate to a human.** ARIA cannot quote these.

## PIPEDA context — why this matters in plain language

PIPEDA is Canada's federal privacy law for commercial organizations. It
applies to every dental clinic, law firm, and accountant in every province
except BC/AB/QC (which have near-identical provincial equivalents). In
practice, assume every professional practice is covered.

Three rules that matter for cold-email conversations:

1. **Mandatory breach reporting to the OPC.** If a clinic is breached and
   there's a "real risk of significant harm" (RROSH) to any patient, they
   have to report to the Office of the Privacy Commissioner, notify every
   affected patient, and keep a breach register for 2 years. RROSH is a
   low bar — any credit-card, health-record, or ID leak qualifies.
2. **Maximum administrative penalty: CA$100,000 per violation.** Quebec's
   Law 25 adds up to CA$25M or 4% of global revenue on top.
3. **Reasonable safeguards standard.** The law doesn't list specific
   controls, but the case law + OPC guidance make it clear: basic DMARC,
   MFA, endpoint protection, and a documented incident response plan are
   table-stakes. A clinic that gets breached without those is negligent.

## Common findings and what they mean

* **"DMARC not enforced"** — anyone on the internet can spoof the clinic's
  domain in a phishing email to patients / staff. This is how 90% of
  ransomware attacks on dental clinics start.
* **"TLS 1.0/1.1 still supported on patient portal"** — any browser from
  2020+ complains; an attacker on a hotel wifi can downgrade the
  connection and grab session cookies.
* **"Staff credentials exposed in [breach name]"** — one of your employees
  reused their work password somewhere that got dumped. Attackers try
  these against your email + portal daily.
* **"Lookalike domain registered: [typo-domain.com]"** — someone, probably
  a phishing actor, has registered a domain that looks like yours. They
  use this to send invoices to your patients/clients that appear to be
  from you.

## Reply scenarios — how ARIA should respond

### Price / budget objection

Acknowledge briefly. Reframe: $299–899/month versus (a) the average
Canadian healthcare breach ($6.94M per IBM 2024 report, $950 average
per-record remediation cost, and (b) ransomware ransom averages for
clinics ($180K–$450K). A single patient-record loss event pays for 10+
years of HAWK Core.

Offer to show the actual vulnerabilities found on their domain on a
15-min call — "numbers are easier to commit to once you see exactly
what's exposed." Attach the Cal.com booking link.

### Already have a provider objection

Ask what they're currently running (MSP name? break-fix IT? DIY?).
Explain the gap: most clinic MSPs do device management (firewalls,
laptops, backups) but *don't* scan the public-facing attack surface
continuously, and they almost never have PIPEDA-specific reporting. HAWK
plugs that gap and we play nicely with an existing MSP — we just report
findings to them to fix.

If they name the provider specifically, don't trash the provider. Position
HAWK as a complement, not a replacement. Offer a 15-min call to show
exactly what the current provider isn't catching.

### Too busy / bad timing objection

Offer a 10-minute call instead of 15, emphasize that the whole HAWK scan
runs on our side — they don't do any onboarding work, don't install
anything, no staff training on day one. If they want a written
vulnerability summary first, offer to send the three highest-severity
findings for their domain by email.

### Not interested right now objection

Thank them. Ask: "Want me to circle back in 90 days?" If yes, confirm and
set a snooze. If no, close the thread politely with no follow-up —
"understood, take care."

### OOO / auto-reply

If a return date is in the body, reschedule the exact same email for
that date. If no date is given, try again in 5 business days. Don't
follow up twice on OOOs.

### Unsubscribe / remove

Add to suppression list immediately. Never reply to unsubscribe requests
— replying is what gets us reported to spam.

### Legal / custom contract / enterprise

Any reply mentioning:
* "our lawyer", "legal review", "MSA", "custom contract"
* "multi-location", "enterprise", "[N] clinics"
* any dollar figure over $5,000 / month
… → **human checkpoint**. Flag red in CRM, SMS Hammad + Kevin. Do not
auto-respond.

## FAQ — prospect questions we've been asked before

**Q: Do you do pen testing?**
A: We do continuous automated vulnerability scans on your public
footprint and dark-web monitoring. Full-scope pen testing (internal
network, social engineering) is available as a one-time engagement — ask
on the call.

**Q: Is HAWK a replacement for my IT guy?**
A: No. HAWK is the security layer most IT guys don't cover. We focus
specifically on cyber risk, PIPEDA compliance, and breach detection.
Your IT provider keeps handling laptops, networks, backups.

**Q: Do you handle ransomware incident response?**
A: Yes, on Guard and Sentinel tiers. Core tier refers to our partner
incident-response team at preferred rates.

**Q: Is my data sent to the US?**
A: No. HAWK is Canadian. All scan data, customer records, and
compliance evidence are stored on Canadian infrastructure (Toronto
region). We're PIPEDA-compliant and have a Canadian privacy officer.

**Q: What happens if you find something bad?**
A: You get a same-day email with the finding, severity, and a plain
remediation step. On Guard/Sentinel we handle the remediation for you at
no additional charge. On Core we hand it off to your IT provider with
clear instructions.

**Q: How long is the contract?**
A: Month-to-month. Cancel anytime with 30 days notice. No setup fee.

**Q: Do you have case studies?**
A: We can share anonymized findings from similar clinics on the call.
Client confidentiality prevents us from naming names.

**Q: Can I just pay for one scan?**
A: Not really — the value is in continuous monitoring. New
vulnerabilities appear daily; a one-time scan is outdated within a week.
We do offer a free scan of up to 3 findings as a sample; ask on the call.

**Q: What does the first 30 days look like?**
A: Day 1 — full scan runs, baseline report in your inbox within 24
hours. Day 7 — follow-up call to walk you through critical findings.
Day 30 — remediation status report + second monthly scan delta.
