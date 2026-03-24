"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { useAuth } from "@/components/providers/auth-provider";
import { useCRM } from "@/components/crm/crm-provider";
import { crmClientsApi } from "@/lib/crm-api";
import { ChurnRiskBadge } from "@/components/crm/churn-risk-badge";
import type { Client } from "@/lib/crm-types";

function cents(n: number) {
  return `$${(n / 100).toLocaleString("en-CA")}`;
}

export default function ClientDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { token } = useAuth();
  const { hasFullVisibility } = useCRM();
  const [client, setClient] = useState<Client | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [churnMsg, setChurnMsg] = useState("");

  useEffect(() => {
    if (!token || !id) return;
    crmClientsApi.get(token, id).then(setClient).catch((e) => setError(e.message)).finally(() => setLoading(false));
  }, [token, id]);

  const markChurned = async () => {
    if (!token || !id) return;
    try {
      const updated = await crmClientsApi.markChurned(token, id, "Manually marked churned");
      setClient(updated);
    } catch (e: any) {
      setError(e.message);
    }
  };

  if (loading) return <p className="text-text-secondary text-sm">Loading…</p>;
  if (error) return <p className="text-red-500 text-sm">{error}</p>;
  if (!client) return null;

  return (
    <div className="max-w-2xl mx-auto">
      <div className="flex items-center gap-2 mb-4">
        <Link href="/crm/clients" className="text-text-secondary text-sm hover:text-purple-600">← Clients</Link>
        <span className="text-text-secondary">/</span>
        <span className="text-sm">{client.company_name}</span>
      </div>

      <div className="bg-white border border-surface-3 rounded-lg p-6">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h1 className="text-xl font-semibold">{client.company_name}</h1>
            {client.domain && <p className="text-sm text-text-secondary">{client.domain}</p>}
          </div>
          <div className="flex items-center gap-2">
            <span className={`text-xs px-2 py-0.5 rounded font-medium ${client.status === "active" ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}>
              {client.status}
            </span>
            <ChurnRiskBadge risk={client.churn_risk} />
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 text-sm mb-6">
          <div>
            <p className="text-xs text-text-secondary">Monthly Revenue</p>
            <p className="text-2xl font-bold text-green-600">{cents(client.mrr)}<span className="text-sm font-normal text-text-secondary">/mo</span></p>
          </div>
          <div>
            <p className="text-xs text-text-secondary">Closed By</p>
            <p className="font-medium">{client.closed_by_rep_name || "—"}</p>
          </div>
          <div>
            <p className="text-xs text-text-secondary">Contact</p>
            <p>{client.contact_name || "—"}</p>
            {client.contact_email && <p className="text-xs text-text-secondary">{client.contact_email}</p>}
          </div>
          <div>
            <p className="text-xs text-text-secondary">Closed Date</p>
            <p>{client.closed_at ? new Date(client.closed_at).toLocaleDateString() : "—"}</p>
          </div>
          {client.churn_risk_reason && (
            <div className="col-span-2">
              <p className="text-xs text-text-secondary">Churn Reason</p>
              <p>{client.churn_risk_reason}</p>
            </div>
          )}
        </div>

        {hasFullVisibility && client.status === "active" && (
          <div className="border-t border-surface-3 pt-4">
            <button
              onClick={markChurned}
              className="px-4 py-2 text-sm border border-red-200 text-red-600 rounded hover:bg-red-50"
            >
              Mark as Churned
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
