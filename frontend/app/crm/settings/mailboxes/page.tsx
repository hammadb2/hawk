"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import toast from "react-hot-toast";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { CRM_API_BASE_URL } from "@/lib/crm/api-url";
import { crmPageSubtitle, crmPageTitle, crmSurfaceCard } from "@/lib/crm/crm-surface";

interface Mailbox {
  id: string;
  email_address: string;
  display_name: string | null;
  domain: string;
  provider: string | null;
  smtp_host: string;
  smtp_port: number;
  smtp_username: string;
  smtp_use_tls: boolean;
  smtp_use_ssl: boolean;
  imap_host: string;
  imap_port: number;
  imap_username: string;
  imap_use_ssl: boolean;
  daily_cap: number;
  sent_today: number;
  sent_today_date: string | null;
  sent_total: number | null;
  bounce_rate_7d: number | null;
  status: "active" | "paused" | "disabled" | string;
  warmup_status: string | null;
  vertical: string | null;
  notes: string | null;
  last_send_at: string | null;
  last_error: string | null;
}

interface MailboxHealth {
  total: number;
  active: number;
  paused: number;
  capacity_today: number;
  used_today: number;
  remaining_today: number;
  crypto_configured: boolean;
}

const EMPTY_FORM = {
  email_address: "",
  display_name: "",
  domain: "",
  smtp_host: "",
  smtp_port: 587,
  smtp_username: "",
  smtp_password: "",
  smtp_use_tls: true,
  smtp_use_ssl: false,
  imap_host: "",
  imap_port: 993,
  imap_username: "",
  imap_password: "",
  imap_use_ssl: true,
  daily_cap: 40,
  vertical: "",
  notes: "",
};

type FormState = typeof EMPTY_FORM;

export default function MailboxesPage() {
  const { profile } = useCrmAuth();
  const supabase = useMemo(() => createClient(), []);
  const [mailboxes, setMailboxes] = useState<Mailbox[]>([]);
  const [health, setHealth] = useState<MailboxHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [showBulk, setShowBulk] = useState(false);
  const [bulkCsv, setBulkCsv] = useState("");
  const [testResult, setTestResult] = useState<Record<string, unknown> | null>(null);

  const authHeader = useCallback(async (): Promise<string | null> => {
    const {
      data: { session },
    } = await supabase.auth.getSession();
    return session?.access_token ? `Bearer ${session.access_token}` : null;
  }, [supabase]);

  const api = useCallback(
    async <T,>(path: string, init?: RequestInit): Promise<T> => {
      const token = await authHeader();
      if (!token) throw new Error("Not signed in");
      const res = await fetch(`${CRM_API_BASE_URL}${path}`, {
        ...init,
        headers: {
          "Content-Type": "application/json",
          Authorization: token,
          ...(init?.headers || {}),
        },
        cache: "no-store",
      });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error((body as { detail?: string }).detail ?? `HTTP ${res.status}`);
      }
      return (await res.json()) as T;
    },
    [authHeader],
  );

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api<{ mailboxes: Mailbox[]; health: MailboxHealth }>(
        "/api/crm/settings/mailboxes",
      );
      setMailboxes(data.mailboxes || []);
      setHealth(data.health || null);
    } catch (e) {
      toast.error(`Load failed: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    if (profile?.role === "ceo") void load();
    else setLoading(false);
  }, [profile?.role, load]);

  const resetForm = () => {
    setForm(EMPTY_FORM);
    setEditId(null);
    setShowForm(false);
  };

  const openEdit = (mbx: Mailbox) => {
    setEditId(mbx.id);
    setForm({
      email_address: mbx.email_address,
      display_name: mbx.display_name || "",
      domain: mbx.domain,
      smtp_host: mbx.smtp_host,
      smtp_port: mbx.smtp_port,
      smtp_username: mbx.smtp_username,
      smtp_password: "",
      smtp_use_tls: mbx.smtp_use_tls,
      smtp_use_ssl: mbx.smtp_use_ssl,
      imap_host: mbx.imap_host,
      imap_port: mbx.imap_port,
      imap_username: mbx.imap_username,
      imap_password: "",
      imap_use_ssl: mbx.imap_use_ssl,
      daily_cap: mbx.daily_cap,
      vertical: mbx.vertical || "",
      notes: mbx.notes || "",
    });
    setShowForm(true);
  };

  const save = useCallback(async () => {
    setSaving(true);
    try {
      const payload: Record<string, unknown> = { ...form };
      if (editId && !payload.smtp_password) delete payload.smtp_password;
      if (editId && !payload.imap_password) delete payload.imap_password;
      if (!payload.vertical) delete payload.vertical;
      if (editId) {
        await api(`/api/crm/settings/mailboxes/${editId}`, {
          method: "PATCH",
          body: JSON.stringify(payload),
        });
        toast.success("Mailbox updated");
      } else {
        await api("/api/crm/settings/mailboxes", {
          method: "POST",
          body: JSON.stringify(payload),
        });
        toast.success("Mailbox added");
      }
      resetForm();
      await load();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  }, [api, editId, form, load]);

  const setStatus = async (id: string, status: "active" | "paused") => {
    try {
      await api(`/api/crm/settings/mailboxes/${id}/${status === "active" ? "resume" : "pause"}`, {
        method: "POST",
      });
      toast.success(`Mailbox ${status === "active" ? "resumed" : "paused"}`);
      await load();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const softDelete = async (id: string) => {
    if (!confirm("Disable this mailbox? It will no longer send or be polled for replies.")) return;
    try {
      await api(`/api/crm/settings/mailboxes/${id}`, { method: "DELETE" });
      toast.success("Mailbox disabled");
      await load();
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const testConnection = async (id: string) => {
    setTestResult(null);
    try {
      const data = await api<Record<string, unknown>>(
        `/api/crm/settings/mailboxes/${id}/test-connection`,
        { method: "POST" },
      );
      setTestResult(data);
      if ((data as { ok?: boolean }).ok) toast.success("SMTP + IMAP OK");
      else toast.error("Test failed — see details");
    } catch (e) {
      toast.error((e as Error).message);
    }
  };

  const bulkImport = async () => {
    if (!bulkCsv.trim()) return;
    setSaving(true);
    try {
      const data = await api<{ count: number; errors: Array<{ error: string }> }>(
        "/api/crm/settings/mailboxes/bulk-import",
        {
          method: "POST",
          body: JSON.stringify({ csv_text: bulkCsv }),
        },
      );
      toast.success(`Imported ${data.count} mailbox(es)`);
      if (data.errors?.length) toast.error(`${data.errors.length} row(s) failed`);
      setBulkCsv("");
      setShowBulk(false);
      await load();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  if (profile?.role !== "ceo") {
    return (
      <div className="mx-auto max-w-5xl p-6">
        <h1 className={crmPageTitle}>Mailboxes</h1>
        <p className={crmPageSubtitle}>CEO-only access.</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className={crmPageTitle}>Mailboxes</h1>
          <p className={crmPageSubtitle}>
            Cold-outbound mailboxes used by the rolling dispatcher. Round-robin across active inboxes, per-mailbox daily caps, IMAP reply polling every 5 min.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            className="rounded-lg border border-ink-700 bg-[#1a1a24] px-4 py-2 text-sm text-ink-100 hover:bg-[#222230]"
            onClick={() => setShowBulk(true)}
          >
            Bulk import CSV
          </button>
          <button
            className="rounded-lg bg-signal-400 px-4 py-2 text-sm font-medium text-white hover:bg-signal"
            onClick={() => {
              resetForm();
              setShowForm(true);
            }}
          >
            + Add mailbox
          </button>
        </div>
      </div>

      {health && !health.crypto_configured && (
        <div className="rounded-xl border border-signal/40 bg-ink-800/20 p-4 text-amber-200">
          <div className="font-semibold">MAILBOX_ENCRYPTION_KEY is not set</div>
          <div className="mt-1 text-sm">
            Mailbox credentials cannot be stored until this is configured on Railway. Generate a key with
            <code className="mx-1 rounded bg-ink-950/60 px-1 py-0.5">python -c &quot;from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())&quot;</code>
            and set it as <code>MAILBOX_ENCRYPTION_KEY</code>.
          </div>
        </div>
      )}

      {health && (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
          <KPICard label="Active" value={health.active} color="emerald" />
          <KPICard label="Paused" value={health.paused} color="amber" />
          <KPICard label="Capacity today" value={health.capacity_today} color="blue" />
          <KPICard label="Used today" value={health.used_today} color="slate" />
          <KPICard label="Remaining today" value={health.remaining_today} color="emerald" />
        </div>
      )}

      <section className={crmSurfaceCard}>
        {loading ? (
          <div className="p-8 text-center text-ink-200">Loading…</div>
        ) : mailboxes.length === 0 ? (
          <div className="p-8 text-center text-ink-200">
            No mailboxes configured. Add one or bulk-import a CSV to start sending cold emails.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-[#11111a] text-xs uppercase tracking-wide text-ink-200">
                <tr>
                  <th className="px-3 py-2">Email</th>
                  <th className="px-3 py-2">Vertical</th>
                  <th className="px-3 py-2">Status</th>
                  <th className="px-3 py-2">Sent today</th>
                  <th className="px-3 py-2">Cap</th>
                  <th className="px-3 py-2">Bounce 7d</th>
                  <th className="px-3 py-2">Last send</th>
                  <th className="px-3 py-2 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {mailboxes.map((mbx) => (
                  <tr key={mbx.id} className="border-t border-[#1e1e2e] text-ink-100">
                    <td className="px-3 py-2">
                      <div className="font-medium">{mbx.email_address}</div>
                      <div className="text-xs text-ink-0">{mbx.domain}</div>
                    </td>
                    <td className="px-3 py-2">{mbx.vertical || "any"}</td>
                    <td className="px-3 py-2">
                      <StatusPill status={mbx.status} />
                    </td>
                    <td className="px-3 py-2">{mbx.sent_today ?? 0}</td>
                    <td className="px-3 py-2">{mbx.daily_cap}</td>
                    <td className="px-3 py-2">
                      {mbx.bounce_rate_7d != null ? `${(mbx.bounce_rate_7d * 100).toFixed(1)}%` : "—"}
                    </td>
                    <td className="px-3 py-2 text-xs text-ink-200">
                      {mbx.last_send_at ? new Date(mbx.last_send_at).toLocaleString() : "—"}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <div className="inline-flex flex-wrap justify-end gap-1">
                        <ActionButton onClick={() => testConnection(mbx.id)}>Test</ActionButton>
                        <ActionButton onClick={() => openEdit(mbx)}>Edit</ActionButton>
                        {mbx.status === "active" ? (
                          <ActionButton onClick={() => setStatus(mbx.id, "paused")}>Pause</ActionButton>
                        ) : (
                          <ActionButton onClick={() => setStatus(mbx.id, "active")}>Resume</ActionButton>
                        )}
                        <ActionButton danger onClick={() => softDelete(mbx.id)}>
                          Disable
                        </ActionButton>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {testResult && (
        <section className={crmSurfaceCard}>
          <div className="p-4">
            <div className="mb-2 flex items-center justify-between">
              <div className="text-sm font-semibold text-ink-100">Last test result</div>
              <button className="text-xs text-ink-0 hover:text-ink-100" onClick={() => setTestResult(null)}>
                Dismiss
              </button>
            </div>
            <pre className="overflow-auto rounded bg-ink-950/60 p-3 text-xs text-ink-100">
              {JSON.stringify(testResult, null, 2)}
            </pre>
          </div>
        </section>
      )}

      {showForm && (
        <Modal title={editId ? "Edit mailbox" : "Add mailbox"} onClose={resetForm}>
          <MailboxForm
            form={form}
            setForm={setForm}
            editing={!!editId}
            saving={saving}
            onSave={save}
            onCancel={resetForm}
          />
        </Modal>
      )}

      {showBulk && (
        <Modal title="Bulk import mailboxes" onClose={() => setShowBulk(false)}>
          <div className="space-y-3 p-4 text-sm text-ink-100">
            <p className="text-ink-200">
              Paste a CSV with header row. Required columns:
            </p>
            <code className="block whitespace-pre-wrap rounded bg-ink-950/60 p-2 text-xs text-ink-100">
              email_address,display_name,domain,smtp_host,smtp_port,smtp_username,smtp_password,smtp_use_tls,smtp_use_ssl,imap_host,imap_port,imap_username,imap_password,imap_use_ssl,daily_cap,vertical,notes
            </code>
            <textarea
              className="h-56 w-full rounded border border-ink-700 bg-[#0b0b12] p-3 font-mono text-xs text-ink-100"
              value={bulkCsv}
              onChange={(e) => setBulkCsv(e.target.value)}
              placeholder="email_address,domain,smtp_host,smtp_port,smtp_username,smtp_password,imap_host,imap_port,imap_username,imap_password,daily_cap,vertical\n..."
            />
            <div className="flex justify-end gap-2">
              <button className="rounded border border-ink-700 px-3 py-1.5 text-sm" onClick={() => setShowBulk(false)}>
                Cancel
              </button>
              <button
                className="rounded bg-signal-400 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
                onClick={bulkImport}
                disabled={saving || !bulkCsv.trim()}
              >
                {saving ? "Importing…" : "Import"}
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
}

function KPICard({ label, value, color }: { label: string; value: string | number; color: string }) {
  const map: Record<string, string> = {
    emerald: "border-signal/30",
    blue: "border-sky-500/30",
    amber: "border-signal/30",
    slate: "border-[#1e1e2e]",
  };
  return (
    <div className={`rounded-xl border bg-[#111118] p-4 ${map[color] ?? map.slate}`}>
      <p className="text-xs font-medium text-ink-200">{label}</p>
      <p className="mt-1 text-2xl font-bold text-white">{value}</p>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const styles: Record<string, string> = {
    active: "bg-signal/20 text-signal-200 border-signal/30",
    paused: "bg-signal/20 text-amber-200 border-signal/30",
    disabled: "bg-ink-600/30 text-ink-200 border-ink-600/30",
  };
  return (
    <span className={`inline-flex rounded border px-2 py-0.5 text-xs font-medium ${styles[status] ?? styles.disabled}`}>
      {status}
    </span>
  );
}

function ActionButton({
  children,
  onClick,
  danger,
}: {
  children: React.ReactNode;
  onClick: () => void;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded border px-2 py-1 text-xs ${
        danger
          ? "border-red/40 text-red hover:bg-red/100/10"
          : "border-ink-700 text-ink-100 hover:bg-[#1e1e2e]"
      }`}
    >
      {children}
    </button>
  );
}

function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-950/70 p-4" onClick={onClose}>
      <div
        className="max-h-[90vh] w-full max-w-2xl overflow-auto rounded-xl border border-ink-700 bg-[#0f0f18]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-ink-800 px-4 py-3">
          <h2 className="text-base font-semibold text-ink-0">{title}</h2>
          <button onClick={onClose} className="text-ink-200 hover:text-ink-100">
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function MailboxForm({
  form,
  setForm,
  editing,
  saving,
  onSave,
  onCancel,
}: {
  form: FormState;
  setForm: (f: FormState) => void;
  editing: boolean;
  saving: boolean;
  onSave: () => void;
  onCancel: () => void;
}) {
  const upd = <K extends keyof FormState>(k: K, v: FormState[K]) => setForm({ ...form, [k]: v });
  return (
    <div className="grid gap-3 p-4 text-sm text-ink-100 sm:grid-cols-2">
      <Field label="Email address *" value={form.email_address} onChange={(v) => upd("email_address", v)} />
      <Field label="Display name" value={form.display_name} onChange={(v) => upd("display_name", v)} />
      <Field label="Sending domain *" value={form.domain} onChange={(v) => upd("domain", v)} />
      <SelectField
        label="Vertical"
        value={form.vertical}
        onChange={(v) => upd("vertical", v)}
        options={["", "dental", "legal", "accounting"]}
      />

      <div className="sm:col-span-2 pt-2 text-xs uppercase tracking-wide text-ink-200">SMTP</div>
      <Field label="SMTP host *" value={form.smtp_host} onChange={(v) => upd("smtp_host", v)} />
      <Field
        label="SMTP port *"
        value={String(form.smtp_port)}
        onChange={(v) => upd("smtp_port", Number(v) || 587)}
      />
      <Field label="SMTP username *" value={form.smtp_username} onChange={(v) => upd("smtp_username", v)} />
      <Field
        label={editing ? "SMTP password (blank = keep)" : "SMTP password *"}
        value={form.smtp_password}
        onChange={(v) => upd("smtp_password", v)}
        type="password"
      />
      <Checkbox label="STARTTLS" value={form.smtp_use_tls} onChange={(v) => upd("smtp_use_tls", v)} />
      <Checkbox label="Implicit TLS (465)" value={form.smtp_use_ssl} onChange={(v) => upd("smtp_use_ssl", v)} />

      <div className="sm:col-span-2 pt-2 text-xs uppercase tracking-wide text-ink-200">IMAP (reply poller)</div>
      <Field label="IMAP host *" value={form.imap_host} onChange={(v) => upd("imap_host", v)} />
      <Field
        label="IMAP port *"
        value={String(form.imap_port)}
        onChange={(v) => upd("imap_port", Number(v) || 993)}
      />
      <Field label="IMAP username *" value={form.imap_username} onChange={(v) => upd("imap_username", v)} />
      <Field
        label={editing ? "IMAP password (blank = keep)" : "IMAP password *"}
        value={form.imap_password}
        onChange={(v) => upd("imap_password", v)}
        type="password"
      />
      <Checkbox label="IMAP SSL (993)" value={form.imap_use_ssl} onChange={(v) => upd("imap_use_ssl", v)} />

      <div className="sm:col-span-2 pt-2 text-xs uppercase tracking-wide text-ink-200">Limits</div>
      <Field
        label="Daily cap"
        value={String(form.daily_cap)}
        onChange={(v) => upd("daily_cap", Number(v) || 40)}
      />
      <Field label="Notes" value={form.notes} onChange={(v) => upd("notes", v)} />

      <div className="sm:col-span-2 mt-3 flex justify-end gap-2 border-t border-ink-800 pt-3">
        <button className="rounded border border-ink-700 px-3 py-1.5 text-sm" onClick={onCancel}>
          Cancel
        </button>
        <button
          onClick={onSave}
          disabled={saving}
          className="rounded bg-signal-400 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
        >
          {saving ? "Saving…" : editing ? "Save changes" : "Add mailbox"}
        </button>
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs text-ink-200">
      {label}
      <input
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded border border-ink-700 bg-[#0b0b12] px-3 py-2 text-sm text-ink-100"
      />
    </label>
  );
}

function SelectField({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: string[];
}) {
  return (
    <label className="flex flex-col gap-1 text-xs text-ink-200">
      {label}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded border border-ink-700 bg-[#0b0b12] px-3 py-2 text-sm text-ink-100"
      >
        {options.map((o) => (
          <option key={o || "__any"} value={o}>
            {o || "(any)"}
          </option>
        ))}
      </select>
    </label>
  );
}

function Checkbox({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-center gap-2 text-sm text-ink-100">
      <input
        type="checkbox"
        checked={value}
        onChange={(e) => onChange(e.target.checked)}
        className="h-4 w-4 rounded border-ink-600 bg-[#0b0b12]"
      />
      {label}
    </label>
  );
}
