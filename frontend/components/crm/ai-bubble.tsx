"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import { useCrmAuth } from "@/components/crm/crm-auth-provider";
import { CRM_API_BASE_URL } from "@/lib/crm/api-url";
import Link from "next/link";

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  function_name?: string;
}

const BLOCKED_ROLES = ["va", "client"];

export function AiBubble() {
  const { profile, session } = useCrmAuth();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const headers = useMemo((): Record<string, string> => {
    if (!session?.access_token) return {};
    return {
      Authorization: `Bearer ${session.access_token}`,
      "Content-Type": "application/json",
    };
  }, [session?.access_token]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = useCallback(async () => {
    if (!input.trim() || sending || !session?.access_token) return;
    const userMessage = input;
    setInput("");
    setSending(true);

    setMessages((prev) => [...prev, { role: "user", content: userMessage }]);

    try {
      // Auto-create conversation if none exists
      let convId = conversationId;
      if (!convId) {
        const cr = await fetch(`${CRM_API_BASE_URL}/api/crm/ai/conversations`, {
          method: "POST",
          headers,
          body: JSON.stringify({ title: "New conversation" }),
        });
        if (cr.ok) {
          const cd = await cr.json();
          convId = cd.id;
          setConversationId(convId);
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
        if (!conversationId && data.conversation_id) {
          setConversationId(data.conversation_id);
        }
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: data.reply,
            function_name: data.function_called,
          },
        ]);
      } else {
        setMessages((prev) => [
          ...prev,
          { role: "assistant", content: "Something went wrong. Please try again." },
        ]);
      }
    } catch {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Connection error. Please try again." },
      ]);
    }
    setSending(false);
  }, [input, sending, session?.access_token, headers, conversationId]);

  // Don't render for blocked roles
  if (!profile || BLOCKED_ROLES.includes(profile.role || "")) {
    return null;
  }

  return (
    <>
      {/* Floating bubble button */}
      <button
        onClick={() => setOpen(!open)}
        className="fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-emerald-600 text-white shadow-lg hover:bg-emerald-700 transition-all hover:scale-105"
        title="AI Command Center"
      >
        {open ? (
          <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        ) : (
          <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
          </svg>
        )}
      </button>

      {/* Chat panel */}
      {open && (
        <div className="fixed bottom-24 right-6 z-50 flex h-[500px] w-[380px] flex-col rounded-2xl border border-slate-200 bg-white shadow-2xl">
          {/* Header */}
          <div className="flex items-center justify-between rounded-t-2xl border-b border-slate-200 bg-emerald-600 px-4 py-3">
            <div>
              <p className="text-sm font-semibold text-white">HAWK AI</p>
              <p className="text-xs text-emerald-100">Command Center</p>
            </div>
            <div className="flex items-center gap-2">
              <Link
                href="/crm/ai"
                className="rounded-lg bg-emerald-700 px-2 py-1 text-xs text-white hover:bg-emerald-800 transition"
              >
                Full page
              </Link>
              <button onClick={() => setOpen(false)} className="text-white/80 hover:text-white">
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-3">
            {messages.length === 0 && (
              <div className="flex h-full items-center justify-center">
                <div className="text-center">
                  <p className="text-sm font-medium text-slate-600">How can I help?</p>
                  <p className="mt-1 text-xs text-slate-400">
                    Ask about reports, team, pipeline, or give commands.
                  </p>
                </div>
              </div>
            )}
            <div className="space-y-3">
              {messages.map((msg, i) => (
                <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                  <div
                    className={`max-w-[85%] rounded-xl px-3 py-2 text-sm ${
                      msg.role === "user"
                        ? "bg-emerald-600 text-white"
                        : "bg-slate-100 text-slate-800"
                    }`}
                  >
                    <div className="whitespace-pre-wrap">{msg.content}</div>
                    {msg.function_name && (
                      <p className="mt-1 text-xs text-emerald-600 font-mono">{msg.function_name}</p>
                    )}
                  </div>
                </div>
              ))}
              {sending && (
                <div className="flex justify-start">
                  <div className="rounded-xl bg-slate-100 px-3 py-2">
                    <div className="flex gap-1">
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" style={{ animationDelay: "0ms" }} />
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" style={{ animationDelay: "150ms" }} />
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-400" style={{ animationDelay: "300ms" }} />
                    </div>
                  </div>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>
          </div>

          {/* Input */}
          <div className="border-t border-slate-200 p-3">
            <div className="flex gap-2">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && void sendMessage()}
                placeholder="Type a command..."
                className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 focus:border-emerald-400 focus:outline-none"
              />
              <button
                onClick={() => void sendMessage()}
                disabled={sending || !input.trim()}
                className="rounded-lg bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-700 disabled:opacity-50 transition"
              >
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                </svg>
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
