"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
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

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-zinc-500">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-700 border-t-[#00C48C]" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-50">Attacker simulation</h1>
        <p className="mt-2 text-sm text-zinc-500">
          A weekly red-team style narrative based on your latest HAWK findings — not a guarantee of how a real actor
          would behave, but a structured way to prioritize fixes.
        </p>
        {weekStart && (
          <p className="mt-1 text-xs text-zinc-600">Week starting {weekStart}</p>
        )}
      </div>

      {!bodyMd ? (
        <p className="rounded-lg border border-zinc-800 bg-zinc-900/40 px-4 py-8 text-center text-sm text-zinc-500">
          No briefing yet. After your first scheduled run, this page will show the latest narrative.
        </p>
      ) : (
        <article className="prose prose-invert prose-sm max-w-none rounded-xl border border-zinc-800 bg-zinc-950/50 p-6 prose-headings:text-zinc-100 prose-p:text-zinc-300 prose-li:text-zinc-300">
          {title && <h2 className="!mt-0 text-lg font-semibold text-zinc-100">{title}</h2>}
          <ReactMarkdown>{bodyMd}</ReactMarkdown>
        </article>
      )}

      <p className="text-center text-sm text-zinc-600">
        <Link href="/portal" className="text-[#00C48C] hover:underline">
          Back to portal home
        </Link>
      </p>
    </div>
  );
}
