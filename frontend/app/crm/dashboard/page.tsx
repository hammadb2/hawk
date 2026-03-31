"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { CeoLiveDashboard } from "@/components/crm/dashboard/ceo-live-dashboard";
import type { Prospect } from "@/lib/crm/types";

export default function CrmDashboardPage() {
  const { authReady, profileFetched, session, profile } = useCrmAuth();
  const router = useRouter();
  const supabase = useMemo(() => createClient(), []);
  const [hotLeads, setHotLeads] = useState<Prospect[]>([]);

  const loadHot = useCallback(async () => {
    if (!profile || !["ceo", "hos"].includes(profile.role)) {
      setHotLeads([]);
      return;
    }
    const { data } = await supabase.from("prospects").select("*").eq("is_hot", true).order("last_activity_at", { ascending: false }).limit(8);
    setHotLeads((data as Prospect[]) ?? []);
  }, [profile, supabase]);

  useEffect(() => {
    if (!authReady) return;
    if (!session) router.replace("/crm/login");
  }, [authReady, session, router]);

  useEffect(() => {
    void loadHot();
  }, [loadHot]);

  if (!authReady || !session) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-zinc-500">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-700 border-t-emerald-500" />
      </div>
    );
  }

  if (!profileFetched) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-zinc-500">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-700 border-t-emerald-500" />
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="space-y-4 rounded-xl border border-amber-500/40 bg-amber-500/5 p-6 text-sm text-amber-100">
        <p className="font-medium text-amber-50">CRM profile not found</p>
        <p className="text-zinc-400">
          There is no row in <code className="text-zinc-300">public.profiles</code> for your signed-in user, or Supabase
          blocked the read (RLS). Check the browser console for <code className="text-zinc-300">[CRM auth]</code> logs.
        </p>
        <p className="text-zinc-400">
          Your auth user id is <code className="break-all text-emerald-400">{session.user.id}</code> — the{" "}
          <code className="text-zinc-300">profiles.id</code> column must match exactly.
        </p>
      </div>
    );
  }

  const roleLabel = profile.role.replace("_", " ");
  const checklist = profile.onboarding_checklist as Record<string, boolean> | null | undefined;
  const onboardingDone =
    !!profile.onboarding_completed_at ||
    (checklist && ["whatsapp", "video", "first_prospect", "profile"].every((k) => checklist[k]));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-50">Dashboard</h1>
        <p className="text-sm text-zinc-500">
          Signed in as <span className="text-zinc-300">{profile.full_name ?? profile.email}</span> —{" "}
          <span className="uppercase text-emerald-400">{roleLabel}</span>
        </p>
      </div>

      {!onboardingDone && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 text-sm text-amber-100">
          Complete your first-login checklist.{" "}
          <Link href="/crm/onboarding" className="font-medium underline">
            Continue onboarding
          </Link>
        </div>
      )}

      {["ceo", "hos"].includes(profile.role) && (
        <CeoLiveDashboard supabase={supabase} profile={profile} />
      )}

      {["ceo", "hos"].includes(profile.role) && hotLeads.length > 0 && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-500/5 p-4">
          <h2 className="text-sm font-semibold text-rose-200">Hot leads</h2>
          <ul className="mt-2 space-y-2">
            {hotLeads.map((p) => (
              <li key={p.id}>
                <Link href={`/crm/prospects/${p.id}`} className="text-sm text-zinc-200 hover:text-emerald-400 hover:underline">
                  {p.company_name ?? p.domain} <span className="text-zinc-500">({p.domain})</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Link
          href="/crm/pipeline"
          className="rounded-xl border border-zinc-800 bg-zinc-900/60 p-5 transition-colors hover:border-emerald-500/40"
        >
          <div className="text-sm font-medium text-emerald-400">Pipeline</div>
          <p className="mt-1 text-sm text-zinc-500">Kanban, list, table — click a card for the full prospect profile.</p>
        </Link>
        <Link
          href="/crm/onboarding"
          className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-5 transition-colors hover:border-emerald-500/40"
        >
          <div className="text-sm font-medium text-zinc-300">Onboarding</div>
          <p className="mt-1 text-sm text-zinc-500">First-login checklist for new reps.</p>
        </Link>
      </div>
    </div>
  );
}
