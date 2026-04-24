import type { Metadata } from "next";
import { Suspense } from "react";
import { PortalHeader } from "@/components/portal/portal-header";
import { PortalGate } from "@/components/portal/portal-gate";
import { portal } from "@/lib/portal-ui";
import { cn } from "@/lib/utils";

export const metadata: Metadata = {
  title: "HAWK Client Portal",
  description: "Your security score, findings, and HAWK guidance.",
};

function PortalGateFallback() {
  return (
    <div className="flex min-h-[50vh] items-center justify-center text-ink-0">
      <div className={portal.spinner} />
    </div>
  );
}

export default function PortalLayout({ children }: { children: React.ReactNode }) {
  return (
    <div
      className={cn(
        portal.pageBg,
        // Duplicated here so Tailwind always emits these utilities from `app/` (belt + suspenders).
        "min-h-dvh w-full bg-gradient-to-b from-ink-900 via-ink-950 to-ink-950 text-ink-0 antialiased",
      )}
    >
      <PortalHeader />
      <main className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
        <Suspense fallback={<PortalGateFallback />}>
          <PortalGate>{children}</PortalGate>
        </Suspense>
      </main>
    </div>
  );
}
