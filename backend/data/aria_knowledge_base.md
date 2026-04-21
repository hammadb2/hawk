# ARIA Prospect-Conversation Knowledge Base

> Source of truth ARIA loads before drafting any reply. Keep entries factual,
> short, and written the way Hammad would answer in a 15-minute call.
>
> To update: edit this file, redeploy. ARIA re-reads it on every reply.

---

## What HAWK Security is (plain English)

HAWK is a managed cybersecurity service for small US professional
practices — dental clinics, law firms, accounting / CPA firms, medical
practices.

We continuously scan the business's public-facing digital footprint (website,
DNS, email, exposed credentials, patient / client-portal endpoints), flag
everything that could lead to a HIPAA / GLBA / state-AG-reportable breach or
ransomware incident, fix what we can remotely, and escalate the rest to a
human technician.

Plainly: *we're the cybersecurity department most small practices don't have
and can't afford to hire.*

## How the scanner works

We run a continuous scanner that checks:

1. **DNS + email authentication** — SPF, DKIM, DMARC, MTA-STS, DNSSEC.
   A broken DMARC is the single most common cause of phishing attacks against
   practice staff.
2. **TLS / certificate health** — expired certs, weak ciphers, missing HSTS
   on patient / client portals.
3. **Exposed credentials + data** — we match the practice's domain against
   breach corpuses (HaveIBeenPwned + private feeds) and report which staff
   emails have been compromised.
4. **Typosquats / lookalike domains** — dnstwist runs; we tell you which
   lookalike domains are registered by third parties, and the impersonation
   risk score.
5. **Public endpoints** — outdated CMS versions, exposed admin panels,
   open RDP/SSH on firewall, HIPAA / FTC-Safeguards-relevant forms over HTTP.
6. **Dark-web chatter** — we flag any forum post, paste dump, or marketplace
   listing referencing the practice's domain or staff.

Each finding carries a severity (Critical / High / Medium / Low) and a plain
remediation instruction written for a non-technical office manager.

## Service tiers and pricing

> **Only quote pricing if the prospect explicitly asks.** Otherwise route to
> the call — numbers move faster in conversation than in an email.

All pricing is **USD**, month-to-month, 30-day cancellation, no setup fee,
no hardware to install.

* **HAWK Core** — **$249 / month** per practice (up to 10 staff).
  Continuous scan + monthly report + same-business-day email support +
  compliance dashboard (HIPAA for dental/medical, FTC Safeguards WISP for
  CPAs, ABA Opinion 2024-3 client-notification workflow for legal) + staff
  phishing simulation every 90 days. Includes the **$250,000 Breach Response
  Guarantee**.
* **HAWK Guard** — **$449 / month** per practice (up to 25 staff).
  Everything in Core + managed remediation (we fix what we can remotely,
  no extra invoices) + monthly 30-minute strategy call + 24/7 SMS breach
  alert line + **$1,000,000 Breach Response Guarantee** + Insurance Renewal
  Pack (MFA / EDR / WISP attestation PDF that qualifies you for 20–50%
  cyber-insurance premium discounts).
* **HAWK Sentinel** — **$799 / month** per practice (up to 50 staff / multi-
  location).
  Everything in Guard + live SOC monitoring (human analyst reviews alerts
  in business hours) + dedicated incident response retainer + 90-day onsite
  assessment + cyber-insurance liaison + **$2,500,000 Breach Response
  Guarantee**.

Custom enterprise quotes (7+ locations, unusual scope, custom contract) →
**escalate to a human.** ARIA cannot quote these.

## US regulatory context — why this matters, in plain language

The US has **three** laws driving small-practice breach exposure right now.
Match the vertical to the right one:

### 1. HIPAA (dental + medical)

Every dental practice that bills insurance, accepts patient records
electronically, or uses a cloud EHR is a "covered entity" under HIPAA.

- **Breach notification is mandatory.** Any breach of unsecured PHI must be
  reported to HHS OCR and every affected patient within 60 days. Breaches
  affecting 500+ individuals hit the OCR "Wall of Shame" and major media.
- **Civil monetary penalties: up to $2.1M per violation category per year.**
  OCR hit its 50th HIPAA enforcement of 2024 in October; Westend Dental
  paid **$350,000** in December 2024 over a ransomware incident + patient-
  notification failure. Enforcement tempo is the highest it has ever been.
- **The HIPAA Security Rule** requires MFA, access logging, encryption of
  PHI at rest and in transit, written risk analysis, and a documented
  incident response plan. A practice breached without those is assumed
  negligent.

### 2. FTC Safeguards Rule (CPA / accounting / tax prep)

The amended FTC Safeguards Rule (effective June 2023, with the **breach
notification amendment taking effect May 13, 2024**) applies to every CPA
firm, bookkeeper, and tax preparer that handles client financial data.

- **30-day breach notification to the FTC** for any incident affecting
  500+ consumers' unencrypted data.
- **Required written information security program (WISP).** Must cover:
  MFA on all client-data access, continuous monitoring / EDR, encryption,
  qualified individual (CISO-equivalent), access controls, incident
  response plan, annual penetration testing or vulnerability assessment,
  and **external attack surface monitoring** (EASM — which is exactly what
  HAWK does).
- **State AG overlay.** Every state has its own data-breach notification
  law on top of the federal rule; CA, NY, IL, MA, TX, CO have the sharpest
  teeth. Multi-state breaches multiply notification obligations.
- **Cyber-insurance linkage.** Carriers now require WISP attestations and
  external-scan evidence at renewal. HAWK's Insurance Renewal Pack is built
  exactly for this.

### 3. ABA Formal Opinion 24-514 / state variants (legal)

ABA Standing Committee's **Formal Opinion 24-514** (2024) re-affirmed that
lawyers have an **ethical duty under Model Rules 1.1 (competence), 1.4
(communication), and 1.6 (confidentiality)** to notify clients of any
material data incident that could affect representation.

- Most state bars (CA, NY, IL, FL, TX, MA, NJ) have adopted or are
  actively enforcing parallel opinions. Failure to notify is **malpractice
  exposure** — courts and bar associations treat it as a breach of
  fiduciary duty, not just a regulatory slap.
- On top of ABA / state bar: every state's data-breach notification law
  applies to client PII held by the firm. Financial settlements, SSNs,
  estate records, medical records held on behalf of clients all qualify.
- Client-trust accounts + matter management portals are the highest-value
  targets. Wire-fraud diversion on real estate closings is the single
  most common loss driver; HAWK's lookalike-domain + DMARC monitoring
  catches the precursors.

## Common findings and what they mean

* **"DMARC not enforced"** — anyone on the internet can spoof the practice's
  domain in a phishing email to patients / clients / staff. This is how 90%
  of ransomware attacks on small practices start. For law firms this is
  also the #1 precursor to wire-fraud diversion on real-estate closings.
* **"TLS 1.0/1.1 still supported on patient / client portal"** — any
  browser from 2020+ complains; an attacker on a hotel wifi can downgrade
  the connection and grab session cookies.
* **"Staff credentials exposed in [breach name]"** — one of your employees
  reused their work password somewhere that got dumped. Attackers try
  these against your email + portal daily.
* **"Lookalike domain registered: [typo-domain.com]"** — someone, probably
  a phishing actor, has registered a domain that looks like yours. They
  use this to send invoices to your patients/clients that appear to be
  from you.

## Reply scenarios — how ARIA should respond

### Price / budget objection

Acknowledge briefly. Reframe: $249–799/month versus the actual cost of a
breach in their vertical:

- **Dental / medical:** IBM 2024 healthcare breach cost averages **$9.77M**
  per incident; per-record remediation $408; HIPAA OCR settlements now
  averaging $120K–$1.5M per dental/medical SMB. Ransom demands on dental
  clinics averaged $180K–$450K in 2024.
- **CPA / tax:** FTC Safeguards enforcement actions now reach $500K+;
  average tax-prep breach triggers 6–8 state AG notifications and
  $300K–$900K in legal + notification costs alone.
- **Legal:** wire-fraud diversion on a single real-estate closing averages
  $250K–$500K lost. Malpractice-insurance deductibles typically $25K–$100K
  per claim. Client-trust-account breaches have ended firms.

A single loss event pays for 10+ years of HAWK Core. The Breach Response
Guarantee ($250K–$2.5M depending on tier) underwrites exactly this risk.

Offer to show the actual vulnerabilities found on their domain on a
15-min call — "numbers are easier to commit to once you see exactly
what's exposed." Attach the Cal.com booking link.

### Already have a provider objection

Ask what they're currently running (MSP name? break-fix IT? DIY?).
Explain the gap: most SMB MSPs do device management (firewalls, laptops,
backups) but *don't* scan the public-facing attack surface continuously,
and they almost never produce the **evidence artifacts** (WISP, MFA
attestation, EASM scan log) that HIPAA / FTC Safeguards / state bar
opinions now expect at audit or cyber-insurance renewal. HAWK plugs that
gap and we play nicely with an existing MSP — we just report findings to
them to fix.

If they name the provider specifically, don't trash the provider. Position
HAWK as a complement, not a replacement. Offer a 15-min call to show
exactly what the current provider isn't catching.

### Too busy / bad timing objection

Offer a 10-minute call instead of 15, emphasize that the whole HAWK scan
runs on our side — they don't do any onboarding work, don't install
anything, no staff training on day one. If they want a written
vulnerability summary first, offer to send the three highest-severity
findings for their domain by email (this is our free-scan hook).

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
— replying is what gets us reported to spam. Per CAN-SPAM, honor all
opt-out requests within 10 business days.

### Legal / custom contract / enterprise

Any reply mentioning:
* "our lawyer", "legal review", "MSA", "custom contract"
* "multi-location", "enterprise", "[N] offices / clinics / locations"
* any dollar figure over $5,000 / month
… → **human checkpoint**. Flag red in CRM, SMS Hammad + Kevin. Do not
auto-respond.

## FAQ — prospect questions we've been asked before

**Q: Do you do pen testing?**
A: We do continuous automated vulnerability scans on your public
footprint and dark-web monitoring. Full-scope pen testing (internal
network, social engineering) is available as a one-time engagement — ask
on the call. Our EASM output satisfies the FTC Safeguards Rule's annual
vulnerability-assessment requirement for CPA firms.

**Q: Is HAWK a replacement for my IT guy?**
A: No. HAWK is the security layer most IT guys don't cover. We focus
specifically on cyber risk, regulatory compliance (HIPAA / FTC Safeguards /
ABA client-notification workflow depending on vertical), and breach
detection. Your IT provider keeps handling laptops, networks, backups.

**Q: Do you handle ransomware incident response?**
A: Yes, on Guard and Sentinel tiers. Core tier refers to our partner
incident-response team at preferred rates. All tiers include the Breach
Response Guarantee — $250K (Core), $1M (Guard), or $2.5M (Sentinel) — to
underwrite first-party breach costs while response is underway.

**Q: Where is my data stored?**
A: All scan data, customer records, and compliance evidence are stored on
US-region infrastructure (AWS us-east-1 and us-west-2 with a hot-standby
pair). We produce the residency + encryption attestations that HIPAA
Business Associate Agreements and FTC Safeguards auditors ask for.

**Q: Will you sign a Business Associate Agreement (HIPAA)?**
A: Yes. All dental / medical Guard and Sentinel tiers include a standard
HIPAA BAA at no additional cost. Core tier available on request.

**Q: Can you help at cyber-insurance renewal?**
A: Yes — Guard and Sentinel tiers include the **Insurance Renewal Pack**:
a dated PDF attestation covering MFA, EDR, WISP, encryption, and EASM
scan evidence. Clients using this pack have reported 20–50% premium
reductions or, in several cases, moving from denied-renewal to accepted.

**Q: What happens if you find something bad?**
A: You get a same-day email with the finding, severity, and a plain
remediation step. On Guard/Sentinel we handle the remediation for you at
no additional charge. On Core we hand it off to your IT provider with
clear instructions.

**Q: How long is the contract?**
A: Month-to-month. Cancel anytime with 30 days notice. No setup fee.

**Q: Do you have case studies?**
A: We can share anonymized findings from similar practices on the call.
Client confidentiality prevents us from naming names.

**Q: Can I just pay for one scan?**
A: Not really — the value is in continuous monitoring. New
vulnerabilities appear daily; a one-time scan is outdated within a week.
We do offer a **free 3-finding scan** at securedbyhawk.com — enter the
domain, we email the report within 24 hours. Ask on the call for the
full picture.

**Q: What does the first 30 days look like?**
A: Day 1 — full scan runs, baseline report in your inbox within 24
hours. Day 7 — follow-up call to walk you through critical findings.
Day 30 — remediation status report + second monthly scan delta, plus
your vertical-specific compliance artifact (HIPAA risk analysis / FTC
Safeguards WISP / ABA-aligned client-notification workbook).
