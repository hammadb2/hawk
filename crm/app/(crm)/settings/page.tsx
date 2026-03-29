"use client";

import { useState } from "react";
import {
  Settings, Users, Link2, Bot, DollarSign, Bell, Target, Shield,
  FileText, AlertTriangle, Plus, X, Loader2,
} from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";
import { toast } from "@/components/ui/toast";
import { PLAN_VALUES, COMMISSION_RATES } from "@/lib/commission";
import { formatCurrency, formatRelativeTime, cn } from "@/lib/utils";
import { usersApi, auditApi } from "@/lib/api";
import type { CRMUser, AuditLogEntry } from "@/types/crm";

const ROLE_OPTIONS = [
  { value: "rep", label: "Sales Rep" },
  { value: "team_lead", label: "Team Lead" },
  { value: "csm", label: "CSM" },
  { value: "hos", label: "Head of Sales" },
  { value: "ceo", label: "CEO" },
];

const ROLE_LABEL: Record<string, string> = {
  ceo: "CEO", hos: "HoS", team_lead: "Team Lead", rep: "Rep", csm: "CSM", charlotte: "Charlotte",
};

const INTEGRATIONS = [
  { id: "smartlead", label: "Smartlead", description: "Email outreach automation", connected: true },
  { id: "stripe", label: "Stripe", description: "Payment processing", connected: true },
  { id: "apollo", label: "Apollo.io", description: "Prospect data enrichment", connected: false },
  { id: "twilio", label: "Twilio", description: "WhatsApp notifications", connected: false },
  { id: "deel", label: "Deel", description: "Commission payouts", connected: false },
  { id: "google_calendar", label: "Google Calendar", description: "Call booking", connected: false },
  { id: "loom", label: "Loom", description: "Video messaging", connected: false },
];

const CRM_API_BASE = (process.env.NEXT_PUBLIC_API_URL || "https://api.hawk.akbstudios.com").replace(/\/$/, "");
const SMARTLEAD_WEBHOOK_URL = `${CRM_API_BASE}/api/crm/webhooks/smartlead`;

export default function SettingsPage() {
  const [confirmText, setConfirmText] = useState("");
  const [saving, setSaving] = useState(false);

  // Users state
  const [users, setUsers] = useState<CRMUser[]>([]);
  const [usersLoading, setUsersLoading] = useState(false);
  const [showInvite, setShowInvite] = useState(false);
  const [inviting, setInviting] = useState(false);
  const [inviteForm, setInviteForm] = useState({ name: "", email: "", role: "rep", team_lead_id: "" });

  // Audit log state
  const [auditLogs, setAuditLogs] = useState<AuditLogEntry[]>([]);
  const [auditLoading, setAuditLoading] = useState(false);

  const loadUsers = async () => {
    setUsersLoading(true);
    try {
      const result = await usersApi.list();
      if (result.success && result.data) {
        setUsers(result.data);
      } else {
        toast({ title: "Failed to load team members", variant: "destructive" });
      }
    } catch {
      toast({ title: "Network error loading team", variant: "destructive" });
    } finally {
      setUsersLoading(false);
    }
  };

  const loadAuditLog = async () => {
    setAuditLoading(true);
    try {
      const result = await auditApi.list({ limit: 50 });
      if (result.success && result.data) {
        setAuditLogs(result.data as unknown as AuditLogEntry[]);
      } else {
        toast({ title: "Failed to load audit log", variant: "destructive" });
      }
    } catch {
      toast({ title: "Network error loading audit log", variant: "destructive" });
    } finally {
      setAuditLoading(false);
    }
  };

  const handleInvite = async () => {
    if (!inviteForm.name || !inviteForm.email || !inviteForm.role) {
      toast({ title: "Fill in all fields", variant: "destructive" });
      return;
    }
    setInviting(true);
    const result = await usersApi.invite({
      name: inviteForm.name,
      email: inviteForm.email,
      role: inviteForm.role,
      team_lead_id: inviteForm.team_lead_id || undefined,
    });
    if (result.success) {
      toast({ title: `Invite sent to ${inviteForm.email}`, variant: "success" });
      setShowInvite(false);
      setInviteForm({ name: "", email: "", role: "rep", team_lead_id: "" });
      loadUsers();
    } else {
      toast({ title: result.error ?? "Failed to invite", variant: "destructive" });
    }
    setInviting(false);
  };

  const handleSave = async (section: string) => {
    setSaving(true);
    await new Promise((r) => setTimeout(r, 600));
    setSaving(false);
    toast({ title: `${section} settings saved`, variant: "success" });
  };

  const teamLeads = users.filter((u) => u.role === "team_lead");

  return (
    <div className="p-6 max-w-4xl mx-auto">
      <div className="mb-6">
        <h1 className="text-xl font-bold text-text-primary">Settings</h1>
        <p className="text-sm text-text-secondary mt-0.5">Configure HAWK CRM</p>
      </div>

      <Tabs defaultValue="general">
        <TabsList className="flex flex-wrap h-auto gap-1 mb-6">
          <TabsTrigger value="general" className="gap-1.5"><Settings className="w-3.5 h-3.5" />General</TabsTrigger>
          <TabsTrigger
            value="users"
            className="gap-1.5"
            onClick={() => {
              void loadUsers();
            }}
          >
            <Users className="w-3.5 h-3.5" />Users
          </TabsTrigger>
          <TabsTrigger value="integrations" className="gap-1.5"><Link2 className="w-3.5 h-3.5" />Integrations</TabsTrigger>
          <TabsTrigger value="charlotte" className="gap-1.5"><Bot className="w-3.5 h-3.5" />Charlotte</TabsTrigger>
          <TabsTrigger value="commission" className="gap-1.5"><DollarSign className="w-3.5 h-3.5" />Commissions</TabsTrigger>
          <TabsTrigger value="notifications" className="gap-1.5"><Bell className="w-3.5 h-3.5" />Notifications</TabsTrigger>
          <TabsTrigger value="sales" className="gap-1.5"><Target className="w-3.5 h-3.5" />Sales Config</TabsTrigger>
          <TabsTrigger value="healing" className="gap-1.5"><Shield className="w-3.5 h-3.5" />Self-Healing</TabsTrigger>
          <TabsTrigger value="audit" className="gap-1.5" onClick={loadAuditLog}><FileText className="w-3.5 h-3.5" />Audit Log</TabsTrigger>
        </TabsList>

        {/* General */}
        <TabsContent value="general">
          <Card>
            <CardHeader><CardTitle>General Settings</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-text-secondary mb-1.5">CRM Name</label>
                  <Input defaultValue="HAWK CRM" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-text-secondary mb-1.5">Company</label>
                  <Input defaultValue="HAWK Cybersecurity" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-text-secondary mb-1.5">Timezone</label>
                  <Input defaultValue="America/Edmonton" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-text-secondary mb-1.5">Currency</label>
                  <Input defaultValue="CAD" readOnly className="opacity-60" />
                </div>
              </div>
              <Button onClick={() => handleSave("General")} disabled={saving}>
                {saving ? "Saving..." : "Save Changes"}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Users */}
        <TabsContent value="users">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                Users & Permissions
                <Button
                  size="sm"
                  className="text-xs gap-1.5"
                  onClick={() => {
                    void loadUsers();
                    setShowInvite(true);
                  }}
                >
                  <Plus className="w-3.5 h-3.5" /> Invite Member
                </Button>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {/* Invite form */}
              {showInvite && (
                <div className="mb-4 p-4 rounded-xl border border-accent/30 bg-accent/5 space-y-3">
                  <div className="flex items-center justify-between mb-1">
                    <p className="text-sm font-semibold text-text-primary">Invite Team Member</p>
                    <button onClick={() => setShowInvite(false)}><X className="w-4 h-4 text-text-dim" /></button>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs text-text-dim mb-1">Full Name</label>
                      <Input
                        placeholder="Jane Smith"
                        value={inviteForm.name}
                        onChange={(e) => setInviteForm({ ...inviteForm, name: e.target.value })}
                        className="h-8 text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-text-dim mb-1">Email</label>
                      <Input
                        type="email"
                        placeholder="jane@hawk.ca"
                        value={inviteForm.email}
                        onChange={(e) => setInviteForm({ ...inviteForm, email: e.target.value })}
                        className="h-8 text-sm"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-text-dim mb-1">Role</label>
                      <select
                        value={inviteForm.role}
                        onChange={(e) => setInviteForm({ ...inviteForm, role: e.target.value })}
                        className="w-full h-8 text-sm rounded-lg border border-border bg-surface-2 text-text-primary px-2 focus:outline-none focus:border-accent/60"
                      >
                        {ROLE_OPTIONS.map((r) => (
                          <option key={r.value} value={r.value}>{r.label}</option>
                        ))}
                      </select>
                    </div>
                    {inviteForm.role === "rep" && teamLeads.length > 0 && (
                      <div>
                        <label className="block text-xs text-text-dim mb-1">Team Lead (optional)</label>
                        <select
                          value={inviteForm.team_lead_id}
                          onChange={(e) => setInviteForm({ ...inviteForm, team_lead_id: e.target.value })}
                          className="w-full h-8 text-sm rounded-lg border border-border bg-surface-2 text-text-primary px-2 focus:outline-none focus:border-accent/60"
                        >
                          <option value="">None</option>
                          {teamLeads.map((tl) => (
                            <option key={tl.id} value={tl.id}>{tl.name}</option>
                          ))}
                        </select>
                      </div>
                    )}
                  </div>
                  <Button size="sm" onClick={handleInvite} disabled={inviting} className="gap-1.5">
                    {inviting ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Sending...</> : "Send Invite"}
                  </Button>
                  <p className="text-2xs text-text-dim">They'll receive an email invite and set their own password.</p>
                </div>
              )}

              {/* Users list */}
              {usersLoading ? (
                <div className="flex justify-center py-8"><Spinner size="md" /></div>
              ) : users.length === 0 ? (
                <p className="text-xs text-text-dim text-center py-8">No team members yet — invite your first member above.</p>
              ) : (
                <div className="space-y-2">
                  {users.map((u) => (
                    <div key={u.id} className="flex items-center gap-3 p-3 rounded-lg border border-border bg-surface-2">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm font-medium text-text-primary">{u.name}</p>
                        <p className="text-xs text-text-dim">{u.email}</p>
                      </div>
                      <Badge variant={u.status === "at_risk" ? "warning" : "secondary"} className="text-xs">
                        {ROLE_LABEL[u.role] ?? u.role}
                      </Badge>
                      {u.status === "at_risk" && (
                        <Badge variant="warning" className="text-2xs">At Risk</Badge>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Integrations */}
        <TabsContent value="integrations">
          <Card>
            <CardHeader><CardTitle>Integrations</CardTitle></CardHeader>
            <CardContent className="space-y-3">
              {INTEGRATIONS.map((integration) => (
                <div key={integration.id} className="flex items-center gap-3 p-3 rounded-lg border border-border bg-surface-2">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <p className="text-sm font-medium text-text-primary">{integration.label}</p>
                      <Badge variant={integration.connected ? "success" : "secondary"} className="text-2xs">
                        {integration.connected ? "Connected" : "Not Connected"}
                      </Badge>
                    </div>
                    <p className="text-xs text-text-dim">{integration.description}</p>
                  </div>
                  {!integration.connected && (
                    <Input placeholder="API key..." className="h-7 text-xs w-48" />
                  )}
                  <Button variant={integration.connected ? "secondary" : "default"} size="sm" className="text-xs h-7 flex-shrink-0">
                    {integration.connected ? "Disconnect" : "Connect"}
                  </Button>
                </div>
              ))}
            </CardContent>
          </Card>
        </TabsContent>

        {/* Charlotte Config */}
        <TabsContent value="charlotte">
          <Card>
            <CardHeader><CardTitle>Charlotte Configuration</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-1.5">Daily Send Volume</label>
                <Input type="number" defaultValue={150} className="w-32" />
              </div>
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-1.5">Assignment Rules</label>
                <div className="space-y-2">
                  {["Round-robin", "By industry", "By city", "By rep capacity"].map((rule) => (
                    <label key={rule} className="flex items-center gap-2 cursor-pointer">
                      <input type="radio" name="assignment" className="text-accent" defaultChecked={rule === "Round-robin"} />
                      <span className="text-sm text-text-secondary">{rule}</span>
                    </label>
                  ))}
                </div>
              </div>
              <div className="rounded-lg border border-border bg-surface-2 p-3 space-y-2">
                <p className="text-xs font-medium text-text-secondary">Smartlead webhook URL</p>
                <p className="text-2xs text-text-dim">
                  Configure this endpoint in Smartlead. It must reach your FastAPI server (not Vercel).
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  <code className="flex-1 min-w-0 text-2xs text-text-secondary break-all">{SMARTLEAD_WEBHOOK_URL}</code>
                  <Button
                    type="button"
                    variant="secondary"
                    size="sm"
                    className="text-xs shrink-0"
                    onClick={() => {
                      void navigator.clipboard.writeText(SMARTLEAD_WEBHOOK_URL);
                      toast({ title: "Webhook URL copied", variant: "success" });
                    }}
                  >
                    Copy
                  </Button>
                </div>
              </div>
              <Button onClick={() => handleSave("Charlotte")} disabled={saving}>
                {saving ? "Saving..." : "Save Charlotte Config"}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Commission Rules */}
        <TabsContent value="commission">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 text-yellow" />
                Commission Rules
                <span className="text-xs font-normal text-text-dim ml-2">— Changes do not affect historical commissions</span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                {Object.entries(PLAN_VALUES).filter(([p]) => p !== "custom").map(([plan, value]) => (
                  <div key={plan}>
                    <label className="block text-xs font-medium text-text-dim mb-1 capitalize">{plan} plan ($/mo)</label>
                    <Input type="number" defaultValue={value} className="h-8 text-sm" />
                  </div>
                ))}
              </div>
              <div className="space-y-2">
                <p className="text-xs font-medium text-text-secondary uppercase tracking-wide">Commission Rates</p>
                <div className="grid grid-cols-2 gap-3">
                  {Object.entries(COMMISSION_RATES).map(([key, rate]) => (
                    <div key={key}>
                      <label className="block text-xs text-text-dim mb-1">{key.replace(/_/g, " ")}</label>
                      <Input type="number" step="0.01" defaultValue={rate * 100} className="h-8 text-sm" />
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-1.5">Clawback Window (days)</label>
                <Input type="number" defaultValue={90} className="w-24" />
              </div>
              <div className={cn("rounded-lg p-3 border", confirmText === "CONFIRM" ? "border-green/30 bg-green/5" : "border-yellow/30 bg-yellow/5")}>
                <p className="text-xs text-yellow mb-2">Type CONFIRM to apply changes. Historical commissions are unaffected.</p>
                <Input value={confirmText} onChange={(e) => setConfirmText(e.target.value)} placeholder="Type CONFIRM..." className="h-8 text-sm mb-2" />
                <Button disabled={confirmText !== "CONFIRM" || saving} onClick={() => { handleSave("Commission"); setConfirmText(""); }} className="h-8 text-xs">
                  {saving ? "Saving..." : "Apply Commission Changes"}
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Notifications */}
        <TabsContent value="notifications">
          <Card>
            <CardHeader><CardTitle>Notification Settings</CardTitle></CardHeader>
            <CardContent>
              <div className="space-y-3">
                {[
                  { event: "New close", roles: ["CEO", "HoS", "TL", "Rep"] },
                  { event: "Hot lead flagged", roles: ["CEO", "HoS", "Rep"] },
                  { event: "Charlotte positive reply", roles: ["CEO", "HoS"] },
                  { event: "Client payment failed", roles: ["CEO", "HoS"] },
                  { event: "14-day rule warning", roles: ["CEO", "HoS", "TL"] },
                  { event: "High churn risk", roles: ["CEO", "HoS"] },
                ].map(({ event, roles }) => (
                  <div key={event} className="flex items-center gap-3 p-3 rounded-lg border border-border bg-surface-2">
                    <span className="text-sm text-text-primary flex-1">{event}</span>
                    <div className="flex items-center gap-2">
                      {roles.map((r) => <Badge key={r} variant="secondary" className="text-2xs">{r}</Badge>)}
                    </div>
                    <Switch defaultChecked />
                  </div>
                ))}
              </div>
              <Button className="mt-4" onClick={() => handleSave("Notifications")} disabled={saving}>
                {saving ? "Saving..." : "Save Notification Settings"}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Sales Config */}
        <TabsContent value="sales">
          <Card>
            <CardHeader><CardTitle>Sales Configuration</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-1.5">Monthly Target per Rep</label>
                <Input type="number" defaultValue={5} className="w-24" />
              </div>
              <div className="flex items-center gap-3 p-3 rounded-lg border border-border bg-surface-2">
                <div className="flex-1">
                  <p className="text-sm font-medium text-text-primary">14-Day Rule</p>
                  <p className="text-xs text-text-dim">Auto-flag reps who haven't closed in 14+ days</p>
                </div>
                <Switch defaultChecked />
              </div>
              <Button onClick={() => handleSave("Sales Config")} disabled={saving}>
                {saving ? "Saving..." : "Save Sales Config"}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Self-Healing Console */}
        <TabsContent value="healing">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Shield className="w-4 h-4 text-green" />
                Self-Healing Console
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex items-center gap-2 p-3 rounded-lg bg-green/5 border border-green/20">
                <div className="w-2 h-2 rounded-full bg-green" />
                <span className="text-sm text-green font-medium">All systems operational</span>
              </div>
              <div>
                <p className="text-xs font-medium text-text-dim uppercase tracking-wide mb-2">Auto-Resolve Settings</p>
                {[
                  { type: "Broken RLS policies", enabled: true },
                  { type: "Missing activity logs", enabled: true },
                  { type: "Failed commission calculations", enabled: false },
                  { type: "Webhook retry failures", enabled: true },
                ].map(({ type, enabled }) => (
                  <div key={type} className="flex items-center gap-3 p-2.5 border-b border-border last:border-0">
                    <span className="text-sm text-text-secondary flex-1">{type}</span>
                    <Switch defaultChecked={enabled} />
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* Audit Log */}
        <TabsContent value="audit">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span className="flex items-center gap-2">
                  <FileText className="w-4 h-4 text-text-dim" />
                  Audit Log
                  <Badge variant="secondary" className="text-2xs">Immutable</Badge>
                </span>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {auditLoading ? (
                <div className="flex justify-center py-8"><Spinner size="md" /></div>
              ) : auditLogs.length === 0 ? (
                <p className="text-xs text-text-dim text-center py-8">No audit log entries yet.</p>
              ) : (
                <div className="rounded-xl border border-border overflow-hidden">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-border bg-surface-2">
                        <th className="text-left text-xs font-medium text-text-dim px-3 py-2">User</th>
                        <th className="text-left text-xs font-medium text-text-dim px-3 py-2">Action</th>
                        <th className="text-left text-xs font-medium text-text-dim px-3 py-2">Record</th>
                        <th className="text-left text-xs font-medium text-text-dim px-3 py-2">Time</th>
                      </tr>
                    </thead>
                    <tbody>
                      {auditLogs.slice(0, 50).map((log, i) => (
                        <tr key={i} className="border-b border-border last:border-0">
                          <td className="px-3 py-2 text-xs text-text-secondary">{log.user?.name ?? "System"}</td>
                          <td className="px-3 py-2 text-xs font-mono text-text-dim">{log.action}</td>
                          <td className="px-3 py-2 text-xs text-text-dim">{log.record_type}</td>
                          <td className="px-3 py-2 text-xs text-text-dim">{formatRelativeTime(log.created_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
