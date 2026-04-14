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
      <div className="flex min-h-[40vh] items-center justify-center text-slate-600">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-emerald-500" />
      </div>
    );
  }

  if (!profileFetched) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-slate-600">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-emerald-500" />
      </div>
    );
  }

  if (!profile) {
    return (
      <div className="space-y-4 rounded-xl border border-amber-200/90 bg-amber-50 p-6 text-sm text-amber-950">
        <p className="font-medium text-amber-900">CRM profile not found</p>
        <p className="text-slate-600">
          There is no row in <code className="text-slate-700">public.profiles</code> for your signed-in user, or Supabase
          blocked the read (RLS). Check the browser console for <code className="text-slate-700">[CRM auth]</code> logs.
        </p>
        <p className="text-slate-600">
          Your auth user id is <code className="break-all text-emerald-600">{session.user.id}</code> — the{" "}
          <code className="text-slate-700">profiles.id</code> column must match exactly.
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
        <h1 className="text-2xl font-semibold text-slate-900">Dashboard</h1>
        <p className="text-sm text-slate-600">
          Signed in as <span className="text-slate-700">{profile.full_name ?? profile.email}</span> —{" "}
          <span className="uppercase text-emerald-600">{roleLabel}</span>
        </p>
      </div>

      {!onboardingDone && (
        <div className="rounded-xl border border-amber-200/80 bg-amber-50/90 p-4 text-sm text-amber-950">
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
        <div className="rounded-xl border border-rose-200/80 bg-rose-50/90 p-4">
          <h2 className="text-sm font-semibold text-rose-800">Hot leads</h2>
          <ul className="mt-2 space-y-2">
            {hotLeads.map((p) => (
              <li key={p.id}>
                <Link href={`/crm/prospects/${p.id}`} className="text-sm text-slate-800 hover:text-emerald-600 hover:underline">
                  {p.company_name ?? p.domain} <span className="text-slate-600">({p.domain})</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Link
          href="/crm/pipeline"
          className="rounded-xl border border-slate-200 bg-slate-50 p-5 transition-colors hover:border-emerald-500/40"
        >
          <div className="text-sm font-medium text-emerald-600">Pipeline</div>
          <p className="mt-1 text-sm text-slate-600">Kanban, list, table — click a card for the full prospect profile.</p>
        </Link>
        <Link
          href="/crm/onboarding"
          className="rounded-xl border border-slate-200 bg-white shadow-sm p-5 transition-colors hover:border-emerald-500/40"
        >
          <div className="text-sm font-medium text-slate-700">Onboarding</div>
          <p className="mt-1 text-sm text-slate-600">First-login checklist for new reps.</p>
        </Link>
      </div>
    </div>
  );
}
