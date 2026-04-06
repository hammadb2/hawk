"use client";

import { useState } from "react";
import { billingApi } from "@/lib/api";
import { isStripeCheckoutTestMode } from "@/lib/stripe-checkout-mode";

const HAWK = "#00C48C";

/** Shown above Starter/Shield pricing when NEXT_PUBLIC_TEST_MODE=true (or NEXT_PUBLIC_STRIPE_CHECKOUT_TEST_MODE). */
export function StripeTestModeBanner() {
  if (!isStripeCheckoutTestMode()) return null;
  return (
    <div className="mx-auto mt-8 max-w-3xl rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-center text-sm text-amber-100">
      <strong className="font-semibold text-amber-50">Test mode</strong> — use card{" "}
      <span className="font-mono">4242 4242 4242 4242</span>. Checkout uses Stripe test keys and{" "}
      <code className="rounded bg-black/30 px-1 font-mono text-xs">/api/billing/checkout-public-test</code>. Clear{" "}
      <code className="rounded bg-black/30 px-1 font-mono text-xs">NEXT_PUBLIC_TEST_MODE</code> on Vercel for live cards.
    </div>
  );
}

function useCheckout() {
  const [loading, setLoading] = useState(false);
  const go = async (hawk_product: "starter" | "shield") => {
    setLoading(true);
    try {
      const { url } = await billingApi.checkoutPublic({ hawk_product });
      if (url) window.location.href = url;
    } catch (e) {
      console.error(e);
      const raw = e instanceof Error ? e.message : "";
      const msg =
        raw === "Not Found"
          ? "Payment checkout could not reach the billing API. Redeploy the Hawk API with /api/billing/checkout-public, and set NEXT_PUBLIC_API_URL on Vercel to your Railway API URL."
          : raw || "Checkout unavailable. Contact hello@securedbyhawk.com.";
      alert(msg);
    } finally {
      setLoading(false);
    }
  };
  return { loading, go };
}

export function StarterCheckoutButton() {
  const { loading, go } = useCheckout();
  return (
    <button
      type="button"
      disabled={loading}
      onClick={() => go("starter")}
      className="mt-6 block w-full rounded-lg py-3 text-center text-sm font-semibold text-[#07060C] disabled:opacity-60"
      style={{ backgroundColor: HAWK }}
    >
      {loading ? "Redirecting…" : "Get Started"}
    </button>
  );
}

export function ShieldCheckoutButton() {
  const { loading, go } = useCheckout();
  return (
    <button
      type="button"
      disabled={loading}
      onClick={() => go("shield")}
      className="mt-6 block w-full rounded-lg py-3 text-center text-sm font-semibold text-[#07060C] disabled:opacity-60"
      style={{ backgroundColor: HAWK }}
    >
      {loading ? "Redirecting…" : "Get Started — Most Popular"}
    </button>
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
