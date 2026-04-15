"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";

export default function PortalBenchmarkPage() {
  const [narrative, setNarrative] = useState<string | null>(null);
  const [scores, setScores] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      setLoading(true);
      try {
        const res = await fetch("/api/portal/benchmark");
        const j = (await res.json()) as {
          benchmark?: { narrative_md?: string; scores?: Record<string, unknown> };
          error?: string;
        };
        if (!res.ok) {
          setErr(j.error || "Could not load benchmark");
          return;
        }
        const b = j.benchmark;
        setNarrative(b?.narrative_md || null);
        setScores(b?.scores || null);
      } catch {
        setErr("Network error");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const you = scores?.you as number | undefined;
  const avg = scores?.industry_average as number | undefined;
  const top = scores?.top_quartile as number | undefined;
  const peerAvg = scores?.peer_scan_average as number | undefined;
  const peerN = scores?.peer_sample_size as number | undefined;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Competitor benchmark</h1>
        <p className="mt-1 text-sm text-slate-600">
          Your live score vs sector references, plus anonymized fast scans of suggested peer domains (never shown to
          those businesses — for your benchmarking only).
        </p>
        <Link href="/portal" className="mt-2 inline-block text-sm text-emerald-600 hover:underline">
          ← Back to overview
        </Link>
      </div>

      {loading && <p className="text-slate-600">Building your benchmark…</p>}
      {err && <p className="text-rose-400">{err}</p>}

      {you != null && (
        <div className="grid gap-4 rounded-2xl border border-slate-200 bg-white shadow-sm p-6 sm:grid-cols-2 lg:grid-cols-4">
          <div>
            <p className="text-xs uppercase text-slate-600">Your score</p>
            <p className="text-3xl font-bold tabular-nums text-emerald-600">{you}</p>
          </div>
          <div>
            <p className="text-xs uppercase text-slate-600">Sector average (ref.)</p>
            <p className="text-3xl font-bold tabular-nums text-slate-800">{avg ?? "—"}</p>
          </div>
          <div>
            <p className="text-xs uppercase text-slate-600">Top quartile (ref.)</p>
            <p className="text-3xl font-bold tabular-nums text-slate-800">{top ?? "—"}</p>
          </div>
          <div>
            <p className="text-xs uppercase text-slate-600">Peer sample (anon.)</p>
            <p className="text-3xl font-bold tabular-nums text-slate-800">
              {peerAvg != null ? peerAvg : "—"}
              {peerN != null && peerN > 0 ? (
                <span className="ml-1 text-base font-normal text-slate-600">n={peerN}</span>
              ) : null}
            </p>
          </div>
        </div>
      )}

      {narrative && (
        <article className="prose prose-slate prose-sm prose-headings:text-slate-900 prose-p:text-slate-600 prose-li:text-slate-600 max-w-none rounded-2xl border border-slate-200 bg-white shadow-sm p-6">
          <ReactMarkdown>{narrative}</ReactMarkdown>
        </article>
      )}
    </div>
  );
}
