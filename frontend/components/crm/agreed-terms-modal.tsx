"use client";

import { useState } from "react";

export interface AgreedTerms {
  [key: string]: string;
  role: string;
  base_rate: string;
  rate_frequency: string;
  bonus_structure: string;
  start_date: string;
  custom_clauses: string;
}

interface Props {
  open: boolean;
  onClose: () => void;
  onConfirm: (terms: AgreedTerms) => void;
  hireName: string;
  hireRole: string;
}

export function AgreedTermsModal({ open, onClose, onConfirm, hireName, hireRole }: Props) {
  const [terms, setTerms] = useState<AgreedTerms>({
    role: hireRole,
    base_rate: "",
    rate_frequency: "monthly",
    bonus_structure: "",
    start_date: new Date().toISOString().split("T")[0],
    custom_clauses: "",
  });

  if (!open) return null;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onConfirm(terms);
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="w-full max-w-lg rounded-2xl border border-slate-200 bg-white p-6 shadow-xl">
        <h2 className="text-lg font-semibold text-slate-900">Agreed Terms for {hireName}</h2>
        <p className="mt-1 text-sm text-slate-500">
          These terms will be used to generate the contract during onboarding.
        </p>

        <form onSubmit={handleSubmit} className="mt-5 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-700">Role</label>
              <input
                type="text"
                value={terms.role}
                onChange={(e) => setTerms({ ...terms, role: e.target.value })}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-900 focus:border-emerald-400 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-700">Start Date</label>
              <input
                type="date"
                value={terms.start_date}
                onChange={(e) => setTerms({ ...terms, start_date: e.target.value })}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-900 focus:border-emerald-400 focus:outline-none"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-700">Base Rate</label>
              <input
                type="text"
                placeholder="e.g. $500"
                value={terms.base_rate}
                onChange={(e) => setTerms({ ...terms, base_rate: e.target.value })}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-emerald-400 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-700">Rate Frequency</label>
              <select
                value={terms.rate_frequency}
                onChange={(e) => setTerms({ ...terms, rate_frequency: e.target.value })}
                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-900 focus:border-emerald-400 focus:outline-none"
              >
                <option value="hourly">Hourly</option>
                <option value="weekly">Weekly</option>
                <option value="biweekly">Biweekly</option>
                <option value="monthly">Monthly</option>
              </select>
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-700">Bonus Structure</label>
            <textarea
              placeholder="Describe bonus tiers, commission rates, performance bonuses..."
              value={terms.bonus_structure}
              onChange={(e) => setTerms({ ...terms, bonus_structure: e.target.value })}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-emerald-400 focus:outline-none"
              rows={3}
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-slate-700">Custom Clauses (optional)</label>
            <textarea
              placeholder="Any additional terms or clauses..."
              value={terms.custom_clauses}
              onChange={(e) => setTerms({ ...terms, custom_clauses: e.target.value })}
              className="w-full rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-emerald-400 focus:outline-none"
              rows={2}
            />
          </div>

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg px-4 py-2 text-sm text-slate-600 hover:text-slate-900 transition"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="rounded-lg bg-emerald-600 px-5 py-2 text-sm font-semibold text-white hover:bg-emerald-700 transition"
            >
              Confirm &amp; Send Invite
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
