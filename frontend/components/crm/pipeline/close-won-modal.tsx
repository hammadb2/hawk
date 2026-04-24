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
import { readApiErrorResponse } from "@/lib/crm/api-error";
import { CRM_API_BASE_URL } from "@/lib/crm/api-url";
import { formatUsd } from "@/lib/crm/format";
import { PLAN_OPTIONS } from "@/lib/crm/types";
import { crmDialogSurface, crmFieldSurface } from "@/lib/crm/crm-surface";

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
    const r = await fetch(`${CRM_API_BASE_URL}/api/crm/verify-payment`, {
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
      setVerifyError(await readApiErrorResponse(r));
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
        <DialogContent className={crmDialogSurface}>
          <DialogHeader>
            <DialogTitle className="text-white">Close won</DialogTitle>
            <DialogDescription className="text-ink-200">
              We verify Stripe for a successful payment in the last 24 hours before creating commission. You can still
              close the deal and defer commission until payment clears.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label className="text-ink-100">Plan</Label>
              <select
                className={`mt-1 w-full rounded-lg px-3 py-2 text-sm ${crmFieldSurface}`}
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
                <Label className="text-ink-100">Monthly value (USD)</Label>
                <Input
                  type="number"
                  className={`mt-1 ${crmFieldSurface}`}
                  value={customMrr}
                  onChange={(e) => setCustomMrr(e.target.value)}
                  placeholder="2500"
                />
              </div>
            )}
            <div className="rounded-lg border border-[#1e1e2e] bg-[#0d0d14] px-3 py-2 text-sm text-ink-100">
              <div>Monthly value: {formatUsd(mrrCents)}</div>
              <div className="mt-1 text-signal">
                Closing commission preview (30%): {formatUsd(closingCommission)}
              </div>
            </div>
            <div>
              <Label className="text-ink-100">Stripe customer ID (helps verification)</Label>
              <Input
                className={`mt-1 ${crmFieldSurface}`}
                value={stripeId}
                onChange={(e) => setStripeId(e.target.value)}
                placeholder="cus_..."
              />
            </div>
            {verifyError && <p className="text-xs text-red">{verifyError}</p>}
          </div>
          <DialogFooter className="gap-2 sm:gap-0">
            <Button variant="outline" className="border-[#1e1e2e] bg-[#0d0d14] text-ink-100 hover:bg-[#1a1a24]" onClick={() => onOpenChange(false)}>
              Cancel
            </Button>
            <Button
              className="bg-signal-400 hover:bg-signal"
              disabled={saving || verifying || mrrCents <= 0}
              onClick={() => void tryClose()}
            >
              {verifying ? "Verifying…" : "Verify & close"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={deferPrompt} onOpenChange={setDeferPrompt}>
        <DialogContent className={crmDialogSurface}>
          <DialogHeader>
            <DialogTitle className="text-white">Payment not verified in Stripe</DialogTitle>
            <DialogDescription className="text-ink-200">
              Payment not yet confirmed in Stripe. Commission will be created automatically when payment clears (via Stripe
              webhook).
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" className="border-[#1e1e2e] bg-[#0d0d14] text-ink-100 hover:bg-[#1a1a24]" onClick={() => setDeferPrompt(false)}>
              Back
            </Button>
            <Button
              className="bg-amber-600 hover:bg-signal"
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
