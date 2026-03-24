"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/components/providers/auth-provider";
import { crmClientsApi } from "@/lib/crm-api";
import { ChurnRiskBadge } from "@/components/crm/churn-risk-badge";
import type { Client } from "@/lib/crm-types";

function cents(n: number) {
  return `$${(n / 100).toLocaleString("en-CA", { minimumFractionDigits: 0 })}`;
}

export default function ClientsPage() {
  const { token } = useAuth();
  const [clients, setClients] = useState<Client[]>([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState("active");
  const [churnFilter, setChurnFilter] = useState("");
  const [search, setSearch] = useState("");

  const load = async () => {
    if (!token) return;
    try {
      const data = await crmClientsApi.list(token, {
        status: statusFilter || undefined,
        churn_risk: churnFilter || undefined,
        search: search || undefined,
      });
      setClients(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { setLoading(true); load(); }, [token, statusFilter, churnFilter, search]);

  const totalMRR = clients.reduce((sum, c) => sum + c.mrr, 0);

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-xl font-semibold">Clients</h1>
          {!loading && (
            <p className="text-sm text-text-secondary mt-0.5">
              {clients.length} clients · MRR: {cents(totalMRR)}/mo
            </p>
          )}
        </div>
        <div className="flex items-center gap-2">
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search…"
            className="border border-surface-3 rounded px-3 py-1.5 text-sm w-40"
          />
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="border border-surface-3 rounded px-2 py-1.5 text-sm">
            <option value="">All</option>
            <option value="active">Active</option>
            <option value="churned">Churned</option>
          </select>
          <select value={churnFilter} onChange={(e) => setChurnFilter(e.target.value)} className="border border-surface-3 rounded px-2 py-1.5 text-sm">
            <option value="">All Risk</option>
            <option value="high">High Risk</option>
            <option value="medium">Medium Risk</option>
            <option value="low">Low Risk</option>
          </select>
        </div>
      </div>

      <div className="bg-white border border-surface-3 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="border-b border-surface-3 bg-surface-2">
            <tr>
              <th className="text-left px-4 py-2.5 text-xs text-text-secondary font-medium">Company</th>
              <th className="text-left px-4 py-2.5 text-xs text-text-secondary font-medium">MRR</th>
              <th className="text-left px-4 py-2.5 text-xs text-text-secondary font-medium">Churn Risk</th>
              <th className="text-left px-4 py-2.5 text-xs text-text-secondary font-medium">Status</th>
              <th className="text-left px-4 py-2.5 text-xs text-text-secondary font-medium">Closed By</th>
              <th className="text-left px-4 py-2.5 text-xs text-text-secondary font-medium">Closed</th>
            </tr>
          </thead>
          <tbody>
            {clients.map((c) => (
              <tr key={c.id} className="border-b border-surface-3 last:border-0 hover:bg-surface-2">
                <td className="px-4 py-2.5">
                  <Link href={`/crm/clients/${c.id}`} className="font-medium hover:text-purple-600">{c.company_name}</Link>
                  {c.domain && <p className="text-xs text-text-secondary">{c.domain}</p>}
                </td>
                <td className="px-4 py-2.5 font-medium">{cents(c.mrr)}</td>
                <td className="px-4 py-2.5"><ChurnRiskBadge risk={c.churn_risk} /></td>
                <td className="px-4 py-2.5">
                  <span className={`text-xs px-2 py-0.5 rounded font-medium ${c.status === "active" ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}>
                    {c.status}
                  </span>
                </td>
                <td className="px-4 py-2.5 text-xs text-text-secondary">{c.closed_by_rep_name || "—"}</td>
                <td className="px-4 py-2.5 text-xs text-text-secondary">{c.closed_at ? new Date(c.closed_at).toLocaleDateString() : "—"}</td>
              </tr>
            ))}
            {!loading && clients.length === 0 && (
              <tr><td colSpan={6} className="px-4 py-10 text-center text-text-secondary">No clients found.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
