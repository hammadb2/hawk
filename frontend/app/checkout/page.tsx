"use client";

import { Suspense, useMemo, useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { loadStripe } from "@stripe/stripe-js";
import { CardElement, Elements, useElements, useStripe } from "@stripe/react-stripe-js";
import { billingApi } from "@/lib/api";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { portal } from "@/lib/portal-ui";

const ACCENT = "#FFB800";

const SHIELD_FEATURES = [
  "Daily monitoring",
  "Weekly attacker simulation",
  "Real-time alerts",
  "HAWK Certified after 90 days",
  "Financially backed guarantee",
  "Onboarding call",
];

const STARTER_FEATURES = [
  "Daily monitoring",
  "Weekly security summary",
  "Real-time alerts",
  "Remediation guidance",
  "Onboarding resources",
];

function CheckoutFormInner({ plan }: { plan: "shield" | "starter" }) {
  const stripe = useStripe();
  const elements = useElements();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const priceLabel = plan === "shield" ? "CA$997/month" : "CA$199/month";
  const buttonLabel = `Pay ${priceLabel}`;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!stripe || !elements) return;
    const card = elements.getElement(CardElement);
    if (!card) {
      setError("Card field not ready.");
      return;
    }
    setLoading(true);
    setError("");

    try {
      const { client_secret, subscription_id } = await billingApi.createPaymentIntent({
        email: email.trim(),
        name: name.trim(),
        hawk_product: plan,
        test_mode: false,
      });

      const { error: stripeError, paymentIntent } = await stripe.confirmCardPayment(client_secret, {
        payment_method: {
          card,
          billing_details: { name: name.trim(), email: email.trim().toLowerCase() },
        },
      });

      if (stripeError) {
        setError(stripeError.message || "Payment failed");
        setLoading(false);
        return;
      }

      if (paymentIntent?.status !== "succeeded") {
        setError("Payment did not complete. Try again.");
        setLoading(false);
        return;
      }

      await new Promise((r) => setTimeout(r, 800));

      const { redirect_url } = await billingApi.completeCheckoutSession({
        subscription_id,
        email: email.trim().toLowerCase(),
        name: name.trim(),
      });

      if (redirect_url) {
        window.location.href = redirect_url;
        return;
      }
      setError("No redirect URL from server.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={(e) => void handleSubmit(e)} className="space-y-5">
      <div>
        <Label>Full name</Label>
        <Input
          type="text"
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Dr. Jane Smith"
          className="mt-1.5 border-white/10 bg-ink-800 text-ink-0 placeholder:text-ink-200"
        />
      </div>
      <div>
        <Label>Email address</Label>
        <Input
          type="email"
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@yourclinic.com"
          className="mt-1.5 border-white/10 bg-ink-800 text-ink-0 placeholder:text-ink-200"
        />
      </div>
      <div>
        <Label>Card details</Label>
        <div className="mt-1.5 rounded-lg border border-white/10 bg-ink-800 px-3 py-3">
          <CardElement
            options={{
              style: {
                base: {
                  fontSize: "16px",
                  color: "#0f172a",
                  "::placeholder": { color: "#94a3b8" },
                },
                invalid: { color: "#e11d48" },
              },
            }}
          />
        </div>
      </div>
      {error ? <p className="text-sm text-red">{error}</p> : null}
      <Button
        type="submit"
        disabled={!stripe || loading}
        className="w-full bg-signal font-semibold text-white hover:bg-signal-400 disabled:opacity-60"
      >
        {loading ? "Processing…" : buttonLabel}
      </Button>
      <p className="text-center text-xs text-ink-0">
        Backed by our breach response guarantee. Cancel anytime.
      </p>
    </form>
  );
}

function CheckoutPageContent() {
  const searchParams = useSearchParams();
  const planParam = (searchParams.get("plan") || "shield").toLowerCase();
  const plan: "shield" | "starter" = planParam === "starter" ? "starter" : "shield";

  const stripePromise = useMemo(() => {
    const pk = process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY;
    if (!pk) return null;
    return loadStripe(pk);
  }, []);

  const title = plan === "shield" ? "HAWK Shield" : "HAWK Starter";
  const price = plan === "shield" ? "CA$997/month" : "CA$199/month";
  const features = plan === "shield" ? SHIELD_FEATURES : STARTER_FEATURES;

  return (
    <div className={`min-h-dvh ${portal.pageBg}`}>
      <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6">
        <div className="mb-10 flex flex-col items-center gap-4 sm:flex-row sm:justify-between">
          <Link href="/" className="inline-flex items-center rounded-lg bg-ink-950 px-2.5 py-2 ring-1 ring-white/10">
            <Image src="/hawk-logo.png" alt="HAWK" width={180} height={60} className="h-11 w-auto" />
          </Link>
          <Link href="/#pricing" className="text-sm text-ink-200 hover:text-signal">
            ← Back to pricing
          </Link>
        </div>

        {!stripePromise ? (
          <p className="rounded-lg border border-red/30 bg-red/10 px-4 py-3 text-center text-sm text-red">
            Missing Stripe publishable key. Set NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY on Vercel.
          </p>
        ) : (
          <div className="grid gap-8 lg:grid-cols-2 lg:gap-12">
            <div className="rounded-2xl border border-white/10 bg-ink-800 p-6 shadow-sm sm:p-8">
              <h1 className="text-2xl font-bold text-ink-0">{title}</h1>
              <p className="mt-2 text-3xl font-semibold" style={{ color: ACCENT }}>
                {price}
              </p>
              <ul className="mt-6 space-y-2 text-sm text-ink-200">
                {features.map((f) => (
                  <li key={f} className="flex gap-2">
                    <span style={{ color: ACCENT }}>✓</span>
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
              <p className="mt-8 text-sm leading-relaxed text-ink-0">
                Backed by our breach response guarantee.
                <br />
                Cancel anytime.
              </p>
            </div>

            <div className="rounded-2xl border border-white/10 bg-ink-800 p-6 shadow-sm sm:p-8">
              <h2 className="mb-6 text-lg font-semibold text-ink-0">Payment</h2>
              <Elements stripe={stripePromise}>
                <CheckoutFormInner plan={plan} />
              </Elements>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default function CheckoutPage() {
  return (
    <Suspense
      fallback={
        <div className={`flex min-h-dvh items-center justify-center ${portal.pageBg}`}>
          <div className="h-10 w-10 animate-spin rounded-full border-2 border-white/10 border-t-signal" />
        </div>
      }
    >
      <CheckoutPageContent />
    </Suspense>
  );
}
