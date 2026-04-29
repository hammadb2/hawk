"use client";

import Link from "next/link";
import { motion } from "framer-motion";
import { HeroScan } from "@/components/marketing/hero-scan";
import { SmoothScroll } from "@/components/marketing/smooth-scroll";

const ENTERPRISE_BOOKING =
  process.env.NEXT_PUBLIC_CAL_COM_BOOKING_URL || "https://cal.com/hawksecurity/15min";

/**
 * Marketing home. Premium dark canvas, graphite surfaces, signal amber accent.
 * Scoped to html.marketing-route via <SmoothScroll /> so the portal/CRM stays light.
 */
export function MarketingHome() {
  return (
    <div className="relative min-h-dvh w-full overflow-x-hidden bg-ink-950 font-display text-ink-0 antialiased selection:bg-signal/40 selection:text-ink-950">
      <SmoothScroll />

      {/* Ambient amber glow behind the top of the page */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-[720px] bg-ink-vignette"
      />
      <div aria-hidden className="pointer-events-none absolute inset-0 grid-ink" />
      <div aria-hidden className="noise-overlay" />

      <MarketingNav />

      <main className="relative z-10">
        <HeroSection />
        <RegulatorySection />
        <HowItWorks />
        <GuaranteeSection />
        <HawkCertified />
        <PricingSection />
        <FinalCTA />
      </main>

      <MarketingFooter />
    </div>
  );
}

/* ============================== NAV ============================== */

function MarketingNav() {
  return (
    <header className="sticky top-0 z-40 border-b border-white/5 bg-ink-950/70 backdrop-blur-xl">
      <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6 sm:px-8">
        <Link href="/" className="group inline-flex items-center" title="HAWK">
          <img src="/hawk-logo.png" alt="HAWK" className="h-10 w-auto" />
        </Link>
        <nav className="hidden items-center gap-8 md:flex">
          <a href="#regulatory" className="text-sm text-ink-100 transition-colors hover:text-ink-0">
            Regulatory
          </a>
          <a href="#how" className="text-sm text-ink-100 transition-colors hover:text-ink-0">
            How it works
          </a>
          <a href="#guarantee" className="text-sm text-ink-100 transition-colors hover:text-ink-0">
            Guarantee
          </a>
          <a href="#pricing" className="text-sm text-ink-100 transition-colors hover:text-ink-0">
            Pricing
          </a>
          <a href="#certified" className="text-sm text-ink-100 transition-colors hover:text-ink-0">
            Certification
          </a>
        </nav>
        <div className="flex items-center gap-2">
          <Link
            href="/portal/login"
            className="hidden text-sm font-medium text-ink-100 transition-colors hover:text-ink-0 sm:inline-flex"
          >
            Log in
          </Link>
          <a
            href="#scan"
            className="inline-flex items-center gap-1.5 rounded-full bg-signal px-4 py-2 text-sm font-semibold text-ink-950 shadow-signal-sm transition-colors hover:bg-signal-400"
          >
            Free scan
          </a>
        </div>
      </div>
    </header>
  );
}

/* ============================== HERO ============================== */

function HeroSection() {
  return (
    <section id="scan" className="relative scroll-mt-24 px-6 pb-24 pt-16 sm:px-8 sm:pb-32 sm:pt-24">
      <div className="mx-auto grid max-w-7xl items-center gap-14 lg:grid-cols-[1.15fr_1fr] lg:gap-20">
        <motion.div
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          className="max-w-2xl"
        >
          <span className="text-eyebrow inline-flex items-center gap-2 text-signal">
            <span className="h-1.5 w-1.5 rounded-full bg-signal" />
            Cybersecurity. Built for regulated practices.
          </span>
          <h1 className="mt-6 text-display-xl text-balance text-ink-0">
            Cybersecurity for{" "}
            <span className="gradient-signal">dental, legal, and CPA</span>{" "}
            practices.
          </h1>
          <p className="mt-6 max-w-xl text-pretty text-lg leading-relaxed text-ink-100 sm:text-xl">
            HIPAA. FTC Safeguards. ABA 2024 cyber ethics. Continuous external monitoring with a
            breach response guarantee up to $2.5M in writing at signup.
          </p>
          <p className="mt-4 text-sm text-ink-200">
            Enter your domain. Watch the same signals ransomware affiliates harvest, before they ever
            contact you.
          </p>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 22, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.8, delay: 0.15, ease: [0.22, 1, 0.36, 1] }}
          className="relative flex justify-center lg:justify-end"
        >
          <HeroScan />
        </motion.div>
      </div>

      {/* Trust bar */}
      <motion.div
        initial={{ opacity: 0, y: 12 }}
        whileInView={{ opacity: 1, y: 0 }}
        viewport={{ once: true, amount: 0.6 }}
        transition={{ duration: 0.6, delay: 0.25 }}
        className="mx-auto mt-20 grid max-w-5xl grid-cols-2 gap-x-6 gap-y-6 border-t border-white/5 pt-8 text-center sm:grid-cols-4 sm:gap-10"
      >
        <TrustStat label="Response SLA" value="Under 5 min" />
        <TrustStat label="Guarantee ceiling" value="$2.5M" />
        <TrustStat label="Scan coverage" value="500+ checks" />
        <TrustStat label="Certification" value="90 day path" />
      </motion.div>
    </section>
  );
}

function TrustStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="font-display text-xl font-semibold tracking-tight text-ink-0 sm:text-2xl">
        {value}
      </p>
      <p className="mt-1 text-xs font-medium uppercase tracking-[0.18em] text-ink-300">{label}</p>
    </div>
  );
}

/* ========================== REGULATORY ========================== */

const REGULATORY: Array<{
  tag: string;
  vertical: string;
  rule: string;
  body: string;
  citation: string;
}> = [
  {
    tag: "Dental and medical",
    vertical: "Dental practices",
    rule: "HIPAA Security Rule",
    body: "Patient records require continuous technical safeguards. We map your external attack surface to 164.308 administrative and 164.312 technical controls every day, not once a year.",
    citation: "45 CFR 164",
  },
  {
    tag: "Law firms",
    vertical: "Law firms",
    rule: "ABA 2024 Cyber Ethics",
    body: "The 2024 Formal Opinion requires reasonable efforts to monitor for incidents. Continuous monitoring, plain English reports, and an auditable trail your insurer and bar can see.",
    citation: "ABA 2024 Opinion",
  },
  {
    tag: "CPA and tax",
    vertical: "CPA and tax firms",
    rule: "FTC Safeguards Rule",
    body: "The amended Rule requires a written plan, annual risk assessment, and ongoing monitoring. We deliver the monitoring layer plus the evidence you need at renewal.",
    citation: "16 CFR 314",
  },
];

function RegulatorySection() {
  return (
    <section id="regulatory" className="relative scroll-mt-24 px-6 py-24 sm:px-8 sm:py-32">
      <div className="mx-auto max-w-7xl">
        <SectionHeading
          eyebrow="Regulatory posture"
          title="Built for the rules that actually apply to your practice."
          subtitle="Three professions. Three hard regulatory triggers. One platform that treats compliance as a product surface, not a PDF."
        />

        <div className="mt-16 grid gap-6 md:grid-cols-3">
          {REGULATORY.map((r, i) => (
            <motion.article
              key={r.rule}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.3 }}
              transition={{ duration: 0.55, delay: i * 0.08, ease: [0.22, 1, 0.36, 1] }}
              className="group relative overflow-hidden rounded-2xl border border-white/5 bg-ink-800/60 p-7 transition-colors hover:border-signal/30"
            >
              <div
                aria-hidden
                className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-signal/60 to-transparent opacity-0 transition-opacity group-hover:opacity-100"
              />
              <p className="text-eyebrow text-signal">{r.tag}</p>
              <h3 className="mt-5 font-display text-2xl font-semibold tracking-tight text-ink-0">
                {r.rule}
              </h3>
              <p className="mt-3 text-sm leading-relaxed text-ink-100">{r.body}</p>
              <p className="mt-7 font-mono text-[11px] uppercase tracking-widest text-ink-300">
                {r.citation}
              </p>
            </motion.article>
          ))}
        </div>
      </div>
    </section>
  );
}

/* ========================== HOW IT WORKS ========================== */

const STEPS = [
  {
    step: "01",
    title: "We scan.",
    body: "External probe of every hostname, port, cert, email record, and leaked credential tied to your domain. Depth that maps to the Rule, not a marketing checklist.",
  },
  {
    step: "02",
    title: "We monitor.",
    body: "Continuous coverage. The moment a cert expires, a service drifts open, or credentials surface on a stealer dump, you hear about it. Not next quarter.",
  },
  {
    step: "03",
    title: "You fix.",
    body: "Every finding ships with a plain English remediation. Your IT contact follows the steps. We verify the fix and close the loop, on the record.",
  },
  {
    step: "04",
    title: "You get certified.",
    body: "90 days of clean monitoring earns HAWK Certified status. Embeddable badge, public verification page, and a posture certificate your clients can actually check.",
  },
];

function HowItWorks() {
  return (
    <section id="how" className="relative scroll-mt-24 border-y border-white/5 bg-ink-900/40 px-6 py-24 sm:px-8 sm:py-32">
      <div className="mx-auto max-w-7xl">
        <SectionHeading
          eyebrow="How it works"
          title="Four steps. Every one of them a product, not a promise."
        />
        <ol className="mt-16 grid gap-6 md:grid-cols-2 lg:grid-cols-4">
          {STEPS.map((s, i) => (
            <motion.li
              key={s.step}
              initial={{ opacity: 0, y: 24 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.3 }}
              transition={{ duration: 0.55, delay: i * 0.08, ease: [0.22, 1, 0.36, 1] }}
              className="relative rounded-2xl border border-white/5 bg-ink-800/50 p-7"
            >
              <span className="font-mono text-xs font-semibold tracking-widest text-signal">{s.step}</span>
              <h3 className="mt-4 font-display text-xl font-semibold tracking-tight text-ink-0">
                {s.title}
              </h3>
              <p className="mt-3 text-sm leading-relaxed text-ink-100">{s.body}</p>
            </motion.li>
          ))}
        </ol>
      </div>
    </section>
  );
}

/* ========================== GUARANTEE ========================== */

const GUARANTEE_TIERS = [
  { tier: "Core", ceiling: "$250,000", sub: "HAWK Core" },
  { tier: "Guard", ceiling: "$1,000,000", sub: "HAWK Guard" },
  { tier: "Sentinel", ceiling: "$2,500,000", sub: "HAWK Sentinel" },
];

function GuaranteeSection() {
  return (
    <section id="guarantee" className="relative scroll-mt-24 px-6 py-24 sm:px-8 sm:py-32">
      <div className="mx-auto max-w-7xl">
        <SectionHeading
          eyebrow="Breach response guarantee"
          title="We stand behind the work in writing."
          subtitle="If you follow our recommendations and your external surface is breached, we cover your incident response costs up to your plan ceiling. Signed at signup. No arbitration games."
        />

        <div className="mt-16 grid gap-5 md:grid-cols-3">
          {GUARANTEE_TIERS.map((g, i) => (
            <motion.div
              key={g.tier}
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.4 }}
              transition={{ duration: 0.6, delay: i * 0.1, ease: [0.22, 1, 0.36, 1] }}
              className="relative overflow-hidden rounded-2xl border border-white/5 bg-ink-800/55 p-8"
            >
              <p className="text-eyebrow text-ink-300">{g.sub}</p>
              <p className="mt-4 font-display text-5xl font-bold tracking-tighter text-ink-0 sm:text-[3.75rem]">
                {g.ceiling}
              </p>
              <p className="mt-2 text-sm text-ink-100">Breach response ceiling</p>
              <div
                aria-hidden
                className="pointer-events-none absolute inset-x-0 bottom-0 h-px bg-gradient-to-r from-transparent via-signal/40 to-transparent"
              />
            </motion.div>
          ))}
        </div>

        <div className="mt-10 text-center">
          <Link
            href="/guarantee-terms"
            className="inline-flex items-center gap-2 font-medium text-signal transition-colors hover:text-signal-300"
          >
            Read the full guarantee terms
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
              <path d="M5 12h14m0 0l-6-6m6 6l-6 6" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </Link>
        </div>
      </div>
    </section>
  );
}

/* ========================== HAWK CERTIFIED ========================== */

function HawkCertified() {
  return (
    <section
      id="certified"
      className="relative scroll-mt-24 overflow-hidden border-y border-white/5 bg-ink-900/40 px-6 py-24 sm:px-8 sm:py-32"
    >
      <div className="mx-auto grid max-w-7xl items-center gap-16 lg:grid-cols-2 lg:gap-24">
        <div>
          <SectionHeading
            eyebrow="HAWK Certified"
            title="Proof your clients can verify."
            align="left"
          />
          <p className="mt-6 max-w-xl text-lg leading-relaxed text-ink-100">
            After 90 days of clean continuous monitoring, your practice earns HAWK Certified status.
            You get an embeddable badge, a public verification page, and a signed posture certificate
            your clients and insurer can actually check.
          </p>
          <ul className="mt-8 space-y-3 text-sm text-ink-100">
            <Bullet>Dental clinics post it in the waiting room.</Bullet>
            <Bullet>Law firms embed it in client intake and engagement letters.</Bullet>
            <Bullet>CPA firms include it on proposals and insurance renewal packets.</Bullet>
          </ul>
        </div>

        <motion.div
          initial={{ opacity: 0, scale: 0.96 }}
          whileInView={{ opacity: 1, scale: 1 }}
          viewport={{ once: true, amount: 0.4 }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          className="relative mx-auto w-full max-w-md"
        >
          <div aria-hidden className="absolute inset-[-32px] rounded-[40px] bg-signal/5 blur-3xl" />
          <div className="relative overflow-hidden rounded-3xl border border-white/10 bg-ink-800/80 p-8 shadow-ink backdrop-blur">
            <div className="absolute inset-x-0 top-0 h-1 bg-signal" />
            <div className="flex items-start gap-5">
              <span className="inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-signal/15 text-signal">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden>
                  <path
                    d="M12 3l8 4v6a9 9 0 0 1-16 0V7l8-4z"
                    stroke="currentColor"
                    strokeWidth="1.8"
                    strokeLinejoin="round"
                  />
                  <path d="M8.5 12l2.5 2.5L16 9" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </span>
              <div>
                <p className="text-eyebrow text-ink-300">Verified posture</p>
                <p className="mt-2 font-display text-3xl font-bold tracking-tight text-ink-0">
                  HAWK Certified
                </p>
                <p className="mt-1 text-sm text-ink-100">90 day clean monitoring window</p>
              </div>
            </div>
            <div className="mt-8 rounded-xl border border-white/10 bg-ink-900/80 px-4 py-3 font-mono text-xs text-ink-100">
              securedbyhawk.com/verify/your-practice
            </div>
            <div className="mt-4 flex items-center gap-2 text-xs text-ink-200">
              <span className="inline-flex h-1.5 w-1.5 rounded-full bg-signal" />
              Signed posture certificate. Embeddable badge. Public verification URL.
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  );
}

function Bullet({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex items-start gap-3">
      <span className="mt-1.5 inline-flex h-1.5 w-1.5 shrink-0 rounded-full bg-signal" />
      <span>{children}</span>
    </li>
  );
}

/* ========================== PRICING ========================== */

const PLANS: Array<{
  name: string;
  tagline: string;
  price: string;
  period: string;
  cta: { label: string; href: string; style: "primary" | "ghost" };
  highlights: string[];
  featured?: boolean;
}> = [
  {
    name: "HAWK Core",
    tagline: "For solo and small practices.",
    price: "$249",
    period: "per month",
    cta: { label: "Start Core", href: `/portal/login?next=${encodeURIComponent("/portal/billing?plan=starter")}`, style: "ghost" },
    highlights: [
      "Daily external scan",
      "Plain English monthly report",
      "Critical and high finding alerts",
      "$250K breach response guarantee",
    ],
  },
  {
    name: "HAWK Guard",
    tagline: "For growing multi seat practices.",
    price: "$449",
    period: "per month",
    cta: { label: "Start Guard", href: `/portal/login?next=${encodeURIComponent("/portal/billing?plan=shield")}`, style: "primary" },
    highlights: [
      "Everything in Core",
      "Weekly posture report",
      "Insurance renewal evidence pack",
      "$1M breach response guarantee",
    ],
    featured: true,
  },
  {
    name: "HAWK Sentinel",
    tagline: "For large firms and multi location groups.",
    price: "$799",
    period: "per month",
    cta: { label: "Book Sentinel intro", href: ENTERPRISE_BOOKING, style: "ghost" },
    highlights: [
      "Everything in Guard",
      "24/7 monitoring and named analyst",
      "Quarterly tabletop exercise",
      "$2.5M breach response guarantee",
    ],
  },
];

function PricingSection() {
  return (
    <section id="pricing" className="relative scroll-mt-24 px-6 py-24 sm:px-8 sm:py-32">
      <div className="mx-auto max-w-7xl">
        <SectionHeading
          eyebrow="Pricing"
          title="Three tiers. USD. No setup fees."
          subtitle="Every tier includes continuous monitoring, remediation guidance, the certification path, and a breach response guarantee."
        />

        <div className="mt-16 grid gap-6 md:grid-cols-3">
          {PLANS.map((p) => (
            <article
              key={p.name}
              className={`relative flex flex-col overflow-hidden rounded-2xl border p-7 sm:p-8 ${
                p.featured
                  ? "border-signal/40 bg-gradient-to-b from-ink-800/80 to-ink-900/80 shadow-signal"
                  : "border-white/5 bg-ink-800/55"
              }`}
            >
              {p.featured && (
                <span className="absolute right-6 top-6 inline-flex rounded-full bg-signal/15 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-widest text-signal">
                  Most picked
                </span>
              )}
              <div>
                <p className="font-display text-xl font-semibold text-ink-0">{p.name}</p>
                <p className="mt-1 text-sm text-ink-200">{p.tagline}</p>
              </div>
              <div className="mt-8 flex items-baseline gap-1">
                <span className="font-display text-5xl font-bold tracking-tighter text-ink-0">{p.price}</span>
                <span className="text-sm text-ink-200">{p.period}</span>
              </div>
              <ul className="mt-6 space-y-3 text-sm text-ink-100">
                {p.highlights.map((h) => (
                  <li key={h} className="flex items-start gap-2.5">
                    <CheckGlyph />
                    <span>{h}</span>
                  </li>
                ))}
              </ul>
              <div className="mt-8 pt-2">
                {p.cta.style === "primary" ? (
                  <Link
                    href={p.cta.href}
                    className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-signal px-5 py-3 text-sm font-semibold text-ink-950 shadow-signal-sm transition-colors hover:bg-signal-400"
                  >
                    {p.cta.label}
                  </Link>
                ) : p.cta.href.startsWith("http") ? (
                  <a
                    href={p.cta.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-white/15 bg-ink-900 px-5 py-3 text-sm font-semibold text-ink-0 transition-colors hover:border-white/30"
                  >
                    {p.cta.label}
                  </a>
                ) : (
                  <Link
                    href={p.cta.href}
                    className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-white/15 bg-ink-900 px-5 py-3 text-sm font-semibold text-ink-0 transition-colors hover:border-white/30"
                  >
                    {p.cta.label}
                  </Link>
                )}
              </div>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}

function CheckGlyph() {
  return (
    <svg width="14" height="14" viewBox="0 0 20 20" fill="none" className="mt-0.5 shrink-0 text-signal" aria-hidden>
      <path d="M4 10.5l4 4 8-9" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/* ========================== FINAL CTA ========================== */

function FinalCTA() {
  return (
    <section className="relative px-6 py-28 sm:px-8 sm:py-36">
      <div aria-hidden className="pointer-events-none absolute inset-x-10 top-0 h-px bg-gradient-to-r from-transparent via-signal/40 to-transparent" />
      <div className="mx-auto max-w-4xl text-center">
        <motion.h2
          initial={{ opacity: 0, y: 16 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true, amount: 0.6 }}
          transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
          className="text-balance text-display-lg text-ink-0"
        >
          See what attackers see.{" "}
          <span className="gradient-signal">Before they contact you.</span>
        </motion.h2>
        <p className="mx-auto mt-6 max-w-xl text-base leading-relaxed text-ink-100 sm:text-lg">
          One domain. One free scan. A full report in 24 hours, no credit card required.
        </p>
        <div className="mt-10 flex flex-col items-center justify-center gap-3 sm:flex-row">
          <Link
            href="/free-scan"
            className="inline-flex items-center justify-center gap-2 rounded-full bg-signal px-8 py-4 text-base font-semibold text-ink-950 shadow-signal transition-colors hover:bg-signal-400"
          >
            Run the free scan
          </Link>
          <a
            href={ENTERPRISE_BOOKING}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center justify-center gap-2 rounded-full border border-white/15 px-8 py-4 text-base font-semibold text-ink-0 transition-colors hover:border-white/30"
          >
            Talk to a specialist
          </a>
        </div>
      </div>
    </section>
  );
}

/* ========================== FOOTER ============================= */

function MarketingFooter() {
  return (
    <footer className="relative border-t border-white/5 bg-ink-950 px-6 py-14 sm:px-8">
      <div className="mx-auto flex max-w-7xl flex-col items-start justify-between gap-10 lg:flex-row lg:items-center">
        <div className="flex items-center gap-3">
          <img src="/hawk-logo.png" alt="HAWK" className="h-10 w-auto" />
          <p className="text-xs text-ink-200">Built by Hawk Security.</p>
        </div>
        <nav className="flex flex-wrap items-center gap-x-8 gap-y-3 text-sm text-ink-100">
          <Link href="/privacy" className="transition-colors hover:text-ink-0">
            Privacy
          </Link>
          <Link href="/guarantee-terms" className="transition-colors hover:text-ink-0">
            Guarantee terms
          </Link>
          <Link href="/free-scan" className="transition-colors hover:text-ink-0">
            Free scan
          </Link>
          <Link href="/portal/login" className="transition-colors hover:text-ink-0">
            Client portal
          </Link>
        </nav>
        <p className="text-xs text-ink-300">
          HAWK Security. All rights reserved. {new Date().getFullYear()}.
        </p>
      </div>
    </footer>
  );
}

/* ========================== SECTION HEADING ============================= */

function SectionHeading({
  eyebrow,
  title,
  subtitle,
  align = "center",
}: {
  eyebrow: string;
  title: string;
  subtitle?: string;
  align?: "center" | "left";
}) {
  const axis = align === "center" ? "text-center mx-auto" : "text-left";
  return (
    <div className={`max-w-3xl ${axis}`}>
      <p className={`text-eyebrow text-signal ${align === "center" ? "" : ""}`}>{eyebrow}</p>
      <h2 className="mt-4 text-balance text-display-md text-ink-0">{title}</h2>
      {subtitle && <p className="mt-5 text-pretty text-base leading-relaxed text-ink-100 sm:text-lg">{subtitle}</p>}
    </div>
  );
}
