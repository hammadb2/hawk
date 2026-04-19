"use client";

import { useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { CeoLiveDashboard } from "@/components/crm/dashboard/ceo-live-dashboard";
import { useHotLeads } from "@/lib/crm/hooks";

function DashboardSkeleton() {
  return (
    <div className="space-y-6">
      <div className="space-y-2">
        <div className="h-8 w-48 animate-pulse rounded-lg bg-crmSurface" />
        <div className="h-4 w-72 animate-pulse rounded-lg bg-crmSurface2" />
      </div>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-28 animate-pulse rounded-xl bg-crmSurface" />
        ))}
      </div>
    </div>
  );
}

export default function CrmDashboardPage() {
  const { authReady, profileFetched, session, profile } = useCrmAuth();
  const router = useRouter();
  const supabase = useMemo(() => createClient(), []);
  const showHot = !!profile && ["ceo", "hos"].includes(profile.role);
  const { data: hotLeads = [] } = useHotLeads(showHot);

  useEffect(() => {
    if (!authReady) return;
    if (!session) router.replace("/crm/login");
  }, [authReady, session, router]);

  if (!authReady || !session) {
    return <DashboardSkeleton />;
  }

  if (!profileFetched) {
    return <DashboardSkeleton />;
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
        <h1 className="text-2xl font-semibold text-white">Dashboard</h1>
        <p className="text-sm text-slate-400">
          Signed in as <span className="text-slate-200">{profile.full_name ?? profile.email}</span> —{" "}
          <span className="font-medium uppercase tracking-wider text-emerald-400">{roleLabel}</span>
        </p>
      </div>

      {!onboardingDone && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-100">
          Complete your first-login checklist.{" "}
          <Link href="/crm/onboarding" className="font-medium text-amber-400 underline">
            Continue onboarding
          </Link>
        </div>
      )}

      {["ceo", "hos"].includes(profile.role) && (
        <CeoLiveDashboard supabase={supabase} profile={profile} accessToken={session.access_token ?? null} />
      )}

      {["ceo", "hos"].includes(profile.role) && hotLeads.length > 0 && (
        <div className="rounded-xl border border-rose-500/30 bg-rose-950/40 p-4">
          <h2 className="text-sm font-semibold text-rose-300">Hot leads</h2>
          <ul className="mt-2 space-y-2">
            {hotLeads.map((p) => (
              <li key={p.id}>
                <Link href={`/crm/prospects/${p.id}`} className="text-sm text-slate-200 hover:text-emerald-400 hover:underline">
                  {p.company_name ?? p.domain} <span className="text-slate-500">({p.domain})</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Link
          href="/crm/pipeline"
          className="rounded-xl border border-crmBorder bg-crmSurface p-5 shadow-lg transition-colors hover:border-emerald-500/40"
        >
          <div className="text-sm font-medium text-emerald-400">Pipeline</div>
          <p className="mt-1 text-sm text-slate-400">Kanban, list, table — click a card for the full prospect profile.</p>
        </Link>
        <Link
          href="/crm/onboarding"
          className="rounded-xl border border-crmBorder bg-crmSurface2 p-5 shadow-lg transition-colors hover:border-emerald-500/40"
        >
          <div className="text-sm font-medium text-white">Onboarding</div>
          <p className="mt-1 text-sm text-slate-400">First-login checklist for new reps.</p>
        </Link>
      </div>
    </div>
  );
}
