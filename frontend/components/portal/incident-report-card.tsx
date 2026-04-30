"use client";

/**
 * One-click "Report an incident" card (priority list #34).
 *
 * Lives on the portal dashboard. Sends an authenticated POST through
 * ``portalApi.reportIncident`` which kicks off the full fan-out on the
 * backend (log row, SLA clock, OpenPhone SMS, Resend confirmation,
 * internal support-ticket mirror). On success we surface the case id
 * and SLA deadline inline so the client has a receipt without leaving
 * the page. A two-step click guard keeps an accidental tap from firing
 * the page — the button swaps to "Confirm" for 5s before submitting.
 */

import { useEffect, useRef, useState } from "react";
import toast from "react-hot-toast";
import { Button } from "@/components/ui/button";
import { createClient } from "@/lib/supabase/client";
import { portalApi } from "@/lib/api";

type IncidentResult = {
  case_id: string;
  reported_at: string;
  sla_deadline: string;
  sla_minutes: number;
  ceo_sms_status: string;
  client_email_status: string;
};

function formatDeadline(iso: string): string {
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return d.toLocaleString(undefined, {
      hour: "numeric",
      minute: "2-digit",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

export function IncidentReportCard() {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [description, setDescription] = useState("");
  const [result, setResult] = useState<IncidentResult | null>(null);
  const confirmTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Auto-cancel the "Confirm" state after 5 seconds so a forgotten click
  // doesn't stay armed indefinitely.
  useEffect(() => {
    if (!confirmOpen) return;
    confirmTimer.current = setTimeout(() => setConfirmOpen(false), 5000);
    return () => {
      if (confirmTimer.current) clearTimeout(confirmTimer.current);
    };
  }, [confirmOpen]);

  async function submit() {
    setBusy(true);
    try {
      const supabase = createClient();
      const {
        data: { session },
      } = await supabase.auth.getSession();
      if (!session?.access_token) {
        toast.error("Sign in again to report an incident.");
        return;
      }
      const res = await portalApi.reportIncident(
        { description: description.trim() },
        session.access_token,
      );
      setResult({
        case_id: res.case_id,
        reported_at: res.reported_at,
        sla_deadline: res.sla_deadline,
        sla_minutes: res.sla_minutes,
        ceo_sms_status: res.ceo_sms_status,
        client_email_status: res.client_email_status,
      });
      setConfirmOpen(false);
      setDescription("");
      toast.success(`Incident ${res.case_id} received — response team paged.`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not send incident report.");
    } finally {
      setBusy(false);
    }
  }

  if (result) {
    return (
      <div className="rounded-xl border border-red/30 bg-red/5 p-4">
        <h2 className="text-sm font-semibold text-red">Incident logged — {result.case_id}</h2>
        <p className="mt-2 text-sm text-ink-100">
          Our response team has been paged. First-response SLA is {result.sla_minutes} minutes —
          we will reach you by <span className="font-medium text-ink-0">{formatDeadline(result.sla_deadline)}</span>.
        </p>
        <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-ink-200">
          <dt>CEO SMS</dt>
          <dd className="font-mono text-ink-100">{result.ceo_sms_status}</dd>
          <dt>Client email</dt>
          <dd className="font-mono text-ink-100">{result.client_email_status}</dd>
        </dl>
        <p className="mt-3 text-xs text-ink-200">
          A confirmation email is on its way. If you need to add context (timeline, affected
          systems, suspicious emails), reply to that thread.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-red/30 bg-red/5 p-4">
      <h2 className="text-sm font-semibold text-red">Report a security incident</h2>
      <p className="mt-2 text-sm text-ink-200">
        Hit this if you suspect an active breach — suspicious logins, extortion emails, ransomware
        notes, unauthorized wire requests, anything unusual. One click pages our response team with
        an SLA clock, emails you a case id, and opens an internal ticket for our reps.
      </p>
      <label className="mt-3 block text-xs font-medium text-ink-0">
        Optional — what&apos;s happening?
        <textarea
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="e.g. 'Finance received a wire transfer email from our CEO but he never sent it.'"
          maxLength={4000}
          rows={3}
          className="mt-1 block w-full rounded-md border border-white/10 bg-ink-800 p-2 text-sm text-ink-0 placeholder:text-ink-200"
        />
      </label>
      <div className="mt-3 flex items-center gap-2">
        {!confirmOpen ? (
          <Button
            type="button"
            onClick={() => setConfirmOpen(true)}
            className="bg-red text-white hover:bg-red/90"
          >
            Report incident
          </Button>
        ) : (
          <>
            <Button
              type="button"
              disabled={busy}
              onClick={() => void submit()}
              className="bg-red text-white hover:bg-red/90"
            >
              {busy ? "Paging team…" : "Confirm — page the response team"}
            </Button>
            <Button
              type="button"
              disabled={busy}
              variant="ghost"
              onClick={() => setConfirmOpen(false)}
              className="text-ink-200 hover:text-ink-0"
            >
              Cancel
            </Button>
          </>
        )}
      </div>
    </div>
  );
}
