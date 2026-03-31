"use client";

import { useMemo, useState } from "react";
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
import { formatUsd } from "@/lib/crm/format";
import { PLAN_OPTIONS } from "@/lib/crm/types";

export function CloseWonModal({
  open,
  onOpenChange,
  onConfirm,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onConfirm: (payload: {
    planId: string;
    mrrCents: number;
    paymentConfirmed: boolean;
    stripeCustomerId: string | null;
  }) => Promise<void>;
}) {
  const [planId, setPlanId] = useState<string>("shield");
  const [customMrr, setCustomMrr] = useState<string>("");
  const [paymentConfirmed, setPaymentConfirmed] = useState(false);
  const [stripeId, setStripeId] = useState("");
  const [saving, setSaving] = useState(false);

  const mrrCents = useMemo(() => {
    if (planId === "custom") {
      const n = parseFloat(customMrr || "0");
      if (!Number.isFinite(n)) return 0;
      return Math.round(n * 100);
    }
    const p = PLAN_OPTIONS.find((x) => x.id === planId);
    return p?.mrrCents ?? 0;
  }, [planId, customMrr]);

  const closingCommission = Math.round(mrrCents * 0.3);

  async function handleConfirm() {
    if (!paymentConfirmed) return;
    setSaving(true);
    try {
      await onConfirm({
        planId,
        mrrCents,
        paymentConfirmed,
        stripeCustomerId: stripeId.trim() || null,
      });
      onOpenChange(false);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="border-zinc-800 bg-zinc-950">
        <DialogHeader>
          <DialogTitle className="text-zinc-100">Close won</DialogTitle>
          <DialogDescription className="text-zinc-400">
            Do not log a close until payment is confirmed in Stripe.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <Label className="text-zinc-300">Plan</Label>
            <select
              className="mt-1 w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100"
              value={planId}
              onChange={(e) => setPlanId(e.target.value)}
            >
              {PLAN_OPTIONS.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </div>
          {planId === "custom" && (
            <div>
              <Label className="text-zinc-300">Monthly value (USD)</Label>
              <Input
                type="number"
                className="mt-1 border-zinc-700 bg-zinc-900"
                value={customMrr}
                onChange={(e) => setCustomMrr(e.target.value)}
                placeholder="2500"
              />
            </div>
          )}
          <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 px-3 py-2 text-sm text-zinc-300">
            <div>Monthly value: {formatUsd(mrrCents)}</div>
            <div className="mt-1 text-emerald-400">
              Closing commission preview (30%): {formatUsd(closingCommission)}
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm text-zinc-200">
            <input
              type="checkbox"
              checked={paymentConfirmed}
              onChange={(e) => setPaymentConfirmed(e.target.checked)}
              className="h-4 w-4 rounded border-zinc-600"
            />
            Payment confirmed in Stripe (required)
          </label>
          <div>
            <Label className="text-zinc-300">Stripe customer ID (optional)</Label>
            <Input
              className="mt-1 border-zinc-700 bg-zinc-900"
              value={stripeId}
              onChange={(e) => setStripeId(e.target.value)}
              placeholder="cus_..."
            />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" className="border-zinc-700" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            className="bg-emerald-600 hover:bg-emerald-500"
            disabled={saving || !paymentConfirmed || mrrCents <= 0}
            onClick={() => void handleConfirm()}
          >
            Confirm close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
