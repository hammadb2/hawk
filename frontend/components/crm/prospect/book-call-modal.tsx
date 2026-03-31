"use client";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

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
      <DialogContent className="max-h-[90vh] max-w-3xl border-zinc-800 bg-zinc-950 p-0">
        <DialogHeader className="border-b border-zinc-800 px-4 py-3">
          <DialogTitle className="text-zinc-100">Book a call</DialogTitle>
          <p className="text-xs text-zinc-500">Set NEXT_PUBLIC_CALCOM_URL to your Cal.com link.</p>
        </DialogHeader>
        <div className="h-[min(70vh,640px)] w-full">
          <iframe title="Cal.com" src={url} className="h-full w-full rounded-b-xl bg-white" />
        </div>
        <div className="flex justify-end border-t border-zinc-800 px-4 py-2">
          <Button variant="outline" className="border-zinc-700" onClick={() => onOpenChange(false)}>
            Close
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
