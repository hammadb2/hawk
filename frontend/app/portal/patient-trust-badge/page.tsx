"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

type Eligibility = {
  eligible: boolean;
  reason: string | null;
  vertical: string | null;
  readiness_pct: number | null;
  certified_at: string | null;
  readiness_floor: number;
};

type StatusResponse = {
  eligibility: Eligibility;
  company_name: string;
  earned_on: string;
  badge_url: string;
  verify_url: string;
  embed: { html: string; image_url: string; verify_url: string };
};

const FRIENDLY_REASON: Record<string, string> = {
  not_healthcare_vertical:
    "The Patient Trust Badge uses HIPAA-aligned language and is only available to healthcare practices.",
  below_readiness_floor:
    "Your insurance-readiness score isn't quite at the threshold yet — once it hits 80% (or you complete HAWK Certified), this badge unlocks automatically.",
  no_portal_profile: "We couldn't load your portal profile. Try refreshing.",
  hawk_certified: "Earned via HAWK Certified.",
  insurance_readiness_above_floor: "Earned via insurance-readiness ≥ 80%.",
};

export default function PatientTrustBadgePage() {
  const [data, setData] = useState<StatusResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      setLoading(true);
      try {
        const res = await fetch("/api/portal/patient-trust-badge");
        const j = (await res.json()) as StatusResponse & { error?: string };
        if (!res.ok) {
          setErr(j.error || "Could not load badge status");
          return;
        }
        setData(j);
      } catch {
        setErr("Network error");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const copy = async (key: string, text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(key);
      setTimeout(() => setCopied(null), 1500);
    } catch {
      setErr("Could not copy to clipboard");
    }
  };

  const reasonLabel = useMemo(() => {
    if (!data) return null;
    const r = data.eligibility.reason;
    return (r && FRIENDLY_REASON[r]) || null;
  }, [data]);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-ink-0">Patient Trust Badge</h1>
        <p className="mt-1 text-sm text-ink-200">
          A patient-facing badge confirming your practice has HIPAA-aligned security
          monitoring with HAWK. Display it on your website, intake forms, or waiting-room
          signage.
        </p>
        <Link href="/portal" className="mt-2 inline-block text-sm text-signal hover:underline">
          ← Back to overview
        </Link>
      </div>

      {loading && <p className="text-ink-200">Loading…</p>}
      {err && <p className="text-red">{err}</p>}

      {!loading && !err && data && (
        <>
          {data.eligibility.eligible ? (
            <section className="rounded-2xl border border-white/10 bg-ink-800 shadow-sm p-6">
              <div className="flex flex-wrap gap-6">
                <div className="shrink-0">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src="/api/portal/patient-trust-badge.svg"
                    alt={`HAWK Patient Trust Badge — ${data.company_name}`}
                    width={300}
                    height={190}
                    className="rounded-lg border border-white/10 bg-black/20"
                  />
                </div>
                <div className="min-w-0 flex-1 space-y-3">
                  <div>
                    <p className="text-xs uppercase tracking-widest text-signal">
                      You&apos;re eligible
                    </p>
                    <p className="text-sm text-ink-100">
                      {reasonLabel || "Earned — display on your site any time."}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <a
                      href="/api/portal/patient-trust-badge.svg"
                      download="hawk-patient-trust-badge.svg"
                      className="inline-flex items-center gap-2 rounded-full bg-signal px-4 py-2 text-sm font-semibold text-ink-950 shadow-signal-sm transition-colors hover:bg-signal-400"
                    >
                      Download SVG
                    </a>
                    <a
                      href={data.verify_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 rounded-full border border-white/10 px-4 py-2 text-sm text-ink-100 transition-colors hover:bg-white/5"
                    >
                      Verification page
                    </a>
                  </div>
                </div>
              </div>

              <div className="mt-6 space-y-4 border-t border-white/10 pt-5">
                <div>
                  <h2 className="text-sm font-semibold uppercase tracking-wide text-ink-200">
                    Embed on your website
                  </h2>
                  <p className="mt-1 text-xs text-ink-200">
                    Copy this snippet into your site&apos;s footer or your &quot;About / Privacy&quot; page.
                    The badge image is hosted by HAWK; the link points to a public verify page.
                  </p>
                </div>
                <div className="rounded-lg border border-white/10 bg-black/20 p-3">
                  <pre className="whitespace-pre-wrap break-all text-xs text-ink-100">
                    {data.embed.html}
                  </pre>
                  <button
                    type="button"
                    onClick={() => copy("html", data.embed.html)}
                    className="mt-2 rounded-md bg-white/5 px-3 py-1 text-xs text-ink-100 hover:bg-white/10"
                  >
                    {copied === "html" ? "Copied!" : "Copy HTML"}
                  </button>
                </div>
                <div className="rounded-lg border border-white/10 bg-black/20 p-3">
                  <p className="text-xs text-ink-200">Direct image URL</p>
                  <pre className="mt-1 whitespace-pre-wrap break-all text-xs text-ink-100">
                    {data.embed.image_url}
                  </pre>
                  <button
                    type="button"
                    onClick={() => copy("img", data.embed.image_url)}
                    className="mt-2 rounded-md bg-white/5 px-3 py-1 text-xs text-ink-100 hover:bg-white/10"
                  >
                    {copied === "img" ? "Copied!" : "Copy URL"}
                  </button>
                </div>
              </div>
            </section>
          ) : (
            <section className="rounded-2xl border border-white/10 bg-ink-800 shadow-sm p-6">
              <p className="text-xs uppercase tracking-widest text-ink-200">
                Not eligible yet
              </p>
              <p className="mt-2 text-sm text-ink-100">
                {reasonLabel ||
                  "This badge is reserved for healthcare practices that meet HAWK's posture bar."}
              </p>
              {data.eligibility.vertical && (
                <p className="mt-2 text-xs text-ink-200">
                  Detected vertical: <span className="text-ink-100">{data.eligibility.vertical}</span>
                </p>
              )}
              {typeof data.eligibility.readiness_pct === "number" && (
                <p className="mt-1 text-xs text-ink-200">
                  Insurance readiness: <span className="text-ink-100">{data.eligibility.readiness_pct}%</span>
                  {" "}— need {data.eligibility.readiness_floor}%.
                </p>
              )}
              <Link
                href="/portal/journey"
                className="mt-4 inline-block text-sm text-signal hover:underline"
              >
                Open your journey to see what&apos;s unlocking next →
              </Link>
            </section>
          )}
        </>
      )}
    </div>
  );
}
