"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/components/providers/auth-provider";
import { useCRM } from "@/components/crm/crm-provider";
import { crmTeamApi } from "@/lib/crm-api";
import type { CRMUserStats } from "@/lib/crm-types";

function cents(n: number) {
  return `$${(n / 100).toLocaleString("en-CA", { minimumFractionDigits: 0 })}`;
}

export default function TeamMemberPage() {
  const { id } = useParams<{ id: string }>();
  const { token } = useAuth();
  const { hasFullVisibility } = useCRM();
  const [rep, setRep] = useState<CRMUserStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token || !id) return;
    crmTeamApi.get(token, id).then(setRep).catch((e) => setError(e.message)).finally(() => setLoading(false));
  }, [token, id]);

  const deactivate = async () => {
    if (!token || !id) return;
    try {
      const updated = await crmTeamApi.deactivate(token, id);
      setRep((r) => r ? { ...r, is_active: false } : r);
    } catch (e: any) { setError(e.message); }
  };

  if (loading) return <p className="text-text-secondary text-sm">Loading…</p>;
  if (error) return <p className="text-red-500 text-sm">{error}</p>;
  if (!rep) return null;

  const name = [rep.first_name, rep.last_name].filter(Boolean).join(" ") || rep.email;

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center gap-2 mb-4">
        <Link href="/crm/team" className="text-text-secondary text-sm hover:text-purple-600">← Team</Link>
        <span className="text-text-secondary">/</span>
        <span className="text-sm">{name}</span>
      </div>

      <div className="bg-white border border-surface-3 rounded-lg p-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h1 className="text-xl font-semibold">{name}</h1>
            <p className="text-sm text-text-secondary">{rep.email}</p>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-xs capitalize bg-purple-50 text-purple-700 px-2 py-0.5 rounded">{rep.crm_role.replace("_", " ")}</span>
            <span className={`text-xs px-2 py-0.5 rounded ${rep.is_active ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}>
              {rep.is_active ? "Active" : "Inactive"}
            </span>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-4 mb-6">
          <div className="bg-surface-2 rounded-lg p-3 text-center">
            <p className="text-2xl font-bold text-purple-700">{rep.closes_this_month}</p>
            <p className="text-xs text-text-secondary mt-1">Closes This Month</p>
            {rep.monthly_target > 0 && <p className="text-xs text-text-secondary">Target: {rep.monthly_target}</p>}
          </div>
          <div className="bg-surface-2 rounded-lg p-3 text-center">
            <p className="text-2xl font-bold">{rep.total_prospects}</p>
            <p className="text-xs text-text-secondary mt-1">Total Prospects</p>
          </div>
          <div className="bg-surface-2 rounded-lg p-3 text-center">
            <p className="text-lg font-bold text-green-600">{cents(rep.commission_this_month)}</p>
            <p className="text-xs text-text-secondary mt-1">Commission MTD</p>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 text-sm mb-4">
          <div>
            <p className="text-xs text-text-secondary">Monthly Target</p>
            <p>{rep.monthly_target} closes</p>
          </div>
          <div>
            <p className="text-xs text-text-secondary">Added</p>
            <p>{new Date(rep.created_at).toLocaleDateString()}</p>
          </div>
        </div>

        {hasFullVisibility && rep.is_active && (
          <div className="border-t border-surface-3 pt-4">
            <button onClick={deactivate} className="px-4 py-2 text-sm border border-red-200 text-red-600 rounded hover:bg-red-50">
              Deactivate Rep
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
