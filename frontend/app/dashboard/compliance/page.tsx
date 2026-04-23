"use client";

import { useAuth } from "@/components/providers/auth-provider";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import Link from "next/link";
import { Button } from "@/components/ui/button";

const HIPAA_ITEMS = [
  {
    section: "45 CFR 164.312",
    title: "Technical Safeguards",
    summary:
      "Transmission security, access control, and audit controls for ePHI. HAWK findings on TLS, HTTPS redirect, HSTS, and web security headers map directly to these required and addressable implementation specifications.",
  },
  {
    section: "45 CFR 164.308(a)(1)(ii)(A)",
    title: "Risk Analysis",
    summary:
      "Accurate and thorough assessment of foreseeable threats to ePHI confidentiality, integrity, and availability. External exposure findings belong in this analysis.",
  },
  {
    section: "45 CFR 164.404",
    title: "Breach Notification Rule",
    summary:
      "60 day notification clock to HHS and affected individuals when unsecured PHI is acquired, accessed, used, or disclosed without authorization. Media notice for breaches affecting 500 or more individuals.",
  },
];

const FTC_ITEMS = [
  {
    section: "16 CFR 314.4",
    title: "Information Security Program elements",
    summary:
      "Nine required elements including a written program, a Qualified Individual, risk assessment, access controls, encryption, monitoring, training, and service provider oversight.",
  },
  {
    section: "16 CFR 314.4(c)(3)",
    title: "Encryption",
    summary:
      "Customer information transmitted externally or at rest must be encrypted. HAWK findings on weak TLS, expired certificates, or missing HTTPS redirects map to this element.",
  },
  {
    section: "16 CFR 314.5",
    title: "Breach Notification (May 2024)",
    summary:
      "Affirmative 30 day notification duty to the FTC for notification events affecting 500 or more consumers. Effective May 2024 for covered financial institutions including CPA and tax firms.",
  },
];

const ABA_ITEMS = [
  {
    section: "Formal Opinion 24-514",
    title: "Duty to notify clients of material data incidents",
    summary:
      "Lawyers must notify current clients promptly and sufficiently to permit informed decisions about representation affected by a material data incident.",
  },
  {
    section: "Model Rule 1.6(c)",
    title: "Reasonable efforts",
    summary:
      "Make reasonable efforts to prevent inadvertent or unauthorized disclosure of client confidential information. HAWK findings on matter portals, firm websites, and email systems map here.",
  },
  {
    section: "Model Rules 1.1 and 1.4",
    title: "Technology competence and communication",
    summary:
      "Comment 8 to Rule 1.1 requires competence in the technology used to store and transmit client confidences. Rule 1.4 requires keeping clients reasonably informed.",
  },
];

const NIST_MAP = [
  { nist: "PR.AC-5", title: "Identity and access", hawk: "Network (open ports), Web (headers)" },
  { nist: "PR.DS-2", title: "Data in transit", hawk: "SSL/TLS, HTTPS redirect, HSTS" },
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
          <p className="text-text-secondary mt-1">
            HIPAA, FTC Safeguards, ABA Formal Opinion 24-514, and NIST CSF mapping (Pro and Agency).
          </p>
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Upgrade to Pro</CardTitle>
            <CardDescription>
              Vertical aware US compliance mapping (HIPAA, FTC Safeguards Rule, ABA Formal Opinion 24-514, and NIST
              CSF) is included in Pro and Agency plans.
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
        <p className="text-text-secondary mt-1">
          How HAWK findings map to the US framework that applies to each vertical, plus NIST CSF.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>HIPAA Security Rule (dental and medical)</CardTitle>
          <CardDescription>45 CFR 164 Subparts C and D. Enforced by HHS Office for Civil Rights.</CardDescription>
        </CardHeader>
        <CardContent className="pt-0 space-y-4">
          {HIPAA_ITEMS.map((item) => (
            <div key={item.section} className="border-b border-surface-3 pb-4 last:border-0 last:pb-0">
              <p className="font-semibold text-text-primary">
                {item.section} &middot; {item.title}
              </p>
              <p className="text-sm text-text-secondary mt-1">{item.summary}</p>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>FTC Safeguards Rule (accounting, CPA, tax)</CardTitle>
          <CardDescription>16 CFR 314, as amended May 2024. Enforced by the US Federal Trade Commission.</CardDescription>
        </CardHeader>
        <CardContent className="pt-0 space-y-4">
          {FTC_ITEMS.map((item) => (
            <div key={item.section} className="border-b border-surface-3 pb-4 last:border-0 last:pb-0">
              <p className="font-semibold text-text-primary">
                {item.section} &middot; {item.title}
              </p>
              <p className="text-sm text-text-secondary mt-1">{item.summary}</p>
            </div>
          ))}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>ABA Formal Opinion 24-514 (legal)</CardTitle>
          <CardDescription>
            Duty to notify clients of material data incidents. Grounded in Model Rules 1.1, 1.4, and 1.6.
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-0 space-y-4">
          {ABA_ITEMS.map((item) => (
            <div key={item.section} className="border-b border-surface-3 pb-4 last:border-0 last:pb-0">
              <p className="font-semibold text-text-primary">
                {item.section} &middot; {item.title}
              </p>
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
