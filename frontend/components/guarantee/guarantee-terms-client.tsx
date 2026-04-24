"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type ComponentPropsWithoutRef } from "react";
import ReactMarkdown from "react-markdown";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { guaranteeApi } from "@/lib/api";

const STORAGE_KEY = "hawk_guarantee_doc_jwt";
const HAWK = "#FFB800";

type Step = "intro" | "details" | "code" | "doc";

const mdComponents = {
  h1: (props: ComponentPropsWithoutRef<"h1">) => (
    <h1 className="mt-8 text-2xl font-extrabold tracking-tight text-text-primary first:mt-0" {...props} />
  ),
  h2: (props: ComponentPropsWithoutRef<"h2">) => (
    <h2 className="mt-10 scroll-mt-24 text-lg font-bold tracking-tight" style={{ color: HAWK }} {...props} />
  ),
  p: (props: ComponentPropsWithoutRef<"p">) => <p className="my-3 leading-relaxed text-text-secondary" {...props} />,
  blockquote: (props: ComponentPropsWithoutRef<"blockquote">) => (
    <blockquote
      className="my-6 border-l-4 pl-4 text-sm italic text-text-secondary"
      style={{ borderColor: `${HAWK}66` }}
      {...props}
    />
  ),
  strong: (props: ComponentPropsWithoutRef<"strong">) => <strong className="font-semibold text-text-primary" {...props} />,
  ul: (props: ComponentPropsWithoutRef<"ul">) => <ul className="my-4 list-disc space-y-2 pl-6 text-text-secondary" {...props} />,
  ol: (props: ComponentPropsWithoutRef<"ol">) => <ol className="my-4 list-decimal space-y-2 pl-6 text-text-secondary" {...props} />,
  li: (props: ComponentPropsWithoutRef<"li">) => <li className="leading-relaxed" {...props} />,
  hr: () => <hr className="my-8 border-surface-3" />,
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
    <div className="min-h-screen bg-background px-4 py-10 text-text-primary sm:px-6 sm:py-16">
      <div className="mx-auto max-w-3xl">
        <Link href="/" className="text-sm hover:underline" style={{ color: HAWK }}>
          ← Back to home
        </Link>

        <h1 className="mt-8 text-3xl font-extrabold">Guarantee terms</h1>
        <p className="mt-4 text-text-secondary leading-relaxed">
          HAWK Shield includes financially backed incident response coverage subject to your subscription agreement, timely remediation of
          notified critical and high findings, and other conditions in writing at signup.
        </p>

        {step === "doc" && markdown ? (
          <div className="mt-10">
            <div className="mb-6 flex flex-wrap items-center justify-between gap-3 border-b border-surface-3 pb-4">
              <p className="text-sm text-text-dim">Breach Response Guarantee — full text</p>
              <button type="button" onClick={signOutDoc} className="text-sm text-text-dim hover:text-text-secondary">
                Lock document
              </button>
            </div>
            <article className="max-w-none border border-surface-3 bg-surface-1 p-6 sm:p-8">
              <ReactMarkdown components={mdComponents}>{markdown}</ReactMarkdown>
            </article>
          </div>
        ) : (
          <>
            {(step === "intro" || step === "details" || step === "code") && (
              <div className="mt-8 rounded-xl border border-surface-3 bg-surface-1 p-6 sm:p-8">
                {step === "intro" && (
                  <>
                    <p className="text-text-secondary leading-relaxed">
                      The full <strong className="text-text-primary">Breach Response Guarantee</strong> is available as a downloadable legal
                      reference. To reduce scraping, we ask you to verify your work email before viewing.
                    </p>
                    <Button
                      type="button"
                      className="mt-6 w-full font-semibold text-[#07060C] sm:w-auto"
                      style={{ backgroundColor: HAWK }}
                      onClick={() => {
                        setStep("details");
                        setErr(null);
                      }}
                    >
                      View document
                    </Button>
                  </>
                )}

                {step === "details" && (
                  <form onSubmit={onRequestCode} className="space-y-4">
                    <p className="text-sm text-text-secondary">Enter your details. We will email a verification code from noreply@securedbyhawk.com.</p>
                    <div>
                      <label className="mb-1 block text-xs text-text-dim">Full name</label>
                      <Input required value={name} onChange={(e) => setName(e.target.value)} className="border-surface-3 bg-background" />
                    </div>
                    <div>
                      <label className="mb-1 block text-xs text-text-dim">Company</label>
                      <Input required value={company} onChange={(e) => setCompany(e.target.value)} className="border-surface-3 bg-background" />
                    </div>
                    <div>
                      <label className="mb-1 block text-xs text-text-dim">Work email</label>
                      <Input required type="email" value={email} onChange={(e) => setEmail(e.target.value)} className="border-surface-3 bg-background" />
                    </div>
                    {err && <p className="text-sm text-red">{err}</p>}
                    <Button type="submit" disabled={loading} className="font-semibold text-[#07060C]" style={{ backgroundColor: HAWK }}>
                      {loading ? "Sending…" : "Email me a code"}
                    </Button>
                  </form>
                )}

                {step === "code" && (
                  <form onSubmit={onVerify} className="space-y-4">
                    <p className="text-sm text-text-secondary">
                      Enter the 6-digit code sent to <strong className="text-text-primary">{email}</strong>.
                    </p>
                    <div>
                      <label className="mb-1 block text-xs text-text-dim">Verification code</label>
                      <Input
                        required
                        inputMode="numeric"
                        autoComplete="one-time-code"
                        placeholder="000000"
                        value={code}
                        onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                        className="border-surface-3 bg-background font-mono text-lg tracking-[0.3em]"
                        maxLength={6}
                      />
                    </div>
                    {err && <p className="text-sm text-red">{err}</p>}
                    <div className="flex flex-wrap gap-3">
                      <Button type="submit" disabled={loading} className="font-semibold text-[#07060C]" style={{ backgroundColor: HAWK }}>
                        {loading ? "Verifying…" : "Verify and view document"}
                      </Button>
                      <Button type="button" variant="ghost" onClick={() => setStep("details")}>
                        Edit details
                      </Button>
                    </div>
                  </form>
                )}
              </div>
            )}
          </>
        )}

        <p className="mt-10 text-sm text-text-dim">
          Questions:{" "}
          <a href="mailto:hello@securedbyhawk.com" className="hover:underline" style={{ color: HAWK }}>
            hello@securedbyhawk.com
          </a>
        </p>
      </div>
    </div>
  );
}
