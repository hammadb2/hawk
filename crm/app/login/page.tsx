"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { createClient } from "@/lib/supabase";
import { Shield, Mail, Lock, Loader2, AlertCircle, CheckCircle2 } from "lucide-react";

export default function LoginPage() {
  const router = useRouter();
  const supabase = createClient();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [magicLoading, setMagicLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [magicSent, setMagicSent] = useState(false);
  const [mode, setMode] = useState<"password" | "magic">("password");

  const handleSignIn = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      const { data, error: signInError } = await supabase.auth.signInWithPassword({
        email: email.trim(),
        password,
      });

      if (signInError) {
        setError(signInError.message);
        return;
      }

      if (!data.session) {
        setError("Sign in failed. Please try again.");
        return;
      }

      router.push("/dashboard");
    } catch (err) {
      setError("An unexpected error occurred. Please try again.");
      console.error("Login error:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleMagicLink = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setMagicLoading(true);

    try {
      const { error: magicError } = await supabase.auth.signInWithOtp({
        email: email.trim(),
        options: {
          emailRedirectTo: `${window.location.origin}/auth/callback`,
        },
      });

      if (magicError) {
        setError(magicError.message);
        return;
      }

      setMagicSent(true);
    } catch (err) {
      setError("Failed to send magic link. Please try again.");
      console.error("Magic link error:", err);
    } finally {
      setMagicLoading(false);
    }
  };

  if (magicSent) {
    return (
      <div className="min-h-screen flex items-center justify-center px-4" style={{ background: "#07060C" }}>
        <div className="w-full max-w-md text-center">
          <div className="flex items-center justify-center w-16 h-16 mx-auto mb-6 rounded-full bg-green/10 border border-green/30">
            <CheckCircle2 className="w-8 h-8 text-green" />
          </div>
          <h2 className="text-2xl font-semibold text-text-primary mb-2">Check your email</h2>
          <p className="text-text-secondary mb-6">
            We sent a magic link to <span className="text-text-primary font-medium">{email}</span>.
            Click the link to sign in.
          </p>
          <button
            onClick={() => { setMagicSent(false); setEmail(""); }}
            className="text-accent-light hover:text-accent transition-colors text-sm"
          >
            Use a different email
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4" style={{ background: "#07060C" }}>
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="flex items-center gap-3 justify-center mb-10">
          <div className="flex items-center justify-center w-12 h-12 rounded-xl bg-accent/20 border border-accent/40">
            <Shield className="w-6 h-6 text-accent-light" />
          </div>
          <div>
            <div className="text-xl font-bold text-text-primary tracking-tight">HAWK</div>
            <div className="text-xs font-medium text-text-dim uppercase tracking-widest -mt-0.5">CRM</div>
          </div>
        </div>

        {/* Card */}
        <div className="rounded-2xl border border-border p-8" style={{ background: "#0D0B14" }}>
          <h1 className="text-xl font-semibold text-text-primary mb-1">
            {mode === "password" ? "Sign in to your account" : "Send a magic link"}
          </h1>
          <p className="text-text-secondary text-sm mb-6">
            {mode === "password"
              ? "Enter your credentials to access the CRM"
              : "Enter your email and we'll send a sign-in link"}
          </p>

          {error && (
            <div className="flex items-start gap-3 p-3 mb-5 rounded-lg bg-red/10 border border-red/30">
              <AlertCircle className="w-4 h-4 text-red mt-0.5 flex-shrink-0" />
              <p className="text-red text-sm">{error}</p>
            </div>
          )}

          <form onSubmit={mode === "password" ? handleSignIn : handleMagicLink} className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-1.5">
                Email address
              </label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-dim" />
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@hawk.com"
                  required
                  className="w-full pl-9 pr-4 py-3 rounded-lg border border-border bg-surface-2 text-text-primary placeholder:text-text-dim focus:outline-none focus:border-accent/60 focus:ring-1 focus:ring-accent/30 transition-all text-sm"
                />
              </div>
            </div>

            {mode === "password" && (
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-1.5">
                  Password
                </label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-text-dim" />
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••"
                    required
                    className="w-full pl-9 pr-4 py-3 rounded-lg border border-border bg-surface-2 text-text-primary placeholder:text-text-dim focus:outline-none focus:border-accent/60 focus:ring-1 focus:ring-accent/30 transition-all text-sm"
                  />
                </div>
              </div>
            )}

            <button
              type="submit"
              disabled={loading || magicLoading}
              className="w-full py-3 rounded-lg bg-accent hover:bg-accent/90 text-white font-medium text-sm transition-all disabled:opacity-60 disabled:cursor-not-allowed flex items-center justify-center gap-2 mt-2"
            >
              {(loading || magicLoading) && <Loader2 className="w-4 h-4 animate-spin" />}
              {mode === "password" ? "Sign in" : "Send magic link"}
            </button>
          </form>

          <div className="mt-4 text-center">
            {mode === "password" ? (
              <button
                onClick={() => { setMode("magic"); setError(null); }}
                className="text-sm text-text-secondary hover:text-accent-light transition-colors"
              >
                Sign in with a magic link instead
              </button>
            ) : (
              <button
                onClick={() => { setMode("password"); setError(null); }}
                className="text-sm text-text-secondary hover:text-accent-light transition-colors"
              >
                Sign in with password instead
              </button>
            )}
          </div>
        </div>

        <p className="text-center text-text-dim text-xs mt-6">
          HAWK CRM — Internal use only. Unauthorized access is prohibited.
        </p>
      </div>
    </div>
  );
}
