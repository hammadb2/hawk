"use client";

import { useState } from "react";
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

const OUTCOMES = ["Answered", "VM", "No Answer"] as const;

export function LogCallModal({
  open,
  onOpenChange,
  onSave,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onSave: (payload: {
    durationMinutes: number;
    outcome: string;
    summary: string;
    nextAction: string;
  }) => Promise<void>;
}) {
  const [duration, setDuration] = useState("15");
  const [outcome, setOutcome] = useState<string>("Answered");
  const [summary, setSummary] = useState("");
  const [nextAction, setNextAction] = useState("");
  const [saving, setSaving] = useState(false);

  async function submit() {
    setSaving(true);
    try {
      await onSave({
        durationMinutes: Math.max(0, parseInt(duration, 10) || 0),
        outcome,
        summary,
        nextAction,
      });
      setSummary("");
      setNextAction("");
      onOpenChange(false);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={crmDialogSurface}>
        <DialogHeader>
          <DialogTitle className="text-white">Log call</DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-2">
            <div>
              <Label className="text-slate-400">Duration (min)</Label>
              <Input className={crmFieldSurface} value={duration} onChange={(e) => setDuration(e.target.value)} type="number" min={0} />
            </div>
            <div>
              <Label className="text-slate-400">Outcome</Label>
              <select
                className={`mt-1 w-full rounded-lg px-3 py-2 text-sm ${crmFieldSurface}`}
                value={outcome}
                onChange={(e) => setOutcome(e.target.value)}
              >
                {OUTCOMES.map((o) => (
                  <option key={o} value={o}>
                    {o}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <div>
            <Label className="text-slate-400">Summary</Label>
            <textarea className={`mt-1 w-full rounded-lg px-3 py-2 text-sm ${crmFieldSurface}`} rows={3} value={summary} onChange={(e) => setSummary(e.target.value)} />
          </div>
          <div>
            <Label className="text-slate-400">Next action</Label>
            <Input className={crmFieldSurface} value={nextAction} onChange={(e) => setNextAction(e.target.value)} placeholder="Follow-up in 3 days…" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" className="border-[#1e1e2e] bg-[#0d0d14] text-slate-200 hover:bg-[#1a1a24]" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button className="bg-emerald-600 hover:bg-emerald-500" disabled={saving} onClick={() => void submit()}>
            Save to timeline
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
