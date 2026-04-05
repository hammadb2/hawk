"use client";

import { useEffect, useState } from "react";
import { createClient } from "@/lib/supabase/client";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "").replace(/\/$/, "");

export default function CrmHealthPage() {
  const supabase = createClient();
  const [data, setData] = useState<Record<string, unknown> | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function run() {
      if (!API_URL) {
        setErr("Set NEXT_PUBLIC_API_URL");
        return;
      }
      const {
        data: { session },
      } = await supabase.auth.getSession();
      if (!session?.access_token) {
        setErr("Sign in required");
        return;
      }
      const res = await fetch(`${API_URL}/api/crm/health-dashboard`, {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (!res.ok) {
        setErr(await res.text());
        return;
      }
      const j = await res.json();
      if (!cancelled) setData(j);
    }
    void run();
    return () => {
      cancelled = true;
    };
  }, [supabase]);

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-4">
      <h1 className="text-xl font-semibold text-zinc-100">System health</h1>
      {err && <p className="text-sm text-rose-400">{err}</p>}
      {data && (
        <pre className="overflow-x-auto rounded-lg border border-zinc-800 bg-zinc-950 p-4 text-xs text-zinc-300">
          {JSON.stringify(data, null, 2)}
        </pre>
      )}
    </div>
  );
}
