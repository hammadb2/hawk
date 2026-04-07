"use client";

import Link from "next/link";
import { isStripeCheckoutTestMode } from "@/lib/stripe-checkout-mode";

const HAWK = "#00C48C";

/** Shown above Starter/Shield pricing when NEXT_PUBLIC_TEST_MODE=true (or NEXT_PUBLIC_STRIPE_CHECKOUT_TEST_MODE). */
export function StripeTestModeBanner() {
  if (!isStripeCheckoutTestMode()) return null;
  return (
    <div className="mx-auto mt-8 max-w-3xl rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-center text-sm text-amber-100">
      <strong className="font-semibold text-amber-50">Test mode</strong> — use card{" "}
      <span className="font-mono">4242 4242 4242 4242</span>. Embedded checkout at{" "}
      <code className="rounded bg-black/30 px-1 font-mono text-xs">/checkout</code> or{" "}
      <code className="rounded bg-black/30 px-1 font-mono text-xs">/portal/billing</code> uses Stripe test keys. Clear{" "}
      <code className="rounded bg-black/30 px-1 font-mono text-xs">NEXT_PUBLIC_TEST_MODE</code> on Vercel for live
      cards.
    </div>
  );
}

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
