"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { LOST_REASONS } from "@/lib/crm/types";
import { crmDialogSurface, crmFieldSurface } from "@/lib/crm/crm-surface";

export function LostReasonModal({
  open,
  onOpenChange,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onConfirm: (payload: { reason: string; notes: string | null; reactivateOn: string | null }) => Promise<void>;
}) {
  const [reason, setReason] = useState<string>(LOST_REASONS[0]);
  const [notes, setNotes] = useState("");
  const [reactivate, setReactivate] = useState("");
  const [saving, setSaving] = useState(false);

  const needsNotes = reason === "Other";

  async function handleConfirm() {
    if (needsNotes && !notes.trim()) return;
    setSaving(true);
    try {
      await onConfirm({
        reason,
        notes: notes.trim() || null,
        reactivateOn: reactivate || null,
      });
      setNotes("");
      setReactivate("");
      onOpenChange(false);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={crmDialogSurface}>
        <DialogHeader>
          <DialogTitle className="text-white">Mark as lost</DialogTitle>
          <DialogDescription className="text-ink-200">
            A reason is required. This update is logged on the prospect timeline.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label className="text-ink-100">Reason</Label>
            <select
              className={`mt-1 w-full rounded-lg px-3 py-2 text-sm ${crmFieldSurface}`}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            >
              {LOST_REASONS.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </div>
          <div>
            <Label className="text-ink-100">Notes {needsNotes ? "(required)" : "(optional)"}</Label>
            <textarea
              maxLength={500}
              className={`mt-1 w-full rounded-lg px-3 py-2 text-sm ${crmFieldSurface}`}
              rows={3}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
            />
          </div>
          <div>
            <Label className="text-ink-100">Reactivate on (optional)</Label>
            <Input
              type="date"
              className={`mt-1 ${crmFieldSurface}`}
              value={reactivate}
              onChange={(e) => setReactivate(e.target.value)}
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" className="border-[#1e1e2e] bg-[#0d0d14] text-ink-100 hover:bg-[#1a1a24]" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            className="bg-red/15 hover:bg-red/100"
            disabled={saving || (needsNotes && !notes.trim())}
            onClick={() => void handleConfirm()}
          >
            Confirm lost
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
