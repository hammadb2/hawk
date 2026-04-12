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
    <div className="flex min-h-[70vh] flex-col items-center justify-center px-4">
      <div className="w-full max-w-md space-y-6 rounded-2xl border border-zinc-800 bg-[#07060C] p-8 shadow-xl">
        <div className="text-center">
          <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#00C48C]">HAWK Client</p>
          <h1 className="mt-2 text-2xl font-semibold text-zinc-50">Portal sign in</h1>
          <p className="mt-1 text-sm text-zinc-500">Security score, findings, and guidance for your organization.</p>
          {postCheckout && (
            <p className="mt-3 rounded-lg border border-[#00C48C]/30 bg-[#00C48C]/10 px-3 py-3 text-left text-xs leading-relaxed text-zinc-200">
              <strong className="text-[#00C48C]">Payment confirmed.</strong> You aren&apos;t signed in yet — that&apos;s
              normal. Use the <strong>same email you entered in Stripe</strong>. Check your inbox for the HAWK portal invite
              (magic link), or enter that email below and we&apos;ll send a new link.
            </p>
          )}
          {err === "not_linked" && (
            <p className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
              This account isn&apos;t linked to a client portal yet. Use the email from your welcome message after checkout,
              or contact your CSM.
            </p>
          )}
        </div>
        {sent ? (
          <p className="text-center text-sm text-zinc-400">
            We sent a link to <span className="text-zinc-200">{email}</span>. Open it on this device to continue.
          </p>
        ) : (
          <form onSubmit={sendLink} className="space-y-4">
            <div>
              <Label className="text-zinc-400">Work email</Label>
              <Input
                type="email"
                required
                autoComplete="email"
                className="mt-1 border-zinc-700 bg-zinc-900/80"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
              />
            </div>
            <Button type="submit" className="w-full bg-[#00C48C] text-[#07060C] hover:bg-[#00d69a]" disabled={loading}>
              {loading ? "Sending…" : "Email me a magic link"}
            </Button>
          </form>
        )}
        <p className="text-center text-xs text-zinc-600">
          Sales team?{" "}
          <Link href="/crm/login" className="text-[#00C48C] hover:underline">
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
        <div className="flex min-h-[70vh] items-center justify-center text-zinc-500">
          <div className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-700 border-t-[#00C48C]" />
        </div>
      }
    >
      <PortalLoginForm />
    </Suspense>
  );
}
