"use client";

import { useState } from "react";
import {
  Clock, ArrowUpCircle, Settings, Unlock, Lock,
  PauseCircle, PlayCircle, ScanLine, KeyRound, Bell,
} from "lucide-react";
import { UserRole } from "@/types/crm";
const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "";
import { cn } from "@/lib/utils";

interface ProductCommandsProps {
  clientId: string;
  userRole: UserRole;
  companyName: string;
}

interface CommandDef {
  id: string;
  label: string;
  icon: React.ReactNode;
  allowedRoles: UserRole[];
  destructive?: boolean;
  fields?: FieldDef[];
  confirmMessage: string;
}

interface FieldDef {
  key: string;
  label: string;
  type: "number" | "select" | "text" | "textarea";
  options?: string[];
  placeholder?: string;
  min?: number;
  max?: number;
  required?: boolean;
}

const COMMANDS: CommandDef[] = [
  {
    id: "extend-trial",
    label: "Extend Trial",
    icon: <Clock className="w-4 h-4" />,
    allowedRoles: ["ceo", "hos", "csm"],
    confirmMessage: "Extend this customer's trial?",
    fields: [
      { key: "days", label: "Days to extend", type: "number", min: 1, max: 30, required: true },
      { key: "reason", label: "Reason (optional)", type: "text", placeholder: "e.g. Onboarding delay" },
    ],
  },
  {
    id: "convert-trial",
    label: "Convert Trial → Paid",
    icon: <ArrowUpCircle className="w-4 h-4" />,
    allowedRoles: ["ceo", "hos"],
    confirmMessage: "End the trial early and convert this customer to paid?",
    fields: [
      {
        key: "plan",
        label: "Plan",
        type: "select",
        options: ["starter", "shield", "enterprise"],
        required: true,
      },
    ],
  },
  {
    id: "change-plan",
    label: "Change Plan",
    icon: <Settings className="w-4 h-4" />,
    allowedRoles: ["ceo", "hos"],
    confirmMessage: "Change this customer's plan?",
    fields: [
      {
        key: "plan",
        label: "New Plan",
        type: "select",
        options: ["trial", "starter", "shield", "enterprise"],
        required: true,
      },
      { key: "reason", label: "Reason", type: "text", required: true },
    ],
  },
  {
    id: "grant-feature",
    label: "Grant Feature Access",
    icon: <Unlock className="w-4 h-4" />,
    allowedRoles: ["ceo"],
    confirmMessage: "Grant out-of-plan feature access?",
    fields: [
      {
        key: "feature",
        label: "Feature",
        type: "select",
        options: ["compliance", "agency", "hawk_ai", "breach_check", "advanced_reports", "white_label", "api_access"],
        required: true,
      },
      { key: "reason", label: "Reason", type: "text", required: true },
    ],
  },
  {
    id: "revoke-feature",
    label: "Revoke Feature Access",
    icon: <Lock className="w-4 h-4" />,
    allowedRoles: ["ceo"],
    destructive: true,
    confirmMessage: "Revoke feature access? The customer will lose access immediately.",
    fields: [
      {
        key: "feature",
        label: "Feature",
        type: "select",
        options: ["compliance", "agency", "hawk_ai", "breach_check", "advanced_reports", "white_label", "api_access"],
        required: true,
      },
    ],
  },
  {
    id: "pause-account",
    label: "Pause Account",
    icon: <PauseCircle className="w-4 h-4" />,
    allowedRoles: ["ceo"],
    destructive: true,
    confirmMessage: "Pause this account? Billing and access will be suspended immediately.",
    fields: [
      { key: "reason", label: "Reason", type: "text", required: true },
    ],
  },
  {
    id: "reactivate-account",
    label: "Reactivate Account",
    icon: <PlayCircle className="w-4 h-4" />,
    allowedRoles: ["ceo", "hos"],
    confirmMessage: "Reactivate this paused account?",
  },
  {
    id: "add-scan-credits",
    label: "Add Scan Credits",
    icon: <ScanLine className="w-4 h-4" />,
    allowedRoles: ["ceo", "hos", "csm"],
    confirmMessage: "Add free scan credits to this account?",
    fields: [
      { key: "credits", label: "Credits to add", type: "number", min: 1, max: 100, required: true },
      { key: "reason", label: "Reason", type: "text" },
    ],
  },
  {
    id: "force-password-reset",
    label: "Force Password Reset",
    icon: <KeyRound className="w-4 h-4" />,
    allowedRoles: ["ceo"],
    destructive: true,
    confirmMessage: "Force a password reset? The customer will receive a reset email immediately.",
    fields: [
      { key: "reason", label: "Reason", type: "text", required: true },
    ],
  },
  {
    id: "send-notification",
    label: "Send In-Product Notification",
    icon: <Bell className="w-4 h-4" />,
    allowedRoles: ["ceo", "hos", "team_lead", "rep", "csm"],
    confirmMessage: "Send this notification to the customer's HAWK dashboard?",
    fields: [
      { key: "title", label: "Title", type: "text", placeholder: "Notification title", required: true },
      { key: "message", label: "Message", type: "textarea", placeholder: "Notification body…", required: true },
      {
        key: "notification_type",
        label: "Type",
        type: "select",
        options: ["info", "warning", "success", "error"],
      },
    ],
  },
];

export function ProductCommands({ clientId, userRole, companyName }: ProductCommandsProps) {
  const [activeCommand, setActiveCommand] = useState<CommandDef | null>(null);
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; message: string } | null>(null);

  const available = COMMANDS.filter((c) => c.allowedRoles.includes(userRole));

  function openCommand(cmd: CommandDef) {
    setActiveCommand(cmd);
    setFieldValues({});
    setResult(null);
  }

  function closeModal() {
    setActiveCommand(null);
    setFieldValues({});
    setResult(null);
  }

  async function execute() {
    if (!activeCommand) return;
    setLoading(true);
    try {
      const body: Record<string, unknown> = { client_id: clientId };
      for (const [k, v] of Object.entries(fieldValues)) {
        body[k] = k === "days" || k === "credits" ? parseInt(v, 10) : v;
      }
      const res = await fetch(`${API_URL}/api/crm/commands/${activeCommand.id}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail ?? `Request failed: ${res.status}`);
      }
      setResult({ ok: true, message: `${activeCommand.label} — executed successfully.` });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Command failed";
      setResult({ ok: false, message: msg });
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <div className="rounded-xl border border-surface-3 bg-surface-1 p-6">
        <h3 className="font-semibold text-text-primary mb-4">Product Controls</h3>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {available.map((cmd) => (
            <button
              key={cmd.id}
              onClick={() => openCommand(cmd)}
              className={cn(
                "flex items-center gap-2 px-3 py-2.5 rounded-lg text-sm font-medium text-left transition-colors",
                cmd.destructive
                  ? "bg-red-500/10 border border-red-500/20 text-red-400 hover:bg-red-500/20"
                  : "bg-surface-2 border border-surface-3 text-text-secondary hover:text-text-primary hover:bg-surface-3",
              )}
            >
              {cmd.icon}
              {cmd.label}
            </button>
          ))}
        </div>
        {available.length === 0 && (
          <p className="text-sm text-text-dim">No product commands available for your role.</p>
        )}
      </div>

      {/* Confirmation Modal */}
      {activeCommand && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-surface-1 border border-surface-3 rounded-2xl w-full max-w-md shadow-2xl">
            <div className="p-6">
              <h2 className="text-lg font-semibold text-text-primary mb-1">{activeCommand.label}</h2>
              <p className="text-sm text-text-secondary mb-5">
                {activeCommand.confirmMessage} — <span className="font-medium text-text-primary">{companyName}</span>
              </p>

              {/* Fields */}
              {activeCommand.fields && (
                <div className="space-y-3 mb-5">
                  {activeCommand.fields.map((field) => (
                    <div key={field.key}>
                      <label className="block text-xs text-text-dim mb-1">
                        {field.label}
                        {field.required && <span className="text-red-400 ml-0.5">*</span>}
                      </label>
                      {field.type === "select" ? (
                        <select
                          value={fieldValues[field.key] ?? ""}
                          onChange={(e) => setFieldValues((v) => ({ ...v, [field.key]: e.target.value }))}
                          className="w-full bg-surface-2 border border-surface-3 rounded-lg px-3 py-2 text-sm text-text-primary focus:outline-none focus:ring-1 focus:ring-accent"
                        >
                          <option value="">Select…</option>
                          {field.options?.map((o) => (
                            <option key={o} value={o}>{o}</option>
                          ))}
                        </select>
                      ) : field.type === "textarea" ? (
                        <textarea
                          rows={3}
                          value={fieldValues[field.key] ?? ""}
                          placeholder={field.placeholder}
                          onChange={(e) => setFieldValues((v) => ({ ...v, [field.key]: e.target.value }))}
                          className="w-full bg-surface-2 border border-surface-3 rounded-lg px-3 py-2 text-sm text-text-primary placeholder-text-dim focus:outline-none focus:ring-1 focus:ring-accent resize-none"
                        />
                      ) : (
                        <input
                          type={field.type}
                          value={fieldValues[field.key] ?? ""}
                          placeholder={field.placeholder}
                          min={field.min}
                          max={field.max}
                          onChange={(e) => setFieldValues((v) => ({ ...v, [field.key]: e.target.value }))}
                          className="w-full bg-surface-2 border border-surface-3 rounded-lg px-3 py-2 text-sm text-text-primary placeholder-text-dim focus:outline-none focus:ring-1 focus:ring-accent"
                        />
                      )}
                    </div>
                  ))}
                </div>
              )}

              {/* Result */}
              {result && (
                <div className={cn(
                  "rounded-lg px-3 py-2.5 text-sm mb-4",
                  result.ok ? "bg-green-500/10 text-green-400" : "bg-red-500/10 text-red-400",
                )}>
                  {result.message}
                </div>
              )}

              {/* Actions */}
              <div className="flex gap-2 justify-end">
                <button
                  onClick={closeModal}
                  className="px-4 py-2 rounded-lg text-sm text-text-secondary bg-surface-2 hover:bg-surface-3 transition-colors"
                >
                  {result?.ok ? "Close" : "Cancel"}
                </button>
                {!result?.ok && (
                  <button
                    onClick={execute}
                    disabled={loading}
                    className={cn(
                      "px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50",
                      activeCommand.destructive
                        ? "bg-red-500 hover:bg-red-600 text-white"
                        : "bg-accent hover:bg-accent/90 text-white",
                    )}
                  >
                    {loading ? "Executing…" : "Confirm"}
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
