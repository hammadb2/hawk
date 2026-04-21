import type { Metadata } from "next";
import { MarketingShell } from "@/components/marketing/marketing-shell";
import { GuaranteeTermsClient } from "@/components/guarantee/guarantee-terms-client";

export const metadata: Metadata = {
  title: "Guarantee terms. HAWK Security.",
  description:
    "HAWK Breach Response Guarantee. Verify your work email to view the full document.",
  openGraph: {
    title: "Guarantee terms. HAWK Security.",
    description:
      "HAWK Breach Response Guarantee. Verify your work email to view the full document.",
    url: "https://securedbyhawk.com/guarantee-terms",
    siteName: "HAWK Security",
    type: "website",
  },
  robots: { index: true, follow: true },
};

export default function GuaranteeTermsPage() {
  return (
    <MarketingShell ambient={false}>
      <GuaranteeTermsClient />
    </MarketingShell>
  );
}
