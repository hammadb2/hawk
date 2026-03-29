"use client";

import Link from "next/link";
import { AlertTriangle, LogOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getSupabaseClient } from "@/lib/supabase";

export default function SetupRequiredPage() {
  const handleSignOut = async () => {
    const supabase = getSupabaseClient();
    await supabase.auth.signOut({ scope: "local" });
    window.location.href = "/login";
  };

  return (
    <div
      className="min-h-screen flex items-center justify-center p-6"
      style={{ background: "#07060C" }}
    >
      <div className="max-w-md w-full rounded-2xl border border-border bg-surface-1 p-8 space-y-4">
        <div className="flex items-center gap-3 text-yellow">
          <AlertTriangle className="w-8 h-8 flex-shrink-0" />
          <h1 className="text-lg font-semibold text-text-primary">CRM profile not found</h1>
        </div>
        <p className="text-sm text-text-secondary leading-relaxed">
          You are signed in, but there is no user row in the CRM database yet. If you just joined, your admin may still
          need to provision your account. Completing the onboarding checklist does not create this record by itself.
        </p>
        <p className="text-xs text-text-dim">
          If this page keeps appearing after your admin says you are set up, contact support with your email address.
        </p>
        <div className="flex flex-col sm:flex-row gap-2 pt-2">
          <Button variant="secondary" className="flex-1" asChild>
            <Link href="/onboarding">Onboarding checklist</Link>
          </Button>
          <Button className="flex-1 gap-2" onClick={handleSignOut}>
            <LogOut className="w-4 h-4" />
            Sign out
          </Button>
        </div>
      </div>
    </div>
  );
}
