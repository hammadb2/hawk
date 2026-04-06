/**
 * True when marketing pricing should use POST /api/billing/checkout-public-test
 * (Railway STRIPE_SECRET_KEY_TEST, STRIPE_PRICE_*_TEST; webhook verified with STRIPE_WEBHOOK_SECRET_TEST).
 *
 * Set NEXT_PUBLIC_TEST_MODE=true on Vercel, or keep NEXT_PUBLIC_STRIPE_CHECKOUT_TEST_MODE=true for backwards compatibility.
 */
export function isStripeCheckoutTestMode(): boolean {
  return (
    process.env.NEXT_PUBLIC_TEST_MODE === "true" ||
    process.env.NEXT_PUBLIC_STRIPE_CHECKOUT_TEST_MODE === "true"
  );
}
