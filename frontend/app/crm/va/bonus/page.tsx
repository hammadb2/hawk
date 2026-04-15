"use client";

import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/auth/crm-auth-context";
import Link from "next/link";

interface BonusMonth {
  month: string;
  avg_calls_per_day: number;
  days_reported: number;
  bonus_amount: number;
}

interface VaOption {
  id: string;
  full_name: string;
}

const BONUS_TIERS = [
  { threshold: 30, amount: 2000, label: "30+ calls/day → $2,000" },
  { threshold: 25, amount: 1500, label: "25-29 calls/day → $1,500" },
  { threshold: 20, amount: 1000, label: "20-24 calls/day → $1,000" },
  { threshold: 15, amount: 500, label: "15-19 calls/day → $500" },
];

function computeBonus(avgCalls: number): number {
  for (const tier of BONUS_TIERS) {
    if (avgCalls >= tier.threshold) return tier.amount;
  }
  return 0;
}

export default function VaBonusPage() {
  const { profile } = useCrmAuth();
  const supabase = createClient();

  const [vas, setVas] = useState<VaOption[]>([]);
  const [selectedVaId, setSelectedVaId] = useState<string>("");
  const [months, setMonths] = useState<BonusMonth[]>([]);
  const [loading, setLoading] = useState(true);

  const isManager =
    profile?.role === "ceo" ||
    profile?.role === "hos" ||
    profile?.role_type === "va_manager";

  useEffect(() => {
    async function loadVas() {
      const { data } = await supabase
        .from("va_profiles")
        .select("id, full_name")
        .eq("status", "active")
        .order("full_name");
      const list = (data ?? []) as VaOption[];
      setVas(list);

      // If current user is a VA, auto-select themselves
      if (!isManager && profile?.id) {
        const match = list.find(
          (v) => v.id === profile.id || v.full_name === profile.full_name
        );
        if (match) setSelectedVaId(match.id);
        else if (list.length > 0) setSelectedVaId(list[0].id);
      } else if (list.length > 0) {
        setSelectedVaId(list[0].id);
      }
    }
    loadVas();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!selectedVaId) return;

    async function loadBonus() {
      setLoading(true);
      const { data } = await supabase
        .from("va_daily_reports")
        .select("report_date, calls_booked")
        .eq("va_id", selectedVaId)
        .order("report_date", { ascending: false })
        .limit(90);

      const rows = (data ?? []) as { report_date: string; calls_booked: number }[];

      // Group by month
      const byMonth: Record<string, number[]> = {};
      for (const row of rows) {
        const month = row.report_date.slice(0, 7);
        if (!byMonth[month]) byMonth[month] = [];
        byMonth[month].push(row.calls_booked ?? 0);
      }

      const result: BonusMonth[] = Object.entries(byMonth)
        .sort(([a], [b]) => b.localeCompare(a))
        .map(([month, calls]) => {
          const avg = calls.length > 0 ? calls.reduce((s, c) => s + c, 0) / calls.length : 0;
          return {
            month,
            avg_calls_per_day: Math.round(avg * 10) / 10,
            days_reported: calls.length,
            bonus_amount: computeBonus(avg),
          };
        });

      setMonths(result);
      setLoading(false);
    }
    loadBonus();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedVaId]);

  const currentMonth = months[0];
  const pastMonths = months.slice(1);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-slate-900">Bonus Tracker</h1>
          <p className="text-sm text-slate-500">
            Monthly call averages and bonus tiers
          </p>
        </div>
        <Link
          href="/crm/va/roster"
          className="text-sm text-emerald-600 hover:underline"
        >
          &larr; Back to roster
        </Link>
      </div>

      {/* VA selector */}
      {isManager && vas.length > 0 && (
        <div className="flex items-center gap-3">
          <label className="text-sm font-medium text-slate-700">VA:</label>
          <select
            className="rounded-md border border-slate-300 px-3 py-1.5 text-sm"
            value={selectedVaId}
            onChange={(e) => setSelectedVaId(e.target.value)}
          >
            {vas.map((v) => (
              <option key={v.id} value={v.id}>
                {v.full_name}
              </option>
            ))}
          </select>
        </div>
      )}

      {/* Bonus tiers reference */}
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <h2 className="text-sm font-semibold text-slate-800 mb-2">
          Bonus Tiers
        </h2>
        <div className="grid gap-2 sm:grid-cols-4">
          {BONUS_TIERS.map((tier) => (
            <div
              key={tier.threshold}
              className="rounded-lg border border-slate-100 bg-slate-50 px-3 py-2 text-sm"
            >
              <span className="font-medium text-emerald-700">
                ${tier.amount.toLocaleString()}
              </span>
              <span className="text-slate-500 ml-1">
                {tier.threshold}+ avg calls/day
              </span>
            </div>
          ))}
        </div>
      </div>

      {loading ? (
        <p className="text-sm text-slate-400">Loading bonus data...</p>
      ) : (
        <>
          {/* Current month projection */}
          {currentMonth && (
            <div className="rounded-xl border-2 border-emerald-200 bg-emerald-50 p-5">
              <h2 className="text-sm font-semibold text-emerald-900 mb-3">
                Current Month Projection ({currentMonth.month})
              </h2>
              <div className="grid gap-4 sm:grid-cols-3">
                <div>
                  <div className="text-xs text-emerald-700 uppercase tracking-wide">
                    Avg calls/day
                  </div>
                  <div className="text-2xl font-bold text-emerald-800">
                    {currentMonth.avg_calls_per_day}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-emerald-700 uppercase tracking-wide">
                    Days reported
                  </div>
                  <div className="text-2xl font-bold text-emerald-800">
                    {currentMonth.days_reported}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-emerald-700 uppercase tracking-wide">
                    Projected bonus
                  </div>
                  <div className="text-2xl font-bold text-emerald-800">
                    ${currentMonth.bonus_amount.toLocaleString()}
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Past months */}
          {pastMonths.length > 0 && (
            <div className="rounded-xl border border-slate-200 bg-white p-4">
              <h2 className="text-sm font-semibold text-slate-800 mb-3">
                Past Months
              </h2>
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b text-left text-slate-500">
                    <th className="pb-2 font-medium">Month</th>
                    <th className="pb-2 font-medium">Avg calls/day</th>
                    <th className="pb-2 font-medium">Days</th>
                    <th className="pb-2 font-medium">Bonus</th>
                  </tr>
                </thead>
                <tbody>
                  {pastMonths.map((m) => (
                    <tr key={m.month} className="border-b border-slate-100">
                      <td className="py-2 font-medium">{m.month}</td>
                      <td className="py-2">{m.avg_calls_per_day}</td>
                      <td className="py-2">{m.days_reported}</td>
                      <td className="py-2 font-semibold text-emerald-700">
                        ${m.bonus_amount.toLocaleString()}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {months.length === 0 && (
            <p className="text-sm text-slate-400 text-center py-8">
              No daily reports found for this VA yet.
            </p>
          )}
        </>
      )}
    </div>
  );
}
