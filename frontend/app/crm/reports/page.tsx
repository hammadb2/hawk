"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/components/providers/auth-provider";
import { crmReportsApi } from "@/lib/crm-api";

function cents(n: number) {
  return `$${(n / 100).toLocaleString("en-CA", { minimumFractionDigits: 0 })}`;
}

export default function ReportsPage() {
  const { token } = useAuth();
  const [revenue, setRevenue] = useState<any>(null);
  const [pipeline, setPipeline] = useState<any>(null);
  const [commissions, setCommissions] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    Promise.all([
      crmReportsApi.revenue(token),
      crmReportsApi.pipeline(token),
      crmReportsApi.commissions(token),
    ]).then(([r, p, c]) => { setRevenue(r); setPipeline(p); setCommissions(c); }).finally(() => setLoading(false));
  }, [token]);

  if (loading) return <p className="text-text-secondary text-sm">Loading reports…</p>;

  return (
    <div className="max-w-4xl mx-auto flex flex-col gap-6">
      <h1 className="text-xl font-semibold">Reports</h1>

      {/* Revenue */}
      {revenue && (
        <div className="bg-white border border-surface-3 rounded-lg p-5">
          <h2 className="font-medium mb-3">Revenue</h2>
          <div className="flex gap-8 mb-4">
            <div>
              <p className="text-xs text-text-secondary">Total MRR</p>
              <p className="text-2xl font-bold text-green-600">{cents(revenue.total_mrr_cents)}</p>
            </div>
            <div>
              <p className="text-xs text-text-secondary">Active Clients</p>
              <p className="text-2xl font-bold">{revenue.active_clients}</p>
            </div>
          </div>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-3">
                <th className="text-left py-2 text-xs text-text-secondary font-medium">Rep</th>
                <th className="text-right py-2 text-xs text-text-secondary font-medium">MRR</th>
                <th className="text-right py-2 text-xs text-text-secondary font-medium">Clients</th>
              </tr>
            </thead>
            <tbody>
              {revenue.by_rep?.map((r: any) => (
                <tr key={r.crm_user_id} className="border-b border-surface-3 last:border-0">
                  <td className="py-2">{r.rep_name || "—"}</td>
                  <td className="py-2 text-right">{cents(r.mrr_cents)}</td>
                  <td className="py-2 text-right">{r.active_clients}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pipeline */}
      {pipeline && (
        <div className="bg-white border border-surface-3 rounded-lg p-5">
          <h2 className="font-medium mb-3">Pipeline by Stage</h2>
          <div className="flex flex-col gap-2">
            {pipeline.stages?.map((s: any) => (
              <div key={s.stage} className="flex items-center gap-3">
                <span className="text-xs text-text-secondary w-28 capitalize">{s.stage.replace("_", " ")}</span>
                <div className="flex-1 bg-surface-2 rounded-full h-2">
                  <div
                    className="bg-purple-500 h-2 rounded-full"
                    style={{ width: pipeline.total > 0 ? `${(s.count / pipeline.total) * 100}%` : "0%" }}
                  />
                </div>
                <span className="text-xs font-medium w-6 text-right">{s.count}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Commissions */}
      {commissions && (
        <div className="bg-white border border-surface-3 rounded-lg p-5">
          <h2 className="font-medium mb-3">Commission Summary</h2>
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-surface-3">
                <th className="text-left py-2 text-xs text-text-secondary font-medium">Rep</th>
                <th className="text-right py-2 text-xs text-text-secondary font-medium">Total Earned</th>
                <th className="text-right py-2 text-xs text-text-secondary font-medium">Paid</th>
                <th className="text-right py-2 text-xs text-text-secondary font-medium">Unpaid</th>
              </tr>
            </thead>
            <tbody>
              {commissions.reps?.map((r: any) => (
                <tr key={r.crm_user_id} className="border-b border-surface-3 last:border-0">
                  <td className="py-2">{r.name || "—"}</td>
                  <td className="py-2 text-right">{cents(r.total_earned_cents)}</td>
                  <td className="py-2 text-right text-green-600">{cents(r.paid_cents)}</td>
                  <td className="py-2 text-right text-orange-600">{cents(r.unpaid_cents)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
