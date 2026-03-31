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

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

export function CloseWonModal({
  open,
  onOpenChange,
  onConfirm,
  accessToken,
  prospectDomain,
}: {
  open: boolean;
  onOpenChange: (v: boolean) => void;
  onConfirm: (payload: {
    planId: string;
    mrrCents: number;
    stripeCustomerId: string | null;
    commissionDeferred: boolean;
  }) => Promise<void>;
  accessToken: string | null;
  prospectDomain: string;
}) {
  const [planId, setPlanId] = useState<string>("shield");
  const [customMrr, setCustomMrr] = useState<string>("");
  const [stripeId, setStripeId] = useState("");
  const [saving, setSaving] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [deferPrompt, setDeferPrompt] = useState(false);
  const [verifyError, setVerifyError] = useState<string | null>(null);

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

  async function verifyStripe(): Promise<boolean> {
    setVerifyError(null);
    if (!accessToken) {
      setVerifyError("Not signed in");
      return false;
    }
    const r = await fetch(`${API_URL}/api/crm/verify-payment`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify({
        domain: prospectDomain,
        mrr_cents: mrrCents,
        stripe_customer_id: stripeId.trim() || null,
      }),
    });
    if (!r.ok) {
      const t = await r.text();
      setVerifyError(t.slice(0, 200));
      return false;
    }
    const j = (await r.json()) as { verified?: boolean };
    return !!j.verified;
  }

  async function handleConfirm(deferred: boolean) {
    if (mrrCents <= 0) return;
    setSaving(true);
    try {
      await onConfirm({
        planId,
        mrrCents,
        stripeCustomerId: stripeId.trim() || null,
        commissionDeferred: deferred,
      });
      onOpenChange(false);
      setDeferPrompt(false);
    } finally {
      setSaving(false);
    }
  }

  async function tryClose() {
    if (mrrCents <= 0) return;
    setVerifying(true);
    setVerifyError(null);
    try {
      const ok = await verifyStripe();
      if (ok) {
        await handleConfirm(false);
        return;
      }
      setDeferPrompt(true);
    } finally {
      setVerifying(false);
    }
  }

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="border-zinc-800 bg-zinc-950">
          <DialogHeader>
            <DialogTitle className="text-zinc-100">Close won</DialogTitle>
            <DialogDescription className="text-zinc-400">
              We verify Stripe for a successful payment in the last 24 hours before creating commission. You can still
              close the deal and defer commission until payment clears.
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
            <div>
              <Label className="text-zinc-300">Stripe customer ID (helps verification)</Label>
              <Input
                className="mt-1 border-zinc-700 bg-zinc-900"
                value={stripeId}
                onChange={(e) => setStripeId(e.target.value)}
                placeholder="cus_..."
              />
            </div>
            {verifyError && <p className="text-xs text-rose-400">{verifyError}</p>}
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" className="border-zinc-700" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button
              className="bg-emerald-600 hover:bg-emerald-500"
              disabled={saving || verifying || mrrCents <= 0}
              onClick={() => void tryClose()}
            >
              {verifying ? "Verifying…" : "Verify & close"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={deferPrompt} onOpenChange={setDeferPrompt}>
        <DialogContent className="border-zinc-800 bg-zinc-950">
          <DialogHeader>
            <DialogTitle className="text-zinc-100">Payment not verified in Stripe</DialogTitle>
            <DialogDescription className="text-zinc-400">
              Payment not yet confirmed in Stripe. Commission will be created automatically when payment clears (via Stripe
              webhook).
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" className="border-zinc-700" onClick={() => setDeferPrompt(false)}>
              Back
            </Button>
            <Button
              className="bg-amber-600 hover:bg-amber-500"
              disabled={saving}
              onClick={() => void handleConfirm(true)}
            >
              Close anyway (defer commission)
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
