"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type Msg = { role: "user" | "assistant"; content: string };

export default function PortalAskPage() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;
    setInput("");
    const nextUser: Msg = { role: "user", content: text };
    setMessages((m) => [...m, nextUser]);
    setLoading(true);
    try {
      const res = await fetch("/api/portal/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          conversation_history: messages.map((x) => ({ role: x.role, content: x.content })),
        }),
      });
      const j = (await res.json().catch(() => ({}))) as { reply?: string; error?: string };
      if (!res.ok) {
        setMessages((m) => [
          ...m,
          { role: "assistant", content: j.error || "Something went wrong. Try again." },
        ]);
        return;
      }
      setMessages((m) => [...m, { role: "assistant", content: j.reply || "—" }]);
    } catch {
      setMessages((m) => [...m, { role: "assistant", content: "Network error." }]);
    } finally {
      setLoading(false);
    }
  }, [input, loading, messages]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-ink-0">Ask ARIA</h1>
        <p className="mt-1 text-sm text-ink-200">
          Answers use your latest scan, industry, and Canadian privacy context (PIPEDA / C-27). Not legal advice.
        </p>
        <Link href="/portal" className="mt-2 inline-block text-sm text-signal hover:underline">
          ← Back to overview
        </Link>
      </div>

      <div className="flex min-h-[420px] flex-col rounded-2xl border border-white/10 bg-ink-800 shadow-sm">
        <div className="flex-1 space-y-4 overflow-y-auto p-4">
          {messages.length === 0 && (
            <p className="text-sm text-ink-200">
              Ask ARIA about your findings, email security, what to fix first, or how PIPEDA applies to your situation.
            </p>
          )}
          {messages.map((msg, i) => (
            <div
              key={i}
              className={`rounded-xl px-4 py-3 text-sm ${
                msg.role === "user"
                  ? "ml-8 bg-ink-800 text-ink-0"
                  : "mr-8 border border-white/10 bg-ink-800 text-ink-0 shadow-sm"
              }`}
            >
              {msg.role === "assistant" ? (
                <div className="prose prose-invert prose-sm prose-headings:text-ink-0 prose-p:text-ink-200 prose-li:text-ink-200 max-w-none prose-p:leading-relaxed prose-headings:text-ink-0">
                  <ReactMarkdown>{msg.content}</ReactMarkdown>
                </div>
              ) : (
                msg.content
              )}
            </div>
          ))}
          {loading && <p className="text-xs text-ink-200">Thinking…</p>}
        </div>
        <div className="flex gap-2 border-t border-white/10 p-4">
          <Input
            className="border-white/10 bg-ink-800"
            placeholder="Ask anything about your security posture…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && void send()}
          />
          <Button className="shrink-0 bg-signal text-white" disabled={loading} onClick={() => void send()}>
            Send
          </Button>
        </div>
      </div>
    </div>
  );
}
