"use client";

import type { ReactNode } from "react";
import { crmSurfaceCard } from "@/lib/crm/crm-surface";

export function SettingsCard({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) {
  return (
    <section className={`${crmSurfaceCard} p-5`}>
      <header className="mb-4">
        <h2 className="text-sm font-semibold text-white">{title}</h2>
        {description ? <p className="mt-1 text-xs text-ink-200">{description}</p> : null}
      </header>
      <div className="space-y-4">{children}</div>
    </section>
  );
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="block text-xs font-medium text-ink-100">{label}</span>
      {children}
      {hint ? <span className="mt-1 block text-[11px] text-ink-0">{hint}</span> : null}
    </label>
  );
}

const inputCls =
  "mt-1 w-full rounded-md border border-[#1e1e2e] bg-[#0d0d14] px-3 py-2 text-sm text-white placeholder:text-ink-0 focus:border-signal/50 focus:outline-none";

export function TextInput({
  value,
  onChange,
  placeholder,
  type = "text",
  min,
  max,
  step,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: "text" | "number" | "email" | "tel" | "url";
  min?: number;
  max?: number;
  step?: number;
}) {
  return (
    <input
      type={type}
      className={inputCls}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      min={min}
      max={max}
      step={step}
    />
  );
}

export function Toggle({
  value,
  onChange,
  label,
  description,
}: {
  value: string;
  onChange: (v: string) => void;
  label: string;
  description?: string;
}) {
  const on = value === "true" || value === "1" || value === "yes";
  return (
    <button
      type="button"
      onClick={() => onChange(on ? "false" : "true")}
      className="flex w-full items-center justify-between gap-4 rounded-md border border-[#1e1e2e] bg-[#0d0d14] px-3 py-2 text-left hover:bg-[#14141f]"
    >
      <span>
        <span className="block text-sm text-ink-100">{label}</span>
        {description ? <span className="mt-0.5 block text-[11px] text-ink-0">{description}</span> : null}
      </span>
      <span
        className={[
          "relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition",
          on ? "bg-signal" : "bg-ink-700",
        ].join(" ")}
      >
        <span
          className={[
            "inline-block h-4 w-4 transform rounded-full bg-ink-800 transition",
            on ? "translate-x-4" : "translate-x-0.5",
          ].join(" ")}
        />
      </span>
    </button>
  );
}

export function Select({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <select
      className={inputCls}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}

/** Comma-separated string ↔ JSON-array string stored in the DB. */
export function ChipListField({
  value,
  onChange,
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  let parsed: string[] = [];
  try {
    const p = JSON.parse(value || "[]");
    if (Array.isArray(p)) parsed = p.map((x) => String(x));
  } catch {
    parsed = value
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
  }
  const text = parsed.join(", ");
  return (
    <textarea
      className={`${inputCls} min-h-[72px] font-mono`}
      value={text}
      onChange={(e) => {
        const arr = e.target.value
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean);
        onChange(JSON.stringify(arr));
      }}
      placeholder={placeholder}
    />
  );
}
