"use client";

import { useAuth } from "@/components/providers/auth-provider";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import Link from "next/link";
import { Button } from "@/components/ui/button";

const PIPEDA_ITEMS = [
  { section: "4.7", title: "Safeguards", summary: "Security safeguards to protect personal information. HAWK findings (e.g. SSL, headers, DNS) help show technical safeguards." },
  { section: "4.1.3", title: "Accuracy", summary: "Reasonable steps to ensure accuracy. Secure channels (HTTPS, valid certs) support data integrity." },
];

const BILL_C26_ITEMS = [
  { section: "S.7", title: "Cybersecurity obligations", summary: "Operators of critical systems must protect and report. HAWK surfaces external exposure (ports, TLS, headers) relevant to baseline security." },
];

const NIST_MAP = [
  { nist: "PR.AC-5", title: "Identity and access", hawk: "Network (open ports), Web (headers)" },
  { nist: "PR.DS-2", title: "Data-in-transit", hawk: "SSL/TLS, HTTPS redirect, HSTS" },
  { nist: "PR.IP-1", title: "Baseline configuration", hawk: "All findings (hardening)" },
];

export default function DashboardCompliancePage() {
  const { user } = useAuth();
  const isProOrAgency = user?.plan === "pro" || user?.plan === "agency";

  if (!isProOrAgency) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Compliance</h1>
          <p className="text-text-secondary mt-1">PIPEDA, Bill C-26, and NIST mapping (Pro & Agency).</p>
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Upgrade to Pro</CardTitle>
            <CardDescription>
              Compliance mapping (PIPEDA 4.7, Bill C-26 S.7, NIST) is included in Pro and Agency plans.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Link href="/dashboard/settings">
              <Button>Go to billing</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Compliance</h1>
        <p className="text-text-secondary mt-1">How HAWK findings map to PIPEDA, Bill C-26, and NIST.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>PIPEDA (Personal Information Protection)</CardTitle>
          <CardDescription>Relevant principles and how HAWK helps.</CardDescription>
        </CardHeader>
        <CardContent className="pt-0 space-y-4">
          {PIPEDA_ITEMS.map((item) => (
            <div key={item.section} className="border-b border-surface-3 pb-4 last:border-0 last:pb-0">
              <p className="font-semibold text-text-primary">§{item.section} — {item.title}</p>
              <p className="text-sm text-text-secondary mt-1">{item.summary}</p>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Bill C-26 (Critical Cyber Systems)</CardTitle>
          <CardDescription>Cybersecurity obligations for designated operators.</CardDescription>
        </CardHeader>
        <CardContent className="pt-0 space-y-4">
          {BILL_C26_ITEMS.map((item) => (
            <div key={item.section} className="border-b border-surface-3 pb-4 last:border-0 last:pb-0">
              <p className="font-semibold text-text-primary">{item.section} — {item.title}</p>
              <p className="text-sm text-text-secondary mt-1">{item.summary}</p>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>NIST CSF mapping</CardTitle>
          <CardDescription>HAWK check categories aligned to NIST subcategories.</CardDescription>
        </CardHeader>
        <CardContent className="pt-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-text-secondary border-b border-surface-3">
                <th className="pb-2 pr-4">NIST</th>
                <th className="pb-2 pr-4">Category</th>
                <th className="pb-2">HAWK</th>
              </tr>
            </thead>
            <tbody>
              {NIST_MAP.map((row) => (
                <tr key={row.nist} className="border-b border-surface-3/50">
                  <td className="py-3 pr-4 font-mono text-text-dim">{row.nist}</td>
                  <td className="py-3 pr-4 text-text-primary">{row.title}</td>
                  <td className="py-3 text-text-secondary">{row.hawk}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
