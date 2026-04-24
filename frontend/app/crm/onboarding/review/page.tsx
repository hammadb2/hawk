"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useLiveEffect } from "@/lib/hooks/use-refresh-signal";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { CRM_API_BASE_URL } from "@/lib/crm/api-url";
import { crmEmptyState, crmPageSubtitle, crmPageTitle, crmSurfaceCard } from "@/lib/crm/crm-surface";

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
        const raw = Array.isArray(data) ? data : (data.items || []);
            setItems(raw.map((item: Record<string, unknown>) => ({
              ...item,
              profile_name: (item.profile as Record<string, unknown>)?.full_name ?? item.profile_name ?? "",
              profile_email: (item.profile as Record<string, unknown>)?.email ?? item.profile_email ?? "",
              profile_role: (item.profile as Record<string, unknown>)?.role ?? item.profile_role ?? "",
            })) as ReviewItem[]);
      }
    } catch (err) {
      console.error("Failed to load review queue:", err);
    }
    setLoading(false);
  }, [session?.access_token, filter]);

  useLiveEffect(() => {
    void load();
  }, [load]);

  if (!profile || (profile.role !== "ceo" && profile.role !== "hos" && profile.role_type !== "va_manager")) {
    return (
      <div className="p-8 text-center">
        <p className="text-ink-200">You do not have permission to view this page.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white">Onboarding Review Queue</h1>
          <p className={crmPageSubtitle}>Review and approve new hire onboarding submissions.</p>
        </div>
      </div>

      <div className="flex gap-2">
        {(["pending_review", "approved", "rejected", "all"] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium transition ${
              filter === f
                ? "bg-signal/15 text-signal-200 ring-1 ring-signal/40"
                : "border border-[#1e1e2e] bg-[#111118] text-ink-200 hover:text-ink-100"
            }`}
          >
            {f === "pending_review" ? "Pending" : f.charAt(0).toUpperCase() + f.slice(1)}
          </button>
        ))}
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-white/10 border-t-signal" />
        </div>
      ) : items.length === 0 ? (
        <div className={`p-8 text-center ${crmEmptyState}`}>
          <p className="text-sm text-ink-200">No submissions found.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((item) => (
            <Link
              key={item.id}
              href={`/crm/onboarding/review/${item.id}`}
              className={`flex items-center justify-between p-4 transition hover:border-signal/40 ${crmSurfaceCard}`}
            >
              <div className="flex items-center gap-4">
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#1a1a24] text-sm font-bold text-ink-100">
                  {(item.profile_name || "?").charAt(0).toUpperCase()}
                </div>
                <div>
                  <p className="font-medium text-white">{item.profile_name || "Unknown"}</p>
                  <p className="text-xs text-ink-200">{item.profile_email || ""} &middot; {item.profile_role || ""}</p>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <span
                  className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${
                    item.status === "pending_review"
                      ? "bg-signal/15 text-signal-200 ring-1 ring-signal/30"
                      : item.status === "approved"
                        ? "bg-signal/15 text-signal-200 ring-1 ring-signal/30"
                        : "bg-red/100/15 text-red ring-1 ring-red/30"
                  }`}
                >
                  {item.status === "pending_review" ? "Pending" : item.status}
                </span>
                <span className="text-xs text-ink-200">
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
