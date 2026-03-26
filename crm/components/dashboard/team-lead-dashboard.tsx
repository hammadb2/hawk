"use client";

import { useState, useEffect } from "react";
import { Users, Target } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatCard } from "@/components/ui/stat-card";
import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";
import { formatCurrency, cn } from "@/lib/utils";
import { useCRMStore } from "@/store/crm-store";

export function TeamLeadDashboard() {
  const { user } = useCRMStore();
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setTimeout(() => setLoading(false), 600);
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-6xl mx-auto">
      <div>
        <h1 className="text-xl font-bold text-text-primary">Team Dashboard</h1>
        <p className="text-sm text-text-secondary mt-0.5">Your team's performance.</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Team Closes" value="7" subValue="This month" trend={{ value: 5 }} accent />
        <StatCard label="Your Closes" value="2" trend={{ value: 0 }} />
        <StatCard label="Override Earned" value={formatCurrency(210)} />
        <StatCard label="Team Pipeline" value={formatCurrency(42000)} trend={{ value: 8 }} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Users className="w-4 h-4 text-accent-light" />
            My Team
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {[
            { name: "Jordan K.", closes: 3, target: 5, atRisk: false, lastClose: "2 days ago" },
            { name: "Alex M.", closes: 2, target: 5, atRisk: false, lastClose: "5 days ago" },
            { name: "Sarah L.", closes: 2, target: 5, atRisk: false, lastClose: "1 day ago" },
            { name: "Mike T.", closes: 0, target: 5, atRisk: true, lastClose: "18 days ago" },
          ].map((rep) => (
            <div key={rep.name} className={cn(
              "flex items-center gap-3 p-3 rounded-lg border transition-all",
              rep.atRisk ? "border-red/30 bg-red/5" : "border-border bg-surface-2"
            )}>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-sm font-medium text-text-primary">{rep.name}</span>
                  {rep.atRisk && <Badge variant="destructive" className="text-2xs">14-Day Risk</Badge>}
                </div>
                <div className="h-1.5 bg-surface-3 rounded-full overflow-hidden">
                  <div
                    className={cn(
                      "h-full rounded-full",
                      rep.closes >= rep.target ? "bg-green" : rep.atRisk ? "bg-red" : "bg-accent"
                    )}
                    style={{ width: `${(rep.closes / rep.target) * 100}%` }}
                  />
                </div>
              </div>
              <div className="text-right flex-shrink-0">
                <p className="text-sm font-semibold text-text-primary">{rep.closes}/{rep.target}</p>
                <p className="text-2xs text-text-dim">Last: {rep.lastClose}</p>
              </div>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
