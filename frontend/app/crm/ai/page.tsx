"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { CRM_API_BASE_URL } from "@/lib/crm/api-url";
import { PipelineStatusTracker } from "@/components/crm/aria/pipeline-status-tracker";
import { PipelineRunTrigger } from "@/components/crm/aria/pipeline-run-trigger";
import { InlineDownloadButton } from "@/components/crm/aria/inline-download-button";
import { ConfirmationCard } from "@/components/crm/aria/confirmation-card";
import { InlineChart, type ChartData } from "@/components/crm/aria/inline-chart";
import { VoiceInput } from "@/components/crm/aria/voice-input";
import { VoiceOutput } from "@/components/crm/aria/voice-output";
import { FileUpload } from "@/components/crm/aria/file-upload";

interface ChatMessage {
  id?: string;
  role: "user" | "assistant" | "system";
  content: string;
  function_name?: string;
  function_result?: string;
  /** Pipeline run ID — renders live status tracker */
  pipeline_run_id?: string;
  /** Download URL for inline PDF report button */
  download_url?: string;
  download_filename?: string;
  /** Confirmation card */
  confirmation?: {
    title: string;
    description: string;
    action: () => Promise<void>;
  };
  /** Chart data for inline visualization */
  chart_data?: ChartData;
}

interface Briefing {
  id: string;
  briefing_date: string;
  content: string;
  created_at: string;
}

interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

const BLOCKED_ROLES = ["va", "client"];
const PIPELINE_ALLOWED_ROLES = ["ceo"];
const PIPELINE_ALLOWED_ROLE_TYPES = ["ceo", "va_manager"];

export default function AiCommandCenterPage() {
  const { profile, session } = useCrmAuth();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [loadingConvs, setLoadingConvs] = useState(true);
  const [showPipelineTrigger, setShowPipelineTrigger] = useState(false);
  const [unreadBriefings, setUnreadBriefings] = useState<Briefing[]>([]);
  const [dismissedBriefingIds, setDismissedBriefingIds] = useState<Set<string>>(new Set());
  const messagesScrollRef = useRef<HTMLDivElement>(null);

  const canRunPipeline = profile && (
    PIPELINE_ALLOWED_ROLES.includes(profile.role || "") ||
    PIPELINE_ALLOWED_ROLE_TYPES.includes(profile.role_type || "")
  );

  const headers = useMemo((): Record<string, string> => {
    if (!session?.access_token) return {};
    return {
      Authorization: `Bearer ${session.access_token}`,
      "Content-Type": "application/json",
    };
  }, [session?.access_token]);

  /* ── Load conversations ──────────────────────────────────────────────── */

  const loadConversations = useCallback(async () => {
    if (!session?.access_token) return;
    try {
      const r = await fetch(`${CRM_API_BASE_URL}/api/crm/ai/conversations`, {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (r.ok) {
        const data = await r.json();
        setConversations(Array.isArray(data) ? data : (data.conversations || []));
      }
    } catch (err) {
      console.error("Failed to load conversations:", err);
    }
    setLoadingConvs(false);
  }, [session?.access_token]);

  useEffect(() => {
    void loadConversations();
  }, [loadConversations]);

  /* ── Load unread briefings ──────────────────────────────────────────── */

  const loadUnreadBriefings = useCallback(async () => {
    if (!session?.access_token) return;
    try {
      const r = await fetch(`${CRM_API_BASE_URL}/api/crm/ai/briefings/unread`, {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (r.ok) {
        const data = await r.json();
        setUnreadBriefings(Array.isArray(data) ? data : []);
      }
    } catch (err) {
      console.error("Failed to load briefings:", err);
    }
  }, [session?.access_token]);

  useEffect(() => {
    void loadUnreadBriefings();
  }, [loadUnreadBriefings]);

  async function dismissBriefing(briefingId: string) {
    setDismissedBriefingIds((prev) => new Set(prev).add(briefingId));
    if (!session?.access_token) return;
    try {
      await fetch(`${CRM_API_BASE_URL}/api/crm/ai/briefings/${briefingId}/read`, {
        method: "POST",
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
    } catch (err) {
      console.error("Failed to mark briefing as read:", err);
    }
  }

  const visibleBriefings = unreadBriefings.filter((b) => !dismissedBriefingIds.has(b.id));

  /* ── Load messages for active conversation ──────────────────────────── */

  const loadMessages = useCallback(async (convId: string) => {
    if (!session?.access_token) return;
    try {
      const r = await fetch(`${CRM_API_BASE_URL}/api/crm/ai/conversations/${convId}/messages`, {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (r.ok) {
        const data = await r.json();
        setMessages(Array.isArray(data) ? data : (data.messages || []));
      }
    } catch (err) {
      console.error("Failed to load messages:", err);
    }
  }, [session?.access_token]);

  function selectConversation(convId: string) {
    setActiveConvId(convId);
    void loadMessages(convId);
  }

  /* ── Create new conversation ─────────────────────────────────────────── */

  async function createConversation() {
    if (!session?.access_token) return;
    try {
      const r = await fetch(`${CRM_API_BASE_URL}/api/crm/ai/conversations`, {
        method: "POST",
        headers,
        body: JSON.stringify({ title: "New conversation" }),
      });
      if (r.ok) {
        const data = await r.json();
        setActiveConvId(data.id);
        setMessages([]);
        void loadConversations();
      }
    } catch (err) {
      console.error("Failed to create conversation:", err);
    }
  }

  /* ── Pipeline run handlers ──────────────────────────────────────────── */

  function handlePipelineStarted(runId: string, vertical: string, location: string) {
    setShowPipelineTrigger(false);
    setMessages((prev) => [
      ...prev,
      { role: "user", content: `Run outbound pipeline: ${vertical} in ${location}` },
      {
        role: "assistant",
        content: `Pipeline started for ${vertical} in ${location}.`,
        pipeline_run_id: runId,
        function_name: "run_outbound_pipeline",
      },
    ]);
  }

  async function handlePipelineComplete(runId: string) {
    if (!session?.access_token) return;
    try {
      const r = await fetch(`${CRM_API_BASE_URL}/api/crm/aria/pipeline/${runId}/report`, {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (r.ok) {
        const data = await r.json();
        if (data.download_url) {
          setMessages((prev) => [
            ...prev,
            {
              role: "assistant",
              content: "Pipeline complete. Download your report below.",
              download_url: data.download_url,
              download_filename: data.filename || `aria-pipeline-${runId.slice(0, 8)}.pdf`,
            },
          ]);
        }
      }
    } catch {
      // Report generation failed silently
    }
  }

  /* ── Send message ────────────────────────────────────────────────────── */

  async function sendMessage() {
    if (!input.trim() || sending || !session?.access_token) return;
    const userMessage = input;
    setInput("");
    setSending(true);

    const userMsg: ChatMessage = { role: "user", content: userMessage };
    setMessages((prev) => [...prev, userMsg]);

    try {
      // Auto-create conversation if none exists
      let convId = activeConvId;
      if (!convId) {
        const cr = await fetch(`${CRM_API_BASE_URL}/api/crm/ai/conversations`, {
          method: "POST",
          headers,
          body: JSON.stringify({ title: "New conversation" }),
        });
        if (cr.ok) {
          const cd = await cr.json();
          convId = cd.id;
          setActiveConvId(convId);
          void loadConversations();
        } else {
          const errData = await cr.json().catch(() => ({ detail: `HTTP ${cr.status}` }));
          const errMsg = typeof errData?.detail === "string" ? errData.detail : `HTTP ${cr.status}`;
          setMessages((prev) => [...prev, { role: "assistant", content: `Failed to start conversation: ${errMsg}` }]);
          setSending(false);
          return;
        }
      }

      const r = await fetch(`${CRM_API_BASE_URL}/api/crm/ai/chat`, {
        method: "POST",
        headers,
        body: JSON.stringify({
          conversation_id: convId,
          content: userMessage,
        }),
      });

      if (r.ok) {
        const data = await r.json();
        if (!activeConvId && data.conversation_id) {
          setActiveConvId(data.conversation_id);
          void loadConversations();
        }
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: data.reply,
            function_name: data.function_called,
            function_result: data.function_result ? JSON.stringify(data.function_result) : undefined,
            chart_data: data.chart_data || undefined,
          },
        ]);
      } else {
        const err = await r.json().catch(() => ({ detail: "Unknown error" }));
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: err.detail || "Something went wrong. Please try again." },
        ]);
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Connection error. Please try again." },
      ]);
    }
    setSending(false);
  }

  useEffect(() => {
    const el = messagesScrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
  }, [messages, sending]);

  /* ── Access control ──────────────────────────────────────────────────── */

  if (profile && BLOCKED_ROLES.includes(profile.role || "")) {
    return (
      <div className="flex items-center justify-center p-12">
        <p className="text-slate-500">The AI Command Center is not available for your role.</p>
      </div>
    );
  }

  return (
    <div className="flex h-full max-h-full min-h-0 w-full min-w-0 flex-1 flex-col overflow-hidden rounded-2xl border border-crmBorder bg-crmBg shadow-xl shadow-black/20 lg:flex-row lg:items-stretch">
      <aside className="hidden min-h-0 w-72 shrink-0 flex-col overflow-hidden border-b border-crmBorder bg-crmSurface lg:flex lg:h-full lg:max-h-full lg:border-b-0 lg:border-r">
        <div className="flex shrink-0 items-center justify-between border-b border-crmBorder px-4 py-4">
          <div>
            <h2 className="text-sm font-semibold text-white">Conversations</h2>
            <p className="mt-0.5 text-[11px] text-slate-500">
              {conversations.length} total
            </p>
          </div>
          <button
            type="button"
            onClick={() => void createConversation()}
            className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-semibold text-white shadow shadow-emerald-900/30 transition hover:bg-emerald-500"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            New
          </button>
        </div>
        <div className="min-h-0 flex-1 space-y-1 overflow-y-auto overscroll-contain p-2">
          {loadingConvs ? (
            <div className="flex justify-center py-6">
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-crmBorder border-t-emerald-500" />
            </div>
          ) : conversations.length === 0 ? (
            <div className="px-3 py-8 text-center">
              <p className="text-xs text-slate-500">No conversations yet.</p>
              <p className="mt-1 text-[11px] text-slate-600">Click “New” to start chatting with ARIA.</p>
            </div>
          ) : (
            conversations.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => selectConversation(c.id)}
                className={`group w-full rounded-xl px-3 py-2.5 text-left text-sm transition ${
                  activeConvId === c.id
                    ? "border border-emerald-500/30 bg-emerald-500/10 font-medium text-emerald-300 shadow-sm shadow-emerald-900/10"
                    : "border border-transparent text-slate-400 hover:border-crmBorder hover:bg-white/5 hover:text-slate-100"
                }`}
              >
                <p className="truncate">{c.title}</p>
                <p className="mt-0.5 text-[11px] text-slate-500">
                  {new Date(c.updated_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}
                </p>
              </button>
            ))
          )}
        </div>
      </aside>

      <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden lg:min-h-0 lg:h-full">
        <div className="flex shrink-0 items-center justify-between gap-3 border-b border-crmBorder bg-gradient-to-r from-crmSurface via-crmSurface to-crmSurface2 px-5 py-3.5">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-emerald-500/15 ring-1 ring-emerald-500/30">
              <svg className="h-5 w-5 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.8}
                  d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
                />
              </svg>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-sm font-semibold text-white">ARIA</h1>
                <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-medium text-emerald-400 ring-1 ring-emerald-500/30">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-emerald-400" />
                  Online
                </span>
              </div>
              <p className="mt-0.5 text-[11px] text-slate-400">
                {profile?.role === "ceo"
                  ? "Full access — all commands available"
                  : `${profile?.role_type || profile?.role || ""} access`}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => void createConversation()}
            className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-emerald-500 lg:hidden"
          >
            + New
          </button>
        </div>

        <div
          ref={messagesScrollRef}
          className="min-h-0 flex-1 overflow-y-auto overflow-x-hidden overscroll-contain bg-crmBg px-4 py-6 sm:px-6"
        >
          <div className="mx-auto flex min-h-full max-w-3xl flex-col gap-4">
            {/* Unread briefing banner */}
            {visibleBriefings.map((briefing) => (
              <div key={briefing.id} className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-4 py-3">
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    <p className="mb-1 text-xs font-semibold text-amber-400">
                      Briefing —{" "}
                      {new Date(briefing.briefing_date + "T00:00:00").toLocaleDateString("en-US", {
                        weekday: "long",
                        month: "short",
                        day: "numeric",
                      })}
                    </p>
                    <div className="max-h-60 overflow-y-auto whitespace-pre-wrap text-sm leading-relaxed text-slate-200">
                      {briefing.content}
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => void dismissBriefing(briefing.id)}
                    className="flex-shrink-0 rounded-lg px-2 py-1 text-xs font-medium text-amber-300 transition hover:bg-amber-500/10"
                  >
                    Dismiss
                  </button>
                </div>
              </div>
            ))}
            {messages.length === 0 && (
              <div className="flex flex-1 flex-col items-center justify-center py-10 text-center">
                <div className="mx-auto mb-5 flex h-20 w-20 items-center justify-center rounded-2xl bg-gradient-to-br from-emerald-500/25 to-emerald-600/10 ring-1 ring-emerald-500/40">
                  <svg className="h-10 w-10 text-emerald-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={1.5}
                      d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
                    />
                  </svg>
                </div>
                <h2 className="text-xl font-semibold tracking-tight text-white">Meet ARIA</h2>
                <p className="mt-1 text-xs font-medium uppercase tracking-wider text-emerald-400">
                  Automated Revenue & Intelligence Assistant
                </p>
                <p className="mx-auto mt-3 max-w-md text-sm leading-relaxed text-slate-400">
                  Your chief of staff. I run pipelines, pull reports, analyze data, generate documents, and monitor the business 24/7.
                </p>
                <div className="mt-7 grid w-full max-w-2xl grid-cols-1 gap-2 sm:grid-cols-2">
                  {[
                    "Show pipeline funnel chart",
                    "Compare revenue this week vs last",
                    "Show campaign health",
                    "Detect business patterns",
                    ...(canRunPipeline ? ["Run outbound pipeline"] : []),
                  ].map((suggestion) => (
                    <button
                      key={suggestion}
                      type="button"
                      onClick={() => {
                        setInput(suggestion);
                      }}
                      className="group flex items-center justify-between rounded-xl border border-crmBorder bg-crmSurface px-4 py-3 text-left text-sm text-slate-300 transition hover:-translate-y-0.5 hover:border-emerald-500/40 hover:bg-crmSurface2 hover:text-white hover:shadow-lg hover:shadow-emerald-900/10"
                    >
                      <span>{suggestion}</span>
                      <svg
                        className="h-4 w-4 text-slate-500 transition group-hover:translate-x-0.5 group-hover:text-emerald-400"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                      </svg>
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((msg, i) => (
              <div
                key={i}
                className={`flex items-start gap-2.5 ${msg.role === "user" ? "justify-end" : "justify-start"}`}
              >
                {msg.role !== "user" && (
                  <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-emerald-500/15 ring-1 ring-emerald-500/30">
                    <svg className="h-4 w-4 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={1.8}
                        d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
                      />
                    </svg>
                  </div>
                )}
                <div
                  className={`max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm ${
                    msg.role === "user"
                      ? "rounded-tr-md bg-emerald-600/90 text-white shadow-emerald-900/20"
                      : "rounded-tl-md border border-crmBorder bg-crmSurface text-slate-200 shadow-black/20"
                  }`}
                >
                  {msg.role === "assistant" && (
                    <div className="mb-1 flex items-center gap-1.5">
                      <p className="text-xs font-semibold text-emerald-400">ARIA</p>
                      {session?.access_token && msg.content && (
                        <VoiceOutput text={msg.content} accessToken={session.access_token} />
                      )}
                    </div>
                  )}
                  <div className="whitespace-pre-wrap">{msg.content}</div>
                  {msg.function_name && (
                    <div className="mt-2 rounded-lg bg-crmSurface2 px-3 py-2">
                      <p className="text-xs text-slate-500">
                        Action: <span className="font-mono text-emerald-400">{msg.function_name}</span>
                      </p>
                    </div>
                  )}
                  {msg.pipeline_run_id && session?.access_token && (
                    <div className="mt-3">
                      <PipelineStatusTracker
                        runId={msg.pipeline_run_id}
                        accessToken={session.access_token}
                        onComplete={() => void handlePipelineComplete(msg.pipeline_run_id!)}
                      />
                    </div>
                  )}
                  {msg.download_url && msg.download_filename && (
                    <InlineDownloadButton
                      url={msg.download_url}
                      filename={msg.download_filename}
                      label={`Download ${msg.download_filename}`}
                    />
                  )}
                  {msg.confirmation && (
                    <div className="mt-3">
                      <ConfirmationCard
                        title={msg.confirmation.title}
                        description={msg.confirmation.description}
                        onConfirm={msg.confirmation.action}
                        onCancel={() => {}}
                      />
                    </div>
                  )}
                  {msg.chart_data && (
                    <InlineChart data={msg.chart_data} />
                  )}
                </div>
              </div>
            ))}
            {sending && (
              <div className="flex items-start gap-2.5">
                <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-emerald-500/15 ring-1 ring-emerald-500/30">
                  <svg className="h-4 w-4 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={1.8}
                      d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"
                    />
                  </svg>
                </div>
                <div className="rounded-2xl rounded-tl-md border border-crmBorder bg-crmSurface px-4 py-3 shadow-sm shadow-black/20">
                  <p className="mb-1 text-xs font-semibold text-emerald-400">ARIA</p>
                  <div className="flex gap-1">
                    <span className="h-2 w-2 animate-bounce rounded-full bg-emerald-400/60" style={{ animationDelay: "0ms" }} />
                    <span className="h-2 w-2 animate-bounce rounded-full bg-emerald-400/60" style={{ animationDelay: "150ms" }} />
                    <span className="h-2 w-2 animate-bounce rounded-full bg-emerald-400/60" style={{ animationDelay: "300ms" }} />
                  </div>
                </div>
              </div>
            )}
            <div aria-hidden className="h-px shrink-0" />
          </div>
        </div>

        {/* Pipeline trigger form */}
        {showPipelineTrigger && session?.access_token && (
          <div className="shrink-0 border-t border-crmBorder bg-crmSurface px-4 py-3">
            <div className="mx-auto max-w-3xl">
              <PipelineRunTrigger
                accessToken={session.access_token}
                onRunStarted={handlePipelineStarted}
              />
            </div>
          </div>
        )}

        <div className="shrink-0 border-t border-crmBorder bg-crmSurface px-4 py-4 sm:px-6">
          <div className="mx-auto max-w-3xl">
            <div className="flex items-center gap-2 rounded-2xl border border-crmBorder bg-crmSurface2 px-2 py-2 shadow-inner shadow-black/20 transition focus-within:border-emerald-500/50 focus-within:ring-1 focus-within:ring-emerald-500/30">
              {session?.access_token && (
                <VoiceInput
                  accessToken={session.access_token}
                  onTranscription={(text) => setInput(text)}
                  disabled={sending}
                />
              )}
              {session?.access_token && (
                <FileUpload
                  accessToken={session.access_token}
                  onAnalysis={(result) => {
                    setMessages((prev) => [
                      ...prev,
                      { role: "user", content: `Analyze file: ${result.filename}` },
                      { role: "assistant", content: result.analysis },
                    ]);
                  }}
                  disabled={sending}
                />
              )}
              {canRunPipeline && (
                <button
                  type="button"
                  onClick={() => setShowPipelineTrigger(!showPipelineTrigger)}
                  className={`inline-flex h-10 w-10 items-center justify-center rounded-xl border transition ${
                    showPipelineTrigger
                      ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-400"
                      : "border-transparent text-slate-400 hover:bg-white/5 hover:text-emerald-400"
                  }`}
                  title="Run outbound pipeline"
                >
                  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                </button>
              )}
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && void sendMessage()}
                placeholder="Ask ARIA anything…"
                className="flex-1 bg-transparent px-2 py-2 text-sm text-white placeholder:text-slate-500 focus:outline-none"
              />
              <button
                type="button"
                onClick={() => void sendMessage()}
                disabled={sending || !input.trim()}
                className="inline-flex h-10 items-center gap-1.5 rounded-xl bg-emerald-600 px-4 text-sm font-semibold text-white shadow shadow-emerald-900/30 transition hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-40 disabled:shadow-none"
              >
                <span>Send</span>
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 12h14m0 0l-6-6m6 6l-6 6" />
                </svg>
              </button>
            </div>
            <p className="mt-2 text-center text-[11px] text-slate-500">
              Press <kbd className="rounded border border-crmBorder bg-crmSurface2 px-1 font-mono text-[10px] text-slate-400">Enter</kbd> to send. ARIA can make mistakes — review actions before confirming.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
