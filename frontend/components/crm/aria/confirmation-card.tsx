"use client";

import { useState } from "react";
import { crmFieldSurface, crmSurfaceCard } from "@/lib/crm/crm-surface";

interface Props {
  title: string;
  description: string;
  onConfirm: () => Promise<void> | void;
  onCancel: () => void;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
}

export function ConfirmationCard({
  title,
  description,
  onConfirm,
  onCancel,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  destructive = false,
}: Props) {
  const [loading, setLoading] = useState(false);
  const [resolved, setResolved] = useState<"confirmed" | "cancelled" | null>(null);

  async function handleConfirm() {
    setLoading(true);
    try {
      await onConfirm();
      setResolved("confirmed");
    } catch {
      setLoading(false);
    }
  }

  function handleCancel() {
    setResolved("cancelled");
    onCancel();
  }

  if (resolved === "confirmed") {
    return (
      <div className="rounded-xl border border-emerald-500/30 bg-emerald-950/30 p-4">
        <p className="text-sm font-medium text-emerald-300">Action confirmed and executed.</p>
      </div>
    );
  }

  if (resolved === "cancelled") {
    return (
      <div className={`p-4 ${crmSurfaceCard}`}>
        <p className="text-sm text-slate-400">Action cancelled.</p>
      </div>
    );
  }

  return (
    <div className={`p-4 ${crmSurfaceCard}`}>
      <h4 className="text-sm font-semibold text-white">{title}</h4>
      <p className="mt-1 text-sm text-slate-400">{description}</p>
      <div className="mt-3 flex gap-2">
        <button
          onClick={() => void handleConfirm()}
          disabled={loading}
          className={`rounded-lg px-4 py-2 text-sm font-medium text-white transition disabled:opacity-50 ${
            destructive
              ? "bg-red-600 hover:bg-red-700"
              : "bg-emerald-600 hover:bg-emerald-700"
          }`}
        >
          {loading ? "Processing..." : confirmLabel}
        </button>
        <button
          onClick={handleCancel}
          disabled={loading}
          className={`px-4 py-2 text-sm font-medium text-slate-300 transition hover:bg-[#1a1a24] disabled:opacity-50 ${crmFieldSurface}`}
        >
          {cancelLabel}
        </button>
      </div>
    </div>
  );
}
