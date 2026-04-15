"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { portalApi } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import toast from "react-hot-toast";

export default function PortalSettingsPage() {
  const supabase = useMemo(() => createClient(), []);
  const [loading, setLoading] = useState(true);
  const [email, setEmail] = useState("");
  const [companyName, setCompanyName] = useState<string | null>(null);
  const [domainInput, setDomainInput] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const {
        data: { user },
      } = await supabase.auth.getUser();
      if (!user) return;
      setEmail((user.email || "").trim());

      const { data: cpp } = await supabase
        .from("client_portal_profiles")
        .select("domain,company_name")
        .eq("user_id", user.id)
        .maybeSingle();

      if (cpp) {
        setCompanyName(cpp.company_name);
        setDomainInput((cpp.domain || "").trim());
      }
    } finally {
      setLoading(false);
    }
  }, [supabase]);

  useEffect(() => {
    void load();
  }, [load]);

  async function saveDomain() {
    const {
      data: { session },
    } = await supabase.auth.getSession();
    if (!session?.access_token) {
      toast.error("Sign in again to continue.");
      return;
    }
    const d = domainInput.trim();
    if (!d) {
      toast.error("Enter a domain.");
      return;
    }
    setSaving(true);
    try {
      await portalApi.setPrimaryDomain({ domain: d }, session.access_token);
      toast.success("Monitoring domain updated.");
      await load();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not save.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-slate-600">
        <div className="h-10 w-10 animate-spin rounded-full border-2 border-slate-200 border-t-emerald-500" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-xl space-y-8">
      <div>
        <Link href="/portal" className="text-sm text-slate-600 hover:text-emerald-600">
          ← Back to dashboard
        </Link>
        <h1 className="mt-4 text-2xl font-semibold text-slate-900">Settings</h1>
        <p className="mt-1 text-sm text-slate-600">Account and monitoring domain for your HAWK subscription.</p>
      </div>

      <section className="rounded-2xl border border-slate-200 bg-white shadow-sm p-6">
        <h2 className="text-sm font-medium uppercase tracking-wide text-slate-600">Account</h2>
        <div className="mt-4 space-y-3 text-sm">
          <div>
            <span className="text-slate-600">Sign-in email</span>
            <p className="mt-0.5 font-mono text-slate-800">{email || "—"}</p>
          </div>
          {companyName ? (
            <div>
              <span className="text-slate-600">Organization</span>
              <p className="mt-0.5 text-slate-800">{companyName}</p>
            </div>
          ) : null}
        </div>
      </section>

      <section className="rounded-2xl border border-slate-200 bg-white shadow-sm p-6">
        <h2 className="text-sm font-medium uppercase tracking-wide text-slate-600">Monitored domain</h2>
        <p className="mt-2 text-sm leading-relaxed text-slate-600">
          This is the primary website or app domain we use for scans and reporting. If you signed up with a generic email
          (Gmail, Outlook, etc.), set your real company domain here. You can update it anytime.
        </p>
        <div className="mt-4 space-y-2">
          <Label className="text-slate-600">Domain</Label>
          <Input
            type="text"
            autoComplete="off"
            placeholder="company.com"
            value={domainInput}
            onChange={(e) => setDomainInput(e.target.value)}
            className="border-slate-200 bg-white text-slate-900 placeholder:text-slate-500"
          />
          <p className="text-xs text-slate-500">Omit https:// and www — e.g. acme.com</p>
        </div>
        <Button
          type="button"
          className="mt-4 bg-emerald-500 font-semibold text-white hover:bg-emerald-600"
          disabled={saving || !domainInput.trim()}
          onClick={() => void saveDomain()}
        >
          {saving ? "Saving…" : "Save domain"}
        </Button>
      </section>
    </div>
  );
}
