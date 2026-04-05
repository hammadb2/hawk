/** @type {import('next').NextConfig} */
const nextConfig = {
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
    NEXT_PUBLIC_SITE_URL: process.env.NEXT_PUBLIC_SITE_URL || "",
    NEXT_PUBLIC_CAL_COM_BOOKING_URL: process.env.NEXT_PUBLIC_CAL_COM_BOOKING_URL || "",
    NEXT_PUBLIC_STRIPE_CHECKOUT_TEST_MODE: process.env.NEXT_PUBLIC_STRIPE_CHECKOUT_TEST_MODE || "",
  },
};

module.exports = nextConfig;
