"use client";

import { crmSurfaceCard } from "@/lib/crm/crm-surface";

export function DangerZoneSection({
  onReset,
  disabled,
}: {
  onReset: () => void;
  disabled?: boolean;
}) {
  return (
    <section className={`${crmSurfaceCard} border-red/30 p-5`}>
      <header className="mb-4">
        <h2 className="text-sm font-semibold text-red">Danger zone</h2>
        <p className="mt-1 text-xs text-ink-200">
          Destructive actions. Nothing here soft-deletes data; these only touch configuration.
        </p>
      </header>
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-4 rounded-md border border-red/30 bg-red/100/5 p-3">
          <div>
            <div className="text-sm font-medium text-white">Reset all settings to defaults</div>
            <p className="mt-1 text-xs text-ink-200">
              Overwrites every known key with its factory default. Unknown keys are left alone.
            </p>
          </div>
          <button
            onClick={onReset}
            disabled={disabled}
            className="shrink-0 rounded-md bg-red/15 px-3 py-2 text-xs font-semibold text-white hover:bg-red/100 disabled:opacity-40"
          >
            Reset
          </button>
        </div>
      </div>
    </section>
  );
}
