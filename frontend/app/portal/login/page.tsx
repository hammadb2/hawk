"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";
import Link from "next/link";
import { createClient } from "@/lib/supabase/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import toast from "react-hot-toast";
import { getPortalMagicLinkCallbackUrl } from "@/lib/site-url";
import { portal } from "@/lib/portal-ui";

function PortalLoginForm() {
  const searchParams = useSearchParams();
  const err = searchParams.get("error");
  const postCheckout = searchParams.get("welcome") === "1";
  const supabase = createClient();
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);

  async function sendLink(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    setLoading(true);
    const nextPath = searchParams.get("next") || "/portal";
    const { error } = await supabase.auth.signInWithOtp({
      email: email.trim().toLowerCase(),
      options: {
        emailRedirectTo: getPortalMagicLinkCallbackUrl(nextPath),
      },
    });
    setLoading(false);
    if (error) {
      toast.error(error.message);
      return;
    }
    setSent(true);
    toast.success("Check your email for the magic link.");
  }

  return (
    <div className="flex min-h-[calc(100dvh-5.5rem)] flex-col items-center justify-center bg-gradient-to-b from-slate-50 via-white to-slate-50 px-4 py-8">
      <div className="w-full max-w-md space-y-6 rounded-2xl border border-slate-200 bg-white p-8 shadow-xl">
        <div className="text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-emerald-600">HAWK Client</p>
          <h1 className="mt-2 text-2xl font-semibold text-slate-900">Portal sign in</h1>
          <p className="mt-1 text-sm text-slate-600">Security score, findings, and guidance for your organization.</p>
          {postCheckout && (
            <p className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-3 text-left text-xs leading-relaxed text-slate-800">
              <strong className="text-emerald-600">Payment confirmed.</strong> You aren&apos;t signed in yet — that&apos;s
              normal. Use the <strong>same email you entered in Stripe</strong>. Check your inbox for the HAWK portal invite
              (magic link), or enter that email below and we&apos;ll send a new link.
            </p>
          )}
          {err === "not_linked" && (
            <p className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
              This account isn&apos;t linked to a client portal yet. Use the email from your welcome message after checkout,
              or contact your CSM.
            </p>
          )}
        </div>
        {sent ? (
          <p className="text-center text-sm text-slate-600">
            We sent a link to <span className="text-slate-800">{email}</span>. Open it on this device to continue.
          </p>
        ) : (
          <form onSubmit={sendLink} className="space-y-4">
            <div>
              <Label className="text-slate-600">Work email</Label>
              <Input
                type="email"
                required
                autoComplete="email"
                className={`mt-1 ${portal.input}`}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
              />
            </div>
            <Button type="submit" className="w-full bg-emerald-500 text-white hover:bg-emerald-600" disabled={loading}>
              {loading ? "Sending…" : "Email me a magic link"}
            </Button>
          </form>
        )}
        <p className="text-center text-xs text-slate-500">
          Sales team?{" "}
          <Link href="/crm/login" className="text-emerald-600 hover:underline">
            HAWK CRM login
          </Link>
        </p>
      </div>
    </div>
  );
}

export default function PortalLoginPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-[calc(100dvh-5.5rem)] items-center justify-center bg-gradient-to-b from-slate-50 via-white to-slate-50 text-slate-600">
          <div className={portal.spinnerSm} />
        </div>
      }
    >
      <PortalLoginForm />
    </Suspense>
  );
}
