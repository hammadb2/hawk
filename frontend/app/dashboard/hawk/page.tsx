"use client";

import { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import ReactMarkdown from "react-markdown";
import { useAuth } from "@/components/providers/auth-provider";
import { hawkApi, scansApi } from "@/lib/api";
import { cn } from "@/lib/utils";

type Message = { role: "user" | "assistant"; content: string };

function TypingDots() {
  return (
    <div className="flex items-center gap-1 px-4 py-3">
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          className="w-2 h-2 rounded-full bg-text-dim"
          animate={{ opacity: [0.3, 1, 0.3] }}
          transition={{ duration: 1.2, repeat: Infinity, delay: i * 0.2 }}
        />
      ))}
    </div>
  );
}

function HawkAvatar() {
  return (
    <div className="w-7 h-7 rounded-full bg-accent flex items-center justify-center shrink-0 text-white text-xs font-bold select-none">
      H
    </div>
  );
}

function Bubble({ msg, index }: { msg: Message; index: number }) {
  const isUser = msg.role === "user";
  return (
    <motion.div
      initial={{ opacity: 0, y: 10, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.25, ease: "easeOut", delay: index * 0.03 }}
      className={cn("flex items-end gap-2", isUser ? "justify-end" : "justify-start")}
    >
      {!isUser && <HawkAvatar />}
      <div
        className={cn(
          "max-w-[78%] rounded-2xl px-4 py-3 text-sm leading-relaxed",
          isUser
            ? "bg-accent text-white rounded-br-sm"
            : "rounded-bl-sm border border-surface-3 bg-surface-2 text-text-primary shadow-sm"
        )}
      >
        {isUser ? (
          <span>{msg.content}</span>
        ) : (
          <div className="prose prose-slate prose-sm max-w-none prose-p:my-1 prose-ul:my-1 prose-li:my-0 prose-headings:font-semibold prose-headings:text-sm prose-headings:text-slate-900 prose-p:text-slate-700 prose-li:text-slate-700 prose-code:text-emerald-700">
            <ReactMarkdown>{msg.content}</ReactMarkdown>
          </div>
        )}
      </div>
      {isUser && (
        <div className="w-7 h-7 rounded-full bg-surface-3 flex items-center justify-center shrink-0 text-text-dim text-xs font-bold select-none">
          U
        </div>
      )}
    </motion.div>
  );
}

export default function AskHawkPage() {
  const { user, token } = useAuth();
  const [message, setMessage] = useState("");
  const [history, setHistory] = useState<Message[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [scanId, setScanId] = useState("");
  const [scans, setScans] = useState<{ id: string; score: number | null; grade: string | null }[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!token) return;
    scansApi.list(token).then((r) => setScans(r.scans.slice(0, 20))).catch(() => {});
  }, [token]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [history, loading]);

  const send = async () => {
    const text = message.trim();
    if (!text || !token || loading) return;
    setError("");
    setLoading(true);
    const userMsg: Message = { role: "user", content: text };
    const prevHistory = history;
    setHistory((h) => [...h, userMsg]);
    setMessage("");

    try {
      const res = await hawkApi.chat(
        {
          message: text,
          scan_id: scanId || undefined,
          conversation_history: prevHistory,
        },
        token
      );
      let replyText = res.reply;
      if (res.trigger_rescan) {
        replyText += `\n\n*(Rescan triggered for: ${res.trigger_rescan})*`;
      }
      setHistory((h) => [...h, { role: "assistant", content: replyText }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
      setHistory((h) => h.slice(0, -1));
    } finally {
      setLoading(false);
      inputRef.current?.focus();
    }
  };

  const isTrial = user?.plan === "trial";
  const isEmpty = history.length === 0 && !loading;

  return (
    <div className="flex flex-col h-[calc(100vh-6rem)] max-w-2xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between pb-4 shrink-0">
        <div>
          <h1 className="text-xl font-bold text-text-primary">Ask HAWK</h1>
          {isTrial && (
            <p className="text-xs text-text-dim mt-0.5">Trial — 5 messages. Upgrade for unlimited.</p>
          )}
        </div>
        <select
          className="h-9 rounded-lg border border-surface-3 bg-surface-1 px-3 text-xs text-text-primary focus:outline-none focus:ring-1 focus:ring-accent"
          value={scanId}
          onChange={(e) => setScanId(e.target.value)}
        >
          <option value="">No scan context</option>
          {scans.map((s) => (
            <option key={s.id} value={s.id}>
              {s.id.slice(0, 8)}… — {s.grade ?? "—"} ({s.score ?? "—"})
            </option>
          ))}
        </select>
      </div>

      {/* Chat area */}
      <div className="flex-1 overflow-y-auto rounded-2xl border border-surface-3 bg-surface-1 p-4 space-y-4 scrollbar-thin scrollbar-thumb-surface-3">
        <AnimatePresence>
          {isEmpty && (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex flex-col items-center justify-center h-full gap-3 py-16 text-center"
            >
              <div className="w-12 h-12 rounded-full bg-accent/20 flex items-center justify-center text-accent text-xl font-bold">
                H
              </div>
              <p className="text-text-secondary text-sm font-medium">Ask me anything about your security</p>
              <div className="flex flex-wrap gap-2 justify-center mt-1">
                {[
                  "What's my biggest risk?",
                  "How do I fix my HTTPS?",
                  "Explain DMARC to me",
                  "Give me a quick action plan",
                ].map((suggestion) => (
                  <button
                    key={suggestion}
                    type="button"
                    onClick={() => {
                      setMessage(suggestion);
                      inputRef.current?.focus();
                    }}
                    className="px-3 py-1.5 rounded-full border border-surface-3 bg-surface-2 text-xs text-text-secondary hover:text-text-primary hover:border-accent/50 transition-colors"
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {history.map((m, i) => (
          <Bubble key={i} msg={m} index={i} />
        ))}

        {loading && (
          <motion.div
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex items-end gap-2"
          >
            <HawkAvatar />
            <div className="bg-surface-2 border border-surface-3 rounded-2xl rounded-bl-sm">
              <TypingDots />
            </div>
          </motion.div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input bar */}
      <div className="pt-3 shrink-0">
        {error && (
          <p className="text-xs text-red mb-2 px-1">{error}</p>
        )}
        <div className="flex gap-2 items-center bg-surface-1 border border-surface-3 rounded-2xl px-4 py-2 focus-within:border-accent/60 transition-colors">
          <input
            ref={inputRef}
            className="flex-1 bg-transparent text-sm text-text-primary placeholder:text-text-dim focus:outline-none"
            placeholder="Ask HAWK anything…"
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && void send()}
            disabled={loading}
          />
          <button
            type="button"
            onClick={() => void send()}
            disabled={loading || !message.trim()}
            className={cn(
              "w-8 h-8 rounded-full flex items-center justify-center transition-all shrink-0",
              message.trim() && !loading
                ? "bg-accent text-white hover:bg-accent/90"
                : "cursor-not-allowed bg-slate-200 text-slate-500"
            )}
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
