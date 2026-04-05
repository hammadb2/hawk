"use client";

import { useState } from "react";
import { billingApi } from "@/lib/api";

const HAWK = "#00C48C";

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
          : raw || "Checkout unavailable. Contact hello@akbstudios.com.";
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
