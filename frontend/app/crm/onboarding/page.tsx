"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { Button } from "@/components/ui/button";
import toast from "react-hot-toast";

const KEYS = ["whatsapp", "video", "first_prospect", "profile"] as const;

const LABELS: Record<(typeof KEYS)[number], string> = {
  whatsapp: "Set up WhatsApp notifications",
  video: "Watch 3-min CRM training video",
  first_prospect: "Add first prospect",
  profile: "Complete profile",
};

export default function CrmOnboardingPage() {
  const supabase = useMemo(() => createClient(), []);
  const { profile, session, refreshProfile } = useCrmAuth();
  const [checklist, setChecklist] = useState<Record<string, boolean>>({});

  const load = useCallback(async () => {
    if (!session?.user?.id) return;
    const { data } = await supabase.from("profiles").select("onboarding_checklist").eq("id", session.user.id).single();
    const raw = (data?.onboarding_checklist as Record<string, boolean> | null) ?? {};
    const next: Record<string, boolean> = {};
    KEYS.forEach((k) => {
      next[k] = !!raw[k];
    });
    setChecklist(next);
  }, [session?.user?.id, supabase]);

  useEffect(() => {
    void load();
  }, [load]);

  async function toggle(key: (typeof KEYS)[number]) {
    if (!session?.user?.id) return;
    const next = { ...checklist, [key]: !checklist[key] };
    setChecklist(next);
    const { error } = await supabase.from("profiles").update({ onboarding_checklist: next }).eq("id", session.user.id);
    if (error) toast.error(error.message);
    else {
      toast.success("Saved");
      await refreshProfile();
    }
  }

  const allDone = KEYS.every((k) => checklist[k]);

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-50">First login checklist</h1>
        <p className="text-sm text-zinc-500">Complete these to get the most from HAWK CRM.</p>
      </div>
      <ul className="space-y-3">
        {KEYS.map((k) => (
          <li key={k} className="flex items-start gap-3 rounded-lg border border-zinc-800 bg-zinc-900/40 px-4 py-3">
            <input
              type="checkbox"
              className="mt-1 h-4 w-4"
              checked={!!checklist[k]}
              onChange={() => void toggle(k)}
            />
            <span className="text-sm text-zinc-200">{LABELS[k]}</span>
          </li>
        ))}
      </ul>
      {allDone && (
        <p className="text-sm text-emerald-400">You&apos;re all set. Head to the pipeline.</p>
      )}
      <Button asChild className="bg-emerald-600">
        <Link href="/crm/pipeline">Go to pipeline</Link>
      </Button>
    </div>
  );
}
