"use client";

import { useState, useEffect } from "react";
import { Ban, Plus } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { suppressionsApi } from "@/lib/api";
import { toast } from "@/components/ui/toast";
import { formatDateTime } from "@/lib/utils";

export function SuppressionsConsole() {
  const [rows, setRows] = useState<Record<string, unknown>[]>([]);
  const [loading, setLoading] = useState(false);
  const [domain, setDomain] = useState("");
  const [email, setEmail] = useState("");
  const [adding, setAdding] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const res = await suppressionsApi.list();
      if (res.success && res.data) {
        setRows(res.data);
      } else {
        setRows([]);
        toast({ title: res.error || "Failed to load suppressions", variant: "destructive" });
      }
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const handleAdd = async () => {
    const d = domain.trim().toLowerCase();
    const e = email.trim().toLowerCase();
    if (!d && !e) {
      toast({ title: "Enter a domain or email", variant: "destructive" });
      return;
    }
    setAdding(true);
    try {
      const res = await suppressionsApi.add({
        ...(d ? { domain: d } : {}),
        ...(e ? { email: e } : {}),
        reason: "manual",
      });
      if (res.success) {
        toast({ title: "Suppression added", variant: "success" });
        setDomain("");
        setEmail("");
        void load();
      } else {
        toast({ title: res.error || "Could not add", variant: "destructive" });
      }
    } finally {
      setAdding(false);
    }
  };

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-xl font-bold text-text-primary flex items-center gap-2">
          <Ban className="w-5 h-5 text-orange" />
          Suppression list
        </h1>
        <p className="text-sm text-text-secondary mt-0.5">
          CASL / outreach blocks — domains and emails Charlotte and reps must not contact.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Add entry</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <p className="text-xs text-text-dim mb-1">Domain</p>
              <Input
                placeholder="example.com"
                value={domain}
                onChange={(ev) => setDomain(ev.target.value)}
              />
            </div>
            <div>
              <p className="text-xs text-text-dim mb-1">Email (optional)</p>
              <Input
                type="email"
                placeholder="person@example.com"
                value={email}
                onChange={(ev) => setEmail(ev.target.value)}
              />
            </div>
          </div>
          <Button size="sm" className="gap-1.5" onClick={() => void handleAdd()} disabled={adding}>
            <Plus className="w-3.5 h-3.5" />
            {adding ? "Adding…" : "Add suppression"}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Current list</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex justify-center py-12">
              <Spinner size="lg" />
            </div>
          ) : rows.length === 0 ? (
            <p className="text-sm text-text-dim text-center py-8">No suppressions yet.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {rows.map((r) => (
                <li
                  key={String(r.id)}
                  className="flex flex-wrap items-center justify-between gap-2 py-2 border-b border-border/60 last:border-0"
                >
                  <span className="text-text-primary">
                    {(r.domain as string) || "—"}{" "}
                    {(r.email as string) ? `· ${r.email as string}` : ""}
                  </span>
                  <span className="text-2xs text-text-dim">
                    {String(r.reason ?? "")} · {r.added_at ? formatDateTime(String(r.added_at)) : ""}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
