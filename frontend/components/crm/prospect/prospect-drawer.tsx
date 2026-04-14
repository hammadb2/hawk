"use client";

import { ProspectProfile } from "@/components/crm/prospect/prospect-profile";

export function ProspectDrawer({
  prospectId,
  onClose,
  onUpdated,
}: {
  prospectId: string | null;
  onClose: () => void;
  onUpdated?: () => void;
}) {
  if (!prospectId) return null;

  return (
    <>
      <button type="button" className="fixed inset-0 z-50 bg-black/50" aria-label="Close profile" onClick={onClose} />
      <aside className="fixed inset-y-0 right-0 z-50 flex w-full max-w-[560px] flex-col border-l border-slate-200 bg-white shadow-2xl">
        <div className="flex-1 overflow-y-auto p-4">
          <ProspectProfile prospectId={prospectId} variant="drawer" onClose={onClose} onUpdated={onUpdated} />
        </div>
      </aside>
    </>
  );
}
