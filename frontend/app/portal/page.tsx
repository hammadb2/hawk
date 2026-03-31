"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";

type PortalProfile = {
  id: string;
  client_id: string;
  company_name: string | null;
  domain: string | null;
};

type ClientRow = {
  id: string;
  prospect_id: string | null;
  mrr_cents: number;
  onboarding_sequence_status: string | null;
};

type ScanRow = {
  id: string;
  hawk_score: number | null;
  grade: string | null;
  findings: Record<string, unknown> | null;
  created_at: string;
};

export default function PortalHomePage() {
  const supabase = useMemo(() => createClient(), []);
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [portal, setPortal] = useState<PortalProfile | null>(null);
  const [client, setClient] = useState<ClientRow | null>(null);
  const [scan, setScan] = useState<ScanRow | null>(null);

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
      .select("id,client_id,company_name,domain")
      .eq("user_id", user.id)
      .maybeSingle();

    if (e1 || !cpp) {
      setPortal(null);
      setClient(null);
      setScan(null);
      setLoading(false);
      return;
    }

    setPortal(cpp as PortalProfile);

    const { data: cl, error: e2 } = await supabase.from("clients").select("id,prospect_id,mrr_cents,onboarding_sequence_status").eq("id", cpp.client_id).single();

    if (e2 || !cl) {
      setClient(null);
      setScan(null);
      setLoading(false);
      return;
    }

    setClient(cl as ClientRow);

    if (cl.prospect_id) {
      const { data: scans } = await supabase
        .from("crm_prospect_scans")
        .select("id,hawk_score,grade,findings,created_at")
        .eq("prospect_id", cl.prospect_id)
        .order("created_at", { ascending: false })
        .limit(1);
      setScan((scans?.[0] as ScanRow) ?? null);
    } else {
      setScan(null);
    }

    setLoading(false);
  }, [router, supabase]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-zinc-500">
        <div className="h-10 w-10 animate-spin rounded-full border-2 border-zinc-700 border-t-[#00C48C]" />
      </div>
    );
  }

  if (!portal || !client) {
    return (
      <div className="mx-auto max-w-lg rounded-xl border border-amber-500/30 bg-amber-500/5 p-6 text-sm text-amber-100">
        <p className="font-medium text-amber-50">No client portal is linked to this account yet.</p>
        <p className="mt-2 text-zinc-400">
          After your first HAWK subscription checkout, we&apos;ll email you a magic link. If you believe this is an error,
          contact your CSM.
        </p>
        <Button asChild className="mt-4 bg-[#00C48C] text-[#07060C]">
          <Link href="/portal/login">Back to login</Link>
        </Button>
      </div>
    );
  }

  const score = scan?.hawk_score ?? 0;
  const grade = scan?.grade ?? "—";
  const findingsRaw = scan?.findings;
  const criticalPreview =
    findingsRaw && typeof findingsRaw === "object" && "critical" in findingsRaw
      ? String((findingsRaw as { critical?: unknown }).critical)
      : null;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-50">{portal.company_name ?? portal.domain ?? "Your organization"}</h1>
        <p className="text-sm text-zinc-500">{portal.domain}</p>
      </div>

      <section className="grid gap-6 lg:grid-cols-3">
        <div className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6 lg:col-span-1">
          <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">HAWK score</p>
          <div className="mt-4 flex items-end gap-2">
            <span className="text-5xl font-bold tabular-nums text-[#00C48C]">{score}</span>
            <span className="pb-2 text-2xl text-zinc-400">/100</span>
          </div>
          <p className="mt-2 text-sm text-zinc-400">
            Grade <span className="font-medium text-zinc-200">{grade}</span>
            <span className="ml-2 text-emerald-500/80">↑</span> trend (coming soon)
          </p>
        </div>

        <div className="rounded-2xl border border-zinc-800 bg-zinc-900/40 p-6 lg:col-span-2">
          <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">Monitoring</p>
          <ul className="mt-4 space-y-3 text-sm text-zinc-300">
            <li className="flex items-center gap-2">
              <span className="h-2 w-2 animate-pulse rounded-full bg-[#00C48C]" />
              Live surface monitoring active
            </li>
            <li>Onboarding: {client.onboarding_sequence_status ?? "—"}</li>
          </ul>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        <div className="rounded-xl border border-rose-500/20 bg-rose-500/5 p-4">
          <h2 className="text-sm font-semibold text-rose-200">Critical issues</h2>
          <p className="mt-2 text-sm text-zinc-400">
            {criticalPreview ? criticalPreview.slice(0, 280) : "No critical findings in the latest scan payload. Full guided view ships in the next iteration."}
          </p>
        </div>
        <div className="rounded-xl border border-emerald-500/20 bg-emerald-500/5 p-4">
          <h2 className="text-sm font-semibold text-emerald-200">Fixed this month</h2>
          <p className="mt-2 text-sm text-zinc-400">Track resolved items here after you mark fixes (Phase 2+).</p>
        </div>
        <div className="rounded-xl border border-zinc-800 bg-zinc-900/50 p-4">
          <h2 className="text-sm font-semibold text-zinc-200">Reports</h2>
          <p className="mt-2 text-sm text-zinc-400">Monthly PDF download will appear here when generated.</p>
        </div>
      </section>

      <section className="rounded-2xl border border-zinc-800 bg-zinc-900/30 p-6">
        <h2 className="text-lg font-semibold text-zinc-100">Ask HAWK</h2>
        <p className="mt-2 text-sm text-zinc-500">
          Personalised security Q&amp;A from your scan context is planned for Phase 4. You&apos;ll chat here with streaming
          answers.
        </p>
      </section>
    </div>
  );
}
