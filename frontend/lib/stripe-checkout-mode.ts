/**
 * True when embedded checkout at /checkout should use Stripe test publishable key + Railway test secret keys.
 * Set NEXT_PUBLIC_TEST_MODE=true on Vercel, or NEXT_PUBLIC_STRIPE_CHECKOUT_TEST_MODE for backwards compatibility.
 */
export function isStripeCheckoutTestMode(): boolean {
  return (
    process.env.NEXT_PUBLIC_TEST_MODE === "true" ||
    process.env.NEXT_PUBLIC_STRIPE_CHECKOUT_TEST_MODE === "true"
  );
}
