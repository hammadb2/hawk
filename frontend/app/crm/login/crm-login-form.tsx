"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import toast from "react-hot-toast";
import { getCrmMagicLinkCallbackUrl } from "@/lib/site-url";
import { crmFieldSurface, crmSurfaceCard } from "@/lib/crm/crm-surface";

export function CrmLoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const err = searchParams.get("error");
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [linkSent, setLinkSent] = useState(false);
  const { authReady, session } = useCrmAuth();
  const supabase = useMemo(() => createClient(), []);

  useEffect(() => {
    if (authReady && session) router.replace("/crm/dashboard");
  }, [authReady, session, router]);

  async function sendLink(e: React.FormEvent) {
    e.preventDefault();
    if (!email.trim()) return;
    setLoading(true);
    const next = searchParams.get("next") ?? "/crm/dashboard";
    const { error } = await supabase.auth.signInWithOtp({
      email: email.trim(),
      options: {
        emailRedirectTo: getCrmMagicLinkCallbackUrl(next),
      },
    });
    setLoading(false);
    if (error) {
      toast.error(error.message);
      return;
    }
    setLinkSent(true);
    toast.success("Check your email for the magic link.");
  }

  return (
    <div className={`w-full max-w-md p-8 shadow-xl ${crmSurfaceCard}`}>
      <h1 className="text-2xl font-semibold tracking-tight text-white">HAWK CRM</h1>
      <p className="mt-2 text-sm text-ink-200">Sign in with a magic link (invite required).</p>
      {err && <p className="mt-4 text-sm text-red">Authentication failed. Try again.</p>}
      <form className="mt-8 space-y-4" onSubmit={sendLink}>
        <div>
          <Label htmlFor="email" className="text-ink-200">
            Work email
          </Label>
          <Input
            id="email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => {
              setEmail(e.target.value);
              setLinkSent(false);
            }}
            className={`mt-1 ${crmFieldSurface}`}
            placeholder="you@company.com"
          />
        </div>
        <Button
          type="submit"
          className="w-full bg-signal-400 hover:bg-signal disabled:opacity-90"
          disabled={loading || linkSent}
        >
          {loading ? "Sending…" : linkSent ? "Sent" : "Send magic link"}
        </Button>
        {linkSent && (
          <p className="text-center text-sm text-ink-200">Check your inbox — edit the email above to send again.</p>
        )}
      </form>
      <p className="mt-6 text-center text-xs text-ink-0">
        <Link href="/" className="underline hover:text-ink-100">
          Back to HAWK product site
        </Link>
      </p>
    </div>
  );
}
