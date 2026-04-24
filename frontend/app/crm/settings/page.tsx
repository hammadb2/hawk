"use client";

import { useCallback, useMemo, useState } from "react";
import toast from "react-hot-toast";
import { useLiveEffect } from "@/lib/hooks/use-refresh-signal";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { createClient } from "@/lib/supabase/client";
import { crmPageSubtitle, crmPageTitle, crmSurfaceCard } from "@/lib/crm/crm-surface";
import { SettingsTabs, type TabId, TABS } from "@/components/crm/settings/settings-tabs";
import { GeneralSection } from "@/components/crm/settings/sections/general-section";
import { OutreachSection } from "@/components/crm/settings/sections/outreach-section";
import { CampaignsSection } from "@/components/crm/settings/sections/campaigns-section";
import { DiscoverySection } from "@/components/crm/settings/sections/discovery-section";
import { ScannerSection } from "@/components/crm/settings/sections/scanner-section";
import { TeamSection } from "@/components/crm/settings/sections/team-section";
import { NotificationsSection } from "@/components/crm/settings/sections/notifications-section";
import { IntegrationsSection } from "@/components/crm/settings/sections/integrations-section";
import { DangerZoneSection } from "@/components/crm/settings/sections/danger-section";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "";

export type SettingsMap = Record<string, string>;

export default function CrmSettingsPage() {
  const { profile } = useCrmAuth();
  const supabase = useMemo(() => createClient(), []);
  const [settings, setSettings] = useState<SettingsMap>({});
  const [dirty, setDirty] = useState<SettingsMap>({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState<TabId>("general");

  const authHeader = useCallback(async (): Promise<string | null> => {
    const {
      data: { session },
    } = await supabase.auth.getSession();
    return session?.access_token ? `Bearer ${session.access_token}` : null;
  }, [supabase]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const token = await authHeader();
      if (!token) {
        setLoading(false);
        return;
      }
      const res = await fetch(`${API_URL}/api/crm/settings`, {
        headers: { Authorization: token },
        cache: "no-store",
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        toast.error(`Failed to load settings: ${body.detail ?? res.status}`);
        setLoading(false);
        return;
      }
      const body = (await res.json()) as { settings: SettingsMap };
      setSettings(body.settings ?? {});
      setDirty({});
    } catch (e) {
      toast.error(`Failed to load settings: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  }, [authHeader]);

  useLiveEffect(() => {
    if (profile?.role === "ceo") void load();
    else setLoading(false);
  }, [profile?.role, load]);

  const setField = useCallback((key: string, value: string) => {
    setDirty((prev) => ({ ...prev, [key]: value }));
  }, []);

  const value = useCallback(
    (key: string, fallback = "") => dirty[key] ?? settings[key] ?? fallback,
    [dirty, settings],
  );

  const hasDirty = Object.keys(dirty).length > 0;

  const save = useCallback(async () => {
    if (!hasDirty) return;
    setSaving(true);
    try {
      const token = await authHeader();
      if (!token) throw new Error("Not signed in");
      const res = await fetch(`${API_URL}/api/crm/settings`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Authorization: token },
        body: JSON.stringify({ updates: dirty }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
      setSettings((prev) => ({ ...prev, ...dirty }));
      setDirty({});
      toast.success("Settings saved");
    } catch (e) {
      toast.error(`Save failed: ${(e as Error).message}`);
    } finally {
      setSaving(false);
    }
  }, [authHeader, dirty, hasDirty]);

  const resetToDefaults = useCallback(async () => {
    if (!window.confirm("Reset every setting to its default value? This cannot be undone.")) return;
    setSaving(true);
    try {
      const token = await authHeader();
      if (!token) throw new Error("Not signed in");
      const res = await fetch(`${API_URL}/api/crm/settings/reset`, {
        method: "POST",
        headers: { Authorization: token },
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.detail ?? `HTTP ${res.status}`);
      }
      toast.success("Settings reset to defaults");
      await load();
    } catch (e) {
      toast.error(`Reset failed: ${(e as Error).message}`);
    } finally {
      setSaving(false);
    }
  }, [authHeader, load]);

  if (profile?.role !== "ceo") {
    return (
      <div className="mx-auto max-w-3xl space-y-6">
        <div>
          <h1 className={crmPageTitle}>Settings</h1>
          <p className={crmPageSubtitle}>Only the CEO can modify CRM settings.</p>
        </div>
        <div className={`${crmSurfaceCard} p-5 text-sm text-ink-200`}>
          Contact your CEO if you need a setting changed.
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className={crmPageTitle}>Settings</h1>
          <p className={crmPageSubtitle}>
            System-wide configuration. Changes apply immediately — no deploy required.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {hasDirty && (
            <span className="text-xs text-signal">
              {Object.keys(dirty).length} unsaved change{Object.keys(dirty).length === 1 ? "" : "s"}
            </span>
          )}
          <button
            onClick={() => setDirty({})}
            disabled={!hasDirty || saving}
            className="rounded-lg border border-[#1e1e2e] bg-[#0d0d14] px-3 py-2 text-xs text-ink-100 hover:bg-[#14141f] disabled:opacity-40"
          >
            Discard
          </button>
          <button
            onClick={() => void save()}
            disabled={!hasDirty || saving}
            className="rounded-lg bg-signal-400 px-4 py-2 text-xs font-semibold text-white hover:bg-signal disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save changes"}
          </button>
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-[220px_minmax(0,1fr)]">
        <SettingsTabs active={activeTab} onChange={setActiveTab} tabs={TABS} />

        <div className="space-y-6">
          {loading ? (
            <div className={`${crmSurfaceCard} p-12 text-center text-sm text-ink-200`}>Loading…</div>
          ) : (
            <>
              {activeTab === "general" && <GeneralSection value={value} onChange={setField} />}
              {activeTab === "outreach" && <OutreachSection value={value} onChange={setField} />}
              {activeTab === "campaigns" && <CampaignsSection value={value} onChange={setField} />}
              {activeTab === "discovery" && <DiscoverySection value={value} onChange={setField} />}
              {activeTab === "scanner" && <ScannerSection value={value} onChange={setField} />}
              {activeTab === "team" && <TeamSection value={value} onChange={setField} />}
              {activeTab === "notifications" && <NotificationsSection value={value} onChange={setField} />}
              {activeTab === "integrations" && <IntegrationsSection value={value} />}
              {activeTab === "danger" && (
                <DangerZoneSection onReset={() => void resetToDefaults()} disabled={saving} />
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
