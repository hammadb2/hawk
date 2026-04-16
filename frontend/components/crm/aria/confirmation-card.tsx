"use client";

import { useState } from "react";

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
      <div className="rounded-xl border border-emerald-200 bg-emerald-50 p-4">
        <p className="text-sm text-emerald-700 font-medium">Action confirmed and executed.</p>
      </div>
    );
  }

  if (resolved === "cancelled") {
    return (
      <div className="rounded-xl border border-slate-200 bg-slate-50 p-4">
        <p className="text-sm text-slate-500">Action cancelled.</p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h4 className="text-sm font-semibold text-slate-800">{title}</h4>
      <p className="mt-1 text-sm text-slate-600">{description}</p>
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
          className="rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50 transition disabled:opacity-50"
        >
          {cancelLabel}
        </button>
      </div>
    </div>
  );
}
