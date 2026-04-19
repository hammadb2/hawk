"use client";

import { STAGE_ORDER } from "@/lib/crm/types";

export function PipelinePageSkeleton() {
  return (
    <div className="space-y-4">
      <div className="h-8 w-48 animate-pulse rounded-lg bg-crmSurface" />
      <div className="h-4 w-full max-w-xl animate-pulse rounded bg-crmSurface2" />
      <div className="flex gap-4 overflow-x-auto pb-4">
        {STAGE_ORDER.map((stage) => (
          <div key={stage} className="flex w-[280px] shrink-0 flex-col rounded-xl border border-crmBorder bg-[#111118]">
            <div className="flex items-center justify-between border-b border-crmBorder px-3 py-2">
              <div className="h-4 w-24 animate-pulse rounded bg-crmSurface2" />
              <div className="h-3 w-16 animate-pulse rounded bg-crmSurface2" />
            </div>
            <div className="flex min-h-[200px] flex-col gap-2 p-2">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="h-24 animate-pulse rounded-xl border border-crmBorder bg-[#16161f]" />
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
