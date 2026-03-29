"use client";

import { useState, useEffect, useMemo } from "react";
import { Building2, Flame } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";
import { EmptyState } from "@/components/ui/empty-state";
import { HawkScoreRing } from "@/components/ui/hawk-score-ring";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { ProspectDrawer } from "@/components/prospect/profile-drawer";
import { AddProspectModal } from "@/components/prospect/add-prospect-modal";
import { useCRMStore } from "@/store/crm-store";
import { prospectsApi } from "@/lib/api";
import { toast } from "@/components/ui/toast";
import { stageLabel, stageBgColor, formatRelativeTime, getInitials, daysSince, cn } from "@/lib/utils";
import type { Prospect } from "@/types/crm";

export default function ProspectsPage() {
  const { prospects, setProspects, setSelectedProspect, setDrawerOpen } = useCRMStore();
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [hotOnly, setHotOnly] = useState(false);
  const [addOpen, setAddOpen] = useState(false);

  // Count uncontacted today (no activity today)
  const uncontactedToday = useMemo(() => {
    const today = new Date().toDateString();
    return prospects.filter((p) => {
      const lastActivity = new Date(p.last_activity_at).toDateString();
      return lastActivity !== today && p.stage !== "closed_won" && p.stage !== "lost";
    }).length;
  }, [prospects]);

  useEffect(() => {
    const load = async () => {
      const hasData = useCRMStore.getState().prospects.length > 0;
      if (!hasData) setLoading(true);
      try {
        const result = await prospectsApi.list();
        if (result.success && result.data) {
          setProspects(result.data);
        } else if (!hasData) {
          toast({ title: "Failed to load prospects", variant: "destructive" });
        }
      } catch {
        if (!hasData) toast({ title: "Network error", variant: "destructive" });
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [setProspects]);

  const filtered = useMemo(() => {
    return prospects.filter((p) => {
      if (hotOnly && !p.is_hot) return false;
      if (search) {
        const q = search.toLowerCase();
        if (!p.company_name.toLowerCase().includes(q) && !p.domain.toLowerCase().includes(q)) {
          return false;
        }
      }
      return true;
    });
  }, [prospects, search, hotOnly]);

  const openProspect = (p: Prospect) => {
    setSelectedProspect(p);
    setDrawerOpen(true);
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-3 px-4 py-3 border-b border-border flex-shrink-0">
        <div className="flex-1">
          <h1 className="text-base font-semibold text-text-primary">
            Prospects
            {uncontactedToday > 0 && (
              <Badge variant="warning" className="ml-2 text-xs">
                {uncontactedToday} uncontacted today
              </Badge>
            )}
          </h1>
          <p className="text-xs text-text-dim">{filtered.length} prospects</p>
        </div>

        <button
          onClick={() => setHotOnly(!hotOnly)}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium border transition-all",
            hotOnly
              ? "bg-yellow/10 border-yellow/30 text-yellow"
              : "border-border text-text-dim hover:text-text-secondary hover:bg-surface-2"
          )}
        >
          <Flame className="w-3.5 h-3.5" />
          Hot only
        </button>

        <div className="w-56">
          <Input
            placeholder="Search prospects..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-8 text-xs"
          />
        </div>

        <Button size="sm" className="h-8 text-xs" onClick={() => setAddOpen(true)}>
          + Add Prospect
        </Button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Spinner size="lg" />
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={Building2}
            title="No prospects found"
            description="Add your first prospect or adjust your search."
            action={{ label: "Add Prospect", onClick: () => setAddOpen(true) }}
          />
        ) : (
          <div className="p-4">
            <div className="rounded-xl border border-border overflow-hidden bg-surface-1">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border bg-surface-2">
                    <th className="text-left text-xs font-medium text-text-dim px-4 py-3">Company</th>
                    <th className="text-left text-xs font-medium text-text-dim px-4 py-3 hidden sm:table-cell">Domain</th>
                    <th className="text-left text-xs font-medium text-text-dim px-4 py-3">Stage</th>
                    <th className="text-left text-xs font-medium text-text-dim px-4 py-3 hidden lg:table-cell">Score</th>
                    <th className="text-left text-xs font-medium text-text-dim px-4 py-3 hidden lg:table-cell">Rep</th>
                    <th className="text-left text-xs font-medium text-text-dim px-4 py-3 hidden xl:table-cell">Last Activity</th>
                    <th className="text-left text-xs font-medium text-text-dim px-4 py-3 hidden xl:table-cell">Source</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((p, i) => (
                    <tr
                      key={p.id}
                      onClick={() => openProspect(p)}
                      className={cn(
                        "cursor-pointer hover:bg-surface-2 transition-colors",
                        i !== filtered.length - 1 && "border-b border-border"
                      )}
                    >
                      <td className="px-4 py-3">
                        <div className="flex items-center gap-2">
                          {p.is_hot && <span className="text-yellow text-xs">★</span>}
                          <span className="text-sm font-medium text-text-primary">{p.company_name}</span>
                        </div>
                        {p.city && <span className="text-xs text-text-dim">{p.city}</span>}
                      </td>
                      <td className="px-4 py-3 hidden sm:table-cell">
                        <span className="text-xs text-text-dim">{p.domain}</span>
                      </td>
                      <td className="px-4 py-3">
                        <span className={cn("text-xs font-medium px-2 py-0.5 rounded-md", stageBgColor(p.stage))}>
                          {stageLabel(p.stage)}
                        </span>
                      </td>
                      <td className="px-4 py-3 hidden lg:table-cell">
                        <HawkScoreRing score={p.hawk_score} size="sm" />
                      </td>
                      <td className="px-4 py-3 hidden lg:table-cell">
                        {p.assigned_rep ? (
                          <div className="flex items-center gap-1.5">
                            <Avatar className="w-5 h-5">
                              <AvatarFallback className="text-2xs">{getInitials(p.assigned_rep.name)}</AvatarFallback>
                            </Avatar>
                            <span className="text-xs text-text-secondary">{p.assigned_rep.name}</span>
                          </div>
                        ) : (
                          <span className="text-xs text-text-dim">Unassigned</span>
                        )}
                      </td>
                      <td className="px-4 py-3 hidden xl:table-cell">
                        <span className={cn(
                          "text-xs",
                          daysSince(p.last_activity_at) >= 14 ? "text-red" :
                          daysSince(p.last_activity_at) >= 7 ? "text-yellow" : "text-text-dim"
                        )}>
                          {formatRelativeTime(p.last_activity_at)}
                        </span>
                      </td>
                      <td className="px-4 py-3 hidden xl:table-cell">
                        <Badge
                          variant={p.source === "charlotte" ? "default" : "secondary"}
                          className="text-2xs capitalize"
                        >
                          {p.source}
                        </Badge>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>

      <ProspectDrawer />
      <AddProspectModal open={addOpen} onClose={() => setAddOpen(false)} />
    </div>
  );
}
