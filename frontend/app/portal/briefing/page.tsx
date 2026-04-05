"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";

export default function PortalBriefingPage() {
  const [md, setMd] = useState<string | null>(null);
  const [title, setTitle] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      setLoading(true);
      try {
        const res = await fetch("/api/portal/threat-briefing");
        const j = (await res.json()) as { briefing?: { title?: string; body_md?: string } | null; error?: string };
        if (!res.ok) {
          setErr(j.error || "Could not load briefing");
          return;
        }
        if (!j.briefing?.body_md) {
          setMd(null);
          setTitle(null);
          return;
        }
        setTitle(j.briefing.title || "Weekly briefing");
        setMd(j.briefing.body_md);
      } catch {
        setErr("Network error");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-50">Weekly AI threat briefing</h1>
        <p className="mt-1 text-sm text-zinc-500">
          Every Monday we email a sector-focused briefing. The latest copy is saved here.
        </p>
        <Link href="/portal" className="mt-2 inline-block text-sm text-[#00C48C] hover:underline">
          ← Back to overview
        </Link>
      </div>

      {loading && <p className="text-zinc-500">Loading…</p>}
      {err && <p className="text-rose-400">{err}</p>}
      {!loading && !err && !md && (
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-6 text-sm text-zinc-400">
          No briefing yet for this week. After the scheduled job runs (Mondays ~7am MT), your analyst-style digest will
          appear here and in your inbox.
        </div>
      )}
      {md && (
        <article className="prose prose-invert prose-sm max-w-none rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6 prose-headings:text-zinc-100">
          {title && <h2 className="!mt-0 text-lg font-semibold text-zinc-100">{title}</h2>}
          <ReactMarkdown>{md}</ReactMarkdown>
        </article>
      )}
    </div>
  );
}
