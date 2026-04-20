"use client";

export type TabId =
  | "general"
  | "outreach"
  | "campaigns"
  | "discovery"
  | "scanner"
  | "team"
  | "notifications"
  | "integrations"
  | "danger";

type Tab = { id: TabId; label: string; description: string };

export const TABS: Tab[] = [
  { id: "general", label: "General", description: "Brand, timezone, CEO contact" },
  { id: "outreach", label: "Outreach", description: "Daily caps + send window" },
  { id: "campaigns", label: "Campaigns", description: "Smartlead campaign IDs" },
  { id: "discovery", label: "Discovery", description: "Google Places + Apify" },
  { id: "scanner", label: "Scanner", description: "SLA + concurrency" },
  { id: "team", label: "Team", description: "Commission + aging rules" },
  { id: "notifications", label: "Notifications", description: "SMS + Slack alerts" },
  { id: "integrations", label: "Integrations", description: "API key status" },
  { id: "danger", label: "Danger zone", description: "Reset + flush" },
];

export function SettingsTabs({
  active,
  onChange,
  tabs,
}: {
  active: TabId;
  onChange: (id: TabId) => void;
  tabs: Tab[];
}) {
  return (
    <nav className="lg:sticky lg:top-24 lg:self-start">
      <ul className="flex flex-wrap gap-1 lg:flex-col">
        {tabs.map((tab) => {
          const isActive = tab.id === active;
          return (
            <li key={tab.id}>
              <button
                onClick={() => onChange(tab.id)}
                className={[
                  "w-full rounded-lg border px-3 py-2 text-left transition",
                  isActive
                    ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                    : "border-transparent text-slate-300 hover:bg-[#14141f]",
                ].join(" ")}
              >
                <div className="text-sm font-medium">{tab.label}</div>
                <div className="mt-0.5 text-[11px] text-slate-500">{tab.description}</div>
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
