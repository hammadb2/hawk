import type { Metadata } from "next";
import { MarketingShell } from "@/components/marketing/marketing-shell";
import { PrivacyContent } from "@/components/marketing/privacy-content";

export const metadata: Metadata = {
  title: "Privacy policy. HAWK Security.",
  description:
    "How HAWK Security collects, stores, and uses business contact and domain scan data. Plain language. No surprises.",
  openGraph: {
    title: "Privacy policy. HAWK Security.",
    description:
      "How HAWK Security collects, stores, and uses business contact and domain scan data.",
    url: "https://securedbyhawk.com/privacy",
    siteName: "HAWK Security",
    type: "website",
  },
  robots: { index: true, follow: true },
};

export default function PrivacyPage() {
  return (
    <MarketingShell ambient={false}>
      <PrivacyContent />
    </MarketingShell>
  );
}
