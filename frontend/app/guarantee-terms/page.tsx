import type { Metadata } from "next";
import { GuaranteeTermsClient } from "@/components/guarantee/guarantee-terms-client";

export const metadata: Metadata = {
  title: "Guarantee terms — HAWK Security",
  description: "HAWK Breach Response Guarantee — verify your email to view the full document.",
};

export default function GuaranteeTermsPage() {
  return <GuaranteeTermsClient />;
}
