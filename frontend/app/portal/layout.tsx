import type { Metadata } from "next";
import { PortalHeader } from "@/components/portal/portal-header";

export const metadata: Metadata = {
  title: "HAWK Client Portal",
  description: "Your security score, findings, and HAWK guidance.",
};

export default function PortalLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-[#07060C] text-zinc-100">
      <PortalHeader />
      <main className="mx-auto max-w-6xl px-4 py-8">{children}</main>
    </div>
  );
}
