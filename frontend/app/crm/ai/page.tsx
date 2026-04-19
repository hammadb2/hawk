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
  const chatEndRef = useRef<HTMLDivElement>(null);

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
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  /* ── Access control ──────────────────────────────────────────────────── */

  if (profile && BLOCKED_ROLES.includes(profile.role || "")) {
    return (
      <div className="flex items-center justify-center p-12">
        <p className="text-slate-500">The AI Command Center is not available for your role.</p>
      </div>
    );
  }

  return (
    <div className="flex h-[calc(100dvh-64px)] bg-crmBg">
      <aside className="hidden w-64 flex-shrink-0 border-r border-crmBorder bg-crmSurface lg:block">
        <div className="flex items-center justify-between border-b border-crmBorder px-4 py-3">
          <h2 className="text-sm font-semibold text-white">Conversations</h2>
          <button
            type="button"
            onClick={() => void createConversation()}
            className="rounded-lg bg-emerald-600 px-2.5 py-1 text-xs font-medium text-white transition hover:bg-emerald-500"
          >
            + New
          </button>
        </div>
        <div className="overflow-y-auto p-2">
          {loadingConvs ? (
            <div className="flex justify-center py-4">
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-crmBorder border-t-emerald-500" />
            </div>
          ) : conversations.length === 0 ? (
            <p className="px-2 py-4 text-center text-xs text-slate-500">No conversations yet.</p>
          ) : (
            conversations.map((c) => (
              <button
                key={c.id}
                type="button"
                onClick={() => selectConversation(c.id)}
                className={`mb-1 w-full rounded-lg px-3 py-2 text-left text-sm transition ${
                  activeConvId === c.id
                    ? "border border-emerald-500/30 bg-emerald-500/15 font-medium text-emerald-400"
                    : "text-slate-400 hover:bg-white/5 hover:text-slate-200"
                }`}
              >
                <p className="truncate">{c.title}</p>
                <p className="text-xs text-slate-500">{new Date(c.updated_at).toLocaleDateString()}</p>
              </button>
            ))
          )}
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <div className="flex items-center justify-between border-b border-crmBorder bg-crmSurface px-4 py-3">
          <div>
            <h1 className="text-sm font-semibold text-white">ARIA</h1>
            <p className="text-xs text-slate-500">
              {profile?.role === "ceo"
                ? "Full access — all commands available"
                : `${profile?.role_type || profile?.role || ""} access`}
            </p>
          </div>
          <button
            type="button"
            onClick={() => void createConversation()}
            className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white transition hover:bg-emerald-500 lg:hidden"
          >
            + New
          </button>
        </div>

        <div className="flex-1 overflow-y-auto bg-crmBg px-4 py-6">
          <div className="mx-auto max-w-3xl space-y-4">
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
              <div className="py-12 text-center">
                <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500/15 ring-2 ring-emerald-500/30">
                  <svg className="h-8 w-8 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={1.5}
                      d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
                    />
                  </svg>
                </div>
                <h2 className="text-lg font-semibold text-white">ARIA</h2>
                <p className="mt-1 text-xs font-medium text-emerald-400">Automated Revenue & Intelligence Assistant</p>
                <p className="mx-auto mt-2 max-w-md text-sm text-slate-400">
                  Your chief of staff. I run pipelines, pull reports, analyze data, generate documents, and monitor the business 24/7.
                </p>
                <div className="mt-6 flex flex-wrap justify-center gap-2">
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
                      className="rounded-lg border border-crmBorder bg-crmSurface px-3 py-2 text-xs text-slate-300 transition hover:border-emerald-500/40 hover:text-emerald-400"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {messages.map((msg, i) => (
              <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                <div
                  className={`max-w-[85%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
                    msg.role === "user"
                      ? "border border-emerald-500/25 bg-emerald-950/50 text-slate-100"
                      : "border border-crmBorder border-l-4 border-l-emerald-500 bg-crmSurface text-slate-200"
                  }`}
                >
                  {msg.role === "assistant" && (
                    <div className="mb-1 flex items-center gap-1">
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
              <div className="flex justify-start">
                <div className="rounded-2xl border border-crmBorder border-l-4 border-l-emerald-500 bg-crmSurface px-4 py-3">
                  <p className="mb-1 text-xs font-semibold text-emerald-400">ARIA</p>
                  <div className="flex gap-1">
                    <span className="h-2 w-2 animate-bounce rounded-full bg-slate-500" style={{ animationDelay: "0ms" }} />
                    <span className="h-2 w-2 animate-bounce rounded-full bg-slate-500" style={{ animationDelay: "150ms" }} />
                    <span className="h-2 w-2 animate-bounce rounded-full bg-slate-500" style={{ animationDelay: "300ms" }} />
                  </div>
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>
        </div>

        {/* Pipeline trigger form */}
        {showPipelineTrigger && session?.access_token && (
          <div className="border-t border-crmBorder bg-crmSurface px-4 py-3">
            <div className="mx-auto max-w-3xl">
              <PipelineRunTrigger
                accessToken={session.access_token}
                onRunStarted={handlePipelineStarted}
              />
            </div>
          </div>
        )}

        <div className="border-t border-crmBorder bg-crmSurface px-4 py-4">
          <div className="mx-auto flex max-w-3xl gap-2">
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
                className={`rounded-xl border px-3 py-3 text-sm font-medium transition ${
                  showPipelineTrigger
                    ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-400"
                    : "border-crmBorder bg-crmSurface2 text-slate-400 hover:border-emerald-500/40 hover:text-emerald-400"
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
              placeholder="Ask ARIA anything..."
              className="flex-1 rounded-xl border border-crmBorder bg-crmSurface2 px-4 py-3 text-sm text-white placeholder:text-slate-500 focus:border-emerald-500/50 focus:outline-none focus:ring-1 focus:ring-emerald-500/20"
            />
            <button
              type="button"
              onClick={() => void sendMessage()}
              disabled={sending || !input.trim()}
              className="rounded-xl bg-emerald-600 px-5 py-3 text-sm font-semibold text-white transition hover:bg-emerald-500 disabled:opacity-50"
            >
              Send
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
