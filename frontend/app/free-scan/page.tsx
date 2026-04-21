import type { Metadata } from "next";
import { FreeScanLanding } from "@/components/free-scan/free-scan-landing";

export const metadata: Metadata = {
  title: "Free 3-finding security scan — HAWK Security",
  description:
    "Enter your domain. Get a plain-English report with the 3 highest-priority external findings on your business within 24 hours. No credit card, no sales call.",
  openGraph: {
    title: "Free 3-finding security scan — HAWK Security",
    description:
      "What attackers see on your external surface — mailed to you within 24 hours.",
    url: "https://securedbyhawk.com/free-scan",
    siteName: "HAWK Security",
    type: "website",
  },
  robots: { index: true, follow: true },
};

export default function FreeScanPage() {
  return <FreeScanLanding />;
}
