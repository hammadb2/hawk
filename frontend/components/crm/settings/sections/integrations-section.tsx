"use client";

import { SettingsCard } from "../fields";

type ValueGetter = (key: string, fallback?: string) => string;

type Item = { name: string; description: string; href?: string };

const INTEGRATIONS: Item[] = [
  {
    name: "Smartlead",
    description: "Outbound email dispatch. Configure API key + inbox pool in Smartlead and set campaign IDs above.",
    href: "https://app.smartlead.ai/",
  },
  {
    name: "Google Places",
    description: "Business discovery — replaces Apify Actor 1. Key is held on the backend (GOOGLE_PLACES_API_KEY).",
    href: "https://console.cloud.google.com/",
  },
  {
    name: "Apify",
    description: "Contact enrichment actors. Budget + limits controlled in Apify console. Toggles live under Discovery.",
    href: "https://console.apify.com/",
  },
  {
    name: "ZeroBounce",
    description: "Email verification between enrichment and draft. Key is held on the backend (ZEROBOUNCE_API_KEY).",
    href: "https://www.zerobounce.net/",
  },
  {
    name: "OpenAI",
    description: "Powers ARIA chat, vertical classification, and personalized email drafts. Model is configurable via OPENAI_MODEL.",
    href: "https://platform.openai.com/",
  },
  {
    name: "Supabase",
    description: "Primary datastore. Manages auth, prospects, settings, real-time live refresh.",
    href: "https://supabase.com/dashboard",
  },
  {
    name: "Hawk Scanner v2",
    description: "Self-hosted vulnerability scanner. Used by SLA auto-scan + manual Scan button.",
  },
  {
    name: "Cal.com",
    description: "Booking integration. Proxied through /api/crm/webhooks/cal.",
    href: "https://cal.com/",
  },
];

export function IntegrationsSection({ value: _value }: { value: ValueGetter }) {
  return (
    <SettingsCard
      title="Connected services"
      description="API keys live in Railway env vars (not here). This panel summarizes what's wired up."
    >
      <ul className="space-y-3">
        {INTEGRATIONS.map((i) => (
          <li key={i.name} className="flex items-start justify-between gap-4 rounded-md border border-[#1e1e2e] bg-[#0d0d14] p-3">
            <div>
              <div className="text-sm font-medium text-white">{i.name}</div>
              <p className="mt-1 text-xs text-ink-200">{i.description}</p>
            </div>
            {i.href ? (
              <a
                href={i.href}
                target="_blank"
                rel="noreferrer"
                className="shrink-0 rounded-md border border-[#1e1e2e] px-3 py-1 text-xs text-ink-100 hover:bg-[#14141f]"
              >
                Open
              </a>
            ) : null}
          </li>
        ))}
      </ul>
    </SettingsCard>
  );
}
