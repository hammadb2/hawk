"use client";

import { useCallback, useEffect, useState, type ComponentPropsWithoutRef } from "react";
import { motion } from "framer-motion";
import ReactMarkdown from "react-markdown";
import { guaranteeApi } from "@/lib/api";

const STORAGE_KEY = "hawk_guarantee_doc_jwt";

type Step = "intro" | "details" | "code" | "doc";

const mdComponents = {
  h1: (props: ComponentPropsWithoutRef<"h1">) => (
    <h1 className="mt-10 font-display text-3xl font-extrabold tracking-tightest text-ink-0 first:mt-0" {...props} />
  ),
  h2: (props: ComponentPropsWithoutRef<"h2">) => (
    <h2 className="mt-10 scroll-mt-24 font-display text-xl font-bold tracking-tight text-signal" {...props} />
  ),
  h3: (props: ComponentPropsWithoutRef<"h3">) => (
    <h3 className="mt-8 font-display text-lg font-semibold tracking-tight text-ink-0" {...props} />
  ),
  p: (props: ComponentPropsWithoutRef<"p">) => (
    <p className="my-4 text-pretty text-base leading-relaxed text-ink-100" {...props} />
  ),
  blockquote: (props: ComponentPropsWithoutRef<"blockquote">) => (
    <blockquote
      className="my-6 border-l-2 border-signal/40 bg-ink-800/40 px-4 py-3 text-sm italic text-ink-100"
      {...props}
    />
  ),
  strong: (props: ComponentPropsWithoutRef<"strong">) => (
    <strong className="font-semibold text-ink-0" {...props} />
  ),
  ul: (props: ComponentPropsWithoutRef<"ul">) => (
    <ul className="my-5 list-disc space-y-2 pl-6 text-ink-100 marker:text-signal/70" {...props} />
  ),
  ol: (props: ComponentPropsWithoutRef<"ol">) => (
    <ol className="my-5 list-decimal space-y-2 pl-6 text-ink-100 marker:text-signal/70" {...props} />
  ),
  li: (props: ComponentPropsWithoutRef<"li">) => <li className="leading-relaxed" {...props} />,
  hr: () => <hr className="my-10 border-white/5" />,
  a: (props: ComponentPropsWithoutRef<"a">) => (
    <a className="text-signal underline-offset-2 hover:underline" {...props} />
  ),
  code: (props: ComponentPropsWithoutRef<"code">) => (
    <code className="rounded bg-ink-800 px-1.5 py-0.5 font-mono text-[0.9em] text-ink-0" {...props} />
  ),
};

export function GuaranteeTermsClient() {
  const [step, setStep] = useState<Step>("intro");
  const [name, setName] = useState("");
  const [company, setCompany] = useState("");
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [markdown, setMarkdown] = useState<string | null>(null);

  const loadDoc = useCallback(async (token: string) => {
    const { markdown: md } = await guaranteeApi.getDocument(token);
    setMarkdown(md);
    setStep("doc");
  }, []);

  useEffect(() => {
    const t = typeof window !== "undefined" ? sessionStorage.getItem(STORAGE_KEY) : null;
    if (!t) return;
    loadDoc(t).catch(() => {
      sessionStorage.removeItem(STORAGE_KEY);
    });
  }, [loadDoc]);

  const onRequestCode = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    setLoading(true);
    try {
      await guaranteeApi.requestCode({ email: email.trim(), name: name.trim(), company: company.trim() });
      setStep("code");
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not send code. Try again.");
    } finally {
      setLoading(false);
    }
  };

  const onVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    setLoading(true);
    try {
      const { access_token } = await guaranteeApi.verify({ email: email.trim(), code: code.trim() });
      sessionStorage.setItem(STORAGE_KEY, access_token);
      await loadDoc(access_token);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Verification failed.");
    } finally {
      setLoading(false);
    }
  };

  const signOutDoc = () => {
    sessionStorage.removeItem(STORAGE_KEY);
    setMarkdown(null);
    setStep("intro");
    setCode("");
  };

  return (
    <section className="relative px-6 pb-28 pt-20 sm:px-8 sm:pb-32 sm:pt-28">
      <div className="mx-auto max-w-4xl">
        <motion.div
          initial={{ opacity: 0, y: 18 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
        >
          <span className="text-eyebrow inline-flex items-center gap-2 text-signal">
            <span className="h-1.5 w-1.5 rounded-full bg-signal" />
            Breach response guarantee
          </span>
          <h1 className="mt-5 font-display text-4xl font-extrabold tracking-tightest text-ink-0 sm:text-5xl">
            Our coverage. In writing.
          </h1>
          <p className="mt-5 max-w-2xl text-pretty text-base leading-relaxed text-ink-100 sm:text-lg">
            HAWK Guard and HAWK Sentinel include a financially backed Breach Response Guarantee. The full document is gated behind a work email verification to reduce scraping. Verification takes under a minute.
          </p>
        </motion.div>

        {step === "doc" && markdown ? (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
            className="mt-12"
          >
            <div className="mb-5 flex flex-wrap items-center justify-between gap-3 border-b border-white/10 pb-4">
              <p className="text-xs uppercase tracking-[0.22em] text-ink-300">
                Breach response guarantee. Full text.
              </p>
              <button
                type="button"
                onClick={signOutDoc}
                className="text-xs font-medium text-ink-200 transition-colors hover:text-ink-0"
              >
                Lock document
              </button>
            </div>
            <article className="rounded-2xl border border-white/5 bg-ink-900/60 p-6 backdrop-blur-xl sm:p-10">
              <ReactMarkdown components={mdComponents}>{markdown}</ReactMarkdown>
            </article>
          </motion.div>
        ) : (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1], delay: 0.1 }}
            className="mt-12"
          >
            <div className="rounded-2xl border border-white/5 bg-ink-900/60 p-6 backdrop-blur-xl sm:p-10">
              {step === "intro" && (
                <div>
                  <p className="text-base leading-relaxed text-ink-100">
                    Enter your work email on the next step. We email a six digit code from{" "}
                    <span className="text-ink-0">noreply@securedbyhawk.com</span>. Enter the code and the full document unlocks on this page.
                  </p>
                  <ul className="mt-6 space-y-3 text-sm leading-relaxed text-ink-200">
                    <Bullet>Covers Guard up to $1M and Sentinel up to $2.5M in incident response costs.</Bullet>
                    <Bullet>Governed by the laws of the jurisdiction in which the client operates. Not subject to a forum we pick.</Bullet>
                    <Bullet>Signed version issued at contract. This page is the reference document.</Bullet>
                  </ul>
                  <button
                    type="button"
                    onClick={() => {
                      setStep("details");
                      setErr(null);
                    }}
                    className="mt-8 inline-flex items-center gap-1.5 rounded-full bg-signal px-5 py-2.5 text-sm font-semibold text-ink-950 shadow-signal-sm transition-colors hover:bg-signal-400"
                  >
                    View document
                  </button>
                </div>
              )}

              {step === "details" && (
                <form onSubmit={onRequestCode} className="space-y-5">
                  <p className="text-sm leading-relaxed text-ink-100">
                    Enter your details. We will email a verification code from{" "}
                    <span className="text-ink-0">noreply@securedbyhawk.com</span>.
                  </p>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <Field label="Full name">
                      <input
                        required
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        className={inputClass}
                        autoComplete="name"
                      />
                    </Field>
                    <Field label="Company">
                      <input
                        required
                        value={company}
                        onChange={(e) => setCompany(e.target.value)}
                        className={inputClass}
                        autoComplete="organization"
                      />
                    </Field>
                  </div>
                  <Field label="Work email">
                    <input
                      required
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className={inputClass}
                      autoComplete="email"
                      placeholder="you@yourpractice.com"
                    />
                  </Field>
                  {err && <p className="text-sm text-rose-300">{err}</p>}
                  <div className="flex flex-wrap gap-3 pt-2">
                    <button
                      type="submit"
                      disabled={loading}
                      className="inline-flex items-center gap-1.5 rounded-full bg-signal px-5 py-2.5 text-sm font-semibold text-ink-950 shadow-signal-sm transition-colors hover:bg-signal-400 disabled:cursor-not-allowed disabled:bg-ink-600 disabled:text-ink-200 disabled:shadow-none"
                    >
                      {loading ? "Sending" : "Email me a code"}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setStep("intro");
                        setErr(null);
                      }}
                      className="inline-flex items-center gap-1.5 rounded-full border border-white/10 px-5 py-2.5 text-sm font-medium text-ink-100 transition-colors hover:border-white/20 hover:text-ink-0"
                    >
                      Back
                    </button>
                  </div>
                </form>
              )}

              {step === "code" && (
                <form onSubmit={onVerify} className="space-y-5">
                  <p className="text-sm leading-relaxed text-ink-100">
                    Enter the six digit code sent to{" "}
                    <span className="font-medium text-ink-0">{email}</span>.
                  </p>
                  <Field label="Verification code">
                    <input
                      required
                      inputMode="numeric"
                      autoComplete="one-time-code"
                      placeholder="000000"
                      value={code}
                      onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                      maxLength={6}
                      className={`${inputClass} font-mono text-lg tracking-[0.4em]`}
                    />
                  </Field>
                  {err && <p className="text-sm text-rose-300">{err}</p>}
                  <div className="flex flex-wrap gap-3 pt-2">
                    <button
                      type="submit"
                      disabled={loading}
                      className="inline-flex items-center gap-1.5 rounded-full bg-signal px-5 py-2.5 text-sm font-semibold text-ink-950 shadow-signal-sm transition-colors hover:bg-signal-400 disabled:cursor-not-allowed disabled:bg-ink-600 disabled:text-ink-200 disabled:shadow-none"
                    >
                      {loading ? "Verifying" : "Verify and view document"}
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        setStep("details");
                        setErr(null);
                      }}
                      className="inline-flex items-center gap-1.5 rounded-full border border-white/10 px-5 py-2.5 text-sm font-medium text-ink-100 transition-colors hover:border-white/20 hover:text-ink-0"
                    >
                      Edit details
                    </button>
                  </div>
                </form>
              )}
            </div>

            <p className="mt-6 text-sm text-ink-300">
              Questions.{" "}
              <a
                href="mailto:hello@securedbyhawk.com"
                className="font-semibold text-signal transition-colors hover:text-signal-400"
              >
                hello@securedbyhawk.com
              </a>
            </p>
          </motion.div>
        )}
      </div>
    </section>
  );
}

const inputClass =
  "block w-full rounded-lg border border-white/10 bg-ink-900/80 px-3 py-2.5 text-sm text-ink-0 placeholder:text-ink-300 transition-colors focus:border-signal/60 focus:outline-none focus:ring-2 focus:ring-signal/30";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1.5 block text-xs font-medium uppercase tracking-[0.14em] text-ink-200">
        {label}
      </span>
      {children}
    </label>
  );
}

function Bullet({ children }: { children: React.ReactNode }) {
  return (
    <li className="flex items-start gap-3">
      <span aria-hidden className="mt-1.5 inline-block h-1.5 w-1.5 shrink-0 rounded-full bg-signal" />
      <span>{children}</span>
    </li>
  );
}
