"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { CRM_API_BASE_URL } from "@/lib/crm/api-url";

interface ReviewItem {
  id: string;
  profile_id: string;
  status: string;
  created_at: string;
  profile_name: string;
  profile_email: string;
  profile_role: string;
}

export default function OnboardingReviewPage() {
  const supabase = useMemo(() => createClient(), []);
  const { profile, session } = useCrmAuth();
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"pending_review" | "approved" | "rejected" | "all">("pending_review");

  const load = useCallback(async () => {
    if (!session?.access_token) return;
    setLoading(true);
    try {
      const r = await fetch(`${CRM_API_BASE_URL}/api/crm/onboarding/review/list?status=${filter}`, {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (r.ok) {
        const data = await r.json();
        setItems(Array.isArray(data) ? data : (data.items || []));
      }
    } catch (err) {
      console.error("Failed to load review queue:", err);
    }
    setLoading(false);
  }, [session?.access_token, filter]);

  useEffect(() => {
    void load();
  }, [load]);

  if (!profile || (profile.role !== "ceo" && profile.role !== "hos" && profile.role_type !== "va_manager")) {
    return (
      <div className="p-8 text-center">
        <p className="text-slate-500">You do not have permission to view this page.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">Onboarding Review Queue</h1>
          <p className="text-sm text-slate-500">Review and approve new hire onboarding submissions.</p>
        </div>
      </div>

      <div className="flex gap-2">
        {(["pending_review", "approved", "rejected", "all"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
              filter === f
                ? "bg-emerald-100 text-emerald-700"
                : "bg-slate-100 text-slate-600 hover:bg-slate-200"
            }`}
          >
            {f === "pending_review" ? "Pending" : f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-emerald-500" />
        </div>
      ) : items.length === 0 ? (
        <div className="rounded-lg border border-slate-200 bg-white p-8 text-center">
          <p className="text-sm text-slate-500">No submissions found.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((item) => (
            <Link
              key={item.id}
              href={`/crm/onboarding/review/${item.id}`}
              className="flex items-center justify-between rounded-lg border border-slate-200 bg-white p-4 shadow-sm hover:border-emerald-300 transition"
            >
              <div className="flex items-center gap-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-100 text-sm font-bold text-slate-600">
                  {(item.profile_name || "?").charAt(0).toUpperCase()}
                </div>
                <div>
                  <p className="font-medium text-slate-900">{item.profile_name || "Unknown"}</p>
                  <p className="text-xs text-slate-500">{item.profile_email || ""} &middot; {item.profile_role || ""}</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span
                  className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                    item.status === "pending_review"
                      ? "bg-amber-100 text-amber-700"
                      : item.status === "approved"
                        ? "bg-emerald-100 text-emerald-700"
                        : "bg-red-100 text-red-700"
                  }`}
                >
                  {item.status === "pending_review" ? "Pending" : item.status}
                </span>
                <span className="text-xs text-slate-400">
                  {new Date(item.created_at).toLocaleDateString()}
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
