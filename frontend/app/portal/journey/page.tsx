"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

type Milestone = { milestone_key: string; achieved_at: string; metadata?: Record<string, unknown> };
type ScanPt = { id: string; created_at: string; hawk_score: number | null; grade: string | null };
type JourneyEvent = { type: string; at: string; title: string; detail?: string };

const LABELS: Record<string, string> = {
  first_critical_fix: "First critical fix verified",
  score_above_70: "Score above 70",
  thirty_days_clean: "30 days clean",
  hawk_certified: "HAWK Certified",
};

export default function PortalJourneyPage() {
  const [milestones, setMilestones] = useState<Milestone[]>([]);
  const [scans, setScans] = useState<ScanPt[]>([]);
  const [events, setEvents] = useState<JourneyEvent[]>([]);
  const [certifiedAt, setCertifiedAt] = useState<string | null>(null);
  const [readiness, setReadiness] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      setLoading(true);
      try {
        const res = await fetch("/api/portal/journey");
        const j = (await res.json()) as {
          milestones?: Milestone[];
          scans?: ScanPt[];
          events?: JourneyEvent[];
          certified_at?: string | null;
          readiness?: number | null;
          error?: string;
        };
        if (!res.ok) {
          setErr(j.error || "Could not load journey");
          return;
        }
        setMilestones(j.milestones || []);
        setScans(j.scans || []);
        setEvents(j.events || []);
        setCertifiedAt(j.certified_at ?? null);
        setReadiness(typeof j.readiness === "number" ? j.readiness : null);
      } catch {
        setErr("Network error");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const maxScore = useMemo(() => {
    const xs = scans.map((s) => s.hawk_score).filter((x): x is number => typeof x === "number");
    return xs.length ? Math.max(...xs, 100) : 100;
  }, [scans]);

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-50">Security journey</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Scans, verified fixes, milestones, and certification — your full security journey with HAWK.
        </p>
        <Link href="/portal" className="mt-2 inline-block text-sm text-[#00C48C] hover:underline">
          ← Back to overview
        </Link>
      </div>

      {loading && <p className="text-zinc-500">Loading…</p>}
      {err && <p className="text-rose-400">{err}</p>}

      {!loading && !err && (
        <>
          <section className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-500">Timeline</h2>
            <ul className="mt-4 max-h-72 space-y-3 overflow-y-auto pr-1 text-sm">
              {events.length === 0 && <li className="text-zinc-500">No events yet — scans and fixes will appear here.</li>}
              {events.map((ev, i) => (
                <li
                  key={`${ev.at}-${ev.type}-${i}`}
                  className="flex gap-3 border-b border-zinc-800/80 pb-3 last:border-0 last:pb-0"
                >
                  <span className="shrink-0 text-xs text-zinc-500">
                    {ev.at ? new Date(ev.at).toLocaleString() : "—"}
                  </span>
                  <div>
                    <p className="font-medium text-zinc-200">{ev.title}</p>
                    {ev.detail ? <p className="mt-0.5 text-xs text-zinc-500">{ev.detail}</p> : null}
                  </div>
                </li>
              ))}
            </ul>
          </section>

          <section className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-500">Score over time</h2>
            <div className="mt-6 flex h-40 items-end gap-1">
              {scans.length === 0 && <p className="text-sm text-zinc-500">No scans yet.</p>}
              {scans.map((s) => {
                const v = s.hawk_score ?? 0;
                const h = Math.round((v / maxScore) * 100);
                return (
                  <div key={s.id} className="flex min-w-[8px] flex-1 flex-col items-center gap-1">
                    <div
                      className="w-full rounded-t bg-[#00C48C]/80"
                      style={{ height: `${Math.max(8, h)}%` }}
                      title={`${v} — ${new Date(s.created_at).toLocaleDateString()}`}
                    />
                  </div>
                );
              })}
            </div>
            <p className="mt-2 text-xs text-zinc-500">
              Readiness today: {readiness ?? "—"} · Certified: {certifiedAt ? new Date(certifiedAt).toLocaleDateString() : "—"}
            </p>
          </section>

          <section className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-zinc-500">Milestone badges</h2>
            <ul className="mt-4 grid gap-3 sm:grid-cols-2">
              {milestones.length === 0 && <li className="text-sm text-zinc-500">Complete fixes to unlock streak badges.</li>}
              {milestones.map((m) => (
                <li
                  key={m.milestone_key}
                  className="flex items-center gap-3 rounded-xl border border-[#00C48C]/25 bg-[#00C48C]/5 px-4 py-3"
                >
                  <span className="text-xl">🏅</span>
                  <div>
                    <p className="font-medium text-zinc-100">{LABELS[m.milestone_key] || m.milestone_key}</p>
                    <p className="text-xs text-zinc-500">{new Date(m.achieved_at).toLocaleString()}</p>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  );
}
