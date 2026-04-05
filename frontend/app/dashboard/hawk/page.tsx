"use client";

import { useState, useRef, useEffect } from "react";
import { motion } from "framer-motion";
import ReactMarkdown from "react-markdown";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/components/providers/auth-provider";
import { hawkApi, scansApi } from "@/lib/api";
import { cn } from "@/lib/utils";

export default function AskHawkPage() {
  const { token } = useAuth();
  const [message, setMessage] = useState("");
  const [history, setHistory] = useState<{ role: string; content: string }[]>([]);
  const [reply, setReply] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [scanId, setScanId] = useState("");
  const [scans, setScans] = useState<{ id: string; score: number | null; grade: string | null }[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!token) return;
    scansApi.list(token).then((r) => setScans(r.scans.slice(0, 20))).catch(() => {});
  }, [token]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [history, reply]);

  const send = async () => {
    const text = message.trim();
    if (!text || !token || loading) return;
    setError("");
    setLoading(true);
    const userMsg = { role: "user" as const, content: text };
    setHistory((h) => [...h, userMsg]);
    setMessage("");
    setReply("");

    try {
      const res = await hawkApi.chat(
        {
          message: text,
          scan_id: scanId || undefined,
          conversation_history: history,
        },
        token
      );
      setReply(res.reply);
      setHistory((h) => [...h, { role: "assistant", content: res.reply }]);
      if (res.trigger_rescan) {
        setReply((r) => r + "\n\n(Rescan triggered for: " + res.trigger_rescan + ")");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
      setHistory((h) => h.slice(0, -1));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Ask HAWK</h1>
        <p className="text-text-secondary mt-1">
          Get step-by-step fix instructions, PIPEDA / Bill C-26 mapping, and rescan suggestions.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Context (optional)</CardTitle>
          <CardDescription>
            Attach a recent scan so HAWK can give specific advice from your findings.
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-0">
          <select
            className="flex h-10 w-full max-w-xs rounded-lg border border-surface-3 bg-surface-1 px-3 py-2 text-sm text-text-primary"
            value={scanId}
            onChange={(e) => setScanId(e.target.value)}
          >
            <option value="">No scan</option>
            {scans.map((s) => (
              <option key={s.id} value={s.id}>
                {s.id.slice(0, 8)}… — {s.grade ?? "—"} ({s.score ?? "—"})
              </option>
            ))}
          </select>
        </CardContent>
      </Card>

      <Card className="flex flex-col min-h-[400px]">
        <CardHeader>
          <CardTitle>Chat</CardTitle>
          <CardDescription>
            Ask HAWK follow-up questions like you would in a GPT-style chat. It reads your findings and replies with concise, practical next steps.
          </CardDescription>
        </CardHeader>
        <CardContent className="pt-0 flex-1 flex flex-col min-h-0">
          <div className="flex-1 overflow-y-auto space-y-4 mb-4 min-h-[240px] max-h-[400px]">
            {history.length === 0 && !reply && !loading && (
              <p className="text-text-dim text-sm">
                e.g. “Summarize my findings in plain English” or “Give me a short checklist to fix my DMARC”.
              </p>
            )}
            {history.map((m, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className={m.role === "user" ? "text-right" : ""}
              >
                <span
                  className={cn(
                    "inline-block rounded-lg px-3 py-2 text-sm max-w-[85%]",
                    m.role === "user"
                      ? "bg-accent text-white"
                      : "bg-surface-2 text-text-primary border border-surface-3"
                  )}
                >
                  {m.content}
                </span>
              </motion.div>
            ))}
            {loading && <p className="text-text-dim text-sm">HAWK is thinking…</p>}
            {reply && !history.some((h) => h.role === "assistant" && h.content === reply) && (
              <motion.div
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                className="rounded-lg px-3 py-2 text-sm bg-surface-2 text-text-primary border border-surface-3 max-w-[85%] prose prose-invert prose-sm"
              >
                <ReactMarkdown>{reply}</ReactMarkdown>
              </motion.div>
            )}
            <div ref={bottomRef} />
          </div>
          {error && <p className="text-sm text-red mb-2">{error}</p>}
          <div className="flex gap-2">
            <input
              className="flex-1 h-10 rounded-lg border border-surface-3 bg-surface-1 px-3 py-2 text-sm text-text-primary placeholder:text-text-dim focus:outline-none focus:ring-2 focus:ring-accent"
              placeholder="Type your question…"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && send()}
              disabled={loading}
            />
            <Button onClick={send} disabled={loading || !message.trim()}>
              {loading ? "Sending…" : "Send"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
