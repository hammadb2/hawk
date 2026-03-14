"use client";

import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/components/providers/auth-provider";
import { billingApi } from "@/lib/api";

export default function DashboardSettingsPage() {
  const searchParams = useSearchParams();
  const { user, token } = useAuth();
  const [invoices, setInvoices] = useState<{ id: string; amount_due: number; status: string; pdf_url?: string; created: number }[]>([]);

  useEffect(() => {
    if (!token) return;
    billingApi.invoices(token).then((r) => setInvoices(r.invoices || [])).catch(() => {});
  }, [token]);

  const openCheckout = async (plan: string) => {
    if (!token) return;
    try {
      const { url } = await billingApi.checkout({ plan }, token);
      if (url) window.location.href = url;
    } catch {
      // not configured
    }
  };

  const openPortal = async () => {
    if (!token) return;
    try {
      const { url } = await billingApi.portal(token);
      if (url) window.location.href = url;
    } catch {
      // no customer
    }
  };

  const billingSuccess = searchParams.get("billing") === "success";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Settings</h1>
        <p className="text-text-secondary mt-1">Account, notifications, and billing.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Account</CardTitle>
          <CardDescription>Your profile and plan.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <p><span className="text-text-dim">Email:</span> {user?.email}</p>
          <p><span className="text-text-dim">Plan:</span> <span className="capitalize">{user?.plan}</span></p>
          {user?.trial_ends_at && (
            <p><span className="text-text-dim">Trial ends:</span> {new Date(user.trial_ends_at).toLocaleDateString()}</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Billing</CardTitle>
          <CardDescription>Manage subscription and invoices.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {billingSuccess && (
            <p className="text-sm text-green">Thank you — your subscription is active.</p>
          )}
          <Button onClick={openPortal} variant="secondary">
            Open customer portal
          </Button>
          <div>
            <p className="text-sm font-medium text-text-secondary mb-2">Upgrade</p>
            <div className="flex gap-2 flex-wrap">
              <Button variant="outline" size="sm" onClick={() => openCheckout("starter")}>Starter $149/mo</Button>
              <Button variant="outline" size="sm" onClick={() => openCheckout("pro")}>Pro $349/mo</Button>
              <Button variant="outline" size="sm" onClick={() => openCheckout("agency")}>Agency $799/mo</Button>
            </div>
          </div>
          {invoices.length > 0 && (
            <div>
              <p className="text-sm font-medium text-text-secondary mb-2">Invoices</p>
              <ul className="space-y-1 text-sm">
                {invoices.map((inv) => (
                  <li key={inv.id} className="flex justify-between">
                    <span>{new Date(inv.created * 1000).toLocaleDateString()} — ${(inv.amount_due / 100).toFixed(2)}</span>
                    {inv.pdf_url && (
                      <a href={inv.pdf_url} target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">PDF</a>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
