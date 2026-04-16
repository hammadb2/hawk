"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import toast from "react-hot-toast";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { ProfileTabs } from "@/components/crm/profile/profile-tabs";
import type { Profile } from "@/lib/crm/types";

export default function MyProfilePage() {
  const { id } = useParams<{ id: string }>();
  const supabase = useMemo(() => createClient(), []);
  const { authReady, profileFetched, session, profile: myProfile } = useCrmAuth();
  const [target, setTarget] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    if (!id) return;
    setLoading(true);
    const { data, error } = await supabase
      .from("profiles")
      .select("id, email, full_name, role, role_type, status")
      .eq("id", id)
      .maybeSingle();
    if (error) toast.error(error.message);
    setTarget((data as Profile) ?? null);
    setLoading(false);
  }, [id, supabase]);

  useEffect(() => {
    if (authReady && session) void load();
  }, [authReady, session, load]);

  if (!authReady || !profileFetched || loading) {
    return (
      <div className="flex min-h-[200px] items-center justify-center text-slate-600">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-emerald-500" />
      </div>
    );
  }

  if (!session || !myProfile) {
    return (
      <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-6 text-sm text-amber-700">
        Please sign in to view this profile.
      </div>
    );
  }

  if (!target) {
    return <p className="p-6 text-sm text-slate-600">Profile not found.</p>;
  }

  const isOwn = myProfile.id === id;
  const isCeo = myProfile.role === "ceo";
  const isHos = myProfile.role === "hos";
  const isVaManager = myProfile.role_type === "va_manager";
  const targetIsVa = target.role_type === "va_outreach";

  // Edit: own profile always, CEO/HoS always, VA manager for VAs
  const canEdit = isOwn || isCeo || isHos || (isVaManager && targetIsVa);

  // Bank details visible to: owner, CEO/HoS, VA manager for VAs
  const showBankDetails = isOwn || isCeo || isHos || (isVaManager && targetIsVa);

  // Delete docs: CEO only
  const canDeleteDocs = isCeo;

  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <Link href="/crm/dashboard" className="text-sm text-emerald-600 hover:underline">
        ← Back to dashboard
      </Link>

      <div>
        <h1 className="text-2xl font-semibold text-slate-900">
          {isOwn ? "My Profile" : target.full_name ?? target.email ?? "Profile"}
        </h1>
        <p className="mt-1 text-sm text-slate-600">
          {target.email} · <span className="capitalize">{target.role?.replace("_", " ")}</span>
          {target.status && (
            <span className={`ml-2 inline-block rounded px-2 py-0.5 text-xs font-medium ${target.status === "active" ? "bg-emerald-100 text-emerald-800" : "bg-slate-100 text-slate-600"}`}>
              {target.status}
            </span>
          )}
        </p>
      </div>

      <ProfileTabs
        targetProfileId={id}
        canEdit={canEdit}
        showBankDetails={showBankDetails}
        canDeleteDocs={canDeleteDocs}
      />
    </div>
  );
}
