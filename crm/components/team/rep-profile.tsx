"use client";

import { useState } from "react";
import {
  AlertTriangle,
  Calendar,
  ChevronDown,
  Clock,
  DollarSign,
  Phone,
  Star,
  TrendingUp,
  UserCheck,
  X,
} from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { formatCurrency, formatDate, getInitials, cn } from "@/lib/utils";
import type { CRMUser, Commission } from "@/types/crm";

interface RepPerformance {
  closes_this_month: number;
  monthly_target: number;
  conversion_rate: number;
  avg_days_to_close: number;
  commission_earned: number;
  commission_ytd: number;
  rank: number;
  days_since_last_close: number;
  at_risk_14_day: boolean;
  calls_made: number;
  looms_sent: number;
  scans_run: number;
  onboarding_complete: boolean;
  onboarding_steps: {
    label: string;
    done: boolean;
  }[];
}

interface MonthlyBarDatum {
  month: string;
  commission: number;
  closes: number;
}

interface CoachingNote {
  id: string;
  content: string;
  created_by: string;
  created_at: string;
}

interface RepProfileProps {
  rep: CRMUser;
  performance: RepPerformance;
  commissionHistory: MonthlyBarDatum[];
  coachingNotes: CoachingNote[];
  canManage?: boolean;
  onClose?: () => void;
  onAtRiskAction?: (action: "extend_7d" | "begin_removal" | "on_leave") => void;
  onAddCoachingNote?: (note: string) => void;
}

export function RepProfile({
  rep,
  performance,
  commissionHistory,
  coachingNotes,
  canManage,
  onClose,
  onAtRiskAction,
  onAddCoachingNote,
}: RepProfileProps) {
  const [newNote, setNewNote] = useState("");
  const [savingNote, setSavingNote] = useState(false);

  const progress = Math.min(
    100,
    (performance.closes_this_month / Math.max(1, performance.monthly_target)) * 100
  );

  const dayColor =
    performance.days_since_last_close <= 7
      ? "text-green"
      : performance.days_since_last_close <= 13
      ? "text-yellow"
      : "text-red";

  const handleSaveNote = async () => {
    const trimmed = newNote.trim();
    if (!trimmed || !onAddCoachingNote) return;
    setSavingNote(true);
    try {
      onAddCoachingNote(trimmed);
      setNewNote("");
    } finally {
      setSavingNote(false);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-start gap-4 p-6 border-b border-border">
        <div className="relative">
          <Avatar className="w-14 h-14">
            <AvatarFallback className="text-lg">{getInitials(rep.name)}</AvatarFallback>
          </Avatar>
          <div
            className={cn(
              "absolute -bottom-0.5 -right-0.5 w-3.5 h-3.5 rounded-full border-2 border-surface-1",
              rep.status === "active" ? "bg-green" :
              rep.status === "at_risk" ? "bg-yellow" : "bg-red"
            )}
          />
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h2 className="text-lg font-bold text-text-primary">{rep.name}</h2>
            {performance.at_risk_14_day && (
              <Badge variant="destructive" className="gap-1">
                <AlertTriangle className="w-3 h-3" />
                14-Day Rule
              </Badge>
            )}
            {performance.rank === 1 && (
              <Badge variant="warning" className="gap-1">
                <Star className="w-3 h-3" />
                #1 Rep
              </Badge>
            )}
          </div>
          <p className="text-sm text-text-dim capitalize mt-0.5">
            {rep.role.replace("_", " ")} · Rank #{performance.rank}
          </p>
          <div className="flex items-center gap-4 mt-2 text-xs text-text-dim">
            <span className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              <span className={dayColor}>
                {performance.days_since_last_close}d since last close
              </span>
            </span>
            {rep.created_at && (
              <span className="flex items-center gap-1">
                <Calendar className="w-3 h-3" />
                Joined {formatDate(rep.created_at)}
              </span>
            )}
          </div>
        </div>

        {onClose && (
          <button
            onClick={onClose}
            className="p-1.5 rounded-lg hover:bg-surface-2 text-text-dim transition-colors"
            aria-label="Close"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* KPI strip */}
      <div className="grid grid-cols-4 gap-px bg-border border-b border-border">
        {[
          { label: "Closes", value: `${performance.closes_this_month}/${performance.monthly_target}` },
          { label: "Conv. %", value: `${performance.conversion_rate}%` },
          { label: "Avg Days", value: `${performance.avg_days_to_close}d` },
          { label: "Commission", value: formatCurrency(performance.commission_earned) },
        ].map(({ label, value }) => (
          <div key={label} className="bg-surface-1 px-4 py-3 text-center">
            <p className="text-sm font-bold text-text-primary">{value}</p>
            <p className="text-2xs text-text-dim mt-0.5">{label}</p>
          </div>
        ))}
      </div>

      {/* At-risk actions bar */}
      {canManage && performance.at_risk_14_day && onAtRiskAction && (
        <div className="flex items-center gap-3 px-6 py-3 bg-red/5 border-b border-red/20">
          <AlertTriangle className="w-4 h-4 text-red shrink-0" />
          <p className="text-xs text-red flex-1">
            This rep has not closed in {performance.days_since_last_close} days and is in the 14-day removal window.
          </p>
          <Button variant="secondary" size="sm" onClick={() => onAtRiskAction("extend_7d")}>
            Extend 7d
          </Button>
          <Button variant="warning" size="sm" onClick={() => onAtRiskAction("on_leave")}>
            On Leave
          </Button>
          <Button variant="danger" size="sm" onClick={() => onAtRiskAction("begin_removal")}>
            Begin Removal
          </Button>
        </div>
      )}

      {/* Tabs */}
      <div className="flex-1 overflow-hidden">
        <Tabs defaultValue="overview" className="h-full flex flex-col">
          <TabsList className="mx-6 mt-4 shrink-0">
            <TabsTrigger value="overview">Overview</TabsTrigger>
            <TabsTrigger value="commissions">Commissions</TabsTrigger>
            <TabsTrigger value="coaching">Coaching Notes</TabsTrigger>
            <TabsTrigger value="onboarding">Onboarding</TabsTrigger>
          </TabsList>

          {/* Overview */}
          <TabsContent value="overview" className="flex-1 overflow-y-auto px-6 pb-6 space-y-4 mt-4">
            {/* Daily non-negotiables */}
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Daily Non-Negotiables (Today)</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {[
                  { label: "Calls made", value: performance.calls_made, target: rep.daily_call_target ?? 30 },
                  { label: "Looms sent", value: performance.looms_sent, target: rep.daily_loom_target ?? 5 },
                  { label: "Scans run", value: performance.scans_run, target: rep.daily_scan_target ?? 10 },
                ].map(({ label, value, target }) => {
                  const pct = Math.min(100, (value / Math.max(1, target)) * 100);
                  return (
                    <div key={label}>
                      <div className="flex items-center justify-between text-xs mb-1">
                        <span className="text-text-dim">{label}</span>
                        <span className="font-semibold text-text-primary">
                          {value}/{target}
                        </span>
                      </div>
                      <div className="h-1.5 bg-surface-3 rounded-full overflow-hidden">
                        <div
                          className={cn(
                            "h-full rounded-full transition-all",
                            pct >= 100 ? "bg-green" : pct >= 50 ? "bg-accent" : "bg-red"
                          )}
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </CardContent>
            </Card>

            {/* Monthly close progress */}
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Monthly Close Progress</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center justify-between text-xs mb-2">
                  <span className="text-text-dim">
                    {performance.closes_this_month} of {performance.monthly_target} closes
                  </span>
                  <span className="font-bold text-text-primary">{Math.round(progress)}%</span>
                </div>
                <div className="h-2 bg-surface-3 rounded-full overflow-hidden">
                  <div
                    className={cn(
                      "h-full rounded-full transition-all",
                      progress >= 100 ? "bg-green" :
                      performance.at_risk_14_day ? "bg-red" : "bg-accent"
                    )}
                    style={{ width: `${progress}%` }}
                  />
                </div>
              </CardContent>
            </Card>

            {/* YTD */}
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Year-to-Date</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-full bg-green/10 flex items-center justify-center shrink-0">
                    <DollarSign className="w-5 h-5 text-green" />
                  </div>
                  <div>
                    <p className="text-xl font-bold text-text-primary">
                      {formatCurrency(performance.commission_ytd)}
                    </p>
                    <p className="text-xs text-text-dim">Total commissions earned YTD</p>
                  </div>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          {/* Commissions */}
          <TabsContent value="commissions" className="flex-1 overflow-y-auto px-6 pb-6 mt-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">12-Month Commission History</CardTitle>
              </CardHeader>
              <CardContent>
                {commissionHistory.length > 0 ? (
                  <ResponsiveContainer width="100%" height={200}>
                    <BarChart data={commissionHistory} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
                      <XAxis
                        dataKey="month"
                        tick={{ fill: "#6B7280", fontSize: 10 }}
                        axisLine={false}
                        tickLine={false}
                      />
                      <YAxis
                        tick={{ fill: "#6B7280", fontSize: 10 }}
                        axisLine={false}
                        tickLine={false}
                        tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
                        width={40}
                      />
                      <Tooltip
                        contentStyle={{ background: "#0D0B14", border: "1px solid #1F1B2E", borderRadius: 8 }}
                        labelStyle={{ color: "#E2E0E8" }}
                        itemStyle={{ color: "#A78BFA" }}
                        formatter={(val: number) => [formatCurrency(val), "Commission"]}
                      />
                      <Bar dataKey="commission" fill="#7C3AED" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                ) : (
                  <p className="text-sm text-text-dim text-center py-8">No commission history yet.</p>
                )}
              </CardContent>
            </Card>
          </TabsContent>

          {/* Coaching Notes */}
          <TabsContent value="coaching" className="flex-1 overflow-y-auto px-6 pb-6 mt-4 space-y-4">
            {canManage && onAddCoachingNote && (
              <Card>
                <CardContent className="pt-4 space-y-3">
                  <Textarea
                    placeholder="Add a private coaching note for this rep..."
                    value={newNote}
                    onChange={(e) => setNewNote(e.target.value)}
                    rows={3}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                        e.preventDefault();
                        handleSaveNote();
                      }
                    }}
                  />
                  <div className="flex items-center justify-between">
                    <span className="text-2xs text-text-dim">Cmd+Enter to save</span>
                    <Button
                      size="sm"
                      onClick={handleSaveNote}
                      disabled={!newNote.trim() || savingNote}
                    >
                      Save Note
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )}

            {coachingNotes.length === 0 ? (
              <div className="text-center py-12">
                <UserCheck className="w-8 h-8 text-text-dim mx-auto mb-2" />
                <p className="text-sm text-text-dim">No coaching notes yet.</p>
              </div>
            ) : (
              <div className="space-y-3">
                {coachingNotes.map((note) => (
                  <Card key={note.id}>
                    <CardContent className="pt-4">
                      <p className="text-sm text-text-secondary whitespace-pre-wrap">{note.content}</p>
                      <p className="text-2xs text-text-dim mt-2">
                        {note.created_by} · {formatDate(note.created_at)}
                      </p>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </TabsContent>

          {/* Onboarding */}
          <TabsContent value="onboarding" className="flex-1 overflow-y-auto px-6 pb-6 mt-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm flex items-center gap-2">
                  Onboarding Status
                  <Badge variant={performance.onboarding_complete ? "success" : "warning"}>
                    {performance.onboarding_complete ? "Complete" : "In Progress"}
                  </Badge>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {performance.onboarding_steps.map((step) => (
                  <div key={step.label} className="flex items-center gap-3">
                    <div className={cn(
                      "w-4 h-4 rounded-full flex items-center justify-center shrink-0",
                      step.done ? "bg-green" : "bg-surface-3"
                    )}>
                      {step.done && (
                        <svg className="w-2.5 h-2.5 text-white" fill="none" viewBox="0 0 12 12">
                          <path d="M2 6l3 3 5-5" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      )}
                    </div>
                    <span className={cn(
                      "text-sm",
                      step.done ? "text-text-secondary line-through" : "text-text-primary"
                    )}>
                      {step.label}
                    </span>
                  </div>
                ))}
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
