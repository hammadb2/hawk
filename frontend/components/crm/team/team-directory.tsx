"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import toast from "react-hot-toast";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import type { CrmRole, Profile } from "@/lib/crm/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { CRM_API_BASE_URL } from "@/lib/crm/api-url";
import { cn } from "@/lib/utils";

function roleLabel(r: string): string {
  return r.replace("_", " ");
}

export function TeamDirectory() {
  const supabase = useMemo(() => createClient(), []);
  const { authReady, profileFetched, session, profile } = useCrmAuth();
  const [rows, setRows] = useState<Profile[]>([]);
  const [tlNames, setTlNames] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviting, setInviting] = useState(false);
  const [form, setForm] = useState({
    email: "",
    full_name: "",
    role: "sales_rep" as "sales_rep" | "team_lead" | "va_manager" | "va",
    whatsapp_number: "",
    team_lead_id: "",
  });

  const load = useCallback(async () => {
    setLoading(true);
    const { data, error } = await supabase
      .from("profiles")
      .select(
        "id, email, full_name, role, team_lead_id, status, monthly_close_target, last_close_at, created_at, onboarding_completed_at, whatsapp_number"
      )
      .in("role", ["sales_rep", "team_lead", "va_manager", "va"] as CrmRole[])
      .order("full_name", { ascending: true, nullsFirst: false });
    if (error) {
      toast.error(error.message);
      setRows([]);
      setLoading(false);
      return;
    }
    const list = (data ?? []) as Profile[];
    setRows(list);
    const tlIds = Array.from(new Set(list.map((p) => p.team_lead_id).filter(Boolean) as string[]));
    if (tlIds.length === 0) {
      setTlNames({});
    } else {
      const { data: tls } = await supabase.from("profiles").select("id, full_name, email").in("id", tlIds);
      const map: Record<string, string> = {};
      for (const t of tls ?? []) {
        map[t.id] = t.full_name ?? t.email ?? t.id.slice(0, 8);
      }
      setTlNames(map);
    }
    setLoading(false);
  }, [supabase]);

  useEffect(() => {
    if (authReady && session && profile) void load();
  }, [authReady, session, profile, load]);

  async function submitInvite() {
    if (!session?.access_token) {
      toast.error("Not signed in");
      return;
    }
    setInviting(true);
    try {
      const body: Record<string, unknown> = {
        email: form.email.trim(),
        full_name: form.full_name.trim(),
        role: form.role,
        whatsapp_number: form.whatsapp_number.trim(),
      };
      if (form.team_lead_id) body.team_lead_id = form.team_lead_id;

      const r = await fetch(`${CRM_API_BASE_URL}/api/crm/invite`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        let msg = (await r.text()).slice(0, 240);
        try {
          const j = JSON.parse(msg) as { detail?: string };
          if (typeof j.detail === "string") msg = j.detail;
        } catch {
          /* plain text */
        }
        toast.error(msg);
        return;
      }
      const j = (await r.json()) as { message?: string; existing_user?: boolean };
      toast.success(j.message || (j.existing_user ? "Rep linked — check email for magic link." : "Invite sent"));
      setInviteOpen(false);
      setForm({ email: "", full_name: "", role: "sales_rep", whatsapp_number: "", team_lead_id: "" });
      await load();
    } finally {
      setInviting(false);
    }
  }

  async function resendInvite(email: string | null) {
    if (!email || !session?.access_token) return;
    const r = await fetch(`${CRM_API_BASE_URL}/api/crm/invite/resend`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${session.access_token}`,
      },
      body: JSON.stringify({ email }),
    });
    if (!r.ok) toast.error((await r.text()).slice(0, 200));
    else toast.success("Email sent");
  }

  async function deactivateRep() {
    if (!session?.access_token || !deactivateTarget) return;
    setDeactivating(true);
    try {
      const r = await fetch(`${CRM_API_BASE_URL}/api/crm/rep/deactivate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({ profile_id: deactivateTarget.id }),
      });
      if (!r.ok) {
        let msg = (await r.text()).slice(0, 240);
        try {
          const j = JSON.parse(msg) as { detail?: string };
          if (typeof j.detail === "string") msg = j.detail;
        } catch {
          /* plain text */
        }
        toast.error(msg);
      } else {
        toast.success("Deactivated — access revoked");
        setDeactivateTarget(null);
        await load();
      }
    } finally {
      setDeactivating(false);
    }
  }

  const [reassignFrom, setReassignFrom] = useState<string | null>(null);
  const [reassignTo, setReassignTo] = useState("");

  /* deactivate confirmation modal */
  const [deactivateTarget, setDeactivateTarget] = useState<Profile | null>(null);
  const [deactivating, setDeactivating] = useState(false);

  async function submitReassign() {
    if (!reassignFrom || !reassignTo || !session?.access_token) return;
    const r = await fetch(`${CRM_API_BASE_URL}/api/crm/rep/reassign-prospects`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${session.access_token}`,
      },
      body: JSON.stringify({ from_rep_id: reassignFrom, to_rep_id: reassignTo }),
    });
    if (!r.ok) toast.error((await r.text()).slice(0, 200));
    else {
      toast.success("Prospects reassigned");
      setReassignFrom(null);
      setReassignTo("");
      await load();
    }
  }

  if (!authReady || !profileFetched) {
    return (
      <div className="flex min-h-[200px] items-center justify-center text-slate-600">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-slate-200 border-t-emerald-500" />
      </div>
    );
  }

  if (!session || !profile) {
    return (
      <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-6 text-sm text-amber-700">
        Please sign in to view the team directory.
      </div>
    );
  }

  if (!["ceo", "hos"].includes(profile.role)) {
    return (
      <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-6 text-sm text-amber-100">
        Team directory is limited to CEO and HoS. Use the scoreboard for rep standings.
      </div>
    );
  }

  const isCeo = profile.role === "ceo";
  const teamLeads = rows.filter((r) => r.role === "team_lead" && r.status === "active");

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap justify-end gap-2">
        {isCeo && (
          <Button type="button" className="bg-emerald-600" onClick={() => setInviteOpen(true)}>
            Invite rep
          </Button>
        )}
        <button
          type="button"
          className="rounded-md border border-slate-200 px-3 py-1.5 text-sm text-slate-700 hover:bg-slate-50"
          onClick={() => void load()}
        >
          Refresh
        </button>
      </div>

      <Dialog open={inviteOpen} onOpenChange={setInviteOpen}>
        <DialogContent className="border-slate-200 bg-white">
          <DialogHeader>
            <DialogTitle className="text-slate-900">Invite rep</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label className="text-slate-600">Email</Label>
              <Input
                className="mt-1 border-slate-200 bg-slate-50"
                value={form.email}
                onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
                placeholder="rep@company.com"
              />
            </div>
            <div>
              <Label className="text-slate-600">Name</Label>
              <Input
                className="mt-1 border-slate-200 bg-slate-50"
                value={form.full_name}
                onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))}
              />
            </div>
            <div>
              <Label className="text-slate-600">Role</Label>
              <select
                className="mt-1 w-full rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-900"
                value={form.role}
                onChange={(e) => setForm((f) => ({ ...f, role: e.target.value as "sales_rep" | "team_lead" | "va_manager" | "va" }))}
              >
                <option value="sales_rep">Sales rep</option>
                <option value="team_lead">Team lead</option>
                <option value="va_manager">VA Manager</option>
                <option value="va">VA</option>
              </select>
            </div>
            <div>
              <Label className="text-slate-600">WhatsApp (E.164, e.g. +15551234567)</Label>
              <Input
                className="mt-1 border-slate-200 bg-slate-50"
                value={form.whatsapp_number}
                onChange={(e) => setForm((f) => ({ ...f, whatsapp_number: e.target.value }))}
              />
            </div>
            <div>
              <Label className="text-slate-600">Team lead (optional)</Label>
              <select
                className="mt-1 w-full rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-900"
                value={form.team_lead_id}
                onChange={(e) => setForm((f) => ({ ...f, team_lead_id: e.target.value }))}
              >
                <option value="">—</option>
                {teamLeads.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.full_name ?? t.email}
                  </option>
                ))}
              </select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" className="border-slate-200" onClick={() => setInviteOpen(false)}>
              Cancel
            </Button>
            <Button className="bg-emerald-600" disabled={inviting} onClick={() => void submitInvite()}>
              {inviting ? "Sending…" : "Send invite"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!reassignFrom} onOpenChange={(o) => !o && setReassignFrom(null)}>
        <DialogContent className="border-slate-200 bg-white">
          <DialogHeader>
            <DialogTitle className="text-slate-900">Reassign prospects</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-slate-600">Move all prospects from this rep to another active rep.</p>
          <div>
            <Label className="text-slate-600">Assign to</Label>
            <select
              className="mt-1 w-full rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-sm text-slate-900"
              value={reassignTo}
              onChange={(e) => setReassignTo(e.target.value)}
            >
              <option value="">Select rep…</option>
              {rows
                .filter((r) => r.id !== reassignFrom && r.status === "active")
                .map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.full_name ?? r.email}
                  </option>
                ))}
            </select>
          </div>
          <DialogFooter>
            <Button variant="outline" className="border-slate-200" onClick={() => setReassignFrom(null)}>
              Cancel
            </Button>
            <Button className="bg-emerald-600" disabled={!reassignTo} onClick={() => void submitReassign()}>
              Reassign
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Deactivate confirmation modal */}
      <Dialog open={!!deactivateTarget} onOpenChange={(o) => !o && setDeactivateTarget(null)}>
        <DialogContent className="border-slate-200 bg-white">
          <DialogHeader>
            <DialogTitle className="text-slate-900">
              Deactivate {deactivateTarget?.full_name ?? deactivateTarget?.email ?? "this user"}?
            </DialogTitle>
          </DialogHeader>
          <p className="text-sm text-slate-600">
            This will set their status to inactive and permanently revoke their login access.
            All historical data will be preserved. This action cannot be easily undone.
          </p>
          <DialogFooter>
            <Button variant="outline" className="border-slate-200" onClick={() => setDeactivateTarget(null)} disabled={deactivating}>
              Cancel
            </Button>
            <Button className="bg-rose-600 hover:bg-rose-700" disabled={deactivating} onClick={() => void deactivateRep()}>
              {deactivating ? "Deactivating\u2026" : "Deactivate"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {loading ? (
        <div className="py-16 text-center text-slate-600">Loading…</div>
      ) : rows.length === 0 ? (
        <p className="rounded-lg border border-slate-200 bg-white shadow-sm px-4 py-10 text-center text-sm text-slate-600">
          No team members found.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-200">
          <table className="w-full min-w-[960px] text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-600">
              <tr>
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2">Email</th>
                <th className="px-3 py-2">Role</th>
                <th className="px-3 py-2">Team lead</th>
                <th className="px-3 py-2">Status</th>
                <th className="px-3 py-2">WhatsApp</th>
                <th className="px-3 py-2">Monthly target</th>
                <th className="px-3 py-2">Last close</th>
                <th className="px-3 py-2">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr key={p.id} className="border-b border-slate-200/90 hover:bg-white shadow-sm">
                  <td className="px-3 py-2 font-medium text-slate-900">
                    <Link href={`/crm/team/${p.id}`} className="text-emerald-600 hover:underline">
                      {p.full_name ?? "—"}
                    </Link>
                  </td>
                  <td className="px-3 py-2 text-slate-600">{p.email ?? "—"}</td>
                  <td className="px-3 py-2 capitalize text-slate-700">{roleLabel(p.role)}</td>
                  <td className="px-3 py-2 text-slate-600">
                    {p.team_lead_id ? (tlNames[p.team_lead_id] ?? p.team_lead_id.slice(0, 8)) : "—"}
                  </td>
                  <td className={cn("px-3 py-2 font-medium capitalize", p.status === "active" ? "text-emerald-600" : "text-amber-400")}>
                    {p.status}
                  </td>
                  <td className="px-3 py-2 text-slate-600">{p.whatsapp_number ?? "—"}</td>
                  <td className="px-3 py-2 text-slate-600">{p.monthly_close_target ?? "—"}</td>
                  <td className="px-3 py-2 text-slate-600">
                    {p.last_close_at ? new Date(p.last_close_at).toLocaleDateString() : "—"}
                  </td>
                  <td className="space-x-2 px-3 py-2">
                    {isCeo && p.email && ["invited", "onboarding"].includes(String(p.status)) && (
                      <button
                        type="button"
                        className="text-xs text-emerald-600 underline"
                        onClick={() => void resendInvite(p.email)}
                      >
                        Resend
                      </button>
                    )}
                    {["ceo", "hos"].includes(profile.role) && (
                      <button
                        type="button"
                        className="text-xs text-slate-600 underline"
                        onClick={() => setReassignFrom(p.id)}
                      >
                        Reassign
                      </button>
                    )}
                    {isCeo && p.role !== "ceo" && (
                      <button
                        type="button"
                        className="text-xs text-rose-400 underline"
                        onClick={() => setDeactivateTarget(p)}
                      >
                        Deactivate
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
