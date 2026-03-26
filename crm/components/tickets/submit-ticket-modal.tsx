"use client";

import { useState } from "react";
import { LifeBuoy, Send } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ticketsApi } from "@/lib/api";
import { toast } from "@/components/ui/toast";

interface SubmitTicketModalProps {
  open: boolean;
  onClose: () => void;
}

export function SubmitTicketModal({ open, onClose }: SubmitTicketModalProps) {
  const [description, setDescription] = useState("");
  const [whatDoing, setWhatDoing] = useState("");
  const [loading, setLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = async () => {
    if (!description.trim()) return;
    setLoading(true);

    try {
      const result = await ticketsApi.submit({
        raw_text: description.trim(),
        what_were_you_doing: whatDoing.trim() || undefined,
      });

      if (result.success) {
        setSubmitted(true);
        toast({ title: "Ticket submitted", variant: "success" });
        setTimeout(() => {
          handleClose();
        }, 2000);
      } else {
        toast({ title: result.error || "Failed to submit ticket", variant: "destructive" });
      }
    } catch {
      toast({ title: "Network error", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setDescription("");
    setWhatDoing("");
    setSubmitted(false);
    onClose();
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) handleClose(); }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-8 h-8 rounded-lg bg-blue/10 border border-blue/25 flex items-center justify-center">
              <LifeBuoy className="w-4 h-4 text-blue" />
            </div>
            <DialogTitle>Submit Support Ticket</DialogTitle>
          </div>
        </DialogHeader>

        {submitted ? (
          <div className="py-6 text-center">
            <div className="w-12 h-12 rounded-full bg-green/10 border border-green/25 flex items-center justify-center mx-auto mb-3">
              <Send className="w-6 h-6 text-green" />
            </div>
            <p className="text-sm font-medium text-text-primary">Ticket submitted!</p>
            <p className="text-xs text-text-dim mt-1">We'll triage it shortly.</p>
          </div>
        ) : (
          <>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-1.5">
                  What happened? <span className="text-red">*</span>
                </label>
                <Textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="Describe the issue in detail..."
                  rows={4}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-1.5">
                  What were you trying to do? <span className="text-text-dim">(optional)</span>
                </label>
                <Textarea
                  value={whatDoing}
                  onChange={(e) => setWhatDoing(e.target.value)}
                  placeholder="Describe what you were doing when this occurred..."
                  rows={2}
                />
              </div>
            </div>

            <DialogFooter>
              <Button variant="ghost" onClick={handleClose} disabled={loading}>Cancel</Button>
              <Button onClick={handleSubmit} disabled={!description.trim() || loading}>
                {loading ? "Submitting..." : "Submit Ticket"}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
