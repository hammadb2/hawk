"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { HttpError, marketingApi } from "@/lib/api";
import { MarketingShell } from "@/components/marketing/marketing-shell";

type Status = "idle" | "submitting" | "success" | "error";

const VERTICALS: ReadonlyArray<{ value: string; label: string }> = [
  { value: "", label: "Select your practice type" },
  { value: "dental", label: "Dental or medical practice" },
  { value: "legal", label: "Law firm" },
  { value: "accounting", label: "Accounting, CPA, or tax firm" },
  { value: "other", label: "Other US small business" },
];

const DOMAIN_RE = /^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$/i;

function normalizeDomain(raw: string): string {
  let d = raw.trim().toLowerCase();
  if (!d) return "";
  if (d.startsWith("http://") || d.startsWith("https://")) {
    try {
      d = new URL(d).hostname;
    } catch {
      // fall through
    }
  }
  if (d.startsWith("www.")) d = d.slice(4);
  d = d.split("/")[0];
  return d;
}

export function FreeScanLanding() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [domainRaw, setDomainRaw] = useState("");
  const [company, setCompany] = useState("");
  const [vertical, setVertical] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const domain = useMemo(() => normalizeDomain(domainRaw), [domainRaw]);

  const canSubmit =
    status !== "submitting" &&
    email.trim().length > 3 &&
    email.includes("@") &&
    DOMAIN_RE.test(domain);

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    if (!canSubmit) return;
    setStatus("submitting");
    setErrorMsg(null);
    try {
      await marketingApi.freeScan({
        name: name.trim() || undefined,
        email: email.trim(),
        domain,
        company_name: company.trim() || undefined,
        vertical: vertical || undefined,
      });
      setStatus("success");
    } catch (err) {
      let msg: string;
      if (err instanceof HttpError) {
        if (err.status === 429) {
          msg = "Too many requests. Please try again in a minute.";
        } else if (err.status === 400 || err.status === 422) {
          msg = "Double check the domain and email address.";
        } else {
          msg = "Something went wrong on our side. Try again in a minute.";
        }
      } else {
        msg = "Something went wrong. Try again in a minute.";
      }
      setErrorMsg(msg);
      setStatus("error");
    }
  }

  return (
    <MarketingShell>
      <section className="relative px-6 pb-20 pt-16 sm:px-8 sm:pb-28 sm:pt-24">
        <div className="mx-auto grid max-w-6xl items-start gap-12 lg:grid-cols-[1.1fr_1fr] lg:gap-16">
          <motion.div
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
          >
            <span className="text-eyebrow inline-flex items-center gap-2 text-signal">
              <span className="h-1.5 w-1.5 rounded-full bg-signal" />
              Free. US small businesses.
            </span>
            <h1 className="mt-5 text-display-lg text-balance text-ink-0">
              See what ransomware crews see on your practice.{" "}
              <span className="gradient-signal">Before they contact you.</span>
            </h1>
            <p className="mt-6 max-w-xl text-pretty text-lg leading-relaxed text-ink-100">
              Enter your domain below. Within 24 hours we email you a plain English report with the
              three highest priority external findings on your business. The same signals attackers harvest from DNS, mail, and TLS before they pick targets.
            </p>

            <ul className="mt-10 space-y-4">
              <ScanBullet>No credit card. No sales call required to read the report.</ScanBullet>
              <ScanBullet>
                Plain English, not log dumps. Anything urgent gets flagged at the top.
              </ScanBullet>
              <ScanBullet>
                Mapped to the US regulation that applies to your practice. HIPAA for dental. FTC
                Safeguards Rule for CPA and tax. ABA 2024 cyber ethics for legal.
              </ScanBullet>
            </ul>

            <p className="mt-10 text-sm leading-relaxed text-ink-200">
              Built by HAWK Security. Backed by a written{" "}
              <Link
                href="/guarantee-terms"
                className="font-semibold text-signal transition-colors hover:text-signal-400"
              >
                Breach Response Guarantee
              </Link>{" "}
              up to $2.5M for paying clients.
            </p>
          </motion.div>

          <motion.div
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1], delay: 0.12 }}
            className="relative"
          >
            <div
              aria-hidden
              className="pointer-events-none absolute inset-0 -z-10 rounded-[28px] bg-signal/10 blur-3xl"
            />
            <div className="relative rounded-2xl border border-white/5 bg-ink-900/70 p-6 backdrop-blur-xl sm:p-8">
              {status === "success" ? (
                <FreeScanSuccess domain={domain} email={email} />
              ) : (
                <form onSubmit={handleSubmit} className="space-y-5" noValidate>
                  <div>
                    <p className="text-eyebrow text-signal">Free scan request</p>
                    <h2 className="mt-3 font-display text-2xl font-bold tracking-tight text-ink-0">
                      Get your three finding report.
                    </h2>
                    <p className="mt-2 text-sm text-ink-200">Report arrives within 24 hours.</p>
                  </div>

                  <Field label="Your domain" required>
                    <input
                      type="text"
                      inputMode="url"
                      autoComplete="url"
                      required
                      placeholder="yourpractice.com"
                      value={domainRaw}
                      onChange={(e) => setDomainRaw(e.target.value)}
                      className={inputClass}
                    />
                    {domainRaw && !DOMAIN_RE.test(domain) ? (
                      <p className="mt-1.5 text-xs text-signal-300">
                        Enter the domain without http or https. For example yourpractice.com
                      </p>
                    ) : null}
                  </Field>

                  <Field label="Work email" required>
                    <input
                      type="email"
                      autoComplete="email"
                      required
                      placeholder="you@yourpractice.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className={inputClass}
                    />
                  </Field>

                  <div className="grid gap-4 sm:grid-cols-2">
                    <Field label="Your name">
                      <input
                        type="text"
                        autoComplete="name"
                        placeholder="Jane Doe"
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        className={inputClass}
                      />
                    </Field>
                    <Field label="Practice or firm">
                      <input
                        type="text"
                        autoComplete="organization"
                        placeholder="Doe Dental"
                        value={company}
                        onChange={(e) => setCompany(e.target.value)}
                        className={inputClass}
                      />
                    </Field>
                  </div>

                  <Field label="Practice type">
                    <select
                      value={vertical}
                      onChange={(e) => setVertical(e.target.value)}
                      className={`${inputClass} appearance-none bg-[length:20px] bg-[right_12px_center] bg-no-repeat pr-10 bg-[url("data:image/svg+xml,%3Csvg%20xmlns%3D%27http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%27%20viewBox%3D%270%200%2020%2020%27%20fill%3D%27%23a1a1aa%27%3E%3Cpath%20d%3D%27M5.23%207.21a.75.75%200%20011.06.02L10%2011.06l3.71-3.83a.75.75%200%20011.08%201.04l-4.25%204.39a.75.75%200%2001-1.08%200L5.21%208.27a.75.75%200%2001.02-1.06z%27%2F%3E%3C%2Fsvg%3E")]`}
                    >
                      {VERTICALS.map((v) => (
                        <option key={v.value} value={v.value} className="bg-ink-900 text-ink-0">
                          {v.label}
                        </option>
                      ))}
                    </select>
                  </Field>

                  {errorMsg ? (
                    <p
                      role="alert"
                      className="rounded-lg border border-rose-400/20 bg-rose-400/10 px-3 py-2 text-sm text-rose-200"
                    >
                      {errorMsg}
                    </p>
                  ) : null}

                  <button
                    type="submit"
                    disabled={!canSubmit}
                    className="w-full rounded-full bg-signal px-5 py-3 text-base font-semibold text-ink-950 shadow-signal-sm transition-colors hover:bg-signal-400 disabled:cursor-not-allowed disabled:bg-ink-700 disabled:text-ink-300 disabled:shadow-none"
                  >
                    {status === "submitting" ? "Requesting scan" : "Run my free scan"}
                  </button>

                  <p className="text-center text-xs text-ink-300">
                    Report emailed within 24 hours. Unsubscribe any time.
                  </p>
                </form>
              )}
            </div>
          </motion.div>
        </div>
      </section>

      <section className="relative border-t border-white/5 bg-ink-900/30 px-6 py-20 sm:px-8 sm:py-24">
        <div className="mx-auto max-w-6xl">
          <div className="text-center">
            <span className="text-eyebrow inline-flex items-center gap-2 text-signal">
              <span className="h-1.5 w-1.5 rounded-full bg-signal" />
              What you get
            </span>
            <h2 className="mx-auto mt-4 max-w-2xl font-display text-3xl font-extrabold tracking-tightest text-ink-0 sm:text-4xl">
              Three steps. Twenty four hours. Plain English.
            </h2>
          </div>
          <div className="mt-14 grid gap-6 sm:grid-cols-3">
            <HowCard
              step="01"
              title="You submit"
              body="Domain and work email. That is it. No credit card. No sales form dance."
            />
            <HowCard
              step="02"
              title="We scan"
              body="Real external attack surface scan on your domain. DNS, mail, TLS, exposed services, auth posture."
            />
            <HowCard
              step="03"
              title="You get the report"
              body="Plain English summary of the three highest priority findings, mapped to the US regulation for your practice."
            />
          </div>
        </div>
      </section>
    </MarketingShell>
  );
}

const inputClass =
  "block w-full rounded-lg border border-white/10 bg-ink-900/80 px-3 py-2.5 text-sm text-ink-0 placeholder:text-ink-300 transition-colors focus:border-signal/60 focus:outline-none focus:ring-2 focus:ring-signal/30";

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-medium uppercase tracking-[0.14em] text-ink-200">
        {label}
        {required ? <span className="ml-1 text-signal">*</span> : null}
      </span>
      {children}
    </label>
  );
}

function ScanBullet({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex items-start gap-3 text-base leading-relaxed text-ink-100">
      <span
        aria-hidden
        className="mt-1 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-signal/15 ring-1 ring-signal/40"
      >
        <svg viewBox="0 0 20 20" fill="none" className="h-3 w-3">
          <path
            d="M4.5 10.5l3 3 8-8"
            stroke="#FFB800"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
      <span>{children}</span>
    </li>
  );
}

function HowCard({ step, title, body }: { step: string; title: string; body: string }) {
  return (
    <div className="relative rounded-2xl border border-white/5 bg-ink-900/60 p-6 backdrop-blur-xl transition-colors hover:border-white/10 sm:p-7">
      <span className="font-mono text-xs tracking-[0.2em] text-signal">{step}</span>
      <h3 className="mt-3 font-display text-lg font-semibold tracking-tight text-ink-0">{title}</h3>
      <p className="mt-2 text-sm leading-relaxed text-ink-200">{body}</p>
    </div>
  );
}

function FreeScanSuccess({ domain, email }: { domain: string; email: string }) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
    >
      <span className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-signal/15 ring-1 ring-signal/40">
        <svg viewBox="0 0 20 20" fill="none" className="h-5 w-5">
          <path
            d="M4.5 10.5l3 3 8-8"
            stroke="#FFB800"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
      <h2 className="mt-5 font-display text-2xl font-bold tracking-tight text-ink-0">
        Scan requested.
      </h2>
      <p className="mt-4 text-base leading-relaxed text-ink-100">
        We kicked off an external attack surface scan on{" "}
        <strong className="text-ink-0">{domain}</strong> the moment you hit submit. Your three finding report will land at{" "}
        <strong className="text-ink-0">{email}</strong> within{" "}
        <strong className="text-ink-0">24 hours</strong>.
      </p>
      <p className="mt-4 text-sm leading-relaxed text-ink-200">
        Anything urgent gets flagged at the top of the report. No sales call required to read it.
      </p>
      <Link
        href="/"
        className="mt-6 inline-flex items-center gap-1.5 rounded-full border border-white/10 px-4 py-2 text-sm font-medium text-ink-100 transition-colors hover:border-white/20 hover:text-ink-0"
      >
        Back to securedbyhawk.com
      </Link>
    </motion.div>
  );
}
