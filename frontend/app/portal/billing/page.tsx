"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { loadStripe } from "@stripe/stripe-js";
import { CardElement, Elements, useElements, useStripe } from "@stripe/react-stripe-js";
import { billingApi } from "@/lib/api";
import { createClient } from "@/lib/supabase/client";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";

const ACCENT = "#10b981";

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

function isPaidClient(row: { billing_status?: string | null; mrr_cents?: number | null } | null): boolean {
  if (!row) return false;
  if (row.billing_status === "active") return true;
  return Number(row.mrr_cents ?? 0) >= 19900;
}

function PortalBillingFormInner({ plan }: { plan: "shield" | "starter" }) {
  const stripe = useStripe();
  const elements = useElements();
  const supabase = useMemo(() => createClient(), []);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const priceLabel = plan === "shield" ? "CA$997/month" : "CA$199/month";
  const buttonLabel = `Pay ${priceLabel}`;

  useEffect(() => {
    void (async () => {
      const {
        data: { session },
      } = await supabase.auth.getSession();
      if (session?.user?.email) {
        setEmail(session.user.email);
        const meta = session.user.user_metadata as { full_name?: string } | undefined;
        if (meta?.full_name) setName(String(meta.full_name));
      }
    })();
  }, [supabase]);

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
      const {
        data: { session },
      } = await supabase.auth.getSession();
      if (!session?.access_token) {
        setError("Sign in again to continue.");
        setLoading(false);
        return;
      }

      const { client_secret, subscription_id } = await billingApi.createPaymentIntentPortal(
        {
          name: name.trim() || name,
          hawk_product: plan,
          test_mode: false,
        },
        session.access_token,
      );

      const { error: stripeError, paymentIntent } = await stripe.confirmCardPayment(client_secret, {
        payment_method: {
          card,
          billing_details: {
            name: name.trim() || email.split("@")[0],
            email: email.trim().toLowerCase(),
          },
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
        name: name.trim() || email.split("@")[0],
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
        <Label className="text-ink-200">Full name</Label>
        <Input
          type="text"
          required
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Dr. Jane Smith"
          className="mt-1.5 border-white/10 bg-ink-800 text-ink-0 placeholder:text-ink-0"
        />
      </div>
      <div>
        <Label className="text-ink-200">Account email</Label>
        <Input
          type="email"
          readOnly
          value={email}
          className="mt-1.5 border-white/10 bg-ink-900 text-ink-200"
        />
        <p className="mt-1 text-xs text-ink-200">Must match your portal sign-in. Charged to this account.</p>
      </div>
      <div>
        <Label className="text-ink-200">Card details</Label>
        <div className="mt-1.5 rounded-lg border border-white/10 bg-ink-800 px-3 py-3">
          <CardElement
            options={{
              style: {
                base: {
                  fontSize: "16px",
                  color: "#0f172a",
                  "::placeholder": { color: "#94a3b8" },
                },
                invalid: { color: "#ff6b6b" },
              },
            }}
          />
        </div>
      </div>
      {error ? <p className="text-sm text-red">{error}</p> : null}
      <Button
        type="submit"
        disabled={!stripe || loading || !email}
        className="w-full bg-signal font-semibold text-white hover:bg-signal-400 disabled:opacity-60"
      >
        {loading ? "Processing…" : buttonLabel}
      </Button>
      <p className="text-center text-xs text-ink-200">
        Backed by our breach response guarantee. Cancel anytime.
      </p>
    </form>
  );
}

function PortalBillingContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const supabase = useMemo(() => createClient(), []);
  const planParam = (searchParams.get("plan") || "shield").toLowerCase();
  const plan: "shield" | "starter" = planParam === "starter" ? "starter" : "shield";

  const stripePromise = useMemo(() => {
    const pk = process.env.NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY;
    if (!pk) return null;
    return loadStripe(pk);
  }, []);

  const [paidCheck, setPaidCheck] = useState<"loading" | "paid" | "unpaid">("loading");

  useEffect(() => {
    void (async () => {
      const {
        data: { session },
      } = await supabase.auth.getSession();
      if (!session) {
        const qs = searchParams.toString();
        const billingPath = "/portal/billing" + (qs ? `?${qs}` : "");
        router.replace(`/portal/login?next=${encodeURIComponent(billingPath)}`);
        return;
      }
      const { data: cpp } = await supabase
        .from("client_portal_profiles")
        .select("client_id")
        .eq("user_id", session.user.id)
        .maybeSingle();
      if (!cpp?.client_id) {
        setPaidCheck("unpaid");
        return;
      }
      const { data: client } = await supabase
        .from("clients")
        .select("billing_status,mrr_cents")
        .eq("id", cpp.client_id)
        .maybeSingle();
      if (isPaidClient(client)) {
        setPaidCheck("paid");
        router.replace("/portal");
        return;
      }
      setPaidCheck("unpaid");
    })();
  }, [router, supabase, searchParams]);

  const title = plan === "shield" ? "HAWK Shield" : "HAWK Starter";
  const price = plan === "shield" ? "CA$997/month" : "CA$199/month";
  const features = plan === "shield" ? SHIELD_FEATURES : STARTER_FEATURES;

  if (paidCheck === "loading" || paidCheck === "paid") {
    return (
      <div className="flex min-h-[50vh] items-center justify-center text-ink-200">
        <div className="h-10 w-10 animate-spin rounded-full border-2 border-white/10 border-t-signal" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl">
      <div className="mb-8 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-lg font-semibold text-ink-0">Subscribe</h1>
        <Link href="/#pricing" className="text-sm text-ink-200 hover:text-signal">
          ← Back to pricing
        </Link>
      </div>

      <p className="mb-6 text-center text-sm text-ink-200">
        Activate your subscription to open the full HAWK client portal.
      </p>

      {!stripePromise ? (
        <p className="rounded-lg border border-red/30 bg-red/10 px-4 py-3 text-center text-sm text-red">
          Missing Stripe publishable key. Set NEXT_PUBLIC_STRIPE_PUBLISHABLE_KEY on Vercel.
        </p>
      ) : (
        <div className="grid gap-8 lg:grid-cols-2 lg:gap-12">
          <div className="rounded-2xl border border-white/10 bg-ink-800 p-6 shadow-sm sm:p-8">
            <h2 className="text-2xl font-bold text-ink-0">{title}</h2>
            <p className="mt-2 text-3xl font-semibold" style={{ color: ACCENT }}>
              {price}
            </p>
            <ul className="mt-6 space-y-2 text-sm text-ink-100">
              {features.map((f) => (
                <li key={f} className="flex gap-2">
                  <span style={{ color: ACCENT }}>✓</span>
                  <span>{f}</span>
                </li>
              ))}
            </ul>
            <p className="mt-8 text-sm leading-relaxed text-ink-200">
              Backed by our breach response guarantee.
              <br />
              Cancel anytime.
            </p>
          </div>

          <div className="rounded-2xl border border-white/10 bg-ink-800 p-6 shadow-sm sm:p-8">
            <h2 className="mb-6 text-lg font-semibold text-ink-0">Payment</h2>
            <Elements stripe={stripePromise}>
              <PortalBillingFormInner plan={plan} />
            </Elements>
          </div>
        </div>
      )}
    </div>
  );
}

export default function PortalBillingPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-ink-900">
          <div className="h-10 w-10 animate-spin rounded-full border-2 border-white/10 border-t-signal" />
        </div>
      }
    >
      <PortalBillingContent />
    </Suspense>
  );
}
