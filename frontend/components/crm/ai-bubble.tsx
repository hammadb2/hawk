"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MessageCircle, Send, X } from "lucide-react";
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
        setMessages((prev) => [...prev, { role: "assistant", content: "Something went wrong. Please try again." }]);
      }
    } catch {
      setMessages((prev) => [...prev, { role: "assistant", content: "Connection error. Please try again." }]);
    }
    setSending(false);
  }, [input, sending, session?.access_token, headers, conversationId]);

  if (!profile || BLOCKED_ROLES.includes(profile.role || "")) {
    return null;
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="group fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-crmSurface text-emerald-400 shadow-lg ring-2 ring-emerald-500/50 transition-all hover:scale-105 hover:bg-crmSurface2 hover:ring-emerald-400/70"
        title="AI Command Center"
      >
        <span
          className="pointer-events-none absolute inset-[-4px] rounded-full border-2 border-emerald-500/40 opacity-70 animate-pulse"
          aria-hidden
        />
        <span className="relative flex h-11 w-11 items-center justify-center rounded-full bg-crmSurface ring-1 ring-emerald-500/30">
          {open ? <X className="h-6 w-6 text-slate-200" /> : <MessageCircle className="h-6 w-6" strokeWidth={1.75} />}
        </span>
      </button>

      {open && (
        <div className="fixed bottom-24 right-6 z-50 flex h-[500px] w-[380px] flex-col overflow-hidden rounded-2xl border border-crmBorder bg-crmSurface shadow-2xl">
          <div className="flex items-center justify-between border-b border-crmBorder bg-crmSurface2 px-4 py-3">
            <div>
              <p className="text-sm font-semibold text-white">HAWK AI</p>
              <p className="text-xs text-slate-500">Command Center</p>
            </div>
            <div className="flex items-center gap-2">
              <Link
                href="/crm/ai"
                className="rounded-lg border border-emerald-500/30 bg-emerald-500/15 px-2 py-1 text-xs text-emerald-400 transition hover:bg-emerald-500/25"
              >
                Full page
              </Link>
              <button type="button" onClick={() => setOpen(false)} className="rounded-lg p-1 text-slate-400 hover:bg-white/5 hover:text-white">
                <X className="h-5 w-5" />
              </button>
            </div>
          </div>

          <div className="flex-1 overflow-y-auto bg-crmBg p-3">
            {messages.length === 0 && (
              <div className="flex h-full items-center justify-center">
                <div className="text-center">
                  <p className="text-sm font-medium text-slate-300">How can I help?</p>
                  <p className="mt-1 text-xs text-slate-500">Ask about reports, team, pipeline, or give commands.</p>
                </div>
              </div>
            )}
            <div className="space-y-3">
              {messages.map((msg, i) => (
                <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                  <div
                    className={
                      msg.role === "user"
                        ? "max-w-[85%] rounded-xl border border-emerald-500/25 bg-emerald-950/40 px-3 py-2 text-sm text-slate-100"
                        : "max-w-[85%] rounded-xl border border-crmBorder border-l-4 border-l-emerald-500 bg-crmSurface2 px-3 py-2 text-sm text-slate-200"
                    }
                  >
                    <div className="whitespace-pre-wrap">{msg.content}</div>
                    {msg.function_name && (
                      <p className="mt-1 font-mono text-xs text-emerald-400/90">{msg.function_name}</p>
                    )}
                  </div>
                </div>
              ))}
              {sending && (
                <div className="flex justify-start">
                  <div className="rounded-xl border border-crmBorder border-l-4 border-l-emerald-500 bg-crmSurface2 px-3 py-2">
                    <div className="flex gap-1">
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-500" style={{ animationDelay: "0ms" }} />
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-500" style={{ animationDelay: "150ms" }} />
                      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-slate-500" style={{ animationDelay: "300ms" }} />
                    </div>
                  </div>
                </div>
              )}
              <div ref={chatEndRef} />
            </div>
          </div>

          <div className="border-t border-crmBorder bg-crmSurface2 p-3">
            <div className="flex gap-2">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && void sendMessage()}
                placeholder="Type a command..."
                className="flex-1 rounded-lg border border-crmBorder bg-crmSurface px-3 py-2 text-sm text-white placeholder:text-slate-500 focus:border-emerald-500/50 focus:outline-none"
              />
              <button
                type="button"
                onClick={() => void sendMessage()}
                disabled={sending || !input.trim()}
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-emerald-600 text-white transition hover:bg-emerald-500 disabled:opacity-50"
              >
                <Send className="h-4 w-4" />
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
