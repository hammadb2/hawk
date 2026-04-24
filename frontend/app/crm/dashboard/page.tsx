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
      <div className="space-y-4 rounded-xl border border-signal/30/90 bg-signal/10 p-6 text-sm text-signal-800">
        <p className="font-medium text-signal-700">CRM profile not found</p>
        <p className="text-ink-200">
          There is no row in <code className="text-ink-100">public.profiles</code> for your signed-in user, or Supabase
          blocked the read (RLS). Check the browser console for <code className="text-ink-100">[CRM auth]</code> logs.
        </p>
        <p className="text-ink-200">
          Your auth user id is <code className="break-all text-signal">{session.user.id}</code> — the{" "}
          <code className="text-ink-100">profiles.id</code> column must match exactly.
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
        <p className="text-sm text-ink-200">
          Signed in as <span className="text-ink-100">{profile.full_name ?? profile.email}</span> —{" "}
          <span className="font-medium uppercase tracking-wider text-signal">{roleLabel}</span>
        </p>
      </div>

      {!onboardingDone && (
        <div className="rounded-xl border border-signal/30 bg-signal/10 p-4 text-sm text-amber-100">
          Complete your first-login checklist.{" "}
          <Link href="/crm/onboarding" className="font-medium text-signal underline">
            Continue onboarding
          </Link>
        </div>
      )}

      {["ceo", "hos"].includes(profile.role) && (
        <CeoLiveDashboard supabase={supabase} profile={profile} accessToken={session.access_token ?? null} />
      )}

      {["ceo", "hos"].includes(profile.role) && hotLeads.length > 0 && (
        <div className="rounded-xl border border-red/30 bg-red/15 p-4">
          <h2 className="text-sm font-semibold text-red">Hot leads</h2>
          <ul className="mt-2 space-y-2">
            {hotLeads.map((p) => (
              <li key={p.id}>
                <Link href={`/crm/prospects/${p.id}`} className="text-sm text-ink-100 hover:text-signal hover:underline">
                  {p.company_name ?? p.domain} <span className="text-ink-0">({p.domain})</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Link
          href="/crm/pipeline"
          className="rounded-xl border border-crmBorder bg-crmSurface p-5 shadow-lg transition-colors hover:border-signal/40"
        >
          <div className="text-sm font-medium text-signal">Pipeline</div>
          <p className="mt-1 text-sm text-ink-200">Kanban, list, table — click a card for the full prospect profile.</p>
        </Link>
        <Link
          href="/crm/onboarding"
          className="rounded-xl border border-crmBorder bg-crmSurface2 p-5 shadow-lg transition-colors hover:border-signal/40"
        >
          <div className="text-sm font-medium text-white">Onboarding</div>
          <p className="mt-1 text-sm text-ink-200">First-login checklist for new reps.</p>
        </Link>
      </div>
    </div>
  );
}
