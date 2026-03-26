"use client";

import { useState, useEffect } from "react";
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
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { AlertTriangle, DollarSign, TrendingUp } from "lucide-react";
import { useCRMStore } from "@/store/crm-store";
import { prospectsApi } from "@/lib/api";
import { toast } from "@/components/ui/toast";
import { PLAN_VALUES, calculateClosingCommission } from "@/lib/commission";
import { formatCurrency } from "@/lib/utils";
import type { Prospect, ClientPlan, CloseWonData } from "@/types/crm";

const PLAN_LABELS: Record<ClientPlan, string> = {
  starter: `Starter — ${formatCurrency(99)}/mo`,
  shield: `Shield — ${formatCurrency(199)}/mo`,
  enterprise: `Enterprise — ${formatCurrency(399)}/mo`,
  custom: "Custom (enter amount)",
};

interface CloseWonModalProps {
  open: boolean;
  onClose: () => void;
  prospect: Prospect | null;
  onConfirm?: () => void;
}

export function CloseWonModal({ open, onClose, prospect, onConfirm }: CloseWonModalProps) {
  const { user, updateProspect, addClient } = useCRMStore();
  const [plan, setPlan] = useState<ClientPlan>("shield");
  const [customMRR, setCustomMRR] = useState("");
  const [paymentConfirmed, setPaymentConfirmed] = useState(false);
  const [stripeId, setStripeId] = useState("");
  const [loading, setLoading] = useState(false);

  const mrr = plan === "custom" ? (parseFloat(customMRR) || 0) : PLAN_VALUES[plan];
  const commission = user
    ? calculateClosingCommission(user.role, mrr, true)
    : 0;

  const canSubmit = plan && mrr > 0 && paymentConfirmed;

  const handleConfirm = async () => {
    if (!prospect || !canSubmit) return;
    setLoading(true);

    const data: CloseWonData = {
      plan,
      mrr,
      payment_confirmed: paymentConfirmed,
      stripe_customer_id: stripeId || undefined,
    };

    try {
      const result = await prospectsApi.closeWon(prospect.id, data);
      if (result.success && result.data) {
        updateProspect(prospect.id, { stage: "closed_won" });
        addClient(result.data);
        toast({
          title: `${prospect.company_name} closed! ${formatCurrency(commission)} commission earned.`,
          variant: "success",
        });
        onConfirm?.();
        handleClose();
      } else {
        toast({ title: result.error || "Failed to close deal", variant: "destructive" });
      }
    } catch {
      toast({ title: "Network error", variant: "destructive" });
    } finally {
      setLoading(false);
    }
  };

  const handleClose = () => {
    setPlan("shield");
    setCustomMRR("");
    setPaymentConfirmed(false);
    setStripeId("");
    onClose();
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) handleClose(); }}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <div className="flex items-center gap-2 mb-1">
            <div className="w-8 h-8 rounded-lg bg-green/10 border border-green/25 flex items-center justify-center flex-shrink-0">
              <TrendingUp className="w-4 h-4 text-green" />
            </div>
            <DialogTitle>Close Won</DialogTitle>
          </div>
          <DialogDescription>
            {prospect?.company_name} — Confirm plan and payment to close this deal.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1.5">
              Plan <span className="text-red">*</span>
            </label>
            <Select value={plan} onValueChange={(v) => setPlan(v as ClientPlan)}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(Object.keys(PLAN_LABELS) as ClientPlan[]).map((p) => (
                  <SelectItem key={p} value={p}>{PLAN_LABELS[p]}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {plan === "custom" && (
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-1.5">
                Monthly Value (CAD) <span className="text-red">*</span>
              </label>
              <div className="relative">
                <DollarSign className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-dim" />
                <Input
                  type="number"
                  value={customMRR}
                  onChange={(e) => setCustomMRR(e.target.value)}
                  placeholder="0"
                  className="pl-8"
                  min="1"
                />
              </div>
            </div>
          )}

          {/* Commission preview */}
          <div className="p-3 rounded-lg bg-green/5 border border-green/20">
            <div className="flex items-center justify-between">
              <span className="text-sm text-text-secondary">Your closing commission</span>
              <span className="text-lg font-bold text-green">{formatCurrency(commission)}</span>
            </div>
            {mrr > 0 && (
              <p className="text-xs text-text-dim mt-0.5">
                Based on {formatCurrency(mrr)}/mo — updates live as plan changes
              </p>
            )}
          </div>

          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1.5">
              Stripe Customer ID <span className="text-text-dim">(optional)</span>
            </label>
            <Input
              value={stripeId}
              onChange={(e) => setStripeId(e.target.value)}
              placeholder="cus_..."
            />
          </div>

          {/* Payment confirmation — REQUIRED */}
          <div className={`flex items-start gap-3 p-3 rounded-lg border ${
            paymentConfirmed ? "border-green/30 bg-green/5" : "border-red/30 bg-red/5"
          }`}>
            <Checkbox
              checked={paymentConfirmed}
              onCheckedChange={(c) => setPaymentConfirmed(!!c)}
              className="mt-0.5"
            />
            <div>
              <p className="text-sm font-medium text-text-primary">Payment confirmed</p>
              <p className="text-xs text-text-dim mt-0.5">
                REQUIRED: I confirm that first-month payment has been received or a valid subscription is active in Stripe. Commissions are subject to 90-day clawback if client cancels.
              </p>
            </div>
          </div>

          {!paymentConfirmed && (
            <div className="flex items-start gap-2 p-2.5 rounded-lg bg-yellow/5 border border-yellow/20">
              <AlertTriangle className="w-3.5 h-3.5 text-yellow mt-0.5 flex-shrink-0" />
              <p className="text-xs text-yellow">
                You must confirm payment before closing. Commission will not be paid on unconfirmed deals.
              </p>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={handleClose} disabled={loading}>
            Cancel
          </Button>
          <Button
            onClick={handleConfirm}
            disabled={!canSubmit || loading}
            className="bg-green/80 hover:bg-green/70 text-white"
          >
            {loading ? "Closing deal..." : "Confirm Close Won"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
