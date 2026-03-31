"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
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
import { cn } from "@/lib/utils";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

function roleLabel(r: string): string {
  return r.replace("_", " ");
}

export function TeamDirectory() {
  const supabase = useMemo(() => createClient(), []);
  const { authReady, session, profile } = useCrmAuth();
  const [rows, setRows] = useState<Profile[]>([]);
  const [tlNames, setTlNames] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviting, setInviting] = useState(false);
  const [form, setForm] = useState({
    email: "",
    full_name: "",
    role: "sales_rep" as "sales_rep" | "team_lead",
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
      .in("role", ["sales_rep", "team_lead"] as CrmRole[])
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

      const r = await fetch(`${API_URL}/api/crm/invite`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        const t = await r.text();
        toast.error(t.slice(0, 200));
        return;
      }
      toast.success("Invite sent");
      setInviteOpen(false);
      setForm({ email: "", full_name: "", role: "sales_rep", whatsapp_number: "", team_lead_id: "" });
      await load();
    } finally {
      setInviting(false);
    }
  }

  async function resendInvite(email: string | null) {
    if (!email || !session?.access_token) return;
    const r = await fetch(`${API_URL}/api/crm/invite/resend`, {
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

  async function deactivateRep(id: string) {
    if (!session?.access_token || !confirm("Deactivate this rep?")) return;
    const r = await fetch(`${API_URL}/api/crm/rep/deactivate`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${session.access_token}`,
      },
      body: JSON.stringify({ profile_id: id }),
    });
    if (!r.ok) toast.error((await r.text()).slice(0, 200));
    else {
      toast.success("Updated");
      await load();
    }
  }

  const [reassignFrom, setReassignFrom] = useState<string | null>(null);
  const [reassignTo, setReassignTo] = useState("");

  async function submitReassign() {
    if (!reassignFrom || !reassignTo || !session?.access_token) return;
    const r = await fetch(`${API_URL}/api/crm/rep/reassign-prospects`, {
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

  if (!authReady || !session || !profile) {
    return (
      <div className="flex min-h-[200px] items-center justify-center text-zinc-500">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-700 border-t-emerald-500" />
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
          className="rounded-md border border-zinc-700 px-3 py-1.5 text-sm text-zinc-300 hover:bg-zinc-900"
          onClick={() => void load()}
        >
          Refresh
        </button>
      </div>

      <Dialog open={inviteOpen} onOpenChange={setInviteOpen}>
        <DialogContent className="border-zinc-800 bg-zinc-950">
          <DialogHeader>
            <DialogTitle className="text-zinc-100">Invite rep</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label className="text-zinc-400">Email</Label>
              <Input
                className="mt-1 border-zinc-700 bg-zinc-900"
                value={form.email}
                onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))}
                placeholder="rep@company.com"
              />
            </div>
            <div>
              <Label className="text-zinc-400">Name</Label>
              <Input
                className="mt-1 border-zinc-700 bg-zinc-900"
                value={form.full_name}
                onChange={(e) => setForm((f) => ({ ...f, full_name: e.target.value }))}
              />
            </div>
            <div>
              <Label className="text-zinc-400">Role</Label>
              <select
                className="mt-1 w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100"
                value={form.role}
                onChange={(e) => setForm((f) => ({ ...f, role: e.target.value as "sales_rep" | "team_lead" }))}
              >
                <option value="sales_rep">Sales rep</option>
                <option value="team_lead">Team lead</option>
              </select>
            </div>
            <div>
              <Label className="text-zinc-400">WhatsApp (E.164, e.g. +15551234567)</Label>
              <Input
                className="mt-1 border-zinc-700 bg-zinc-900"
                value={form.whatsapp_number}
                onChange={(e) => setForm((f) => ({ ...f, whatsapp_number: e.target.value }))}
              />
            </div>
            <div>
              <Label className="text-zinc-400">Team lead (optional)</Label>
              <select
                className="mt-1 w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100"
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
            <Button variant="outline" className="border-zinc-700" onClick={() => setInviteOpen(false)}>
              Cancel
            </Button>
            <Button className="bg-emerald-600" disabled={inviting} onClick={() => void submitInvite()}>
              {inviting ? "Sending…" : "Send invite"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={!!reassignFrom} onOpenChange={(o) => !o && setReassignFrom(null)}>
        <DialogContent className="border-zinc-800 bg-zinc-950">
          <DialogHeader>
            <DialogTitle className="text-zinc-100">Reassign prospects</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-zinc-400">Move all prospects from this rep to another active rep.</p>
          <div>
            <Label className="text-zinc-400">Assign to</Label>
            <select
              className="mt-1 w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100"
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
            <Button variant="outline" className="border-zinc-700" onClick={() => setReassignFrom(null)}>
              Cancel
            </Button>
            <Button className="bg-emerald-600" disabled={!reassignTo} onClick={() => void submitReassign()}>
              Reassign
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {loading ? (
        <div className="py-16 text-center text-zinc-500">Loading…</div>
      ) : rows.length === 0 ? (
        <p className="rounded-lg border border-zinc-800 bg-zinc-900/40 px-4 py-10 text-center text-sm text-zinc-500">
          No sales reps or team leads found.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-zinc-800">
          <table className="w-full min-w-[960px] text-left text-sm">
            <thead className="border-b border-zinc-800 bg-zinc-900/60 text-xs uppercase tracking-wide text-zinc-500">
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
                <tr key={p.id} className="border-b border-zinc-800/80 hover:bg-zinc-900/40">
                  <td className="px-3 py-2 font-medium text-zinc-100">{p.full_name ?? "—"}</td>
                  <td className="px-3 py-2 text-zinc-400">{p.email ?? "—"}</td>
                  <td className="px-3 py-2 capitalize text-zinc-300">{roleLabel(p.role)}</td>
                  <td className="px-3 py-2 text-zinc-400">
                    {p.team_lead_id ? (tlNames[p.team_lead_id] ?? p.team_lead_id.slice(0, 8)) : "—"}
                  </td>
                  <td className={cn("px-3 py-2 font-medium capitalize", p.status === "active" ? "text-emerald-400" : "text-amber-400")}>
                    {p.status}
                  </td>
                  <td className="px-3 py-2 text-zinc-500">{p.whatsapp_number ?? "—"}</td>
                  <td className="px-3 py-2 text-zinc-400">{p.monthly_close_target ?? "—"}</td>
                  <td className="px-3 py-2 text-zinc-500">
                    {p.last_close_at ? new Date(p.last_close_at).toLocaleDateString() : "—"}
                  </td>
                  <td className="space-x-2 px-3 py-2">
                    {isCeo && p.email && ["invited", "onboarding"].includes(String(p.status)) && (
                      <button
                        type="button"
                        className="text-xs text-emerald-400 underline"
                        onClick={() => void resendInvite(p.email)}
                      >
                        Resend
                      </button>
                    )}
                    {["ceo", "hos"].includes(profile.role) && (
                      <>
                        <button
                          type="button"
                          className="text-xs text-zinc-400 underline"
                          onClick={() => setReassignFrom(p.id)}
                        >
                          Reassign
                        </button>
                        <button
                          type="button"
                          className="text-xs text-rose-400 underline"
                          onClick={() => void deactivateRep(p.id)}
                        >
                          Deactivate
                        </button>
                      </>
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
