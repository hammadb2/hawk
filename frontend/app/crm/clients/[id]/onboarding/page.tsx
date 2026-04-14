"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";

const CHECKLIST = [
  "Walk through portal — score, findings, guarantee status",
  "Explain each critical finding in plain English",
  "Walk through fix guide for top critical finding",
  "Show certification progress (90 day countdown)",
  "Explain guarantee conditions — what they need to do to stay covered",
  "Set expectation: we will WhatsApp you if anything changes",
  "Ask: who else in the business needs to know about these findings?",
  "Ask: do you know other business owners who would benefit from seeing their score?",
];

type ClientRow = {
  company_name?: string;
  domain?: string;
  status?: string;
  mrr_cents?: number;
  onboarded_at?: string;
  close_date?: string;
  guarantee_status?: string;
  portal_user_id?: string;
};

function StatusBadge({ label, variant }: { label: string; variant: "green" | "amber" | "red" | "zinc" }) {
  const colors = {
    green: "bg-emerald-50 text-emerald-600 border-emerald-700",
    amber: "bg-amber-900/50 text-amber-400 border-amber-700",
    red: "bg-rose-900/50 text-rose-400 border-rose-700",
    zinc: "bg-slate-100 text-slate-600 border-slate-200",
  };
  return <span className={`inline-block rounded-full border px-2.5 py-0.5 text-xs font-medium ${colors[variant]}`}>{label}</span>;
}

function guaranteeBadge(status: string | undefined) {
  switch (status) {
    case "active": return <StatusBadge label="Guarantee active" variant="green" />;
    case "at_risk": return <StatusBadge label="At risk" variant="amber" />;
    case "breached": return <StatusBadge label="Breached" variant="red" />;
    default: return <StatusBadge label={status || "Pending"} variant="zinc" />;
  }
}

export default function ClientOnboardingChecklistPage() {
  const params = useParams();
  const id = typeof params.id === "string" ? params.id : "";
  const supabase = useMemo(() => createClient(), []);
  const [client, setClient] = useState<ClientRow | null>(null);
  const [done, setDone] = useState<boolean[]>(() => CHECKLIST.map(() => false));
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!id) return;
    void (async () => {
      const { data } = await supabase
        .from("clients")
        .select("company_name, domain, status, mrr_cents, onboarded_at, close_date, guarantee_status, portal_user_id")
        .eq("id", id)
        .maybeSingle();
      setClient(data as ClientRow | null);
      setLoading(false);
    })();
  }, [id, supabase]);

  const completedCount = done.filter(Boolean).length;
  const progress = Math.round((completedCount / CHECKLIST.length) * 100);
  const company = client?.company_name ?? client?.domain ?? "Client";

  const milestones = [
    {
      label: "Stripe payment confirmed",
      done: client?.status === "active" || client?.status === "onboarded",
    },
    {
      label: "Portal account created",
      done: !!client?.portal_user_id,
    },
    {
      label: "Onboarding call completed",
      done: !!client?.onboarded_at,
    },
    {
      label: "Guarantee activated",
      done: client?.guarantee_status === "active",
    },
  ];

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" className="border-slate-200" asChild>
          <Link href="/crm/clients">← Clients</Link>
        </Button>
      </div>

      <div>
        <h1 className="text-2xl font-semibold text-slate-900">Onboarding</h1>
        <p className="mt-1 text-sm text-slate-600">{company} · Shield onboarding</p>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-emerald-500" />
        </div>
      ) : (
        <>
          {/* Client status cards */}
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
              <div className="text-xs font-medium uppercase tracking-wide text-slate-600">Account Status</div>
              <div className="mt-1">
                <StatusBadge
                  label={client?.status || "unknown"}
                  variant={client?.status === "active" ? "green" : client?.status === "churned" ? "red" : "zinc"}
                />
              </div>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
              <div className="text-xs font-medium uppercase tracking-wide text-slate-600">Guarantee</div>
              <div className="mt-1">{guaranteeBadge(client?.guarantee_status)}</div>
            </div>
            <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
              <div className="text-xs font-medium uppercase tracking-wide text-slate-600">Portal</div>
              <div className="mt-1">
                <StatusBadge
                  label={client?.portal_user_id ? "Portal linked" : "No portal account"}
                  variant={client?.portal_user_id ? "green" : "amber"}
                />
              </div>
            </div>
          </div>

          {/* Onboarding milestones */}
          <div className="rounded-xl border border-slate-200 bg-slate-50/90 p-5">
            <h2 className="text-sm font-semibold text-slate-800">Onboarding Milestones</h2>
            <div className="mt-4 space-y-3">
              {milestones.map((m, i) => (
                <div key={i} className="flex items-center gap-3 text-sm">
                  <div className={`flex h-6 w-6 items-center justify-center rounded-full border text-xs font-bold ${m.done ? "border-emerald-500 bg-emerald-50 text-emerald-600" : "border-slate-200 bg-slate-100 text-slate-600"}`}>
                    {m.done ? "\u2713" : i + 1}
                  </div>
                  <span className={m.done ? "text-slate-700" : "text-slate-600"}>{m.label}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Onboarding call checklist */}
          <div className="rounded-xl border border-slate-200 bg-slate-50/90 p-5">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-semibold text-slate-800">Onboarding Call Checklist</h2>
              <span className="text-xs text-slate-600">{completedCount}/{CHECKLIST.length}</span>
            </div>
            <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-100">
              <div
                className="h-full rounded-full bg-emerald-500 transition-all"
                style={{ width: `${progress}%` }}
              />
            </div>
            <ul className="mt-4 space-y-2">
              {CHECKLIST.map((line, i) => (
                <li key={i} className="flex items-start gap-3 rounded-lg border border-slate-200/80 bg-slate-50/80 p-3">
                  <input
                    type="checkbox"
                    className="mt-0.5 accent-emerald-500"
                    checked={done[i]}
                    onChange={(e) =>
                      setDone((d) => {
                        const n = [...d];
                        n[i] = e.target.checked;
                        return n;
                      })
                    }
                  />
                  <span className={`text-sm ${done[i] ? "text-slate-600 line-through" : "text-slate-800"}`}>{line}</span>
                </li>
              ))}
            </ul>
          </div>

          <p className="text-xs text-slate-500">
            After the call — mark onboarding complete and update client status in CRM.
          </p>
        </>
      )}
    </div>
  );
}
