"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import toast from "react-hot-toast";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";

import { readApiErrorResponse } from "@/lib/crm/api-error";
import { CRM_API_BASE_URL } from "@/lib/crm/api-url";
import { crmFieldSurface, crmPageSubtitle, crmPageTitle, crmSurfaceCard } from "@/lib/crm/crm-surface";

export default function ClientEnterpriseDomainsPage() {
  const params = useParams();
  const router = useRouter();
  const clientId = typeof params?.id === "string" ? params.id : "";
  const supabase = useMemo(() => createClient(), []);
  const { authReady, session, profile } = useCrmAuth();

  const [primary, setPrimary] = useState<string>("");
  const [lines, setLines] = useState<string[]>(["", "", "", ""]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    if (!clientId) return;
    setLoading(true);
    const { data, error } = await supabase
      .from("clients")
      .select("domain,monitored_domains")
      .eq("id", clientId)
      .single();
    if (error) {
      toast.error(error.message);
      setLoading(false);
      return;
    }
    setPrimary((data?.domain as string) ?? "");
    const extras = (Array.isArray(data?.monitored_domains) ? data?.monitored_domains : []) as string[];
    const next = ["", "", "", ""];
    extras.slice(0, 4).forEach((d, i) => {
      next[i] = String(d);
    });
    setLines(next);
    setLoading(false);
  }, [clientId, supabase]);

  useEffect(() => {
    if (authReady && session && clientId) void load();
  }, [authReady, session, clientId, load]);

  const save = async () => {
    if (!session?.access_token) {
      toast.error("Not signed in");
      return;
    }
    const domains = lines.map((s) => s.trim()).filter(Boolean);
    setSaving(true);
    try {
      const res = await fetch(`${CRM_API_BASE_URL}/api/crm/clients/${clientId}/monitored-domains`, {
        method: "PATCH",
        headers: {
          Authorization: `Bearer ${session.access_token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ domains }),
      });
      if (!res.ok) {
        toast.error(await readApiErrorResponse(res));
        setSaving(false);
        return;
      }
      toast.success("Monitored domains saved");
      await load();
    } catch {
      toast.error("Request failed");
    }
    setSaving(false);
  };

  if (!authReady || !session || !profile) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-slate-600">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-emerald-500" />
      </div>
    );
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-lg py-16 text-center text-slate-600">
        <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-emerald-500" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-lg space-y-6">
      <div>
        <button
          type="button"
          onClick={() => router.back()}
          className="text-sm text-slate-400 hover:text-emerald-400"
        >
          ← Back
        </button>
        <h1 className={`mt-2 ${crmPageTitle}`}>Enterprise domains</h1>
        <p className={crmPageSubtitle}>
          Primary domain stays <span className="text-slate-300">{primary || "—"}</span>. Add up to four extra apex
          domains for monitoring and portal rollup.
        </p>
      </div>

      <div className={`space-y-3 p-4 ${crmSurfaceCard}`}>
        <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Additional apex domains</p>
        {lines.map((v, i) => (
          <input
            key={i}
            type="text"
            value={v}
            onChange={(e) => {
              const next = [...lines];
              next[i] = e.target.value;
              setLines(next);
            }}
            placeholder={`example${i + 1}.com`}
            className={`w-full px-3 py-2 text-sm placeholder:text-slate-500 ${crmFieldSurface}`}
          />
        ))}
      </div>

      <div className="flex flex-wrap gap-3">
        <button
          type="button"
          disabled={saving}
          onClick={() => void save()}
          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save"}
        </button>
        <Link href="/crm/clients" className="rounded-lg border border-[#1e1e2e] bg-[#0d0d14] px-4 py-2 text-sm text-slate-300 hover:bg-[#1a1a24]">
          All clients
        </Link>
      </div>
    </div>
  );
}
