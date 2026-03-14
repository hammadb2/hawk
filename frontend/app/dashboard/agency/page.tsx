"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/components/providers/auth-provider";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface AgencyClient {
  id: string;
  user_id: string;
  name: string;
  email: string | null;
  company: string | null;
  created_at: string | null;
}

export default function DashboardAgencyPage() {
  const { user, token } = useAuth();
  const [clients, setClients] = useState<AgencyClient[]>([]);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [company, setCompany] = useState("");
  const [error, setError] = useState("");
  const [roiInputs, setRoiInputs] = useState({ clients: 10, avgValue: 5000, closeRate: 0.2 });

  const isAgency = user?.plan === "agency";

  useEffect(() => {
    if (!token || !isAgency) {
      setLoading(false);
      return;
    }
    fetch(`${API_URL}/api/agency/clients`, { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => r.json())
      .then((data) => setClients(data.clients || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [token, isAgency]);

  const addClient = async () => {
    if (!token || !name.trim()) return;
    setError("");
    setAdding(true);
    try {
      const res = await fetch(`${API_URL}/api/agency/clients`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ name: name.trim(), email: email.trim() || undefined, company: company.trim() || undefined }),
      });
      if (!res.ok) throw new Error((await res.json()).detail || "Failed");
      const created = await res.json();
      setClients((prev) => [created, ...prev]);
      setName("");
      setEmail("");
      setCompany("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not add client");
    } finally {
      setAdding(false);
    }
  };

  const deleteClient = async (id: string) => {
    if (!token) return;
    try {
      await fetch(`${API_URL}/api/agency/clients/${id}`, { method: "DELETE", headers: { Authorization: `Bearer ${token}` } });
      setClients((prev) => prev.filter((c) => c.id !== id));
    } catch {
      // ignore
    }
  };

  const roiResult =
    roiInputs.clients * roiInputs.avgValue * roiInputs.closeRate;

  if (!isAgency) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-bold text-text-primary">Agency</h1>
          <p className="text-text-secondary mt-1">Client management, white-label reports, and ROI (Agency plan).</p>
        </div>
        <Card>
          <CardHeader>
            <CardTitle>Agency plan required</CardTitle>
            <CardDescription>
              Upgrade to Agency for client management, white-label reports, client portal, and API access.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Link href="/dashboard/settings">
              <Button>Go to billing</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-text-primary">Agency</h1>
        <p className="text-text-secondary mt-1">Manage clients, white-label reports, and estimate ROI.</p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>ROI calculator</CardTitle>
          <CardDescription>Estimate revenue from offering HAWK to clients.</CardDescription>
        </CardHeader>
        <CardContent className="pt-0 space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="space-y-2">
              <label className="text-sm text-text-secondary"># of clients</label>
              <Input
                type="number"
                min={1}
                value={roiInputs.clients}
                onChange={(e) => setRoiInputs((p) => ({ ...p, clients: Math.max(1, parseInt(e.target.value, 10) || 0) }))}
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm text-text-secondary">Avg. contract value ($)</label>
              <Input
                type="number"
                min={0}
                value={roiInputs.avgValue}
                onChange={(e) => setRoiInputs((p) => ({ ...p, avgValue: Math.max(0, parseInt(e.target.value, 10) || 0) }))}
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm text-text-secondary">Close rate (0–1)</label>
              <Input
                type="number"
                min={0}
                max={1}
                step={0.1}
                value={roiInputs.closeRate}
                onChange={(e) => setRoiInputs((p) => ({ ...p, closeRate: Math.max(0, Math.min(1, parseFloat(e.target.value) || 0)) }))}
              />
            </div>
          </div>
          <p className="text-text-primary font-semibold">
            Estimated revenue: <span className="text-accent">${roiResult.toLocaleString()}</span>
          </p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Clients</CardTitle>
          <CardDescription>Add and manage clients. Generate white-label reports from the client record.</CardDescription>
        </CardHeader>
        <CardContent className="pt-0 space-y-4">
          <div className="flex flex-wrap gap-2 items-end">
            <Input
              placeholder="Client name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-40"
            />
            <Input
              placeholder="Email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-48"
            />
            <Input
              placeholder="Company"
              value={company}
              onChange={(e) => setCompany(e.target.value)}
              className="w-40"
            />
            <Button onClick={addClient} disabled={adding || !name.trim()}>
              {adding ? "Adding…" : "Add client"}
            </Button>
          </div>
          {error && <p className="text-sm text-red">{error}</p>}
          {loading ? (
            <p className="text-text-dim">Loading…</p>
          ) : clients.length === 0 ? (
            <p className="text-text-dim">No clients yet.</p>
          ) : (
            <ul className="space-y-2">
              {clients.map((c) => (
                <li
                  key={c.id}
                  className="flex items-center justify-between py-2 border-b border-surface-3 last:border-0"
                >
                  <div>
                    <span className="font-medium text-text-primary">{c.name}</span>
                    {c.company && <span className="text-text-secondary ml-2">({c.company})</span>}
                    {c.email && <span className="text-text-dim text-sm block">{c.email}</span>}
                  </div>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={async () => {
                        if (!token) return;
                        try {
                          const res = await fetch(`${API_URL}/api/agency/clients/${c.id}/report`, {
                            method: "POST",
                            headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
                            body: JSON.stringify({}),
                          });
                          const data = await res.json();
                          const reportId = data.report_id;
                          if (reportId) {
                            const pdfRes = await fetch(`${API_URL}/api/reports/${reportId}/pdf`, { headers: { Authorization: `Bearer ${token}` } });
                            const blob = await pdfRes.blob();
                            const url = URL.createObjectURL(blob);
                            const a = document.createElement("a");
                            a.href = url;
                            a.download = `hawk-report-${c.name || c.id}.pdf`;
                            a.click();
                            URL.revokeObjectURL(url);
                          }
                        } catch {
                          // ignore
                        }
                      }}
                    >
                      Report
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => deleteClient(c.id)}>
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
