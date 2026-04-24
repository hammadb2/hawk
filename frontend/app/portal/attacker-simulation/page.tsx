"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useLiveEffect } from "@/lib/hooks/use-refresh-signal";
import Link from "next/link";
import { useRouter } from "next/navigation";
import ReactMarkdown from "react-markdown";
import { createClient } from "@/lib/supabase/client";

export default function PortalAttackerSimulationPage() {
  const supabase = useMemo(() => createClient(), []);
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [title, setTitle] = useState<string | null>(null);
  const [bodyMd, setBodyMd] = useState<string | null>(null);
  const [weekStart, setWeekStart] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const {
      data: { user },
    } = await supabase.auth.getUser();
    if (!user) {
      router.replace("/portal/login");
      setLoading(false);
      return;
    }

    const { data: cpp, error: e1 } = await supabase
      .from("client_portal_profiles")
      .select("client_id")
      .eq("user_id", user.id)
      .maybeSingle();

    if (e1 || !cpp) {
      setLoading(false);
      return;
    }

    const { data: rep } = await supabase
      .from("client_attacker_simulation_reports")
      .select("title,body_md,week_start")
      .eq("client_id", cpp.client_id)
      .order("week_start", { ascending: false })
      .limit(1)
      .maybeSingle();

    if (rep) {
      setTitle((rep.title as string) ?? null);
      setBodyMd((rep.body_md as string) ?? null);
      setWeekStart((rep.week_start as string) ?? null);
    } else {
      setTitle(null);
      setBodyMd(null);
      setWeekStart(null);
    }
    setLoading(false);
  }, [router, supabase]);

  useLiveEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-ink-200">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-white/10 border-t-signal" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink-0">Attacker simulation</h1>
        <p className="mt-2 text-sm text-ink-200">
          A weekly red-team style narrative based on your latest HAWK findings — not a guarantee of how a real actor
          would behave, but a structured way to prioritize fixes.
        </p>
        {weekStart && (
          <p className="mt-1 text-xs text-ink-0">Week starting {weekStart}</p>
        )}
      </div>

      {!bodyMd ? (
        <p className="rounded-lg border border-white/10 bg-ink-800 shadow-sm px-4 py-8 text-center text-sm text-ink-200">
          No briefing yet. After your first scheduled run, this page will show the latest narrative.
        </p>
      ) : (
        <article className="prose prose-invert prose-sm prose-headings:text-ink-0 prose-p:text-ink-200 prose-li:text-ink-200 max-w-none rounded-xl border border-white/10 bg-ink-800 p-6 prose-headings:text-ink-0 prose-p:text-ink-100 prose-li:text-ink-100">
          {title && <h2 className="!mt-0 text-lg font-semibold text-ink-0">{title}</h2>}
          <ReactMarkdown>{bodyMd}</ReactMarkdown>
        </article>
      )}

      <p className="text-center text-sm text-ink-0">
        <Link href="/portal" className="text-signal hover:underline">
          Back to portal home
        </Link>
      </p>
    </div>
  );
}
