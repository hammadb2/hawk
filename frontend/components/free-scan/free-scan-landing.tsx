"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import { HttpError, marketingApi } from "@/lib/api";
import { portal } from "@/lib/portal-ui";

type Status = "idle" | "submitting" | "success" | "error";

const VERTICALS: ReadonlyArray<{ value: string; label: string }> = [
  { value: "", label: "Select your practice type" },
  { value: "dental", label: "Dental / medical practice" },
  { value: "legal", label: "Law firm" },
  { value: "accounting", label: "Accounting / CPA / tax firm" },
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
  // strip anything after the first slash just in case (e.g. pasted URL)
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
      // Branch on HTTP status, not message text. The request layer used to
      // throw a plain Error whose message was just the server's `detail`
      // string — status 429/400 were never *in* the message, so the old
      // `err.message.includes("429")` checks never matched and every error
      // fell through to the generic server-side message. `HttpError.status`
      // is the canonical signal.
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
    <div className={`${portal.pageBg} selection:bg-signal/15`}>
      <header className="border-b border-white/10 bg-ink-800/95 backdrop-blur-md">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-4 sm:px-6">
          <Link href="/" className="flex items-center gap-2" title="HAWK Security">
            <span className="flex items-center rounded-lg bg-ink-950 px-2 py-1.5 shadow-sm ring-1 ring-white/10 sm:px-2.5 sm:py-2">
              <img
                src="/hawk-logo.png"
                alt="HAWK Security"
                className="h-11 w-auto sm:h-12"
                width={252}
                height={84}
              />
            </span>
          </Link>
          <Link
            href="/"
            className="text-sm font-medium text-ink-0 hover:text-signal"
          >
            ← Back to homepage
          </Link>
        </div>
      </header>

      <main>
        <section className="px-4 pt-16 pb-10 sm:px-6 sm:pt-24 sm:pb-16">
          <div className="mx-auto grid max-w-5xl gap-12 lg:grid-cols-[1.1fr_1fr] lg:gap-16">
            {/* Left: pitch */}
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.18em] text-signal">
                Free · US small businesses
              </p>
              <h1 className="mt-3 text-balance text-3xl font-extrabold leading-tight tracking-tight text-ink-0 sm:text-4xl md:text-5xl">
                See what ransomware crews see on your practice.{" "}
                <span className="text-signal">Before they contact you.</span>
              </h1>
              <p className="mt-5 text-pretty text-lg leading-relaxed text-ink-200">
                Enter your domain below. Within 24 hours we&apos;ll email you a plain English
                report with the <strong className="text-ink-0">three highest priority external findings</strong>{" "}
                on your business. The same signals attackers harvest from DNS, mail, and TLS before
                they pick targets.
              </p>

              <ul className="mt-8 space-y-4 text-base leading-relaxed text-ink-100">
                <FreeScanBullet>
                  No credit card. No sales call required to read the report.
                </FreeScanBullet>
                <FreeScanBullet>
                  Plain English, not log dumps. If something needs fixing urgently, we flag it at the top.
                </FreeScanBullet>
                <FreeScanBullet>
                  Mapped to the US regulation that applies to your practice. HIPAA for dental. FTC
                  Safeguards Rule for CPA and tax. ABA 2024 cyber ethics for legal.
                </FreeScanBullet>
              </ul>

              <p className="mt-8 text-sm leading-relaxed text-ink-0">
                Built by HAWK Security. Backed by a written{" "}
                <Link href="/guarantee-terms" className={portal.link}>
                  Breach Response Guarantee
                </Link>{" "}
                up to $2.5M for paying clients.
              </p>
            </div>

            {/* Right: form */}
            <div>
              <div className={`${portal.card} p-6 sm:p-8`}>
                {status === "success" ? (
                  <FreeScanSuccess domain={domain} email={email} />
                ) : (
                  <form onSubmit={handleSubmit} className="space-y-4" noValidate>
                    <div>
                      <h2 className="text-xl font-bold tracking-tight text-ink-0">
                        Get your free three finding report
                      </h2>
                      <p className="mt-1 text-sm text-ink-0">
                        Report arrives within 24 hours.
                      </p>
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
                        <p className="mt-1 text-xs text-signal-400">
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

                    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
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
                      <Field label="Practice / firm">
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
                        className={`${inputClass} appearance-none bg-[length:20px] bg-[right_12px_center] bg-no-repeat pr-10 bg-[url("data:image/svg+xml,%3Csvg%20xmlns%3D%27http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%27%20viewBox%3D%270%200%2020%2020%27%20fill%3D%27%2364748b%27%3E%3Cpath%20d%3D%27M5.23%207.21a.75.75%200%20011.06.02L10%2011.06l3.71-3.83a.75.75%200%20011.08%201.04l-4.25%204.39a.75.75%200%2001-1.08%200L5.21%208.27a.75.75%200%2001.02-1.06z%27%2F%3E%3C%2Fsvg%3E")]`}
                      >
                        {VERTICALS.map((v) => (
                          <option key={v.value} value={v.value}>
                            {v.label}
                          </option>
                        ))}
                      </select>
                    </Field>

                    {errorMsg ? (
                      <p
                        role="alert"
                        className="rounded-md border border-red/30 bg-red/10 px-3 py-2 text-sm text-red"
                      >
                        {errorMsg}
                      </p>
                    ) : null}

                    <button
                      type="submit"
                      disabled={!canSubmit}
                      className={`w-full rounded-lg px-5 py-3 text-base font-semibold transition-colors ${
                        canSubmit
                          ? "bg-signal text-white shadow-sm hover:bg-signal-400"
                          : "bg-ink-700 text-ink-0 cursor-not-allowed"
                      }`}
                    >
                      {status === "submitting"
                        ? "Requesting scan…"
                        : "Run my free scan"}
                    </button>

                    <p className="text-center text-xs text-ink-200">
                      We email you the report within 24 hours. You can unsubscribe at any time.
                    </p>
                  </form>
                )}
              </div>
            </div>
          </div>
        </section>

        <section className="border-t border-white/10 bg-ink-900 px-4 py-12 sm:px-6 sm:py-16">
          <div className="mx-auto max-w-5xl">
            <h2 className="text-center text-2xl font-bold tracking-tight text-ink-0 sm:text-3xl">
              What you&apos;ll get
            </h2>
            <div className="mt-10 grid gap-6 sm:grid-cols-3">
              <HowItWorksCard
                step="1"
                title="You submit"
                body="Domain plus your work email. That is it. No credit card. No sales form dance."
              />
              <HowItWorksCard
                step="2"
                title="We scan"
                body="Real external attack surface scan on your domain. DNS, mail, TLS, exposed services, auth posture."
              />
              <HowItWorksCard
                step="3"
                title="You get the report"
                body="Plain English summary of the three highest priority findings, mapped to the US regulation that applies to your practice."
              />
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-white/10 px-4 py-8 sm:px-6">
        <div className="mx-auto flex max-w-5xl flex-col items-center justify-between gap-3 text-xs text-ink-200 sm:flex-row">
          <span>© HAWK Security · securedbyhawk.com</span>
          <div className="flex gap-4">
            <Link href="/privacy" className="hover:text-signal">
              Privacy
            </Link>
            <Link href="/guarantee-terms" className="hover:text-signal">
              Guarantee terms
            </Link>
          </div>
        </div>
      </footer>
    </div>
  );
}

const inputClass =
  "w-full rounded-lg border border-white/10 bg-ink-800 px-3 py-2.5 text-sm text-ink-0 shadow-sm placeholder:text-ink-200 focus:border-signal/60 focus:outline-none focus:ring-2 focus:ring-signal/20";

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
      <span className="mb-1 block text-sm font-medium text-ink-100">
        {label}
        {required ? <span className="ml-1 text-signal">*</span> : null}
      </span>
      {children}
    </label>
  );
}

function FreeScanBullet({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex gap-3">
      <span
        aria-hidden
        className="mt-1 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-signal/15 text-signal"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 20 20"
          fill="currentColor"
          className="h-3 w-3"
        >
          <path
            fillRule="evenodd"
            d="M16.704 5.292a1 1 0 010 1.416l-8 8a1 1 0 01-1.416 0l-4-4A1 1 0 014.704 9.29L8 12.586l7.296-7.294a1 1 0 011.408 0z"
            clipRule="evenodd"
          />
        </svg>
      </span>
      <span>{children}</span>
    </li>
  );
}

function HowItWorksCard({
  step,
  title,
  body,
}: {
  step: string;
  title: string;
  body: string;
}) {
  return (
    <div className={`${portal.card} p-5`}>
      <span className="inline-flex h-8 w-8 items-center justify-center rounded-full bg-signal text-sm font-bold text-white">
        {step}
      </span>
      <h3 className="mt-3 text-lg font-bold tracking-tight text-ink-0">
        {title}
      </h3>
      <p className="mt-2 text-sm leading-relaxed text-ink-200">{body}</p>
    </div>
  );
}

function FreeScanSuccess({ domain, email }: { domain: string; email: string }) {
  return (
    <div>
      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-signal/15 text-signal">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 20 20"
          fill="currentColor"
          className="h-5 w-5"
        >
          <path
            fillRule="evenodd"
            d="M16.704 5.292a1 1 0 010 1.416l-8 8a1 1 0 01-1.416 0l-4-4A1 1 0 014.704 9.29L8 12.586l7.296-7.294a1 1 0 011.408 0z"
            clipRule="evenodd"
          />
        </svg>
      </div>
      <h2 className="mt-4 text-2xl font-bold tracking-tight text-ink-0">
        Scan requested.
      </h2>
      <p className="mt-3 text-base leading-relaxed text-ink-200">
        We kicked off an external attack surface scan on{" "}
        <strong className="text-ink-0">{domain}</strong> the moment you hit submit. Your three finding
        report will land at{" "}
        <strong className="text-ink-0">{email}</strong> within{" "}
        <strong className="text-ink-0">24 hours</strong>.
      </p>
      <p className="mt-4 text-sm text-ink-0">
        If anything is urgent, you&apos;ll see it flagged at the top of the report. No sales call
        required to read it.
      </p>
      <Link
        href="/"
        className="mt-6 inline-flex rounded-lg border border-white/10 bg-ink-800 px-4 py-2 text-sm font-medium text-ink-100 shadow-sm hover:bg-ink-900"
      >
        Back to securedbyhawk.com
      </Link>
    </div>
  );
}
