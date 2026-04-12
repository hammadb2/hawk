"use client";

import Link from "next/link";
const HAWK = "#00C48C";

export function StarterCheckoutButton() {
  const next = encodeURIComponent("/portal/billing?plan=starter");
  return (
    <Link
      href={`/portal/login?next=${next}`}
      className="mt-6 block w-full rounded-lg py-3 text-center text-sm font-semibold text-[#07060C] transition-opacity hover:opacity-90"
      style={{ backgroundColor: HAWK }}
    >
      Get Started
    </Link>
  );
}

export function ShieldCheckoutButton() {
  const next = encodeURIComponent("/portal/billing?plan=shield");
  return (
    <Link
      href={`/portal/login?next=${next}`}
      className="mt-6 block w-full rounded-lg py-3 text-center text-sm font-semibold text-[#07060C] transition-opacity hover:opacity-90"
      style={{ backgroundColor: HAWK }}
    >
      Get Started — Most Popular
    </Link>
  );
}

export function EnterpriseBookingLink({ href }: { href: string }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="mt-6 block w-full rounded-lg border border-surface-3 py-3 text-center text-sm font-semibold text-text-primary hover:bg-surface-2"
    >
      Book a call — Enterprise
    </a>
  );
}
