"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
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

export default function ClientOnboardingChecklistPage() {
  const params = useParams();
  const id = typeof params.id === "string" ? params.id : "";
  const supabase = createClient();
  const [company, setCompany] = useState<string | null>(null);
  const [done, setDone] = useState<boolean[]>(() => CHECKLIST.map(() => false));

  useEffect(() => {
    if (!id) return;
    void (async () => {
      const { data } = await supabase.from("clients").select("company_name").eq("id", id).maybeSingle();
      setCompany((data as { company_name?: string } | null)?.company_name ?? null);
    })();
  }, [id, supabase]);

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-4">
      <div className="flex items-center gap-2">
        <Button variant="outline" size="sm" className="border-zinc-700" asChild>
          <Link href="/crm/clients">← Clients</Link>
        </Button>
      </div>
      <h1 className="text-xl font-semibold text-zinc-100">Onboarding call checklist</h1>
      <p className="text-sm text-zinc-500">{company || "Client"} · Shield onboarding</p>
      <ul className="space-y-3">
        {CHECKLIST.map((line, i) => (
          <li key={i} className="flex items-start gap-3 rounded-lg border border-zinc-800 bg-zinc-900/40 p-3">
            <input
              type="checkbox"
              className="mt-1"
              checked={done[i]}
              onChange={(e) =>
                setDone((d) => {
                  const n = [...d];
                  n[i] = e.target.checked;
                  return n;
                })
              }
            />
            <span className="text-sm text-zinc-200">{line}</span>
          </li>
        ))}
      </ul>
      <p className="text-xs text-zinc-500">
        After the call — mark onboarding complete and update client status in CRM (onboarded_at can be set via admin / future automation).
      </p>
    </div>
  );
}
