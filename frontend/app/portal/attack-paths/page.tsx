"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

type AttackPath = {
  name?: string;
  steps?: string[];
  likelihood?: string;
  impact?: string;
};

export default function PortalAttackPathsPage() {
  const [paths, setPaths] = useState<AttackPath[]>([]);
  const [domain, setDomain] = useState<string | null>(null);
  const [company, setCompany] = useState<string | null>(null);
  const [scanAt, setScanAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      setLoading(true);
      try {
        const res = await fetch("/api/portal/attack-paths");
        const j = (await res.json()) as {
          paths?: AttackPath[];
          domain?: string;
          company_name?: string;
          scan_at?: string;
          error?: string;
        };
        if (!res.ok) {
          setErr(j.error || "Could not load attack paths");
          return;
        }
        setPaths(Array.isArray(j.paths) ? j.paths : []);
        setDomain(j.domain || null);
        setCompany(j.company_name || null);
        setScanAt(j.scan_at || null);
      } catch {
        setErr("Network error");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Attack path scenarios</h1>
        <p className="mt-1 text-sm text-slate-600">
          How an attacker could chain your real findings into a breach — from your latest HAWK scan. Same analysis our
          team uses in the CRM; shown here in plain language.
        </p>
        {(company || domain) && (
          <p className="mt-2 text-sm text-slate-600">
            {company}
            {domain ? ` · ${domain}` : ""}
            {scanAt ? ` · Scan ${new Date(scanAt).toLocaleString()}` : ""}
          </p>
        )}
        <Link href="/portal" className="mt-2 inline-block text-sm text-emerald-600 hover:underline">
          ← Back to overview
        </Link>
      </div>

      {loading && <p className="text-slate-600">Loading…</p>}
      {err && <p className="text-rose-400">{err}</p>}

      {!loading && !err && paths.length === 0 && (
        <div className="rounded-xl border border-slate-200 bg-white shadow-sm p-6 text-sm text-slate-600">
          No attack path narrative yet. After your next full scan completes, HAWK will map the top breach scenarios
          here.
        </div>
      )}

      {!loading && !err && paths.length > 0 && (
        <div className="space-y-6">
          {paths.map((p, pi) => (
            <section
              key={pi}
              className="rounded-2xl border border-emerald-200/80 bg-gradient-to-b from-emerald-50/90 to-white p-6"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-lg font-semibold text-emerald-900">{p.name || `Scenario ${pi + 1}`}</span>
                {p.likelihood && (
                  <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium uppercase text-slate-600 ring-1 ring-slate-200/80">
                    {p.likelihood} likelihood
                  </span>
                )}
              </div>
              {p.impact && <p className="mt-3 text-sm leading-relaxed text-slate-700">{p.impact}</p>}
              {p.steps && p.steps.length > 0 && (
                <div className="mt-6">
                  <p className="text-xs font-semibold uppercase tracking-wide text-emerald-700">Chain</p>
                  <div className="mt-3 flex flex-wrap items-start gap-1">
                    {p.steps.map((step, si) => (
                      <div key={si} className="flex items-center gap-1">
                        {si > 0 && (
                          <span className="px-1 text-emerald-500" aria-hidden>
                            →
                          </span>
                        )}
                        <span className="rounded-lg border border-slate-200 bg-slate-100 px-3 py-2 text-sm text-slate-800">
                          {step}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
