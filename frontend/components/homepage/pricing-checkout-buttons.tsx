"use client";

import Link from "next/link";


export function StarterCheckoutButton() {
  const next = encodeURIComponent("/portal/billing?plan=starter");
  return (
    <Link
      href={`/portal/login?next=${next}`}
      className="mt-6 block w-full rounded-lg bg-accent py-3 text-center text-sm font-semibold text-white transition-opacity hover:bg-accent/90"
    >
      Get started
    </Link>
  );
}

export function ShieldCheckoutButton() {
  const next = encodeURIComponent("/portal/billing?plan=shield");
  return (
    <Link
      href={`/portal/login?next=${next}`}
      className="mt-6 block w-full rounded-lg bg-accent py-3 text-center text-sm font-semibold text-white transition-opacity hover:bg-accent/90"
    >
      Get started. Most picked.
    </Link>
  );
}

export function EnterpriseBookingLink({ href }: { href: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="mt-6 block w-full rounded-lg border border-white/10 bg-ink-800 py-3 text-center text-sm font-semibold text-ink-0 shadow-sm hover:bg-ink-900"
    >
      Book a Sentinel intro
    </a>
  );
}
