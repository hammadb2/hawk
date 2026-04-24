"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import toast from "react-hot-toast";
import { Copy, Mail, RefreshCw, Send, UserPlus } from "lucide-react";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
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
import {
  crmDialogSurface,
  crmEmptyState,
  crmFieldSurface,
  crmSurfaceCard,
  crmTableRow,
  crmTableThead,
  crmTableWrap,
} from "@/lib/crm/crm-surface";

type Prospect = {
  id: string;
  domain: string;
  company_name: string;
  contact_name: string | null;
  contact_email: string | null;
  contact_phone: string | null;
  contact_linkedin_url: string | null;
  contact_title: string | null;
  email_subject: string | null;
  email_body: string | null;
  hawk_score: number | null;
  industry: string | null;
  city: string | null;
  province: string | null;
  vulnerability_found: string | null;
};

type Assignment = {
  id: string;
  prospect_id: string;
  status: string;
  notes: string | null;
  assigned_at: string;
  prospect: Prospect;
};

type VA = {
  id: string;
  full_name: string | null;
  email: string | null;
  role_type: string;
  status: string | null;
  today_assigned: number;
  today_reached_out: number;
  today_booked: number;
};

type Tab = "queue" | "team" | "my";

export function VAConsole() {
  const { profile } = useCrmAuth();
  const roleType = (profile?.role_type || "").toLowerCase();
  const role = (profile?.role || "").toLowerCase();
  const isManagerOrCeo = role === "ceo" || role === "hos" || roleType === "va_manager";
  const isVA = roleType === "va_outreach" || roleType === "va_manager" || role === "ceo" || role === "hos";

  const initial: Tab = isManagerOrCeo ? "queue" : "my";
  const [tab, setTab] = useState<Tab>(initial);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        {isManagerOrCeo && (
          <TabButton active={tab === "queue"} onClick={() => setTab("queue")}>
            Queue
          </TabButton>
        )}
        {isManagerOrCeo && (
          <TabButton active={tab === "team"} onClick={() => setTab("team")}>
            Team
          </TabButton>
        )}
        {isVA && (
          <TabButton active={tab === "my"} onClick={() => setTab("my")}>
            My Queue
          </TabButton>
        )}
      </div>
      {tab === "queue" && isManagerOrCeo && <QueueTab />}
      {tab === "team" && isManagerOrCeo && <TeamTab />}
      {tab === "my" && isVA && <MyQueueTab />}
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "rounded-lg px-4 py-2 text-sm font-medium transition",
        active
          ? "bg-signal/20 text-signal-200 ring-1 ring-signal/40"
          : "text-ink-200 hover:bg-ink-800/5 hover:text-ink-100",
      )}
    >
      {children}
    </button>
  );
}

// ─── Queue tab ──────────────────────────────────────────────────────────

function QueueTab() {
  const { session } = useCrmAuth();
  const [prospects, setProspects] = useState<Prospect[]>([]);
  const [vas, setVAs] = useState<VA[]>([]);
  const [loading, setLoading] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [vertical, setVertical] = useState("");
  const [minScore, setMinScore] = useState("");
  const [assignVAId, setAssignVAId] = useState("");
  const [assigning, setAssigning] = useState(false);

  const refresh = useCallback(async () => {
    if (!session?.access_token) return;
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (vertical) params.set("vertical", vertical);
      if (minScore) params.set("min_score", minScore);
      const [qr, tr] = await Promise.all([
        fetch(`${CRM_API_BASE_URL}/api/crm/va/queue?${params}`, {
          headers: { Authorization: `Bearer ${session.access_token}` },
        }),
        fetch(`${CRM_API_BASE_URL}/api/crm/va/team`, {
          headers: { Authorization: `Bearer ${session.access_token}` },
        }),
      ]);
      if (qr.ok) {
        const j = (await qr.json()) as { prospects: Prospect[] };
        setProspects(j.prospects || []);
      }
      if (tr.ok) {
        const j = (await tr.json()) as { vas: VA[] };
        setVAs(j.vas || []);
      }
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setLoading(false);
    }
  }, [session?.access_token, vertical, minScore]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function bulkAssign() {
    if (!session?.access_token) return;
    if (selected.size === 0) {
      toast.error("Select at least one prospect");
      return;
    }
    if (!assignVAId) {
      toast.error("Pick a VA");
      return;
    }
    setAssigning(true);
    try {
      const r = await fetch(`${CRM_API_BASE_URL}/api/crm/va/assign`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({
          prospect_ids: Array.from(selected),
          va_id: assignVAId,
        }),
      });
      if (!r.ok) {
        toast.error((await r.text()).slice(0, 200));
        return;
      }
      toast.success(`Assigned ${selected.size} to VA`);
      setSelected(new Set());
      void refresh();
    } finally {
      setAssigning(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className={cn(crmSurfaceCard, "flex flex-wrap items-end gap-3 p-4")}>
        <div className="w-36">
          <Label className="text-xs text-ink-200">Vertical</Label>
          <select
            value={vertical}
            onChange={(e) => setVertical(e.target.value)}
            className={cn(crmFieldSurface, "mt-1 w-full rounded-md px-2 py-1.5 text-sm")}
          >
            <option value="">All</option>
            <option value="dental">Dental</option>
            <option value="legal">Legal</option>
            <option value="accounting">Accounting</option>
          </select>
        </div>
        <div className="w-32">
          <Label className="text-xs text-ink-200">Min score</Label>
          <Input
            className={cn(crmFieldSurface, "mt-1")}
            type="number"
            value={minScore}
            onChange={(e) => setMinScore(e.target.value)}
            placeholder="0-100"
          />
        </div>
        <div className="flex-1 min-w-[200px]">
          <Label className="text-xs text-ink-200">Assign selected to</Label>
          <select
            value={assignVAId}
            onChange={(e) => setAssignVAId(e.target.value)}
            className={cn(crmFieldSurface, "mt-1 w-full rounded-md px-2 py-1.5 text-sm")}
          >
            <option value="">Pick a VA…</option>
            {vas.map((v) => (
              <option key={v.id} value={v.id}>
                {v.full_name || v.email} ({v.today_assigned} assigned today)
              </option>
            ))}
          </select>
        </div>
        <Button onClick={bulkAssign} disabled={assigning || selected.size === 0 || !assignVAId}>
          <UserPlus size={14} className="mr-2" />
          Assign {selected.size || ""}
        </Button>
        <Button variant="outline" onClick={() => void refresh()} disabled={loading}>
          <RefreshCw size={14} className={cn("mr-2", loading && "animate-spin")} />
          Refresh
        </Button>
      </div>

      {prospects.length === 0 ? (
        <div className={crmEmptyState}>Nothing in the VA queue yet.</div>
      ) : (
        <div className={crmTableWrap}>
          <table className="w-full text-sm text-ink-100">
            <thead className={crmTableThead}>
              <tr>
                <th className="px-3 py-2 w-8"></th>
                <th className="px-3 py-2 text-left">Company</th>
                <th className="px-3 py-2 text-left">Contact</th>
                <th className="px-3 py-2 text-left">Vertical</th>
                <th className="px-3 py-2 text-left">City</th>
                <th className="px-3 py-2 text-right">Score</th>
              </tr>
            </thead>
            <tbody>
              {prospects.map((p) => (
                <tr key={p.id} className={crmTableRow}>
                  <td className="px-3 py-2">
                    <input
                      type="checkbox"
                      checked={selected.has(p.id)}
                      onChange={() => toggle(p.id)}
                    />
                  </td>
                  <td className="px-3 py-2">
                    <div className="font-medium">{p.company_name || p.domain}</div>
                    <div className="text-xs text-ink-0">{p.domain}</div>
                  </td>
                  <td className="px-3 py-2">
                    <div>{p.contact_name || "—"}</div>
                    <div className="text-xs text-ink-0">{p.contact_email || "—"}</div>
                  </td>
                  <td className="px-3 py-2 capitalize">{p.industry || "—"}</td>
                  <td className="px-3 py-2">{p.city || "—"}</td>
                  <td className="px-3 py-2 text-right">{p.hawk_score ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ─── Team tab ───────────────────────────────────────────────────────────

function TeamTab() {
  const { session } = useCrmAuth();
  const [vas, setVAs] = useState<VA[]>([]);
  const [loading, setLoading] = useState(false);
  const [inviteOpen, setInviteOpen] = useState(false);
  const [inviteForm, setInviteForm] = useState({ email: "", full_name: "", role_type: "va_outreach" });
  const [inviting, setInviting] = useState(false);

  const refresh = useCallback(async () => {
    if (!session?.access_token) return;
    setLoading(true);
    try {
      const r = await fetch(`${CRM_API_BASE_URL}/api/crm/va/team`, {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (r.ok) {
        const j = (await r.json()) as { vas: VA[] };
        setVAs(j.vas || []);
      }
    } finally {
      setLoading(false);
    }
  }, [session?.access_token]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function submitInvite() {
    if (!session?.access_token) return;
    if (!inviteForm.email.trim() || !inviteForm.full_name.trim()) {
      toast.error("Fill in email + name");
      return;
    }
    setInviting(true);
    try {
      const r = await fetch(`${CRM_API_BASE_URL}/api/crm/va/invite`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify(inviteForm),
      });
      if (!r.ok) {
        toast.error((await r.text()).slice(0, 200));
        return;
      }
      toast.success("Invite sent");
      setInviteOpen(false);
      setInviteForm({ email: "", full_name: "", role_type: "va_outreach" });
      void refresh();
    } finally {
      setInviting(false);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-sm text-ink-200">
          {vas.length} VA{vas.length === 1 ? "" : "s"} on the roster
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => void refresh()} disabled={loading}>
            <RefreshCw size={14} className={cn("mr-2", loading && "animate-spin")} />
            Refresh
          </Button>
          <Button onClick={() => setInviteOpen(true)}>
            <UserPlus size={14} className="mr-2" />
            Invite VA
          </Button>
        </div>
      </div>

      {vas.length === 0 ? (
        <div className={crmEmptyState}>
          No VAs invited yet. Click <span className="text-ink-100">Invite VA</span> to send the first one.
        </div>
      ) : (
        <div className={crmTableWrap}>
          <table className="w-full text-sm text-ink-100">
            <thead className={crmTableThead}>
              <tr>
                <th className="px-3 py-2 text-left">Name</th>
                <th className="px-3 py-2 text-left">Email</th>
                <th className="px-3 py-2 text-left">Role</th>
                <th className="px-3 py-2 text-right">Assigned today</th>
                <th className="px-3 py-2 text-right">Reached out</th>
                <th className="px-3 py-2 text-right">Booked</th>
              </tr>
            </thead>
            <tbody>
              {vas.map((v) => (
                <tr key={v.id} className={crmTableRow}>
                  <td className="px-3 py-2 font-medium">{v.full_name || "—"}</td>
                  <td className="px-3 py-2 text-ink-200">{v.email || "—"}</td>
                  <td className="px-3 py-2 capitalize">{v.role_type.replace("_", " ")}</td>
                  <td className="px-3 py-2 text-right">{v.today_assigned}</td>
                  <td className="px-3 py-2 text-right">{v.today_reached_out}</td>
                  <td className="px-3 py-2 text-right text-signal">{v.today_booked}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Dialog open={inviteOpen} onOpenChange={setInviteOpen}>
        <DialogContent className={crmDialogSurface}>
          <DialogHeader>
            <DialogTitle>Invite a VA</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <Label>Email</Label>
              <Input
                className={crmFieldSurface}
                type="email"
                value={inviteForm.email}
                onChange={(e) => setInviteForm({ ...inviteForm, email: e.target.value })}
              />
            </div>
            <div>
              <Label>Full name</Label>
              <Input
                className={crmFieldSurface}
                value={inviteForm.full_name}
                onChange={(e) => setInviteForm({ ...inviteForm, full_name: e.target.value })}
              />
            </div>
            <div>
              <Label>Role</Label>
              <select
                value={inviteForm.role_type}
                onChange={(e) => setInviteForm({ ...inviteForm, role_type: e.target.value })}
                className={cn(crmFieldSurface, "w-full rounded-md px-2 py-1.5 text-sm")}
              >
                <option value="va_outreach">VA (outreach)</option>
                <option value="va_manager">VA Manager</option>
              </select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setInviteOpen(false)} disabled={inviting}>
              Cancel
            </Button>
            <Button onClick={submitInvite} disabled={inviting}>
              {inviting ? "Sending…" : "Send invite"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

// ─── My Queue tab ───────────────────────────────────────────────────────

function MyQueueTab() {
  const { session } = useCrmAuth();
  const [rows, setRows] = useState<Assignment[]>([]);
  const [loading, setLoading] = useState(false);
  const [active, setActive] = useState<Assignment | null>(null);

  const refresh = useCallback(async () => {
    if (!session?.access_token) return;
    setLoading(true);
    try {
      const r = await fetch(`${CRM_API_BASE_URL}/api/crm/va/my-queue`, {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (r.ok) {
        const j = (await r.json()) as { assignments: Assignment[] };
        setRows(j.assignments || []);
      }
    } finally {
      setLoading(false);
    }
  }, [session?.access_token]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-sm text-ink-200">{rows.length} open assignment{rows.length === 1 ? "" : "s"}</div>
        <Button variant="outline" onClick={() => void refresh()} disabled={loading}>
          <RefreshCw size={14} className={cn("mr-2", loading && "animate-spin")} />
          Refresh
        </Button>
      </div>

      {rows.length === 0 ? (
        <div className={crmEmptyState}>Nothing assigned to you yet. Check back soon.</div>
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {rows.map((a) => (
            <AssignmentCard key={a.id} assignment={a} onOpen={() => setActive(a)} />
          ))}
        </div>
      )}

      {active && (
        <OutreachDialog
          assignment={active}
          onClose={() => setActive(null)}
          onUpdated={() => {
            setActive(null);
            void refresh();
          }}
        />
      )}
    </div>
  );
}

function AssignmentCard({ assignment, onOpen }: { assignment: Assignment; onOpen: () => void }) {
  const p = assignment.prospect;
  return (
    <div className={cn(crmSurfaceCard, "p-4 space-y-2")}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="font-medium text-ink-0">{p.company_name || p.domain}</div>
          <div className="text-xs text-ink-0">
            {p.city || "—"} • {p.industry || "—"} • Hawk score {p.hawk_score ?? "—"}
          </div>
        </div>
        <span className="rounded-full bg-ink-800 px-2 py-0.5 text-xs text-ink-100 capitalize">
          {assignment.status.replace("_", " ")}
        </span>
      </div>
      <div className="text-sm">
        <span className="text-ink-200">Contact: </span>
        <span>{p.contact_name || "—"}</span>
      </div>
      <div className="text-xs text-ink-0 break-all">{p.contact_email || "—"}</div>
      <div className="flex gap-2 pt-2">
        <Button size="sm" onClick={onOpen}>
          <Mail size={14} className="mr-2" />
          Open outreach
        </Button>
      </div>
    </div>
  );
}

function OutreachDialog({
  assignment,
  onClose,
  onUpdated,
}: {
  assignment: Assignment;
  onClose: () => void;
  onUpdated: () => void;
}) {
  const { session } = useCrmAuth();
  const p = assignment.prospect;
  const [notes, setNotes] = useState(assignment.notes || "");
  const [saving, setSaving] = useState(false);

  const emailText = useMemo(() => {
    const subject = p.email_subject || "";
    const body = p.email_body || "";
    return `Subject: ${subject}\n\n${body}`;
  }, [p.email_subject, p.email_body]);

  async function updateStatus(status: string, logOutreach = false) {
    if (!session?.access_token) return;
    setSaving(true);
    try {
      const r = await fetch(`${CRM_API_BASE_URL}/api/crm/va/status`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${session.access_token}`,
        },
        body: JSON.stringify({
          assignment_id: assignment.id,
          status,
          notes,
          log_outreach: logOutreach,
          channel: "email",
        }),
      });
      if (!r.ok) {
        toast.error((await r.text()).slice(0, 200));
        return;
      }
      toast.success("Saved");
      onUpdated();
    } finally {
      setSaving(false);
    }
  }

  async function copyEmail() {
    try {
      await navigator.clipboard.writeText(emailText);
      toast.success("Copied email to clipboard");
    } catch {
      toast.error("Could not copy — select + copy manually");
    }
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className={cn(crmDialogSurface, "max-w-2xl")}>
        <DialogHeader>
          <DialogTitle>
            {p.company_name || p.domain}
            <span className="ml-2 text-xs font-normal text-ink-0">
              {p.contact_name ? `— ${p.contact_name}` : ""}
            </span>
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-4">
          <div className={cn(crmSurfaceCard, "p-3 text-sm space-y-1")}>
            <div>
              <span className="text-ink-200">Email: </span>
              <span>{p.contact_email || "—"}</span>
            </div>
            {p.contact_phone && (
              <div>
                <span className="text-ink-200">Phone: </span>
                <span>{p.contact_phone}</span>
              </div>
            )}
            {p.contact_linkedin_url && (
              <div className="break-all">
                <span className="text-ink-200">LinkedIn: </span>
                <a href={p.contact_linkedin_url} target="_blank" rel="noreferrer" className="text-signal underline">
                  {p.contact_linkedin_url}
                </a>
              </div>
            )}
          </div>

          <div>
            <Label>ARIA drafted email</Label>
            <textarea
              readOnly
              value={emailText}
              className={cn(crmFieldSurface, "mt-1 min-h-[200px] w-full p-2 font-mono text-xs")}
            />
            <div className="mt-2 flex gap-2">
              <Button size="sm" variant="outline" onClick={copyEmail}>
                <Copy size={14} className="mr-2" />
                Copy
              </Button>
              <Button
                size="sm"
                onClick={() => void updateStatus("reached_out", true)}
                disabled={saving}
              >
                <Send size={14} className="mr-2" />
                Mark as sent
              </Button>
            </div>
          </div>

          <div>
            <Label>Notes</Label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              className={cn(crmFieldSurface, "mt-1 w-full p-2 text-sm")}
              placeholder="Response received, voicemail left, etc."
              rows={3}
            />
          </div>

          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="outline" onClick={() => void updateStatus("in_progress")} disabled={saving}>
              In progress
            </Button>
            <Button size="sm" variant="outline" onClick={() => void updateStatus("no_answer", true)} disabled={saving}>
              No answer
            </Button>
            <Button size="sm" variant="outline" onClick={() => void updateStatus("not_interested", true)} disabled={saving}>
              Not interested
            </Button>
            <Button size="sm" onClick={() => void updateStatus("call_booked", true)} disabled={saving}>
              Call booked
            </Button>
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={saving}>
            Close
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
