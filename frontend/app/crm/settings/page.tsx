"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/components/providers/auth-provider";
import { crmReportsApi } from "@/lib/crm-api";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "https://hawk.akbstudios.com";

async function getSettings(token: string) {
  const res = await fetch(`${API_URL}/api/crm/settings`, { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) throw new Error("Failed to load settings");
  return res.json();
}

async function updateSettings(token: string, body: object) {
  const res = await fetch(`${API_URL}/api/crm/settings`, {
    method: "PUT",
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error("Failed to save settings");
  return res.json();
}

export default function CRMSettingsPage() {
  const { token } = useAuth();
  const [settings, setSettings] = useState<any>(null);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    if (!token) return;
    getSettings(token).then(setSettings).catch(() => {});
  }, [token]);

  const save = async () => {
    if (!token || !settings) return;
    setSaving(true); setMsg("");
    try {
      const updated = await updateSettings(token, {
        closing_commission_rate: settings.closing_commission_rate,
        residual_commission_rate: settings.residual_commission_rate,
        default_prospect_mrr_cents: settings.default_prospect_mrr_cents,
      });
      setSettings(updated);
      setMsg("Saved.");
    } catch (e: any) {
      setMsg(e.message);
    } finally {
      setSaving(false);
    }
  };

  if (!settings) return <p className="text-text-secondary text-sm">Loading…</p>;

  return (
    <div className="max-w-xl mx-auto">
      <h1 className="text-xl font-semibold mb-6">CRM Settings</h1>
      <div className="bg-white border border-surface-3 rounded-lg p-6 flex flex-col gap-4">
        <div>
          <label className="text-xs text-text-secondary block mb-1">Closing Commission Rate</label>
          <div className="flex items-center gap-2">
            <input
              type="number"
              step="0.01"
              min="0"
              max="1"
              value={settings.closing_commission_rate}
              onChange={(e) => setSettings((s: any) => ({ ...s, closing_commission_rate: +e.target.value }))}
              className="border border-surface-3 rounded px-3 py-2 text-sm w-32"
            />
            <span className="text-sm text-text-secondary">({(settings.closing_commission_rate * 100).toFixed(0)}% of first month MRR)</span>
          </div>
        </div>
        <div>
          <label className="text-xs text-text-secondary block mb-1">Residual Commission Rate</label>
          <div className="flex items-center gap-2">
            <input
              type="number"
              step="0.01"
              min="0"
              max="1"
              value={settings.residual_commission_rate}
              onChange={(e) => setSettings((s: any) => ({ ...s, residual_commission_rate: +e.target.value }))}
              className="border border-surface-3 rounded px-3 py-2 text-sm w-32"
            />
            <span className="text-sm text-text-secondary">({(settings.residual_commission_rate * 100).toFixed(0)}% of MRR per month)</span>
          </div>
        </div>
        <div>
          <label className="text-xs text-text-secondary block mb-1">Default Prospect MRR (cents)</label>
          <div className="flex items-center gap-2">
            <input
              type="number"
              value={settings.default_prospect_mrr_cents}
              onChange={(e) => setSettings((s: any) => ({ ...s, default_prospect_mrr_cents: +e.target.value }))}
              className="border border-surface-3 rounded px-3 py-2 text-sm w-32"
            />
            <span className="text-sm text-text-secondary">(${(settings.default_prospect_mrr_cents / 100).toFixed(0)})</span>
          </div>
        </div>
        <div className="border-t border-surface-3 pt-4 flex items-center justify-between">
          {msg && <span className={`text-sm ${msg === "Saved." ? "text-green-600" : "text-red-500"}`}>{msg}</span>}
          <button onClick={save} disabled={saving} className="ml-auto px-4 py-2 bg-purple-600 text-white text-sm rounded hover:bg-purple-700 disabled:opacity-50">
            {saving ? "Saving…" : "Save Settings"}
          </button>
        </div>
      </div>
    </div>
  );
}
