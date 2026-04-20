"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
import { ProspectScanResultsPanel } from "@/components/crm/prospect/prospect-scan-results";
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
import { provisionClientPortalAfterCloseWon } from "@/lib/crm/provision-portal";
import { cn } from "@/lib/utils";
import {
  Briefcase,
  Building2,
  Flame,
  Mail,
  MapPin,
  Phone,
  Star,
  User,
} from "lucide-react";

function timelineBorderForActivity(type: string): string {
  if (type === "stage_changed") return "border-l-emerald-500";
  if (type.includes("note")) return "border-l-blue-500";
  if (type.includes("call")) return "border-l-purple-500";
  if (type.includes("email")) return "border-l-amber-500";
  return "border-l-slate-600";
}

function OverviewField({
  icon,
  label,
  value,
  capitalize,
}: {
  icon: ReactNode;
  label: string;
  value: string | null | undefined;
  capitalize?: boolean;
}) {
  const raw = value?.trim() ? value : null;
  return (
    <div className="rounded-lg border border-crmBorder bg-crmSurface2 p-3">
      <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-slate-500">
        {icon}
        {label}
      </div>
      <p className={cn("mt-1 text-sm text-white", capitalize && raw && "capitalize")}>{raw ?? "—"}</p>
    </div>
  );
}

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
  const [scanPhase, setScanPhase] = useState<string | null>(null);
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
  const [emailSubject, setEmailSubject] = useState("");
  const [emailBody, setEmailBody] = useState("");
  const [sendingEmail, setSendingEmail] = useState(false);

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

  /** Clear persistent scanning state on this prospect row (e.g. after timeout). */
  const clearScanState = useCallback(
    async (prospectId: string) => {
      await supabase
        .from("prospects")
        .update({
          active_scan_job_id: null,
          scan_started_at: null,
          scan_last_polled_at: null,
          scan_trigger: null,
        })
        .eq("id", prospectId);
    },
    [supabase],
  );

  /** Poll an already-enqueued scan job until complete, then finalize. Reusable
   *  both for fresh scans and for resuming after a page reload. */
  const pollAndFinalize = useCallback(
    async (jobId: string, prospectId: string): Promise<void> => {
      const maxPolls = 400; // ~20 min at 3s
      for (let i = 0; i < maxPolls; i++) {
        setScanPhase(`Scanning… (~${(i + 1) * 3}s)`);
        await new Promise((r) => setTimeout(r, 3000));

        const pollRes = await fetch(`/api/crm/scan-job/${encodeURIComponent(jobId)}`);
        const pollRaw = await pollRes.text();
        let poll: { status?: string; error?: string; detail?: string } = {};
        try {
          if (pollRaw) poll = JSON.parse(pollRaw) as typeof poll;
        } catch {
          toast.error("Invalid response while polling scan status");
          await clearScanState(prospectId);
          return;
        }
        if (!pollRes.ok) {
          toast.error([poll.error, poll.detail].filter(Boolean).join(" — ") || "Poll failed");
          await clearScanState(prospectId);
          return;
        }
        if (poll.status === "failed") {
          toast.error(typeof poll.error === "string" ? poll.error : "Scan job failed");
          await clearScanState(prospectId);
          return;
        }
        if (poll.status === "complete") {
          setScanPhase("Saving results…");
          const finRes = await fetch("/api/crm/run-scan/finalize", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ jobId, prospectId }),
          });
          const finRaw = await finRes.text();
          let fin: { error?: string; detail?: string; score?: number; duplicate?: boolean } = {};
          try {
            if (finRaw) fin = JSON.parse(finRaw) as typeof fin;
          } catch {
            /* ignore */
          }
          if (!finRes.ok) {
            toast.error([fin.error, fin.detail].filter(Boolean).join(" — ") || "Could not save scan");
            await clearScanState(prospectId);
            return;
          }
          toast.success(fin.duplicate ? "Scan already saved" : `Scan complete — score ${fin.score ?? "—"}`);
          await load();
          onUpdated?.();
          return;
        }
      }
      toast.error("Scan timed out — worker may be busy. Try again or check Railway scanner worker.");
      await clearScanState(prospectId);
    },
    [clearScanState, load, onUpdated],
  );

  async function runScan() {
    if (!p) return;
    setScanning(true);
    setScanPhase("Starting…");
    try {
      const startRes = await fetch("/api/crm/run-scan", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prospectId: p.id }),
      });
      const startRaw = await startRes.text();
      let startJson: { error?: string; detail?: string; job_id?: string } = {};
      try {
        if (startRaw) startJson = JSON.parse(startRaw) as typeof startJson;
      } catch {
        /* ignore */
      }
      if (!startRes.ok) {
        const msg = [startJson.error, startJson.detail].filter(Boolean).join(" — ");
        const snippet =
          startRaw && !startRaw.trim().startsWith("{") ? startRaw.replace(/\s+/g, " ").slice(0, 180) : "";
        toast.error(
          msg ||
            `Scan failed (HTTP ${startRes.status})${snippet ? `: ${snippet}` : startRes.statusText ? ` — ${startRes.statusText}` : ""}`,
        );
        return;
      }
      const jobId = startJson.job_id;
      if (!jobId) {
        toast.error("No job_id returned — check API /api/scan/enqueue");
        return;
      }

      setScanPhase("Queued…");
      await pollAndFinalize(jobId, p.id);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Network error — could not reach scan service");
      if (p) {
        await clearScanState(p.id);
      }
    } finally {
      setScanning(false);
      setScanPhase(null);
    }
  }

  /** Resume an in-flight scan after a page reload. Fires once per prospect load. */
  const scanResumeRef = useRef<string | null>(null);
  useEffect(() => {
    if (!p) return;
    const jobId = p.active_scan_job_id;
    if (!jobId) return;
    // Only resume once per job_id to avoid infinite re-polling on list refreshes.
    if (scanResumeRef.current === jobId) return;

    // Watchdog: if it's been stuck for > 20 min, assume worker crashed.
    const startedMs = p.scan_started_at ? new Date(p.scan_started_at).getTime() : 0;
    const ageSec = startedMs ? (Date.now() - startedMs) / 1000 : Number.POSITIVE_INFINITY;
    if (ageSec > 20 * 60) {
      void clearScanState(p.id).then(() => void load());
      return;
    }

    scanResumeRef.current = jobId;
    setScanning(true);
    const elapsed = Math.max(0, Math.round(ageSec));
    setScanPhase(`Resuming… (~${elapsed}s so far)`);
    void (async () => {
      try {
        await pollAndFinalize(jobId, p.id);
      } finally {
        setScanning(false);
        setScanPhase(null);
      }
    })();
  }, [p, clearScanState, pollAndFinalize, load]);

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

  async function sendEmail(e: React.FormEvent) {
    e.preventDefault();
    if (!emailSubject.trim() || !emailBody.trim() || !p?.contact_email) return;
    setSendingEmail(true);
    try {
      await supabase.from("prospect_email_events").insert({
        prospect_id: prospectId,
        subject: emailSubject.trim(),
        sent_at: new Date().toISOString(),
        sequence_step: null,
        source: "manual",
        metadata: { body: emailBody.trim(), sent_by: session?.user?.id },
      });
      await logActivity("email_sent", { subject: emailSubject.trim() });
      toast.success("Email logged");
      setEmailSubject("");
      setEmailBody("");
      await load();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Failed to log email");
    } finally {
      setSendingEmail(false);
    }
  }

  if (loading || !p) {
    return (
      <div className="flex min-h-[200px] items-center justify-center text-slate-500">
        <div className="h-8 w-8 animate-spin rounded-full border-2 border-crmBorder border-t-emerald-500" />
      </div>
    );
  }

  const title = variant === "page" ? "text-2xl" : "text-xl";
  const hasVulnProfile = !!(p.vulnerability_found && String(p.vulnerability_found).trim());

  return (
    <div className="flex h-full flex-col">
      {hasVulnProfile && (
        <div className="mb-4 rounded-xl border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
          <p className="font-semibold uppercase tracking-wide text-amber-400">Vulnerability found</p>
          <p className="mt-1 text-amber-50/95">
            {p.vulnerability_type ? `${p.vulnerability_type}: ` : ""}
            {p.vulnerability_found}
          </p>
        </div>
      )}

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
                <Link key={peer.id} href={`/crm/prospects/${peer.id}`} className="text-emerald-700 underline-offset-2 hover:underline">
                  {peer.company_name ?? peer.id.slice(0, 8)}…
                </Link>
              ))}
            </div>
          )}
          {privileged && domainPeers.length > 0 && (
            <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-amber-500/20 pt-2">
              <span className="text-xs text-amber-200/80">Mark this prospect as duplicate of:</span>
              <select
                className="rounded border border-amber-500/40 bg-[#0d0d14] px-2 py-1 text-xs text-slate-200"
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
        <div className="mb-3 rounded-lg border border-crmBorder bg-crmSurface px-3 py-2 text-sm text-slate-200">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
            <span className="text-slate-500">Other prospects on {p.domain}:</span>
            {domainPeers.map((peer) => (
              <Link key={peer.id} href={`/crm/prospects/${peer.id}`} className="text-emerald-400 underline-offset-2 hover:underline">
                {peer.company_name ?? peer.id.slice(0, 8)}…
              </Link>
            ))}
          </div>
          {privileged && (
            <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-crmBorder pt-2">
              <span className="text-xs text-slate-500">Mark this prospect as duplicate of:</span>
              <select
                className="rounded border border-crmBorder bg-crmSurface2 px-2 py-1 text-xs text-white"
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
                className="h-7 border-crmBorder bg-crmSurface2 text-xs text-slate-200"
                disabled={!duplicateLinkTarget}
                onClick={() => void linkAsDuplicateOf()}
              >
                Link
              </Button>
            </div>
          )}
        </div>
      )}

      <div className="rounded-xl border border-crmBorder bg-crmSurface p-4 shadow-lg lg:p-6">
        <div className="flex flex-col gap-4 border-b border-crmBorder pb-4 lg:flex-row lg:items-start">
          <div className="flex flex-1 gap-4">
            <HawkScoreRing score={p.hawk_score} />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                {variant === "drawer" ? (
                  <Link href={`/crm/prospects/${p.id}`} className={cn(title, "font-semibold text-white underline-offset-4 hover:underline")}>
                    {p.company_name ?? p.domain}
                  </Link>
                ) : (
                  <h1 className={cn(title, "font-semibold text-white")}>{p.company_name ?? p.domain}</h1>
                )}
                <a href={`https://${p.domain}`} target="_blank" rel="noreferrer" className="text-sm text-emerald-400 hover:underline">
                  {p.domain}
                </a>
              </div>
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <select
                  className="rounded-md border border-crmBorder bg-crmSurface2 px-2 py-1 text-xs text-white"
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
                  className={cn(
                    "inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs",
                    p.is_hot ? "border-rose-500/60 text-rose-400" : "border-crmBorder text-slate-400 hover:text-slate-200",
                  )}
                >
                  {p.is_hot ? (
                    <>
                      <Flame className="h-3.5 w-3.5" />
                      Hot
                    </>
                  ) : (
                    <>
                      <Star className="h-3.5 w-3.5" />
                      Mark hot
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <div className="flex flex-col items-end gap-1.5">
              <Button
                size="sm"
                className={cn(
                  "relative overflow-hidden transition-all",
                  scanning
                    ? "cursor-not-allowed bg-gradient-to-r from-amber-600 via-amber-500 to-orange-500 text-white shadow-lg shadow-amber-600/40 ring-2 ring-amber-300/60 ring-offset-2 ring-offset-crmSurface"
                    : "bg-emerald-600 text-white hover:bg-emerald-500 hover:shadow-md hover:shadow-emerald-600/30",
                )}
                onClick={() => void runScan()}
                disabled={scanning}
              >
                {scanning && (
                  <span
                    aria-hidden
                    className="absolute inset-0 -translate-x-full animate-shimmer bg-gradient-to-r from-transparent via-white/30 to-transparent"
                  />
                )}
                <span className="relative flex items-center gap-2">
                  {scanning ? (
                    <>
                      <svg className="h-3.5 w-3.5 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden>
                        <circle cx="12" cy="12" r="10" stroke="currentColor" strokeOpacity="0.25" strokeWidth="4" />
                        <path
                          d="M22 12a10 10 0 0 1-10 10"
                          stroke="currentColor"
                          strokeWidth="4"
                          strokeLinecap="round"
                        />
                      </svg>
                      Scanning…
                    </>
                  ) : (
                    <>
                      <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden>
                        <circle cx="11" cy="11" r="8" />
                        <path d="m21 21-4.3-4.3" />
                      </svg>
                      Run scan
                    </>
                  )}
                </span>
              </Button>
              {scanning && scanPhase && (
                <span className="max-w-[220px] rounded-md border border-amber-400/30 bg-amber-400/10 px-2 py-0.5 text-right text-[10px] font-medium text-amber-200/90">
                  {scanPhase}
                </span>
              )}
            </div>
            <Button size="sm" variant="outline" className="border-crmBorder bg-crmSurface2 text-slate-200" onClick={() => setLogOpen(true)}>
              Log call
            </Button>
            <Button size="sm" variant="outline" className="border-crmBorder bg-crmSurface2 text-slate-200" onClick={() => setBookOpen(true)}>
              Book call
            </Button>
            <Button size="sm" variant="outline" className="border-crmBorder bg-crmSurface2 text-slate-200" asChild>
              <Link href={`/crm/prospects/${prospectId}/call-mode`}>Call mode</Link>
            </Button>
            <Button size="sm" variant="outline" className="border-crmBorder bg-crmSurface2 text-slate-200" onClick={() => setEditOpen(true)}>
              Edit
            </Button>
            <details className="relative">
              <summary className="cursor-pointer list-none rounded-md border border-crmBorder bg-crmSurface2 px-3 py-1.5 text-sm text-slate-200 hover:bg-white/5">
                More
              </summary>
              <div className="absolute right-0 z-10 mt-1 w-52 rounded-lg border border-crmBorder bg-crmSurface py-1 shadow-xl">
                <button
                  type="button"
                  className="block w-full px-3 py-2 text-left text-sm text-slate-200 hover:bg-white/5"
                  onClick={() => {
                    void navigator.clipboard.writeText(`${typeof window !== "undefined" ? window.location.origin : ""}/crm/prospects/${p.id}`);
                    toast.success("Link copied");
                  }}
                >
                  Copy profile link
                </button>
              {canReassign && (
                <div className="border-t border-crmBorder px-3 py-2 text-xs text-slate-400">
                  Reassign
                  <select
                    className="mt-1 w-full rounded border border-crmBorder bg-crmSurface2 px-2 py-1 text-white"
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
              <button
                type="button"
                className="block w-full px-3 py-2 text-left text-sm text-rose-400 hover:bg-white/5"
                onClick={() => setLostOpen(true)}
              >
                Mark lost
              </button>
              <button type="button" className="block w-full px-3 py-2 text-left text-sm text-slate-200 hover:bg-white/5" onClick={() => setWonOpen(true)}>
                Convert to client
              </button>
            </div>
          </details>
          {variant === "drawer" && onClose && (
            <Button size="sm" variant="ghost" className="text-slate-400 hover:bg-white/5 hover:text-white" onClick={onClose}>
              Close
            </Button>
          )}
        </div>
      </div>
      </div>

      <Tabs defaultValue="overview" className="mt-4 flex min-h-0 flex-1 flex-col">
        <TabsList className="h-auto min-h-10 w-full shrink-0 flex-wrap justify-start gap-1 overflow-x-auto rounded-xl border border-crmBorder bg-crmSurface2 p-1 text-slate-500">
          <TabsTrigger
            value="overview"
            className="rounded-lg border border-transparent text-slate-500 data-[state=active]:border-emerald-500/30 data-[state=active]:bg-emerald-500/15 data-[state=active]:text-emerald-400 data-[state=active]:shadow-none"
          >
            Overview
          </TabsTrigger>
          <TabsTrigger
            value="timeline"
            className="rounded-lg border border-transparent text-slate-500 data-[state=active]:border-emerald-500/30 data-[state=active]:bg-emerald-500/15 data-[state=active]:text-emerald-400 data-[state=active]:shadow-none"
          >
            Timeline
          </TabsTrigger>
          <TabsTrigger
            value="scans"
            className="rounded-lg border border-transparent text-slate-500 data-[state=active]:border-emerald-500/30 data-[state=active]:bg-emerald-500/15 data-[state=active]:text-emerald-400 data-[state=active]:shadow-none"
          >
            Scan results
          </TabsTrigger>
          <TabsTrigger
            value="emails"
            className="rounded-lg border border-transparent text-slate-500 data-[state=active]:border-emerald-500/30 data-[state=active]:bg-emerald-500/15 data-[state=active]:text-emerald-400 data-[state=active]:shadow-none"
          >
            Emails
          </TabsTrigger>
          <TabsTrigger
            value="notes"
            className="rounded-lg border border-transparent text-slate-500 data-[state=active]:border-emerald-500/30 data-[state=active]:bg-emerald-500/15 data-[state=active]:text-emerald-400 data-[state=active]:shadow-none"
          >
            Notes
          </TabsTrigger>
          <TabsTrigger
            value="files"
            className="rounded-lg border border-transparent text-slate-500 data-[state=active]:border-emerald-500/30 data-[state=active]:bg-emerald-500/15 data-[state=active]:text-emerald-400 data-[state=active]:shadow-none"
          >
            Files
          </TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="min-h-[200px] space-y-3 text-sm">
          <div className="grid gap-3 sm:grid-cols-2">
            <OverviewField icon={<Briefcase className="h-4 w-4 text-emerald-400" />} label="Industry" value={p.industry} />
            <OverviewField icon={<MapPin className="h-4 w-4 text-emerald-400" />} label="City" value={p.city} />
            <OverviewField icon={<User className="h-4 w-4 text-emerald-400" />} label="Contact" value={p.contact_name} />
            <OverviewField icon={<Mail className="h-4 w-4 text-emerald-400" />} label="Email" value={p.contact_email} />
            <OverviewField icon={<Phone className="h-4 w-4 text-emerald-400" />} label="Phone" value={p.phone} />
            <OverviewField icon={<Building2 className="h-4 w-4 text-emerald-400" />} label="Source" value={p.source ? String(p.source) : null} capitalize />
          </div>
          <p className="text-xs text-slate-500">Apollo enrichment & deal value: Phase 7+.</p>
        </TabsContent>

        <TabsContent value="timeline" className="min-h-[240px] max-h-[50vh] space-y-3 overflow-y-auto pr-1 text-sm">
          {activities.length === 0 && <p className="text-slate-500">No events yet.</p>}
          {activities.map((a) => (
            <div
              key={a.id}
              className={cn(
                "rounded-lg border border-y border-r border-crmBorder bg-crmSurface2 py-2 pl-3 pr-3 border-l-4",
                timelineBorderForActivity(a.type),
              )}
            >
              <div className={cn("text-xs font-medium", activityColor(a.type))}>{activityLabel(a.type)}</div>
              <div className="text-[11px] text-slate-500">{new Date(a.created_at).toLocaleString()}</div>
              {a.notes && <p className="mt-1 text-slate-300">{a.notes}</p>}
              {a.metadata != null &&
                typeof a.metadata === "object" &&
                Object.keys(a.metadata as Record<string, unknown>).length > 0 && (
                  <pre className="mt-1 max-h-24 overflow-auto text-[10px] text-slate-500">{JSON.stringify(a.metadata, null, 2)}</pre>
                )}
            </div>
          ))}
        </TabsContent>

        <TabsContent value="scans" className="min-h-[200px] space-y-4 text-sm">
          {scans.length === 0 && <p className="text-slate-500">No scans yet. Run a scan from the header.</p>}
          {scans.map((s) => (
            <div key={s.id} className="rounded-lg border border-crmBorder bg-crmSurface2 p-4 shadow-lg">
              <ProspectScanResultsPanel
                scan={s}
                scanId={s.id}
                prospectId={prospectId}
                companyName={p?.company_name ?? null}
                domain={p?.domain ?? ""}
                industry={p?.industry ?? s.industry ?? null}
                onVerified={() => void load()}
              />
            </div>
          ))}
        </TabsContent>

        <TabsContent value="emails" className="min-h-[120px] space-y-4 text-sm">
          {p.contact_email && (
            <form onSubmit={sendEmail} className="space-y-2 rounded-lg border border-crmBorder bg-crmSurface2 p-3 shadow-lg">
              <div className="flex items-center gap-2 text-xs text-slate-500">
                <span>To:</span>
                <span className="text-slate-200">{p.contact_email}</span>
              </div>
              <Input
                placeholder="Subject"
                className="border-crmBorder bg-crmSurface text-sm text-white placeholder:text-slate-500"
                value={emailSubject}
                onChange={(e) => setEmailSubject(e.target.value)}
              />
              <textarea
                className="w-full rounded-md border border-crmBorder bg-crmSurface px-3 py-2 text-sm text-white placeholder:text-slate-500"
                rows={4}
                placeholder="Compose your email…"
                value={emailBody}
                onChange={(e) => setEmailBody(e.target.value)}
              />
              <div className="flex justify-end">
                <Button type="submit" size="sm" className="bg-emerald-600" disabled={sendingEmail || !emailSubject.trim() || !emailBody.trim()}>
                  {sendingEmail ? "Sending…" : "Log & send"}
                </Button>
              </div>
            </form>
          )}
          {!p.contact_email && (
            <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
              Add a contact email to this prospect to enable inline email composition.
            </p>
          )}
          {emailEvents.length === 0 && (
            <p className="text-slate-500">
              No email events yet. POST to the API webhook (see{" "}
              <Link href="/crm/charlotte" className="text-emerald-400 hover:underline">
                Charlotte
              </Link>
              ) or connect Smartlead with <code className="text-slate-500">X-CRM-Webhook-Secret</code>.
            </p>
          )}
          {emailEvents.map((ev) => {
            const src = ev.source ?? "webhook";
            const meta = ev.metadata && typeof ev.metadata === "object" && Object.keys(ev.metadata).length > 0;
            return (
              <div key={ev.id} className="rounded-lg border border-crmBorder bg-crmSurface2 px-3 py-2 shadow-sm">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <div className="font-medium text-white">{ev.subject ?? "(No subject)"}</div>
                  <span className="rounded bg-crmSurface px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-slate-400">{src}</span>
                </div>
                {ev.external_id && <div className="mt-1 font-mono text-[10px] text-slate-500">id: {ev.external_id}</div>}
                <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-slate-400">
                  {ev.sequence_step != null && <span>Step {ev.sequence_step}</span>}
                  {ev.sent_at && (
                    <span className="inline-flex items-center gap-1.5">
                      <span className="h-2 w-2 shrink-0 rounded-full bg-blue-500" />
                      Sent {new Date(ev.sent_at).toLocaleString()}
                    </span>
                  )}
                  {ev.opened_at && (
                    <span className="inline-flex items-center gap-1.5">
                      <span className="h-2 w-2 shrink-0 rounded-full bg-amber-400" />
                      Opened {new Date(ev.opened_at).toLocaleString()}
                    </span>
                  )}
                  {ev.clicked_at && (
                    <span className="inline-flex items-center gap-1.5">
                      <span className="h-2 w-2 shrink-0 rounded-full bg-slate-400" />
                      Clicked {new Date(ev.clicked_at).toLocaleString()}
                    </span>
                  )}
                  {ev.replied_at && (
                    <span className="inline-flex items-center gap-1.5">
                      <span className="h-2 w-2 shrink-0 rounded-full bg-emerald-500" />
                      Replied {new Date(ev.replied_at).toLocaleString()}
                    </span>
                  )}
                </div>
                {meta && (
                  <pre className="mt-2 max-h-28 overflow-auto text-[10px] text-slate-500">{JSON.stringify(ev.metadata, null, 2)}</pre>
                )}
              </div>
            );
          })}
        </TabsContent>

        <TabsContent value="notes" className="min-h-[200px] space-y-3">
          <div className="space-y-2">
            <textarea
              className="w-full rounded-md border border-crmBorder bg-crmSurface2 px-3 py-2 text-sm text-white placeholder:text-slate-500"
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
                <li key={n.id} className="rounded-lg border border-crmBorder bg-crmSurface2 px-3 py-2 text-sm text-slate-200 shadow-sm">
                  {isEditing ? (
                    <div className="space-y-2">
                      <textarea
                        className="w-full rounded-md border border-crmBorder bg-crmSurface px-3 py-2 text-sm text-white"
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
                          className="border-slate-200"
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
                      <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-slate-600">
                        <span>
                          {new Date(n.created_at).toLocaleString()}
                          {n.updated_at !== n.created_at && (
                            <span className="ml-1 text-slate-500">· edited {new Date(n.updated_at).toLocaleString()}</span>
                          )}
                        </span>
                        {isAuthor && (
                          <span className="flex gap-2">
                            <button
                              type="button"
                              className="text-emerald-600 hover:underline"
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
              <Label className="text-xs text-slate-500">Title</Label>
              <Input
                className="border-crmBorder bg-crmSurface2 text-white"
                value={fileTitle}
                onChange={(e) => setFileTitle(e.target.value)}
              />
            </div>
            <div className="flex-[2]">
              <Label className="text-xs text-slate-500">URL</Label>
              <Input
                className="border-crmBorder bg-crmSurface2 text-white placeholder:text-slate-500"
                value={fileUrl}
                onChange={(e) => setFileUrl(e.target.value)}
                placeholder="https://…"
              />
            </div>
            <Button type="submit" className="bg-emerald-600 text-white hover:bg-emerald-500">
              Add
            </Button>
          </form>
          <ul className="space-y-2">
            {files.map((f) => (
              <li key={f.id}>
                <a href={f.file_url} target="_blank" rel="noreferrer" className="text-emerald-400 hover:underline">
                  {f.title}
                </a>
                <span className="ml-2 text-xs text-slate-500">{new Date(f.created_at).toLocaleDateString()}</span>
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
        accessToken={session?.access_token ?? null}
        prospectDomain={p.domain}
        onConfirm={async ({ planId, mrrCents, stripeCustomerId, commissionDeferred }) => {
          if (!session?.user?.id) return;
          const fromStage = p.stage;
          const { data: newClient, error: clientErr } = await supabase
            .from("clients")
            .insert({
              prospect_id: p.id,
              company_name: p.company_name,
              domain: p.domain,
              plan: planId,
              mrr_cents: mrrCents,
              stripe_customer_id: stripeCustomerId,
              closing_rep_id: p.assigned_rep_id ?? session.user.id,
              status: "active",
              commission_deferred: commissionDeferred,
            })
            .select("id")
            .single();
          if (clientErr || !newClient?.id) {
            toast.error(clientErr?.message ?? "Could not create client");
            return;
          }
          await supabase.from("prospects").update({ stage: "closed_won", last_activity_at: new Date().toISOString() }).eq("id", p.id);
          await logActivity("stage_changed", { from: fromStage, to: "closed_won", plan: planId });
          const baseMsg = commissionDeferred
            ? "Client created — commission will post when Stripe payment clears"
            : "Client created — commission recorded (30% of MRR)";
          const prov = await provisionClientPortalAfterCloseWon(newClient.id);
          if (prov.ok) {
            const portalNote =
              prov.idempotent && !prov.invited_email
                ? " Portal already linked."
                : prov.invited_email
                  ? ` Portal invite sent to ${prov.invited_email}.`
                  : " Portal invite sent.";
            toast.success(baseMsg + portalNote);
          } else {
            toast.success(baseMsg);
            toast.error(`Portal setup: ${prov.detail}`);
          }
          await load();
          onUpdated?.();
        }}
      />

      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="border-crmBorder bg-crmSurface text-slate-200">
          <DialogHeader>
            <DialogTitle className="text-white">Edit prospect</DialogTitle>
          </DialogHeader>
          <form
            className="space-y-2"
            onSubmit={(e) => {
              e.preventDefault();
              void saveEdit(new FormData(e.currentTarget));
            }}
          >
            <input type="hidden" name="_id" value={p.id} />
            <Label className="text-slate-500">Company</Label>
            <Input name="company_name" defaultValue={p.company_name ?? ""} className="border-crmBorder bg-crmSurface2 text-white" />
            <Label className="text-slate-500">Industry</Label>
            <Input name="industry" defaultValue={p.industry ?? ""} className="border-crmBorder bg-crmSurface2 text-white" />
            <Label className="text-slate-500">City</Label>
            <Input name="city" defaultValue={p.city ?? ""} className="border-crmBorder bg-crmSurface2 text-white" />
            <Label className="text-slate-500">Contact name</Label>
            <Input name="contact_name" defaultValue={p.contact_name ?? ""} className="border-crmBorder bg-crmSurface2 text-white" />
            <Label className="text-slate-500">Contact email</Label>
            <Input name="contact_email" defaultValue={p.contact_email ?? ""} className="border-crmBorder bg-crmSurface2 text-white" />
            <Label className="text-slate-500">Phone</Label>
            <Input name="phone" defaultValue={p.phone ?? ""} className="border-crmBorder bg-crmSurface2 text-white" />
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
