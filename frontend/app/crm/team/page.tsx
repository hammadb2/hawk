"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/components/providers/auth-provider";
import { crmTeamApi } from "@/lib/crm-api";
import type { CRMUserStats } from "@/lib/crm-types";

export default function TeamPage() {
  const { token } = useAuth();
  const [reps, setReps] = useState<CRMUserStats[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAdd, setShowAdd] = useState(false);
  const [form, setForm] = useState({ email: "", password: "", first_name: "", last_name: "", crm_role: "sales_rep", monthly_target: 0 });
  const [error, setError] = useState("");

  const load = async () => {
    if (!token) return;
    try { setReps(await crmTeamApi.list(token)); }
    finally { setLoading(false); }
  };

  useEffect(() => { load(); }, [token]);

  const addRep = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token) return;
    try {
      await crmTeamApi.create(token, form);
      setShowAdd(false);
      setForm({ email: "", password: "", first_name: "", last_name: "", crm_role: "sales_rep", monthly_target: 0 });
      load();
    } catch (err: any) { setError(err.message); }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h1 className="text-xl font-semibold">Team</h1>
        <button onClick={() => setShowAdd(!showAdd)} className="bg-purple-600 text-white px-4 py-1.5 rounded text-sm hover:bg-purple-700">
          + Add Rep
        </button>
      </div>

      {showAdd && (
        <div className="bg-white border border-surface-3 rounded-lg p-5 mb-4">
          <h2 className="font-medium mb-3">Add CRM User</h2>
          <form onSubmit={addRep} className="grid grid-cols-2 gap-3">
            {[["email", "Email *"], ["password", "Password *"], ["first_name", "First Name"], ["last_name", "Last Name"]].map(([key, label]) => (
              <div key={key}>
                <label className="text-xs text-text-secondary block mb-1">{label}</label>
                <input
                  type={key === "password" ? "password" : "text"}
                  value={(form as any)[key]}
                  onChange={(e) => setForm((f) => ({ ...f, [key]: e.target.value }))}
                  className="w-full border border-surface-3 rounded px-3 py-1.5 text-sm"
                />
              </div>
            ))}
            <div>
              <label className="text-xs text-text-secondary block mb-1">Role</label>
              <select value={form.crm_role} onChange={(e) => setForm((f) => ({ ...f, crm_role: e.target.value }))} className="w-full border border-surface-3 rounded px-2 py-1.5 text-sm">
                <option value="sales_rep">Sales Rep</option>
                <option value="team_lead">Team Lead</option>
                <option value="head_of_sales">Head of Sales</option>
                <option value="ceo">CEO</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-text-secondary block mb-1">Monthly Target (closes)</label>
              <input type="number" value={form.monthly_target} onChange={(e) => setForm((f) => ({ ...f, monthly_target: +e.target.value }))} className="w-full border border-surface-3 rounded px-3 py-1.5 text-sm" />
            </div>
            {error && <p className="col-span-2 text-red-500 text-xs">{error}</p>}
            <div className="col-span-2 flex justify-end gap-2">
              <button type="button" onClick={() => setShowAdd(false)} className="px-4 py-2 text-sm text-text-secondary">Cancel</button>
              <button type="submit" className="px-4 py-2 text-sm bg-purple-600 text-white rounded hover:bg-purple-700">Create</button>
            </div>
          </form>
        </div>
      )}

      <div className="bg-white border border-surface-3 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="border-b border-surface-3 bg-surface-2">
            <tr>
              <th className="text-left px-4 py-2.5 text-xs text-text-secondary font-medium">Name</th>
              <th className="text-left px-4 py-2.5 text-xs text-text-secondary font-medium">Role</th>
              <th className="text-center px-4 py-2.5 text-xs text-text-secondary font-medium">Closes MTD</th>
              <th className="text-center px-4 py-2.5 text-xs text-text-secondary font-medium">Prospects</th>
              <th className="text-left px-4 py-2.5 text-xs text-text-secondary font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {reps.map((rep) => (
              <tr key={rep.id} className="border-b border-surface-3 last:border-0 hover:bg-surface-2">
                <td className="px-4 py-2.5">
                  <Link href={`/crm/team/${rep.id}`} className="font-medium hover:text-purple-600">
                    {[rep.first_name, rep.last_name].filter(Boolean).join(" ") || rep.email}
                  </Link>
                  <p className="text-xs text-text-secondary">{rep.email}</p>
                </td>
                <td className="px-4 py-2.5 text-text-secondary text-xs capitalize">{rep.crm_role.replace("_", " ")}</td>
                <td className="px-4 py-2.5 text-center">
                  <span className="font-semibold text-purple-700">{rep.closes_this_month}</span>
                  {rep.monthly_target > 0 && <span className="text-text-secondary text-xs"> / {rep.monthly_target}</span>}
                </td>
                <td className="px-4 py-2.5 text-center text-text-secondary">{rep.total_prospects}</td>
                <td className="px-4 py-2.5">
                  <span className={`text-xs px-2 py-0.5 rounded ${rep.is_active ? "bg-green-100 text-green-700" : "bg-gray-100 text-gray-500"}`}>
                    {rep.is_active ? "Active" : "Inactive"}
                  </span>
                </td>
              </tr>
            ))}
            {!loading && reps.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-10 text-center text-text-secondary">No team members yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
