"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/components/providers/auth-provider";
import { domainsApi, type Domain } from "@/lib/api";

export default function DashboardDomainsPage() {
  const { token } = useAuth();
  const [domains, setDomains] = useState<Domain[]>([]);
  const [loading, setLoading] = useState(true);
  const [newDomain, setNewDomain] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) return;
    domainsApi
      .list(token)
      .then((r) => setDomains(r.domains))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [token]);

  const add = async () => {
    const d = newDomain.trim().toLowerCase().replace(/^https?:\/\//, "").split("/")[0].replace(/^www\./, "");
    if (!d || !token) return;
    setError("");
    setAdding(true);
    try {
      const created = await domainsApi.create({ domain: d, scan_frequency: "on_demand" }, token);
      setDomains((prev) => [created, ...prev]);
      setNewDomain("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add domain");
    } finally {
      setAdding(false);
    }
  };

  const remove = async (id: string) => {
    if (!token) return;
    try {
      await domainsApi.delete(id, token);
      setDomains((prev) => prev.filter((x) => x.id !== id));
    } catch {
      // ignore
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Domains</h1>
        <p className="text-text-secondary mt-1">Manage domains to scan. Plan limits apply.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Add domain</CardTitle>
        </CardHeader>
        <CardContent className="pt-0 flex gap-2 flex-wrap items-center">
            <Input
              placeholder="example.com"
              value={newDomain}
              onChange={(e) => setNewDomain(e.target.value)}
              className="w-64"
            />
            <Button onClick={add} disabled={adding || !newDomain.trim()}>
              {adding ? "Adding…" : "Add"}
            </Button>
            {error && <p className="text-sm text-red w-full">{error}</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Your domains</CardTitle>
        </CardHeader>
        <CardContent className="pt-0">
            {loading ? (
              <p className="text-text-dim">Loading…</p>
            ) : domains.length === 0 ? (
              <p className="text-text-dim">No domains yet. Add one above.</p>
            ) : (
              <ul className="space-y-2">
                {domains.map((d) => (
                  <li key={d.id} className="flex items-center justify-between py-2 border-b border-surface-3 last:border-0">
                    <span className="font-medium">{d.domain}</span>
                    <div className="flex items-center gap-2">
                      <span className="text-sm text-text-dim">{d.scan_frequency || "on_demand"}</span>
                      <Button variant="ghost" size="sm" onClick={() => remove(d.id)}>
                        Remove
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
        </CardContent>
      </Card>
    </div>
  );
}
