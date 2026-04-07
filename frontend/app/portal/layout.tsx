import type { Metadata } from "next";
import { Suspense } from "react";
import { PortalHeader } from "@/components/portal/portal-header";
import { PortalGate } from "@/components/portal/portal-gate";

export const metadata: Metadata = {
  title: "HAWK Client Portal",
  description: "Your security score, findings, and HAWK guidance.",
};

function PortalGateFallback() {
  return (
    <div className="flex min-h-[50vh] items-center justify-center text-zinc-500">
      <div className="h-10 w-10 animate-spin rounded-full border-2 border-zinc-700 border-t-[#00C48C]" />
    </div>
  );
}

export default function PortalLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-[#07060C] text-zinc-100">
      <PortalHeader />
      <main className="mx-auto max-w-6xl px-4 py-8">
        <Suspense fallback={<PortalGateFallback />}>
          <PortalGate>{children}</PortalGate>
        </Suspense>
      </main>
    </div>
  );
}
