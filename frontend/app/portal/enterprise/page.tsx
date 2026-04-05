"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase/client";

type ScanRow = {
  id: string;
  domain: string;
  hawk_score: number | null;
  grade: string | null;
  created_at: string;
};

export default function PortalEnterprisePage() {
  const supabase = useMemo(() => createClient(), []);
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [primary, setPrimary] = useState<string | null>(null);
  const [extras, setExtras] = useState<string[]>([]);
  const [rows, setRows] = useState<ScanRow[]>([]);

  const load = useCallback(async () => {
    setLoading(true);
    const {
      data: { user },
    } = await supabase.auth.getUser();
    if (!user) {
      router.replace("/portal/login");
      setLoading(false);
      return;
    }

    const { data: cpp, error: e1 } = await supabase
      .from("client_portal_profiles")
      .select("client_id,domain")
      .eq("user_id", user.id)
      .maybeSingle();

    if (e1 || !cpp) {
      setLoading(false);
      return;
    }

    const { data: cl } = await supabase
      .from("clients")
      .select("domain,monitored_domains")
      .eq("id", cpp.client_id)
      .single();

    setPrimary((cl?.domain as string) ?? (cpp.domain as string) ?? null);
    setExtras(Array.isArray(cl?.monitored_domains) ? (cl?.monitored_domains as string[]) : []);

    const { data: scans } = await supabase
      .from("client_domain_scans")
      .select("id,domain,hawk_score,grade,created_at")
      .eq("client_id", cpp.client_id)
      .order("created_at", { ascending: false })
      .limit(40);

    setRows((scans ?? []) as ScanRow[]);
    setLoading(false);
  }, [router, supabase]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-zinc-500">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-700 border-t-[#00C48C]" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-zinc-50">Enterprise domains</h1>
        <p className="mt-2 text-sm text-zinc-500">
          Latest fast-scan scores for your primary domain and any extra domains your HAWK team monitors. Add domains
          through your account team — up to four extra apex domains.
        </p>
      </div>

      <div className="rounded-xl border border-zinc-800 bg-zinc-950/50 p-4 text-sm text-zinc-400">
        <p>
          <span className="text-zinc-200">Primary:</span> {primary ?? "—"}
        </p>
        {extras.length > 0 && (
          <p className="mt-2">
            <span className="text-zinc-200">Additional monitored:</span> {extras.join(", ")}
          </p>
        )}
        {extras.length === 0 && (
          <p className="mt-2 text-zinc-600">No additional domains configured yet.</p>
        )}
      </div>

      {rows.length === 0 ? (
        <p className="rounded-lg border border-zinc-800 bg-zinc-900/40 px-4 py-8 text-center text-sm text-zinc-500">
          No rollup scans yet. Once your team adds monitored domains and the daily job runs, scores appear here.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-zinc-800">
          <table className="w-full min-w-[520px] text-left text-sm">
            <thead className="border-b border-zinc-800 bg-zinc-900/60 text-xs uppercase tracking-wide text-zinc-500">
              <tr>
                <th className="px-3 py-2">Domain</th>
                <th className="px-3 py-2">Score</th>
                <th className="px-3 py-2">Grade</th>
                <th className="px-3 py-2">Recorded</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-b border-zinc-800/80 hover:bg-zinc-900/40">
                  <td className="px-3 py-2 font-medium text-zinc-200">{r.domain}</td>
                  <td className="px-3 py-2 text-zinc-300">{r.hawk_score ?? "—"}</td>
                  <td className="px-3 py-2 capitalize text-zinc-400">{r.grade ?? "—"}</td>
                  <td className="px-3 py-2 text-zinc-500">{new Date(r.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-center text-sm text-zinc-600">
        <Link href="/portal" className="text-[#00C48C] hover:underline">
          Back to portal home
        </Link>
      </p>
    </div>
  );
}
