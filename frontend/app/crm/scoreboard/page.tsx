"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/components/providers/auth-provider";
import { crmScoreboardApi } from "@/lib/crm-api";
import type { ScoreboardEntry } from "@/lib/crm-types";

function cents(n: number) {
  return `$${(n / 100).toLocaleString("en-CA", { minimumFractionDigits: 0 })}`;
}

export default function ScoreboardPage() {
  const { token } = useAuth();
  const [data, setData] = useState<{ leaderboard: ScoreboardEntry[]; my_rank: number | null; total_reps: number } | null>(null);
  const [period, setPeriod] = useState<"week" | "month" | "quarter" | "all">("month");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) return;
    setLoading(true);
    crmScoreboardApi.get(token, period).then(setData).finally(() => setLoading(false));
  }, [token, period]);

  return (
    <div className="max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-xl font-semibold">🏆 Scoreboard</h1>
        <div className="flex border border-surface-3 rounded overflow-hidden">
          {(["week", "month", "quarter", "all"] as const).map((p) => (
            <button
              key={p}
              onClick={() => setPeriod(p)}
              className={`px-3 py-1.5 text-sm capitalize ${period === p ? "bg-purple-600 text-white" : "text-text-secondary hover:bg-surface-2"}`}
            >
              {p === "all" ? "All Time" : p}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <p className="text-text-secondary text-sm">Loading…</p>
      ) : (
        <div className="bg-white border border-surface-3 rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead className="border-b border-surface-3 bg-surface-2">
              <tr>
                <th className="text-left px-4 py-2.5 text-xs text-text-secondary font-medium w-12">Rank</th>
                <th className="text-left px-4 py-2.5 text-xs text-text-secondary font-medium">Rep</th>
                <th className="text-center px-4 py-2.5 text-xs text-text-secondary font-medium">Closes</th>
                <th className="text-center px-4 py-2.5 text-xs text-text-secondary font-medium">Target</th>
                <th className="text-right px-4 py-2.5 text-xs text-text-secondary font-medium">Commission</th>
              </tr>
            </thead>
            <tbody>
              {data?.leaderboard.map((entry) => (
                <tr
                  key={entry.crm_user_id}
                  className={`border-b border-surface-3 last:border-0 ${entry.rank === data.my_rank ? "bg-purple-50" : "hover:bg-surface-2"}`}
                >
                  <td className="px-4 py-3 text-center">
                    {entry.rank === 1 ? "👑" : entry.rank === 2 ? "🥈" : entry.rank === 3 ? "🥉" : (
                      <span className="text-text-secondary">#{entry.rank}</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <p className="font-medium">{entry.name || entry.email}</p>
                    <p className="text-xs text-text-secondary capitalize">{entry.role.replace("_", " ")}</p>
                  </td>
                  <td className="px-4 py-3 text-center">
                    <span className="font-semibold text-purple-700">{entry.closes}</span>
                  </td>
                  <td className="px-4 py-3 text-center text-text-secondary">{entry.monthly_target || "—"}</td>
                  <td className="px-4 py-3 text-right font-medium">{cents(entry.commission_cents)}</td>
                </tr>
              ))}
              {data?.leaderboard.length === 0 && (
                <tr><td colSpan={5} className="px-4 py-10 text-center text-text-secondary">No data yet.</td></tr>
              )}
            </tbody>
          </table>
          {data?.my_rank && (
            <div className="px-4 py-2 border-t border-surface-3 bg-purple-50 text-sm text-purple-700">
              Your rank: #{data.my_rank} of {data.total_reps} reps
            </div>
          )}
        </div>
      )}
    </div>
  );
}
