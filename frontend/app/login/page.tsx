import { redirect } from "next/navigation";

/** Self-serve signup removed — pay via Stripe, then magic link at /portal/login */
export default function LoginPage() {
  redirect("/portal/login");
}
