"use client";

import { useState } from "react";
import toast from "react-hot-toast";
import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { crmDialogSurface, crmFieldSurface } from "@/lib/crm/crm-surface";

function normalizeDomain(raw: string): string {
  let d = raw.trim().toLowerCase();
  for (const prefix of ["https://", "http://"]) {
    if (d.startsWith(prefix)) d = d.slice(prefix.length);
  }
  d = d.split("/")[0].split("?")[0].trim();
  if (d.startsWith("www.")) d = d.slice(4);
  return d;
}

export function AddProspectModal({
  open,
  onOpenChange,
  onCreated,
  sessionUserId,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onCreated?: () => void;
  sessionUserId: string;
}) {
  const [domain, setDomain] = useState("");
  const [company, setCompany] = useState("");
  const [industry, setIndustry] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const nd = normalizeDomain(domain);
    if (!nd) {
      toast.error("Enter a domain");
      return;
    }
    setSaving(true);
    try {
      const supabase = createClient();
      const { error } = await supabase.from("prospects").insert({
        domain: nd,
        company_name: company.trim() || null,
        industry: industry.trim() || null,
        stage: "new",
        assigned_rep_id: sessionUserId,
        source: "manual",
        hawk_score: 0,
        is_hot: false,
        last_activity_at: new Date().toISOString(),
      });
      if (error) {
        if (error.code === "23505" || error.message.includes("unique")) {
          toast.error("That domain is already in the pipeline");
        } else {
          toast.error(error.message);
        }
        return;
      }
      toast.success("Prospect added");
      setDomain("");
      setCompany("");
      setIndustry("");
      onOpenChange(false);
      onCreated?.();
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={crmDialogSurface}>
        <form onSubmit={(e) => void submit(e)}>
          <DialogHeader>
            <DialogTitle className="text-white">Add prospect</DialogTitle>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div>
              <Label className="text-slate-400">Domain *</Label>
              <Input
                className={`mt-1 ${crmFieldSurface}`}
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
                placeholder="acme.com"
                required
              />
            </div>
            <div>
              <Label className="text-slate-400">Company</Label>
              <Input
                className={`mt-1 ${crmFieldSurface}`}
                value={company}
                onChange={(e) => setCompany(e.target.value)}
                placeholder="Acme Inc."
              />
            </div>
            <div>
              <Label className="text-slate-400">Industry</Label>
              <Input
                className={`mt-1 ${crmFieldSurface}`}
                value={industry}
                onChange={(e) => setIndustry(e.target.value)}
                placeholder="Legal"
              />
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" className="border-[#1e1e2e] bg-[#0d0d14] text-slate-200 hover:bg-[#1a1a24]" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button type="submit" className="bg-emerald-600" disabled={saving}>
              {saving ? "Saving…" : "Add"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
