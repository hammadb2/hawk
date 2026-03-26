"use client";

import { useState, useEffect } from "react";
import { Users, TrendingUp, DollarSign, Target } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatCard } from "@/components/ui/stat-card";
import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";
import { formatCurrency, cn } from "@/lib/utils";

export function HOSDashboard() {
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setTimeout(() => setLoading(false), 700);
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Spinner size="lg" />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div>
        <h1 className="text-xl font-bold text-text-primary">Sales Dashboard</h1>
        <p className="text-sm text-text-secondary mt-0.5">Team performance overview.</p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard label="Team Closes" value="14" subValue="This month" trend={{ value: 8 }} accent />
        <StatCard label="Total Pipeline" value={formatCurrency(84000)} trend={{ value: 12 }} />
        <StatCard label="Avg Close Rate" value="28%" trend={{ value: 3 }} />
        <StatCard label="MRR Added" value={formatCurrency(2800)} trend={{ value: 14 }} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users className="w-4 h-4 text-accent-light" />
              Rep Leaderboard
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {[
              { name: "Jordan K.", closes: 5, target: 5, commission: 1485, atRisk: false },
              { name: "Alex M.", closes: 4, target: 5, commission: 1188, atRisk: false },
              { name: "Sarah L.", closes: 3, target: 5, commission: 891, atRisk: false },
              { name: "Mike T.", closes: 1, target: 5, commission: 297, atRisk: true },
              { name: "Emma R.", closes: 1, target: 5, commission: 297, atRisk: true },
            ].map((rep, i) => (
              <div key={rep.name} className="flex items-center gap-3">
                <span className={cn(
                  "text-sm font-bold w-5 text-center",
                  i === 0 ? "text-yellow" : "text-text-dim"
                )}>
                  #{i + 1}
                </span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-sm font-medium text-text-primary">{rep.name}</span>
                    {rep.atRisk && <Badge variant="warning" className="text-2xs">At Risk</Badge>}
                  </div>
                  <div className="h-1.5 bg-surface-3 rounded-full overflow-hidden">
                    <div
                      className={cn(
                        "h-full rounded-full",
                        rep.closes >= rep.target ? "bg-green" : "bg-accent"
                      )}
                      style={{ width: `${(rep.closes / rep.target) * 100}%` }}
                    />
                  </div>
                </div>
                <div className="text-right flex-shrink-0">
                  <p className="text-sm font-semibold text-text-primary">{rep.closes}/{rep.target}</p>
                  <p className="text-2xs text-text-dim">{formatCurrency(rep.commission)}</p>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Target className="w-4 h-4 text-green" />
              Team Target Progress
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-center mb-6">
              <div className="text-5xl font-bold text-text-primary mb-1">14</div>
              <div className="text-sm text-text-secondary">of 25 team target</div>
            </div>
            <div className="h-4 bg-surface-3 rounded-full overflow-hidden mb-3">
              <div
                className="h-full bg-gradient-to-r from-accent to-accent-light rounded-full transition-all"
                style={{ width: "56%" }}
              />
            </div>
            <div className="flex items-center justify-between text-xs text-text-dim">
              <span>56% achieved</span>
              <span>11 closes remaining</span>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
