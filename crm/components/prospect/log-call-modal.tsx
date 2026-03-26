"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Phone } from "lucide-react";
import { prospectsApi } from "@/lib/api";
import { toast } from "@/components/ui/toast";
import type { Prospect } from "@/types/crm";

interface LogCallModalProps {
  open: boolean;
  onClose: () => void;
  prospect: Prospect | null;
}

type CallOutcome = "answered" | "voicemail" | "no_answer";

export function LogCallModal({ open, onClose, prospect }: LogCallModalProps) {
  const [duration, setDuration] = useState("");
  const [outcome, setOutcome] = useState<CallOutcome>("answered");
  const [notes, setNotes] = useState("");
  const [nextAction, setNextAction] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async () => {
    if (!prospect) return;
    setLoading(true);

    try {
      const result = await prospectsApi.logCall(prospect.id, {
        duration_minutes: parseInt(duration) || 0,
        outcome,
        notes: notes.trim() || undefined,
        next_action: nextAction.trim() || undefined,
      });

      if (result.success) {
        toast({ title: "Call logged successfully", variant: "success" });
        handleClose();
      } else {
        toast({ title: result.error || "Failed to log call", variant: "destructive" });
      }
    } catch {
      toast({ title: "Network error", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setDuration("");
    setOutcome("answered");
    setNotes("");
    setNextAction("");
    onClose();
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) handleClose(); }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-8 h-8 rounded-lg bg-blue/10 border border-blue/25 flex items-center justify-center">
              <Phone className="w-4 h-4 text-blue" />
            </div>
            <DialogTitle>Log Call</DialogTitle>
          </div>
        </DialogHeader>

        <div className="space-y-4">
          <p className="text-sm text-text-secondary">
            Logging call for <span className="text-text-primary font-medium">{prospect?.company_name}</span>
          </p>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-1.5">
                Duration (minutes)
              </label>
              <Input
                type="number"
                value={duration}
                onChange={(e) => setDuration(e.target.value)}
                placeholder="0"
                min="0"
              />
            </div>

            <div>
              <label className="block text-sm font-medium text-text-secondary mb-1.5">
                Outcome
              </label>
              <Select value={outcome} onValueChange={(v) => setOutcome(v as CallOutcome)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="answered">Answered</SelectItem>
                  <SelectItem value="voicemail">Voicemail</SelectItem>
                  <SelectItem value="no_answer">No Answer</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>

          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1.5">
              Summary notes
            </label>
            <Textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="What was discussed?"
              rows={3}
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1.5">
              Next action
            </label>
            <Input
              value={nextAction}
              onChange={(e) => setNextAction(e.target.value)}
              placeholder="e.g., Send proposal by Friday"
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={handleClose} disabled={loading}>Cancel</Button>
          <Button onClick={handleSubmit} disabled={loading}>
            {loading ? "Logging..." : "Log Call"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
