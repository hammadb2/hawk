import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "HAWK Client Portal",
  description: "Your security score, findings, and HAWK guidance.",
};

export default function PortalLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-[#07060C] text-zinc-100">
      <header className="border-b border-zinc-800/80 bg-[#07060C]/95 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-4">
          <Link href="/portal" className="flex items-center gap-2">
            <span className="text-lg font-bold tracking-tight text-zinc-50">HAWK</span>
            <span className="rounded-md bg-[#00C48C]/15 px-2 py-0.5 text-xs font-medium text-[#00C48C]">Client</span>
          </Link>
          <nav className="text-sm">
            <Link href="/portal/login" className="text-zinc-400 hover:text-[#00C48C]">
              Sign out / login
            </Link>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-8">{children}</main>
    </div>
  );
}
