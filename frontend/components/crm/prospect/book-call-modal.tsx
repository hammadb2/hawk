"use client";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { crmDialogSurface } from "@/lib/crm/crm-surface";

const DEFAULT_CAL = "https://cal.com";

export function BookCallModal({
  open,
  onOpenChange,
  domain,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  domain: string;
}) {
  const base = process.env.NEXT_PUBLIC_CALCOM_URL || DEFAULT_CAL;
  const url = base.includes("?") ? `${base}&notes=${encodeURIComponent(domain)}` : `${base}?notes=${encodeURIComponent(domain)}`;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className={`max-h-[90vh] max-w-3xl p-0 ${crmDialogSurface}`}>
        <DialogHeader className="border-b border-[#1e1e2e] px-4 py-3">
          <DialogTitle className="text-white">Book a call</DialogTitle>
          <p className="text-xs text-ink-200">Set NEXT_PUBLIC_CALCOM_URL to your Cal.com link.</p>
        </DialogHeader>
        <div className="h-[min(70vh,640px)] w-full bg-[#0d0d14]">
          <iframe title="Cal.com" src={url} className="h-full w-full rounded-b-xl bg-ink-800" />
        </div>
        <div className="flex justify-end border-t border-[#1e1e2e] px-4 py-2">
          <Button variant="outline" className="border-[#1e1e2e] bg-[#0d0d14] text-ink-100 hover:bg-[#1a1a24]" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
