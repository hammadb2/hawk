"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { AlertTriangle } from "lucide-react";
import { useCRMStore } from "@/store/crm-store";
import { prospectsApi } from "@/lib/api";
import { toast } from "@/components/ui/toast";
import type { Prospect, LostReasonData } from "@/types/crm";

const LOST_REASONS = [
  "Price too high",
  "No decision maker access",
  "Went with competitor",
  "No budget right now",
  "Not interested",
  "Could not reach after 5 attempts",
  "Other (requires note)",
] as const;

interface LostModalProps {
  open: boolean;
  onClose: () => void;
  prospect: Prospect | null;
  onConfirm?: (data: LostReasonData) => void;
}

export function LostModal({ open, onClose, prospect, onConfirm }: LostModalProps) {
  const { updateProspect } = useCRMStore();
  const [reason, setReason] = useState("");
  const [notes, setNotes] = useState("");
  const [reactivateDate, setReactivateDate] = useState("");
  const [loading, setLoading] = useState(false);

  const isOther = reason === "Other (requires note)";
  const canSubmit = reason && (!isOther || notes.trim().length > 0);

  const handleConfirm = async () => {
    if (!prospect || !canSubmit) return;
    setLoading(true);

    const data: LostReasonData = {
      reason,
      notes: notes.trim() || null,
      reactivate_at: reactivateDate || null,
    };

    try {
      const result = await prospectsApi.moveLost(prospect.id, data);
      if (result.success) {
        updateProspect(prospect.id, {
          stage: "lost",
          lost_reason: reason,
          lost_notes: notes || null,
          reactivate_at: reactivateDate || null,
        });
        toast({ title: `${prospect.company_name} marked as lost`, variant: "default" });
        onConfirm?.(data);
        handleClose();
      } else {
        toast({ title: result.error || "Failed to mark as lost", variant: "destructive" });
      }
    } catch {
      toast({ title: "Network error", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setReason("");
    setNotes("");
    setReactivateDate("");
    onClose();
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(o) => {
        if (!o) handleClose();
      }}
    >
      <DialogContent hideClose className="max-w-md">
        <DialogHeader>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-8 h-8 rounded-lg bg-red/10 border border-red/25 flex items-center justify-center flex-shrink-0">
              <AlertTriangle className="w-4 h-4 text-red" />
            </div>
            <DialogTitle>Mark as Lost</DialogTitle>
          </div>
          <DialogDescription>
            {prospect?.company_name} — This cannot be undone without a Head of Sales override.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1.5">
              Lost reason <span className="text-red">*</span>
            </label>
            <Select value={reason} onValueChange={setReason}>
              <SelectTrigger>
                <SelectValue placeholder="Select a reason..." />
              </SelectTrigger>
              <SelectContent>
                {LOST_REASONS.map((r) => (
                  <SelectItem key={r} value={r}>{r}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1.5">
              Notes {isOther && <span className="text-red">*</span>}
              {!isOther && <span className="text-text-dim">(optional)</span>}
            </label>
            <Textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Additional context..."
              rows={3}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1.5">
              Reactivate on date <span className="text-text-dim">(optional)</span>
            </label>
            <Input
              type="date"
              value={reactivateDate}
              onChange={(e) => setReactivateDate(e.target.value)}
              min={new Date().toISOString().split("T")[0]}
            />
            <p className="text-2xs text-text-dim mt-1">
              If set, prospect automatically moves back to New on this date.
            </p>
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={handleClose} disabled={loading}>
            Cancel
          </Button>
          <Button
            variant="danger"
            onClick={handleConfirm}
            disabled={!canSubmit || loading}
          >
            {loading ? "Marking as lost..." : "Confirm Lost"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
