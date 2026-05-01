"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useLiveEffect } from "@/lib/hooks/use-refresh-signal";
import toast from "react-hot-toast";
import { Button } from "@/components/ui/button";
import { createClient } from "@/lib/supabase/client";

type Finding = {
  id?: string;
  severity?: string;
  title?: string;
  description?: string;
  interpretation?: string;
  fix_guide?: string;
  layer?: string;
  screenshot_data_url?: string;
};

type StatusRow = {
  finding_id: string;
  status: string;
  scan_id: string;
  verified_at: string | null;
  verify_error: string | null;
};

const STATUSES = ["open", "in_progress", "fixed", "accepted_risk"] as const;

export default function PortalFindingsPage() {
  const supabase = useMemo(() => createClient(), []);
  const [loading, setLoading] = useState(true);
  const [prospectId, setProspectId] = useState<string | null>(null);
  const [scanId, setScanId] = useState<string | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [statusMap, setStatusMap] = useState<Record<string, StatusRow>>({});
  const [verifying, setVerifying] = useState<string | null>(null);
  const [expandedGuide, setExpandedGuide] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    const {
      data: { user },
    } = await supabase.auth.getUser();
    if (!user) return;
    const { data: cpp } = await supabase
      .from("client_portal_profiles")
      .select("client_id")
      .eq("user_id", user.id)
      .maybeSingle();
    if (!cpp?.client_id) {
      setLoading(false);
      return;
    }
    const { data: cl } = await supabase.from("clients").select("prospect_id").eq("id", cpp.client_id).maybeSingle();
    const pid = cl?.prospect_id as string | undefined;
    if (!pid) {
      setLoading(false);
      return;
    }
    setProspectId(pid);
    const { data: scans } = await supabase
      .from("crm_prospect_scans")
      .select("id,findings")
      .eq("prospect_id", pid)
      .order("created_at", { ascending: false })
      .limit(1);
    const sc = scans?.[0] as { id: string; findings: unknown } | undefined;
    if (!sc) {
      setLoading(false);
      return;
    }
    setScanId(sc.id);
    const wrap = sc.findings as Record<string, unknown> | null;
    const fl = wrap && Array.isArray(wrap.findings) ? (wrap.findings as Finding[]) : [];
    setFindings(fl);

    const { data: stRows } = await supabase.from("portal_finding_status").select("*").eq("client_id", cpp.client_id);
    const map: Record<string, StatusRow> = {};
    for (const r of stRows || []) {
      const row = r as StatusRow & { client_id: string };
      map[row.finding_id] = row;
    }
    setStatusMap(map);
    setLoading(false);
  }, [supabase]);

  useLiveEffect(() => {
    void load();
  }, [load]);

  async function setStatus(findingId: string, status: (typeof STATUSES)[number]) {
    if (!prospectId || !scanId) return;
    const res = await fetch("/api/portal/finding-status", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        prospectId,
        scanId,
        findingId,
        status,
      }),
    });
    const j = (await res.json().catch(() => ({}))) as { auto_verify_queued?: boolean; error?: string; detail?: string };
    if (!res.ok) {
      toast.error([j.error, j.detail].filter(Boolean).join(" ") || "Could not update status");
      return;
    }
    setStatusMap((m) => ({
      ...m,
      [findingId]: {
        ...m[findingId],
        finding_id: findingId,
        status,
        scan_id: scanId,
        verified_at: m[findingId]?.verified_at ?? null,
        verify_error: m[findingId]?.verify_error ?? null,
      },
    }));
    if (status === "fixed" && j.auto_verify_queued) {
      toast.success("Marked fixed — HAWK is running a fast verification scan…");
    } else {
      toast.success("Status updated");
    }
  }

  async function verifyNow(findingId: string) {
    if (!prospectId || !scanId) return;
    setVerifying(findingId);
    try {
      const res = await fetch("/api/crm/finding-verify", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prospectId, scanId, findingId }),
      });
      const j = (await res.json().catch(() => ({}))) as {
        verified?: boolean;
        message?: string;
        error?: string;
        detail?: string;
      };
      if (!res.ok) {
        toast.error([j.error, j.detail].filter(Boolean).join(" ") || "Verify failed");
        return;
      }
      if (j.verified) {
        toast.success(j.message || "Verified — great work!");
        await load();
      } else {
        toast(j.message || "Still showing exposure", { icon: "ℹ️" });
        await load();
      }
    } finally {
      setVerifying(null);
    }
  }

  if (loading) {
    return (
      <div className="flex min-h-[30vh] items-center justify-center text-ink-200">
        <div className="h-10 w-10 animate-spin rounded-full border-2 border-white/10 border-t-signal" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink-0">Remediation tracking</h1>
        <p className="mt-1 text-sm text-ink-200">
          Set status per finding. When you mark <strong className="text-ink-100">Fixed</strong>, we automatically run a
          fast verification scan; you can also tap <strong className="text-ink-100">Verify fix</strong> to re-check
          manually. Score updates and WhatsApp streak messages fire when verification succeeds.
        </p>
        <Link href="/portal" className="mt-2 inline-block text-sm text-signal hover:underline">
          ← Back to overview
        </Link>
      </div>

      {findings.length === 0 ? (
        <p className="text-sm text-ink-200">No findings in the latest scan.</p>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-white/10">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="border-b border-white/10 bg-ink-800 text-xs uppercase text-ink-200">
              <tr>
                <th className="px-4 py-3">Severity</th>
                <th className="px-4 py-3">Finding</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Verify</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/10">
              {findings.filter((f) => f.id).map((f) => {
                const fid = String(f.id);
                const st = statusMap[fid]?.status || "open";
                return (
                  <tr key={fid} className="bg-ink-900/90">
                    <td className="px-4 py-3 capitalize text-ink-100">{f.severity || "—"}</td>
                    <td className="max-w-md px-4 py-3 text-ink-0">
                      <div className="font-medium">{f.title || "Finding"}</div>
                      {f.description && <p className="mt-1 text-xs text-ink-200 line-clamp-3">{f.description}</p>}
                      {f.interpretation && (
                        <p className="mt-1 text-xs text-ink-100 italic">{f.interpretation}</p>
                      )}
                      {f.fix_guide && (
                        <div className="mt-2">
                          <button
                            type="button"
                            onClick={() => setExpandedGuide(expandedGuide === fid ? null : fid)}
                            className="text-xs font-medium text-signal hover:underline"
                          >
                            {expandedGuide === fid ? "Hide fix guide ▲" : "How to fix ▼"}
                          </button>
                          {expandedGuide === fid && (
                            <pre className="mt-2 whitespace-pre-wrap rounded-lg border border-white/10 bg-black/30 p-3 text-xs leading-relaxed text-ink-100">
                              {f.fix_guide}
                            </pre>
                          )}
                        </div>
                      )}
                      {f.screenshot_data_url && f.screenshot_data_url.startsWith("data:image") && (
                        <div className="mt-3">
                          <p className="mb-1 text-[10px] font-medium uppercase text-ink-200">Live view</p>
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={f.screenshot_data_url}
                            alt=""
                            className="max-h-48 max-w-full rounded border border-white/10 object-contain"
                          />
                        </div>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <select
                        className="rounded-md border border-white/10 bg-ink-800 px-2 py-1 text-ink-0 shadow-sm"
                        value={st}
                        onChange={(e) => void setStatus(fid, e.target.value as (typeof STATUSES)[number])}
                      >
                        {STATUSES.map((s) => (
                          <option key={s} value={s}>
                            {s.replaceAll("_", " ")}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="px-4 py-3">
                      {st === "fixed" ? (
                        <Button
                          size="sm"
                          className="bg-signal text-white"
                          disabled={verifying === fid}
                          onClick={() => void verifyNow(fid)}
                        >
                          {verifying === fid ? "Scanning…" : "Verify fix"}
                        </Button>
                      ) : (
                        <span className="text-ink-0">—</span>
                      )}
                      {statusMap[fid]?.verified_at && (
                        <p className="mt-1 text-xs text-signal/90">Verified</p>
                      )}
                      {statusMap[fid]?.verify_error && (
                        <p className="mt-1 text-xs text-signal">{statusMap[fid]?.verify_error}</p>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
