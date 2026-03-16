"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/components/providers/auth-provider";
import { cn } from "@/lib/utils";

const STEPS = ["welcome", "profile", "domain", "plan", "done"];
const PLAN_OPTIONS = [
  { id: "starter", name: "Starter", price: "$149/mo", domains: "1 domain", scans: "Weekly" },
  { id: "pro", name: "Pro", price: "$349/mo", domains: "3 domains", scans: "Daily", badge: "PIPEDA & C-26" },
  { id: "agency", name: "Agency", price: "$799/mo", domains: "10 domains", scans: "White-label", badge: "Client portal" },
];

export default function OnboardingPage() {
  const router = useRouter();
  const { user, token, refreshUser } = useAuth();
  const [step, setStep] = useState(0);
  const [profile, setProfile] = useState({ industry: "", province: "" });
  const [domain, setDomain] = useState("");
  const [selectedPlan, setSelectedPlan] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const d = params.get("domain");
    if (d) setDomain(d);
  }, []);

  if (!mounted) {
    return <div className="min-h-screen flex items-center justify-center bg-background text-text-secondary">Loading…</div>;
  }
  if (!user && !token) {
    router.replace("/login?register=1");
    return null;
  }

  const updateProfile = async () => {
    if (!token) return;
    setError("");
    setLoading(true);
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      await fetch(`${apiUrl}/api/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      await refreshUser();
      setStep(1);
    } catch {
      setError("Could not update profile.");
    } finally {
      setLoading(false);
    }
  };

  const finishOnboarding = () => {
    if (selectedPlan && selectedPlan !== "trial") {
      router.push("/dashboard/settings?billing=checkout&plan=" + selectedPlan);
    } else {
      router.push("/dashboard");
    }
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-6 bg-background">
      <div className="w-full max-w-lg">
        <div className="flex justify-between mb-8 text-sm text-text-dim">
          {STEPS.map((s, i) => (
            <span key={s} className={i <= step ? "text-text-secondary" : ""}>
              {i + 1}. {s}
            </span>
          ))}
        </div>

        <AnimatePresence mode="wait">
          {step === 0 && (
            <motion.div
              key="welcome"
              initial={{ opacity: 0, x: 10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -10 }}
              className="space-y-6"
            >
              <Card>
                <CardHeader>
                  <CardTitle>Welcome to HAWK</CardTitle>
                  <CardDescription>
                    You’re on a 7-day free trial. Add a domain, run a scan, and explore the dashboard.
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <Button onClick={() => setStep(1)} className="w-full">Continue</Button>
                </CardContent>
              </Card>
            </motion.div>
          )}

          {step === 1 && (
            <motion.div
              key="profile"
              initial={{ opacity: 0, x: 10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -10 }}
            >
              <Card>
                <CardHeader>
                  <CardTitle>Profile (optional)</CardTitle>
                  <CardDescription>Helps us tailor compliance advice (e.g. province, industry).</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-2">
                    <Label>Industry</Label>
                    <Input
                      placeholder="e.g. Healthcare, Finance"
                      value={profile.industry}
                      onChange={(e) => setProfile((p) => ({ ...p, industry: e.target.value }))}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Province</Label>
                    <Input
                      placeholder="e.g. Ontario"
                      value={profile.province}
                      onChange={(e) => setProfile((p) => ({ ...p, province: e.target.value }))}
                    />
                  </div>
                  <Button onClick={() => setStep(2)} className="w-full">Continue</Button>
                </CardContent>
              </Card>
            </motion.div>
          )}

          {step === 2 && (
            <motion.div
              key="domain"
              initial={{ opacity: 0, x: 10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -10 }}
            >
              <Card>
                <CardHeader>
                  <CardTitle>Add your first domain</CardTitle>
                  <CardDescription>Trial includes 1 domain. We’ll run an on-demand scan.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-2">
                    <Label>Domain</Label>
                    <Input
                      placeholder="yourcompany.com"
                      value={domain}
                      onChange={(e) => setDomain(e.target.value)}
                    />
                  </div>
                  <Button
                    onClick={async () => {
                      if (!domain.trim() || !token) {
                        setStep(3);
                        return;
                      }
                      setLoading(true);
                      setError("");
                      try {
                        const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
                        await fetch(`${apiUrl}/api/domains`, {
                          method: "POST",
                          headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
                          body: JSON.stringify({ domain: domain.trim().toLowerCase().replace(/^https?:\/\//, "").replace(/^www\./, ""), scan_frequency: "on_demand" }),
                        });
                        setStep(3);
                      } catch {
                        setError("Could not add domain. You can add it later from the dashboard.");
                        setStep(3);
                      } finally {
                        setLoading(false);
                      }
                    }}
                    className="w-full"
                    disabled={loading}
                  >
                    {loading ? "Adding…" : domain.trim() ? "Add domain & continue" : "Skip & continue"}
                  </Button>
                  {error && <p className="text-sm text-red">{error}</p>}
                </CardContent>
              </Card>
            </motion.div>
          )}

          {step === 3 && (
            <motion.div
              key="plan"
              initial={{ opacity: 0, x: 10 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -10 }}
            >
              <Card>
                <CardHeader>
                  <CardTitle>Choose a plan</CardTitle>
                  <CardDescription>Stay on trial or pick a plan. You can change later.</CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <button
                    type="button"
                    onClick={() => setSelectedPlan("trial")}
                    className={cn(
                      "w-full rounded-lg border p-4 text-left transition-colors",
                      selectedPlan === "trial" ? "border-accent bg-surface-2" : "border-surface-3 hover:border-surface-3"
                    )}
                  >
                    <span className="font-semibold">Free trial</span>
                    <span className="ml-2 text-text-secondary">7 days · 1 domain · 5 Ask HAWK messages</span>
                  </button>
                  {PLAN_OPTIONS.map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      onClick={() => setSelectedPlan(p.id)}
                      className={cn(
                        "w-full rounded-lg border p-4 text-left transition-colors",
                        selectedPlan === p.id ? "border-accent bg-surface-2" : "border-surface-3 hover:border-surface-3"
                      )}
                    >
                      <span className="font-semibold">{p.name}</span>
                      <span className="ml-2 text-text-secondary">{p.price} · {p.domains} · {p.scans}</span>
                      {p.badge && <span className="ml-2 text-xs text-accent">{p.badge}</span>}
                    </button>
                  ))}
                  <Button onClick={finishOnboarding} className="w-full mt-4">
                    {selectedPlan && selectedPlan !== "trial" ? "Continue to checkout" : "Go to dashboard"}
                  </Button>
                </CardContent>
              </Card>
            </motion.div>
          )}

          {step === 4 && (
            <motion.div
              key="done"
              initial={{ opacity: 0, x: 10 }}
              animate={{ opacity: 1, x: 0 }}
            >
              <Card>
                <CardHeader>
                  <CardTitle>You’re all set</CardTitle>
                  <CardDescription>Head to the dashboard to run scans and view findings.</CardDescription>
                </CardHeader>
                <CardContent>
                  <Link href="/dashboard">
                    <Button className="w-full">Open dashboard</Button>
                  </Link>
                </CardContent>
              </Card>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
