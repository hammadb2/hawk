"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/components/providers/auth-provider";
import { crmCommissionsApi } from "@/lib/crm-api";
import type { Commission } from "@/lib/crm-types";

function cents(n: number) {
  return `$${(n / 100).toLocaleString("en-CA", { minimumFractionDigits: 0 })}`;
}

export default function EarningsPage() {
  const { token } = useAuth();
  const [commissions, setCommissions] = useState<Commission[]>([]);
  const [loading, setLoading] = useState(true);
  const [paidFilter, setPaidFilter] = useState<"all" | "paid" | "unpaid">("all");

  useEffect(() => {
    if (!token) return;
    const paid = paidFilter === "all" ? undefined : paidFilter === "paid";
    crmCommissionsApi.my(token, paid).then(setCommissions).finally(() => setLoading(false));
  }, [token, paidFilter]);

  const totalEarned = commissions.reduce((s, c) => s + c.amount, 0);
  const totalPaid = commissions.filter((c) => c.paid).reduce((s, c) => s + c.amount, 0);
  const totalUnpaid = commissions.filter((c) => !c.paid).reduce((s, c) => s + c.amount, 0);

  const closing = commissions.filter((c) => c.commission_type === "closing").reduce((s, c) => s + c.amount, 0);
  const residual = commissions.filter((c) => c.commission_type === "residual").reduce((s, c) => s + c.amount, 0);

  return (
    <div className="max-w-3xl mx-auto">
      <h1 className="text-xl font-semibold mb-6">💰 My Earnings</h1>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        {[
          { label: "Total Earned", value: cents(totalEarned) },
          { label: "Paid", value: cents(totalPaid) },
          { label: "Unpaid", value: cents(totalUnpaid) },
          { label: "Monthly Residual", value: cents(residual) },
        ].map(({ label, value }) => (
          <div key={label} className="bg-white border border-surface-3 rounded-lg p-4">
            <p className="text-xs text-text-secondary">{label}</p>
            <p className="text-xl font-bold mt-1">{value}</p>
          </div>
        ))}
      </div>

      <div className="bg-white border border-surface-3 rounded-lg overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-surface-3">
          <span className="font-medium text-sm">Commission History</span>
          <div className="flex border border-surface-3 rounded overflow-hidden">
            {(["all", "paid", "unpaid"] as const).map((f) => (
              <button
                key={f}
                onClick={() => setPaidFilter(f)}
                className={`px-3 py-1 text-xs capitalize ${paidFilter === f ? "bg-purple-600 text-white" : "text-text-secondary hover:bg-surface-2"}`}
              >
                {f}
              </button>
            ))}
          </div>
        </div>
        <table className="w-full text-sm">
          <thead className="border-b border-surface-3 bg-surface-2">
            <tr>
              <th className="text-left px-4 py-2.5 text-xs text-text-secondary font-medium">Type</th>
              <th className="text-right px-4 py-2.5 text-xs text-text-secondary font-medium">Amount</th>
              <th className="text-left px-4 py-2.5 text-xs text-text-secondary font-medium">Period</th>
              <th className="text-left px-4 py-2.5 text-xs text-text-secondary font-medium">Status</th>
              <th className="text-left px-4 py-2.5 text-xs text-text-secondary font-medium">Date</th>
            </tr>
          </thead>
          <tbody>
            {commissions.map((c) => (
              <tr key={c.id} className="border-b border-surface-3 last:border-0 hover:bg-surface-2">
                <td className="px-4 py-2.5 capitalize">{c.commission_type}</td>
                <td className="px-4 py-2.5 text-right font-medium">{cents(c.amount)}</td>
                <td className="px-4 py-2.5 text-xs text-text-secondary">
                  {c.period_start && c.period_end
                    ? `${c.period_start} – ${c.period_end}`
                    : "—"}
                </td>
                <td className="px-4 py-2.5">
                  <span className={`text-xs px-2 py-0.5 rounded ${c.paid ? "bg-green-100 text-green-700" : "bg-yellow-100 text-yellow-700"}`}>
                    {c.paid ? "Paid" : "Unpaid"}
                  </span>
                </td>
                <td className="px-4 py-2.5 text-xs text-text-secondary">{new Date(c.created_at).toLocaleDateString()}</td>
              </tr>
            ))}
            {!loading && commissions.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-10 text-center text-text-secondary">No commissions yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
