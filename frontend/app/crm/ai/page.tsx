"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { CRM_API_BASE_URL } from "@/lib/crm/api-url";

interface ChatMessage {
  id?: string;
  role: "user" | "assistant" | "system";
  content: string;
  function_name?: string;
  function_result?: string;
}

interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

const BLOCKED_ROLES = ["va", "client"];

export default function AiCommandCenterPage() {
  const supabase = useMemo(() => createClient(), []);
  const { profile, session } = useCrmAuth();
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [loadingConvs, setLoadingConvs] = useState(true);
  const chatEndRef = useRef<HTMLDivElement>(null);

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
        setConversations(data.conversations || []);
      }
    } catch (err) {
      console.error("Failed to load conversations:", err);
    }
    setLoadingConvs(false);
  }, [session?.access_token]);

  useEffect(() => {
    void loadConversations();
  }, [loadConversations]);

  /* ── Load messages for active conversation ──────────────────────────── */

  const loadMessages = useCallback(async (convId: string) => {
    if (!session?.access_token) return;
    try {
      const r = await fetch(`${CRM_API_BASE_URL}/api/crm/ai/conversations/${convId}/messages`, {
        headers: { Authorization: `Bearer ${session.access_token}` },
      });
      if (r.ok) {
        const data = await r.json();
        setMessages(data.messages || []);
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
          setMessages((prev) => [...prev, { role: "assistant", content: "Failed to start conversation. Please try again." }]);
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
    <div className="flex h-[calc(100dvh-64px)]">
      {/* Sidebar — conversation list */}
      <aside className="hidden w-64 flex-shrink-0 border-r border-slate-200 bg-slate-50 lg:block">
        <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-700">Conversations</h2>
          <button
            onClick={() => void createConversation()}
            className="rounded-lg bg-emerald-600 px-2.5 py-1 text-xs font-medium text-white hover:bg-emerald-700 transition"
          >
            + New
          </button>
        </div>
        <div className="overflow-y-auto p-2">
          {loadingConvs ? (
            <div className="flex justify-center py-4">
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-slate-200 border-t-emerald-500" />
            </div>
          ) : conversations.length === 0 ? (
            <p className="px-2 py-4 text-center text-xs text-slate-400">No conversations yet.</p>
          ) : (
            conversations.map((c) => (
              <button
                key={c.id}
                onClick={() => selectConversation(c.id)}
                className={`w-full rounded-lg px-3 py-2 text-left text-sm transition mb-1 ${
                  activeConvId === c.id
                    ? "bg-emerald-100 text-emerald-700 font-medium"
                    : "text-slate-600 hover:bg-slate-100"
                }`}
              >
                <p className="truncate">{c.title}</p>
                <p className="text-xs text-slate-400">{new Date(c.updated_at).toLocaleDateString()}</p>
              </button>
            ))
          )}
        </div>
      </aside>

      {/* Main chat area */}
      <div className="flex flex-1 flex-col">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3">
          <div>
            <h1 className="text-sm font-semibold text-slate-900">AI Command Center</h1>
            <p className="text-xs text-slate-500">
              {profile?.role === "ceo"
                ? "Full access — all commands available"
                : `${profile?.role_type || profile?.role || ""} access`}
            </p>
          </div>
          <button
            onClick={() => void createConversation()}
            className="rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-700 transition lg:hidden"
          >
            + New
          </button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto px-4 py-6">
          <div className="mx-auto max-w-3xl space-y-4">
            {messages.length === 0 && (
              <div className="text-center py-12">
                <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-emerald-100">
                  <svg className="h-8 w-8 text-emerald-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                  </svg>
                </div>
                <h2 className="text-lg font-semibold text-slate-900">HAWK AI Command Center</h2>
                <p className="mt-2 text-sm text-slate-500 max-w-md mx-auto">
                  Ask me anything about your operations. I can pull reports, send emails, manage team members, generate documents, and more.
                </p>
                <div className="mt-6 flex flex-wrap justify-center gap-2">
                  {[
                    "Show VA performance this week",
                    "Summarize pipeline health",
                    "Generate a weekly report PDF",
                    "Show pending onboarding submissions",
                  ].map((suggestion) => (
                    <button
                      key={suggestion}
                      onClick={() => {
                        setInput(suggestion);
                      }}
                      className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600 hover:border-emerald-300 hover:text-emerald-600 transition"
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
                      ? "bg-emerald-600 text-white"
                      : "bg-slate-100 text-slate-800 border border-slate-200"
                  }`}
                >
                  {msg.role === "assistant" && (
                    <p className="mb-1 text-xs font-semibold text-emerald-600">HAWK AI</p>
                  )}
                  <div className="whitespace-pre-wrap">{msg.content}</div>
                  {msg.function_name && (
                    <div className="mt-2 rounded-lg bg-slate-200/50 px-3 py-2">
                      <p className="text-xs text-slate-500">
                        Action: <span className="font-mono text-emerald-600">{msg.function_name}</span>
                      </p>
                    </div>
                  )}
                </div>
              </div>
            ))}
            {sending && (
              <div className="flex justify-start">
                <div className="rounded-2xl bg-slate-100 border border-slate-200 px-4 py-3">
                  <p className="text-xs font-semibold text-emerald-600 mb-1">HAWK AI</p>
                  <div className="flex gap-1">
                    <span className="h-2 w-2 animate-bounce rounded-full bg-slate-400" style={{ animationDelay: "0ms" }} />
                    <span className="h-2 w-2 animate-bounce rounded-full bg-slate-400" style={{ animationDelay: "150ms" }} />
                    <span className="h-2 w-2 animate-bounce rounded-full bg-slate-400" style={{ animationDelay: "300ms" }} />
                  </div>
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>
        </div>

        {/* Input */}
        <div className="border-t border-slate-200 bg-white px-4 py-4">
          <div className="mx-auto flex max-w-3xl gap-2">
            <input
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && void sendMessage()}
              placeholder="Ask HAWK AI anything..."
              className="flex-1 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-900 placeholder:text-slate-400 focus:border-emerald-400 focus:outline-none focus:ring-1 focus:ring-emerald-400/20"
            />
            <button
              onClick={() => void sendMessage()}
              disabled={sending || !input.trim()}
              className="rounded-xl bg-emerald-600 px-5 py-3 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-50 transition"
            >
              Send
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
