"use client";

import { useAuth } from "@/components/providers/auth-provider";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import Link from "next/link";
import { Button } from "@/components/ui/button";

const HIPAA_ITEMS = [
  { section: "164.312", title: "Technical Safeguards", summary: "Access controls, audit controls, integrity controls, and transmission security. HAWK findings (SSL/TLS, open ports, headers) map directly to technical safeguards." },
  { section: "164.308", title: "Administrative Safeguards", summary: "Security management, risk analysis, contingency planning. HAWK score helps document your risk posture." },
];

const FTC_ITEMS = [
  { section: "314.4(c)", title: "Information Security Program", summary: "Encryption of customer data in transit and at rest. HAWK validates TLS, HTTPS enforcement, and HSTS." },
  { section: "314.4(d)", title: "Monitoring & Testing", summary: "Regularly test your safeguards. HAWK provides continuous external attack surface monitoring." },
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
          <p className="text-text-secondary mt-1">HIPAA, FTC Safeguards Rule, and NIST mapping (Pro & Agency).</p>
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Upgrade to Pro</CardTitle>
            <CardDescription>
              Compliance mapping (HIPAA, FTC Safeguards Rule, NIST) is included in Pro and Agency plans.
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
        <p className="text-text-secondary mt-1">How HAWK findings map to HIPAA, FTC Safeguards Rule, and NIST.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>HIPAA Security Rule (Healthcare)</CardTitle>
          <CardDescription>Technical and administrative safeguards for protected health information.</CardDescription>
        </CardHeader>
        <CardContent className="pt-0 space-y-4">
          {HIPAA_ITEMS.map((item) => (
            <div key={item.section} className="border-b border-surface-3 pb-4 last:border-0 last:pb-0">
              <p className="font-semibold text-text-primary">§{item.section} — {item.title}</p>
              <p className="text-sm text-text-secondary mt-1">{item.summary}</p>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>FTC Safeguards Rule (Financial Services)</CardTitle>
          <CardDescription>Information security requirements for financial institutions.</CardDescription>
        </CardHeader>
        <CardContent className="pt-0 space-y-4">
          {FTC_ITEMS.map((item) => (
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
