"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Shield, MessageCircle, PlayCircle, UserPlus, User, CheckCircle2, Circle, ArrowRight } from "lucide-react";

const ONBOARDING_ITEMS = [
  {
    id: "whatsapp",
    icon: MessageCircle,
    title: "Set up WhatsApp notifications",
    description: "Get real-time alerts on closes, hot leads, and client churn risks.",
    action: "Go to Settings",
    href: "/settings",
  },
  {
    id: "training",
    icon: PlayCircle,
    title: "Watch 3-min CRM training video",
    description: "Learn how to use the pipeline, log calls, and close deals in HAWK CRM.",
    action: "Watch video",
    href: "#",
    external: true,
  },
  {
    id: "prospect",
    icon: UserPlus,
    title: "Add your first prospect",
    description: "Start building your pipeline by adding a company to track.",
    action: "Go to Pipeline",
    href: "/pipeline",
  },
  {
    id: "profile",
    icon: User,
    title: "Complete your profile",
    description: "Add your WhatsApp number and profile photo.",
    action: "Edit profile",
    href: "/settings",
  },
] as const;

type ItemId = (typeof ONBOARDING_ITEMS)[number]["id"];

export default function OnboardingPage() {
  const router = useRouter();
  const [completed, setCompleted] = useState<Set<ItemId>>(new Set());

  useEffect(() => {
    const stored = localStorage.getItem("hawk_crm_onboarding");
    if (stored) {
      try {
        const parsed = JSON.parse(stored) as ItemId[];
        setCompleted(new Set(parsed));
      } catch {
        // ignore parse errors
      }
    }
  }, []);

  const toggleItem = (id: ItemId) => {
    setCompleted((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      localStorage.setItem("hawk_crm_onboarding", JSON.stringify(Array.from(next)));
      return next;
    });
  };

  const handleFinish = () => {
    localStorage.setItem("hawk_crm_onboarding_done", "true");
    router.push("/dashboard");
  };

  const allDone = completed.size === ONBOARDING_ITEMS.length;
  const progress = (completed.size / ONBOARDING_ITEMS.length) * 100;

  return (
    <div className="min-h-screen flex items-center justify-center px-4" style={{ background: "#07060C" }}>
      <div className="w-full max-w-lg">
        {/* Logo */}
        <div className="flex items-center gap-3 justify-center mb-8">
          <div className="flex items-center justify-center w-12 h-12 rounded-xl bg-accent/20 border border-accent/40">
            <Shield className="w-6 h-6 text-accent-light" />
          </div>
          <div>
            <div className="text-xl font-bold text-text-primary tracking-tight">HAWK</div>
            <div className="text-xs font-medium text-text-dim uppercase tracking-widest -mt-0.5">CRM</div>
          </div>
        </div>

        <div className="rounded-2xl border border-border p-8" style={{ background: "#0D0B14" }}>
          <div className="mb-6">
            <h1 className="text-xl font-semibold text-text-primary mb-1">Welcome to HAWK CRM</h1>
            <p className="text-text-secondary text-sm">
              Complete these steps to get started. You can always skip and come back later.
            </p>
          </div>

          {/* Progress bar */}
          <div className="mb-6">
            <div className="flex items-center justify-between text-xs text-text-dim mb-2">
              <span>{completed.size} of {ONBOARDING_ITEMS.length} completed</span>
              <span>{Math.round(progress)}%</span>
            </div>
            <div className="h-1.5 bg-surface-3 rounded-full overflow-hidden">
              <div
                className="h-full bg-accent rounded-full transition-all duration-500"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>

          {/* Checklist */}
          <div className="space-y-3 mb-8">
            {ONBOARDING_ITEMS.map((item) => {
              const Icon = item.icon;
              const isDone = completed.has(item.id);

              return (
                <div
                  key={item.id}
                  className={`flex items-start gap-4 p-4 rounded-xl border transition-all cursor-pointer ${
                    isDone
                      ? "border-green/30 bg-green/5"
                      : "border-border bg-surface-2 hover:border-accent/40"
                  }`}
                  onClick={() => toggleItem(item.id)}
                >
                  <div className="mt-0.5">
                    {isDone ? (
                      <CheckCircle2 className="w-5 h-5 text-green" />
                    ) : (
                      <Circle className="w-5 h-5 text-text-dim" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-0.5">
                      <Icon className="w-4 h-4 text-accent-light flex-shrink-0" />
                      <span className={`text-sm font-medium ${isDone ? "text-text-secondary line-through" : "text-text-primary"}`}>
                        {item.title}
                      </span>
                    </div>
                    <p className="text-xs text-text-dim">{item.description}</p>
                  </div>
                  {!isDone && (
                    <div
                      onClick={(e) => {
                        e.stopPropagation();
                        if (!("external" in item && item.external)) {
                          router.push(item.href);
                        }
                      }}
                      className="text-xs text-accent-light hover:text-accent transition-colors flex-shrink-0 cursor-pointer mt-0.5"
                    >
                      {item.action} →
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Actions */}
          <div className="flex items-center justify-between">
            <button
              onClick={handleFinish}
              className="text-sm text-text-dim hover:text-text-secondary transition-colors"
            >
              Skip for now
            </button>
            <button
              onClick={handleFinish}
              disabled={!allDone}
              className={`flex items-center gap-2 px-5 py-2.5 rounded-lg text-sm font-medium transition-all ${
                allDone
                  ? "bg-accent hover:bg-accent/90 text-white"
                  : "bg-surface-3 text-text-dim cursor-not-allowed"
              }`}
            >
              Go to Dashboard
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
