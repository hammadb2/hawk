/** True when marketing pricing should hit Stripe test keys/prices (Railway STRIPE_*_TEST). */
export function isStripeCheckoutTestMode(): boolean {
  return process.env.NEXT_PUBLIC_STRIPE_CHECKOUT_TEST_MODE === "true";
}
