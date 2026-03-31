"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import type {
  CrmActivityRow,
  CrmProspectScanRow,
  Prospect,
  ProspectEmailEventRow,
  ProspectFileRow,
  ProspectNoteRow,
  ProspectStage,
} from "@/lib/crm/types";
import { STAGE_META, STAGE_ORDER } from "@/lib/crm/types";
import { activityColor, activityLabel } from "@/lib/crm/activity-types";
import { HawkScoreRing } from "@/components/crm/prospect/hawk-score-ring";
import { LogCallModal } from "@/components/crm/prospect/log-call-modal";
import { BookCallModal } from "@/components/crm/prospect/book-call-modal";
import { LostReasonModal } from "@/components/crm/pipeline/lost-modal";
import { CloseWonModal } from "@/components/crm/pipeline/close-won-modal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import toast from "react-hot-toast";
import { cn } from "@/lib/utils";

export function ProspectProfile({
  prospectId,
  variant,
  onClose,
  onUpdated,
}: {
  prospectId: string;
  variant: "drawer" | "page";
  onClose?: () => void;
  onUpdated?: () => void;
}) {
  const supabase = useMemo(() => createClient(), []);
  const { profile, session } = useCrmAuth();
  const [p, setP] = useState<Prospect | null>(null);
  const [activities, setActivities] = useState<CrmActivityRow[]>([]);
  const [notes, setNotes] = useState<ProspectNoteRow[]>([]);
  const [scans, setScans] = useState<CrmProspectScanRow[]>([]);
  const [files, setFiles] = useState<ProspectFileRow[]>([]);
  const [reps, setReps] = useState<{ id: string; full_name: string | null; email: string | null }[]>([]);
  const [domainPeers, setDomainPeers] = useState<{ id: string; company_name: string | null; created_at: string }[]>([]);
  const [emailEvents, setEmailEvents] = useState<ProspectEmailEventRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [duplicateHint, setDuplicateHint] = useState(false);
  const [duplicateLinkTarget, setDuplicateLinkTarget] = useState("");
  const [editingNoteId, setEditingNoteId] = useState<string | null>(null);
  const [noteEditDraft, setNoteEditDraft] = useState("");

  const [logOpen, setLogOpen] = useState(false);
  const [bookOpen, setBookOpen] = useState(false);
  const [lostOpen, setLostOpen] = useState(false);
  const [wonOpen, setWonOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [newNote, setNewNote] = useState("");
  const [fileTitle, setFileTitle] = useState("");
  const [fileUrl, setFileUrl] = useState("");

  const canReassign = profile?.role === "ceo" || profile?.role === "hos";
  const privileged = profile?.role === "ceo" || profile?.role === "hos";

  const load = useCallback(async () => {
    setLoading(true);
    const { data: prospect, error } = await supabase.from("prospects").select("*").eq("id", prospectId).single();
    if (error || !prospect) {
      toast.error(error?.message ?? "Not found");
      setP(null);
      setLoading(false);
      return;
    }
    setP(prospect as Prospect);

    const [{ data: act }, { data: n }, { data: sc }, { data: fi }, { data: em }] = await Promise.all([
      supabase.from("activities").select("*").eq("prospect_id", prospectId).order("created_at", { ascending: false }),
      supabase.from("prospect_notes").select("*").eq("prospect_id", prospectId).order("created_at", { ascending: false }),
      supabase.from("crm_prospect_scans").select("*").eq("prospect_id", prospectId).order("created_at", { ascending: false }),
      supabase.from("prospect_files").select("*").eq("prospect_id", prospectId).order("created_at", { ascending: false }),
      supabase.from("prospect_email_events").select("*").eq("prospect_id", prospectId).order("created_at", { ascending: false }),
    ]);
    setActivities((act as CrmActivityRow[]) ?? []);
    setNotes((n as ProspectNoteRow[]) ?? []);
    setScans((sc as CrmProspectScanRow[]) ?? []);
    setFiles((fi as ProspectFileRow[]) ?? []);
    setEmailEvents((em as ProspectEmailEventRow[]) ?? []);
    setEditingNoteId(null);
    setNoteEditDraft("");

    const { data: peers } = await supabase
      .from("prospects")
      .select("id, company_name, created_at")
      .eq("domain", (prospect as Prospect).domain)
      .neq("id", prospectId)
      .order("created_at", { ascending: false });
    const peerList = peers ?? [];
    setDomainPeers(peerList);
    const day = 24 * 60 * 60 * 1000;
    const recent = peerList.filter((row: { created_at: string }) => Date.now() - new Date(row.created_at).getTime() < day);
    setDuplicateHint(recent.length > 0 || !!(prospect as Prospect).duplicate_of);

    if (canReassign) {
      const { data: r } = await supabase.from("profiles").select("id, full_name, email").in("role", ["sales_rep", "team_lead"]);
      setReps(r ?? []);
    }

    setLoading(false);
  }, [supabase, prospectId, canReassign]);

  useEffect(() => {
    void load();
  }, [load]);

  async function logActivity(
    type: string,
    metadata: Record<string, unknown>,
    notesText: string | null = null
  ) {
    if (!session?.user?.id) return;
    await supabase.from("activities").insert({
      prospect_id: prospectId,
      type,
      created_by: session.user.id,
      notes: notesText,
      metadata,
    });
  }

  async function runScan() {
    if (!p) return;
    setScanning(true);
    try {
      const res = await fetch("/api/crm/run-scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prospectId: p.id }),
      });
      const j = await res.json().catch(() => ({}));
      if (!res.ok) {
        toast.error(j.error ?? "Scan failed");
        return;
      }
      toast.success(`Scan complete — score ${j.score ?? "—"}`);
      await load();
      onUpdated?.();
    } finally {
      setScanning(false);
    }
  }

  async function toggleHot() {
    if (!p) return;
    const next = !p.is_hot;
    await supabase.from("prospects").update({ is_hot: next, last_activity_at: new Date().toISOString() }).eq("id", p.id);
    await logActivity("hot_lead_flagged", { hot: next });
    toast.success(next ? "Marked hot" : "Unmarked");
    await load();
    onUpdated?.();
  }

  async function changeStage(next: ProspectStage) {
    if (!p) return;
    if (next === "lost") {
      setLostOpen(true);
      return;
    }
    if (next === "closed_won") {
      setWonOpen(true);
      return;
    }
    const from = p.stage;
    await supabase
      .from("prospects")
      .update({ stage: next, last_activity_at: new Date().toISOString() })
      .eq("id", p.id);
    await logActivity("stage_changed", { from, to: next });
    toast.success("Stage updated");
    await load();
    onUpdated?.();
  }

  async function saveEdit(form: FormData) {
    if (!p) return;
    await supabase
      .from("prospects")
      .update({
        company_name: String(form.get("company_name") || ""),
        industry: String(form.get("industry") || "") || null,
        city: String(form.get("city") || "") || null,
        contact_name: String(form.get("contact_name") || "") || null,
        contact_email: String(form.get("contact_email") || "") || null,
        phone: String(form.get("phone") || "") || null,
      })
      .eq("id", p.id);
    toast.success("Saved");
    setEditOpen(false);
    await load();
    onUpdated?.();
  }

  async function reassignTo(repId: string) {
    if (!p || !repId) return;
    const prev = p.assigned_rep_id;
    await supabase.from("prospects").update({ assigned_rep_id: repId }).eq("id", p.id);
    await logActivity("prospect_reassigned", { previous_rep: prev, new_rep: repId });
    toast.success("Reassigned");
    await load();
    onUpdated?.();
  }

  async function dismissDuplicate() {
    if (!p) return;
    await supabase.from("prospects").update({ duplicate_of: null }).eq("id", p.id);
    setDuplicateHint(false);
    toast.success("Duplicate flag cleared");
    await load();
  }

  async function linkAsDuplicateOf() {
    if (!p || !duplicateLinkTarget) return;
    await supabase.from("prospects").update({ duplicate_of: duplicateLinkTarget }).eq("id", p.id);
    await logActivity("duplicate_linked", { canonical_prospect_id: duplicateLinkTarget });
    toast.success("Linked to selected prospect as canonical record");
    setDuplicateLinkTarget("");
    await load();
    onUpdated?.();
  }

  async function saveNoteEdit() {
    if (!editingNoteId || !noteEditDraft.trim()) return;
    await supabase
      .from("prospect_notes")
      .update({ body: noteEditDraft.trim(), updated_at: new Date().toISOString() })
      .eq("id", editingNoteId);
    setEditingNoteId(null);
    setNoteEditDraft("");
    toast.success("Note updated");
    await load();
  }

  async function deleteNote(noteId: string) {
    if (!confirm("Delete this note?")) return;
    await supabase.from("prospect_notes").delete().eq("id", noteId);
    if (editingNoteId === noteId) {
      setEditingNoteId(null);
      setNoteEditDraft("");
    }
    toast.success("Note deleted");
    await load();
  }

  async function addNote() {
    if (!newNote.trim() || !session?.user?.id) return;
    await supabase.from("prospect_notes").insert({
      prospect_id: prospectId,
      author_id: session.user.id,
      body: newNote.trim(),
    });
    await logActivity("note_added", { preview: newNote.trim().slice(0, 120) }, newNote.trim());
    setNewNote("");
    await load();
  }

  async function addFile(e: React.FormEvent) {
    e.preventDefault();
    if (!fileTitle.trim() || !fileUrl.trim() || !session?.user?.id) return;
    await supabase.from("prospect_files").insert({
      prospect_id: prospectId,
      title: fileTitle.trim(),
      file_url: fileUrl.trim(),
      kind: "link",
      created_by: session.user.id,
    });
    setFileTitle("");
    setFileUrl("");
    toast.success("File link added");
    await load();
  }

  if (loading || !p) {
    return (
      <div className="flex min-h-[200px] items-center justify-center text-zinc-500">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-zinc-700 border-t-emerald-500" />
      </div>
    );
  }

  const title = variant === "page" ? "text-2xl" : "text-xl";

  return (
    <div className="flex h-full flex-col">
      {(duplicateHint || p.duplicate_of) && (
        <div className="mb-3 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-100">
          <p>
            Possible duplicate for this domain — contact HoS if unsure.
            {privileged && (
              <>
                {" "}
                <button type="button" className="underline" onClick={() => void dismissDuplicate()}>
                  Clear duplicate flag
                </button>
              </>
            )}
          </p>
          {domainPeers.length > 0 && (
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-amber-200/90">
              <span className="text-amber-200/70">Other records on {p.domain}:</span>
              {domainPeers.map((peer) => (
                <Link key={peer.id} href={`/crm/prospects/${peer.id}`} className="text-emerald-300 underline-offset-2 hover:underline">
                  {peer.company_name ?? peer.id.slice(0, 8)}…
                </Link>
              ))}
            </div>
          )}
          {privileged && domainPeers.length > 0 && (
            <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-amber-500/20 pt-2">
              <span className="text-xs text-amber-200/80">Mark this prospect as duplicate of:</span>
              <select
                className="rounded border border-amber-500/30 bg-zinc-950 px-2 py-1 text-xs text-zinc-100"
                value={duplicateLinkTarget}
                onChange={(e) => setDuplicateLinkTarget(e.target.value)}
              >
                <option value="">Choose canonical record…</option>
                {domainPeers.map((peer) => (
                  <option key={peer.id} value={peer.id}>
                    {peer.company_name ?? peer.id.slice(0, 8)}…
                  </option>
                ))}
              </select>
              <Button
                size="sm"
                variant="outline"
                className="h-7 border-amber-500/40 text-xs"
                disabled={!duplicateLinkTarget}
                onClick={() => void linkAsDuplicateOf()}
              >
                Link
              </Button>
            </div>
          )}
        </div>
      )}

      {domainPeers.length > 0 && !(duplicateHint || p.duplicate_of) && (
        <div className="mb-3 rounded-lg border border-zinc-700 bg-zinc-900/60 px-3 py-2 text-sm text-zinc-300">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
            <span className="text-zinc-500">Other prospects on {p.domain}:</span>
            {domainPeers.map((peer) => (
              <Link key={peer.id} href={`/crm/prospects/${peer.id}`} className="text-emerald-400 underline-offset-2 hover:underline">
                {peer.company_name ?? peer.id.slice(0, 8)}…
              </Link>
            ))}
          </div>
          {privileged && (
            <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-zinc-800 pt-2">
              <span className="text-xs text-zinc-500">Mark this prospect as duplicate of:</span>
              <select
                className="rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-xs text-zinc-100"
                value={duplicateLinkTarget}
                onChange={(e) => setDuplicateLinkTarget(e.target.value)}
              >
                <option value="">Choose canonical record…</option>
                {domainPeers.map((peer) => (
                  <option key={peer.id} value={peer.id}>
                    {peer.company_name ?? peer.id.slice(0, 8)}…
                  </option>
                ))}
              </select>
              <Button
                size="sm"
                variant="outline"
                className="h-7 border-zinc-700 text-xs"
                disabled={!duplicateLinkTarget}
                onClick={() => void linkAsDuplicateOf()}
              >
                Link
              </Button>
            </div>
          )}
        </div>
      )}

      <div className="flex flex-col gap-4 border-b border-zinc-800 pb-4 lg:flex-row lg:items-start">
        <div className="flex flex-1 gap-4">
          <HawkScoreRing score={p.hawk_score} />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              {variant === "drawer" ? (
                <Link href={`/crm/prospects/${p.id}`} className={cn(title, "font-semibold text-zinc-50 underline-offset-4 hover:underline")}>
                  {p.company_name ?? p.domain}
                </Link>
              ) : (
                <h1 className={cn(title, "font-semibold text-zinc-50")}>{p.company_name ?? p.domain}</h1>
              )}
              <a href={`https://${p.domain}`} target="_blank" rel="noreferrer" className="text-sm text-emerald-400 hover:underline">
                {p.domain}
              </a>
            </div>
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <select
                className="rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1 text-xs text-zinc-100"
                value={p.stage}
                onChange={(e) => void changeStage(e.target.value as ProspectStage)}
              >
                {STAGE_ORDER.map((s) => (
                  <option key={s} value={s}>
                    {STAGE_META[s].label}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => void toggleHot()}
                className={cn("rounded-md border px-2 py-1 text-xs", p.is_hot ? "border-rose-500 text-rose-300" : "border-zinc-700 text-zinc-400")}
              >
                {p.is_hot ? "★ Hot" : "☆ Mark hot"}
              </button>
            </div>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" className="bg-emerald-600" onClick={() => runScan()} disabled={scanning}>
            {scanning ? "Scanning…" : "Run scan"}
          </Button>
          <Button size="sm" variant="outline" className="border-zinc-700" onClick={() => setLogOpen(true)}>
            Log call
          </Button>
          <Button size="sm" variant="outline" className="border-zinc-700" onClick={() => setBookOpen(true)}>
            Book call
          </Button>
          <Button size="sm" variant="outline" className="border-zinc-700" onClick={() => setEditOpen(true)}>
            Edit
          </Button>
          <details className="relative">
            <summary className="cursor-pointer list-none rounded-md border border-zinc-700 px-3 py-1.5 text-sm text-zinc-200 hover:bg-zinc-900">
              More
            </summary>
            <div className="absolute right-0 z-10 mt-1 w-52 rounded-lg border border-zinc-800 bg-zinc-950 py-1 shadow-xl">
              <button
                type="button"
                className="block w-full px-3 py-2 text-left text-sm hover:bg-zinc-900"
                onClick={() => {
                  void navigator.clipboard.writeText(`${typeof window !== "undefined" ? window.location.origin : ""}/crm/prospects/${p.id}`);
                  toast.success("Link copied");
                }}
              >
                Copy profile link
              </button>
              {canReassign && (
                <div className="border-t border-zinc-800 px-3 py-2 text-xs text-zinc-500">
                  Reassign
                  <select
                    className="mt-1 w-full rounded border border-zinc-700 bg-zinc-900 px-2 py-1 text-zinc-100"
                    value={p.assigned_rep_id ?? ""}
                    onChange={(e) => void reassignTo(e.target.value)}
                  >
                    <option value="">—</option>
                    {reps.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.full_name ?? r.email}
                      </option>
                    ))}
                  </select>
                </div>
              )}
              <button type="button" className="block w-full px-3 py-2 text-left text-sm text-rose-300 hover:bg-zinc-900" onClick={() => setLostOpen(true)}>
                Mark lost
              </button>
              <button type="button" className="block w-full px-3 py-2 text-left text-sm hover:bg-zinc-900" onClick={() => setWonOpen(true)}>
                Convert to client
              </button>
            </div>
          </details>
          {variant === "drawer" && onClose && (
            <Button size="sm" variant="ghost" onClick={onClose}>
              Close
            </Button>
          )}
        </div>
      </div>

      <Tabs defaultValue="overview" className="mt-4 flex min-h-0 flex-1 flex-col">
        <TabsList className="w-full shrink-0 flex-wrap justify-start gap-1 overflow-x-auto">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="timeline">Timeline</TabsTrigger>
          <TabsTrigger value="scans">Scan results</TabsTrigger>
          <TabsTrigger value="emails">Emails</TabsTrigger>
          <TabsTrigger value="notes">Notes</TabsTrigger>
          <TabsTrigger value="files">Files</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="min-h-[200px] space-y-3 text-sm">
          <div className="grid gap-2 sm:grid-cols-2">
            <div>
              <span className="text-zinc-500">Industry</span>
              <p className="text-zinc-200">{p.industry ?? "—"}</p>
            </div>
            <div>
              <span className="text-zinc-500">City</span>
              <p className="text-zinc-200">{p.city ?? "—"}</p>
            </div>
            <div>
              <span className="text-zinc-500">Contact</span>
              <p className="text-zinc-200">{p.contact_name ?? "—"}</p>
            </div>
            <div>
              <span className="text-zinc-500">Email</span>
              <p className="text-zinc-200">{p.contact_email ?? "—"}</p>
            </div>
            <div>
              <span className="text-zinc-500">Phone</span>
              <p className="text-zinc-200">{p.phone ?? "—"}</p>
            </div>
            <div>
              <span className="text-zinc-500">Source</span>
              <p className="capitalize text-zinc-200">{p.source}</p>
            </div>
          </div>
          <p className="text-xs text-zinc-500">Apollo enrichment & deal value: Phase 7+.</p>
        </TabsContent>

        <TabsContent value="timeline" className="min-h-[240px] max-h-[50vh] space-y-3 overflow-y-auto pr-1 text-sm">
          {activities.length === 0 && <p className="text-zinc-500">No events yet.</p>}
          {activities.map((a) => (
            <div key={a.id} className="rounded-lg border border-zinc-800 bg-zinc-900/50 px-3 py-2">
              <div className={cn("text-xs font-medium", activityColor(a.type))}>{activityLabel(a.type)}</div>
              <div className="text-[11px] text-zinc-500">{new Date(a.created_at).toLocaleString()}</div>
              {a.notes && <p className="mt-1 text-zinc-300">{a.notes}</p>}
              {a.metadata != null &&
                typeof a.metadata === "object" &&
                Object.keys(a.metadata as Record<string, unknown>).length > 0 && (
                  <pre className="mt-1 max-h-24 overflow-auto text-[10px] text-zinc-500">{JSON.stringify(a.metadata, null, 2)}</pre>
                )}
            </div>
          ))}
        </TabsContent>

        <TabsContent value="scans" className="min-h-[200px] space-y-2 text-sm">
          {scans.length === 0 && <p className="text-zinc-500">No scans yet. Run a scan from the header.</p>}
          {scans.map((s) => (
            <div key={s.id} className="rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2">
              <div className="flex justify-between text-zinc-200">
                <span>Score {s.hawk_score ?? "—"}</span>
                <span className="text-zinc-500">{new Date(s.created_at).toLocaleString()}</span>
              </div>
              <pre className="mt-2 max-h-40 overflow-auto text-[11px] text-zinc-400">{JSON.stringify(s.findings, null, 2)}</pre>
            </div>
          ))}
        </TabsContent>

        <TabsContent value="emails" className="min-h-[120px] space-y-2 text-sm">
          {emailEvents.length === 0 && (
            <p className="text-zinc-500">
              No email events yet. POST to the API webhook (see{" "}
              <Link href="/crm/charlotte" className="text-emerald-400 hover:underline">
                Charlotte
              </Link>
              ) or connect Smartlead with <code className="text-zinc-400">X-CRM-Webhook-Secret</code>.
            </p>
          )}
          {emailEvents.map((ev) => {
            const src = ev.source ?? "webhook";
            const meta = ev.metadata && typeof ev.metadata === "object" && Object.keys(ev.metadata).length > 0;
            return (
              <div key={ev.id} className="rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <div className="font-medium text-zinc-200">{ev.subject ?? "(No subject)"}</div>
                  <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-zinc-400">{src}</span>
                </div>
                {ev.external_id && (
                  <div className="mt-1 font-mono text-[10px] text-zinc-500">id: {ev.external_id}</div>
                )}
                <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-[11px] text-zinc-500">
                  {ev.sequence_step != null && <span>Step {ev.sequence_step}</span>}
                  {ev.sent_at && <span>Sent {new Date(ev.sent_at).toLocaleString()}</span>}
                  {ev.opened_at && <span>Opened {new Date(ev.opened_at).toLocaleString()}</span>}
                  {ev.clicked_at && <span>Clicked {new Date(ev.clicked_at).toLocaleString()}</span>}
                  {ev.replied_at && <span>Replied {new Date(ev.replied_at).toLocaleString()}</span>}
                </div>
                {meta && (
                  <pre className="mt-2 max-h-28 overflow-auto text-[10px] text-zinc-500">{JSON.stringify(ev.metadata, null, 2)}</pre>
                )}
              </div>
            );
          })}
        </TabsContent>

        <TabsContent value="notes" className="min-h-[200px] space-y-3">
          <div className="space-y-2">
            <textarea
              className="w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100"
              rows={3}
              placeholder="Add a note…"
              value={newNote}
              onChange={(e) => setNewNote(e.target.value)}
            />
            <Button size="sm" className="bg-emerald-600" onClick={() => void addNote()}>
              Add note
            </Button>
          </div>
          <ul className="space-y-2">
            {notes.map((n) => {
              const isAuthor = session?.user?.id === n.author_id;
              const isEditing = editingNoteId === n.id;
              return (
                <li key={n.id} className="rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2 text-sm text-zinc-200">
                  {isEditing ? (
                    <div className="space-y-2">
                      <textarea
                        className="w-full rounded-md border border-zinc-700 bg-zinc-900 px-3 py-2 text-sm text-zinc-100"
                        rows={4}
                        value={noteEditDraft}
                        onChange={(e) => setNoteEditDraft(e.target.value)}
                      />
                      <div className="flex gap-2">
                        <Button size="sm" className="bg-emerald-600" onClick={() => void saveNoteEdit()}>
                          Save
                        </Button>
                        <Button
                          size="sm"
                          variant="outline"
                          className="border-zinc-700"
                          onClick={() => {
                            setEditingNoteId(null);
                            setNoteEditDraft("");
                          }}
                        >
                          Cancel
                        </Button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <p className="whitespace-pre-wrap">{n.body}</p>
                      <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-zinc-500">
                        <span>
                          {new Date(n.created_at).toLocaleString()}
                          {n.updated_at !== n.created_at && (
                            <span className="ml-1 text-zinc-600">· edited {new Date(n.updated_at).toLocaleString()}</span>
                          )}
                        </span>
                        {isAuthor && (
                          <span className="flex gap-2">
                            <button
                              type="button"
                              className="text-emerald-400 hover:underline"
                              onClick={() => {
                                setEditingNoteId(n.id);
                                setNoteEditDraft(n.body);
                              }}
                            >
                              Edit
                            </button>
                            <button type="button" className="text-rose-400 hover:underline" onClick={() => void deleteNote(n.id)}>
                              Delete
                            </button>
                          </span>
                        )}
                      </div>
                    </>
                  )}
                </li>
              );
            })}
          </ul>
        </TabsContent>

        <TabsContent value="files" className="min-h-[200px] space-y-3">
          <form className="flex flex-col gap-2 sm:flex-row sm:items-end" onSubmit={addFile}>
            <div className="flex-1">
              <Label className="text-xs text-zinc-500">Title</Label>
              <Input className="border-zinc-700 bg-zinc-900" value={fileTitle} onChange={(e) => setFileTitle(e.target.value)} />
            </div>
            <div className="flex-[2]">
              <Label className="text-xs text-zinc-500">URL</Label>
              <Input className="border-zinc-700 bg-zinc-900" value={fileUrl} onChange={(e) => setFileUrl(e.target.value)} placeholder="https://…" />
            </div>
            <Button type="submit" className="bg-zinc-800">
              Add
            </Button>
          </form>
          <ul className="space-y-2">
            {files.map((f) => (
              <li key={f.id}>
                <a href={f.file_url} target="_blank" rel="noreferrer" className="text-emerald-400 hover:underline">
                  {f.title}
                </a>
                <span className="ml-2 text-xs text-zinc-500">{new Date(f.created_at).toLocaleDateString()}</span>
              </li>
            ))}
          </ul>
        </TabsContent>
      </Tabs>

      <LogCallModal
        open={logOpen}
        onOpenChange={setLogOpen}
        onSave={async (payload) => {
          await logActivity(
            "call_logged",
            {
              duration_minutes: payload.durationMinutes,
              outcome: payload.outcome,
              next_action: payload.nextAction,
            },
            payload.summary
          );
          await supabase.from("prospects").update({ last_activity_at: new Date().toISOString() }).eq("id", prospectId);
          toast.success("Call logged");
          await load();
          onUpdated?.();
        }}
      />

      <BookCallModal open={bookOpen} onOpenChange={setBookOpen} domain={p.domain} />

      <LostReasonModal
        open={lostOpen}
        onOpenChange={setLostOpen}
        onConfirm={async ({ reason, notes, reactivateOn }) => {
          const fromStage = p.stage;
          await supabase
            .from("prospects")
            .update({
              stage: "lost",
              lost_reason: reason,
              lost_notes: notes,
              reactivate_on: reactivateOn,
              last_activity_at: new Date().toISOString(),
            })
            .eq("id", p.id);
          await logActivity("stage_changed", { from: fromStage, to: "lost", reason });
          toast.success("Marked lost");
          await load();
          onUpdated?.();
        }}
      />

      <CloseWonModal
        open={wonOpen}
        onOpenChange={setWonOpen}
        onConfirm={async ({ planId, mrrCents, stripeCustomerId }) => {
          if (!session?.user?.id) return;
          const fromStage = p.stage;
          await supabase.from("clients").insert({
            prospect_id: p.id,
            company_name: p.company_name,
            domain: p.domain,
            plan: planId,
            mrr_cents: mrrCents,
            stripe_customer_id: stripeCustomerId,
            closing_rep_id: p.assigned_rep_id ?? session.user.id,
            status: "active",
          });
          await supabase.from("prospects").update({ stage: "closed_won", last_activity_at: new Date().toISOString() }).eq("id", p.id);
          await logActivity("stage_changed", { from: fromStage, to: "closed_won", plan: planId });
          toast.success("Client created — commission recorded (30% of MRR)");
          await load();
          onUpdated?.();
        }}
      />

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="border-zinc-800 bg-zinc-950">
          <DialogHeader>
            <DialogTitle className="text-zinc-100">Edit prospect</DialogTitle>
          </DialogHeader>
          <form
            className="space-y-2"
            onSubmit={(e) => {
              e.preventDefault();
              void saveEdit(new FormData(e.currentTarget));
            }}
          >
            <input type="hidden" name="_id" value={p.id} />
            <Label className="text-zinc-400">Company</Label>
            <Input name="company_name" defaultValue={p.company_name ?? ""} className="border-zinc-700 bg-zinc-900" />
            <Label className="text-zinc-400">Industry</Label>
            <Input name="industry" defaultValue={p.industry ?? ""} className="border-zinc-700 bg-zinc-900" />
            <Label className="text-zinc-400">City</Label>
            <Input name="city" defaultValue={p.city ?? ""} className="border-zinc-700 bg-zinc-900" />
            <Label className="text-zinc-400">Contact name</Label>
            <Input name="contact_name" defaultValue={p.contact_name ?? ""} className="border-zinc-700 bg-zinc-900" />
            <Label className="text-zinc-400">Contact email</Label>
            <Input name="contact_email" defaultValue={p.contact_email ?? ""} className="border-zinc-700 bg-zinc-900" />
            <Label className="text-zinc-400">Phone</Label>
            <Input name="phone" defaultValue={p.phone ?? ""} className="border-zinc-700 bg-zinc-900" />
            <DialogFooter>
              <Button type="submit" className="bg-emerald-600">
                Save
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
