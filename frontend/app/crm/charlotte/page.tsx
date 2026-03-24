"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/components/providers/auth-provider";
import { crmCharlotteApi } from "@/lib/crm-api";
import type { CharlotteEmail, CharlotteStats } from "@/lib/crm-types";

export default function CharlottePage() {
  const { token } = useAuth();
  const [stats, setStats] = useState<CharlotteStats | null>(null);
  const [emails, setEmails] = useState<CharlotteEmail[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCampaign, setShowCampaign] = useState(false);
  const [campaignTargets, setCampaignTargets] = useState("");
  const [subject, setSubject] = useState("Quick security check for {{company}}");
  const [body, setBody] = useState("Hi {{contact_name}}, I noticed {{company}} might have some exposure online. I ran a quick scan — want me to send over the results? Takes 2 minutes to review.");
  const [campaignMsg, setCampaignMsg] = useState("");
  const [campaignError, setCampaignError] = useState("");

  const load = async () => {
    if (!token) return;
    try {
      const [s, e] = await Promise.all([
        crmCharlotteApi.getStats(token),
        crmCharlotteApi.listEmails(token),
      ]);
      setStats(s);
      setEmails(e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [token]);

  const sendCampaign = async () => {
    if (!token) return;
    setCampaignError(""); setCampaignMsg("");
    try {
      const lines = campaignTargets.split("\n").filter(Boolean);
      const targets = lines.map((line) => {
        const [company_name, contact_email, contact_name, domain] = line.split(",").map((s) => s.trim());
        return { company_name, contact_email, contact_name, domain };
      }).filter((t) => t.company_name && t.contact_email);

      if (targets.length === 0) return setCampaignError("Enter targets as: Company Name, email@example.com");

      const res = await crmCharlotteApi.createCampaign(token, { targets, subject_template: subject, body_template: body });
      setCampaignMsg(`Queued ${res.queued} emails.`);
      setCampaignTargets("");
      setShowCampaign(false);
      load();
    } catch (e: any) {
      setCampaignError(e.message);
    }
  };

  if (loading) return <p className="text-text-secondary text-sm">Loading…</p>;

  return (
    <div className="max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold">🤖 Charlotte</h1>
          <p className="text-sm text-text-secondary">Automated email outreach</p>
        </div>
        <button onClick={() => setShowCampaign(!showCampaign)} className="bg-purple-600 text-white px-4 py-2 rounded text-sm hover:bg-purple-700">
          + New Campaign
        </button>
      </div>

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-4 gap-4 mb-6">
          {[
            { label: "Sent Today", value: stats.sent_today },
            { label: "Total Sent", value: stats.total_sent },
            { label: "Open Rate", value: `${(stats.open_rate * 100).toFixed(1)}%` },
            { label: "Reply Rate", value: `${(stats.reply_rate * 100).toFixed(1)}%` },
          ].map(({ label, value }) => (
            <div key={label} className="bg-white border border-surface-3 rounded-lg p-4 text-center">
              <p className="text-2xl font-bold">{value}</p>
              <p className="text-xs text-text-secondary mt-1">{label}</p>
            </div>
          ))}
        </div>
      )}

      {campaignMsg && <p className="text-green-600 text-sm mb-4">{campaignMsg}</p>}

      {/* Campaign form */}
      {showCampaign && (
        <div className="bg-white border border-surface-3 rounded-lg p-5 mb-6">
          <h2 className="font-medium mb-4">New Campaign</h2>
          <div className="flex flex-col gap-3">
            <div>
              <label className="text-xs text-text-secondary block mb-1">Targets (one per line: Company, email, contact_name, domain)</label>
              <textarea
                value={campaignTargets}
                onChange={(e) => setCampaignTargets(e.target.value)}
                rows={5}
                placeholder={"Acme Corp, john@acme.com, John, acme.com\nBeta LLC, jane@beta.io, Jane, beta.io"}
                className="w-full border border-surface-3 rounded px-3 py-2 text-sm font-mono"
              />
            </div>
            <div>
              <label className="text-xs text-text-secondary block mb-1">Subject (use {"{{company}}"})</label>
              <input value={subject} onChange={(e) => setSubject(e.target.value)} className="w-full border border-surface-3 rounded px-3 py-2 text-sm" />
            </div>
            <div>
              <label className="text-xs text-text-secondary block mb-1">Body (use {"{{company}}"} and {"{{contact_name}}"})</label>
              <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={4} className="w-full border border-surface-3 rounded px-3 py-2 text-sm" />
            </div>
            {campaignError && <p className="text-red-500 text-xs">{campaignError}</p>}
            <div className="flex gap-2 justify-end">
              <button onClick={() => setShowCampaign(false)} className="px-4 py-2 text-sm text-text-secondary">Cancel</button>
              <button onClick={sendCampaign} className="px-4 py-2 text-sm bg-purple-600 text-white rounded hover:bg-purple-700">Send Campaign</button>
            </div>
          </div>
        </div>
      )}

      {/* Email log */}
      <div className="bg-white border border-surface-3 rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b border-surface-3 font-medium text-sm">Email Log</div>
        <table className="w-full text-sm">
          <thead className="border-b border-surface-3 bg-surface-2">
            <tr>
              <th className="text-left px-4 py-2.5 text-xs text-text-secondary font-medium">To</th>
              <th className="text-left px-4 py-2.5 text-xs text-text-secondary font-medium">Subject</th>
              <th className="text-left px-4 py-2.5 text-xs text-text-secondary font-medium">Status</th>
              <th className="text-left px-4 py-2.5 text-xs text-text-secondary font-medium">Sent</th>
            </tr>
          </thead>
          <tbody>
            {emails.map((e) => (
              <tr key={e.id} className="border-b border-surface-3 last:border-0 hover:bg-surface-2">
                <td className="px-4 py-2.5">{e.to_email}</td>
                <td className="px-4 py-2.5 text-text-secondary truncate max-w-xs">{e.subject || "—"}</td>
                <td className="px-4 py-2.5">
                  <span className={`px-2 py-0.5 rounded text-xs font-medium ${
                    e.status === "replied" ? "bg-green-100 text-green-700" :
                    e.status === "opened" ? "bg-blue-100 text-blue-700" :
                    e.status === "bounced" ? "bg-red-100 text-red-700" :
                    "bg-gray-100 text-gray-600"
                  }`}>{e.status}</span>
                </td>
                <td className="px-4 py-2.5 text-text-secondary text-xs">{e.sent_at ? new Date(e.sent_at).toLocaleDateString() : "—"}</td>
              </tr>
            ))}
            {emails.length === 0 && (
              <tr><td colSpan={4} className="px-4 py-10 text-center text-text-secondary">No emails sent yet.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
