"use client";

import { useState, useEffect, useMemo } from "react";
import { Users, AlertTriangle } from "lucide-react";
import { useRouter } from "next/navigation";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Spinner } from "@/components/ui/spinner";
import { EmptyState } from "@/components/ui/empty-state";
import { useAuthReady } from "@/components/layout/providers";
import { useCRMStore } from "@/store/crm-store";
import { clientsApi } from "@/lib/api";
import { toast } from "@/components/ui/toast";
import { formatCurrency, formatDate, churnRiskColor, cn } from "@/lib/utils";
import type { ClientStatus, ChurnRisk, ClientPlan } from "@/types/crm";

const STATUS_LABELS: Record<ClientStatus, string> = {
  active: "Active",
  past_due: "Past Due",
  churned: "Churned",
  paused: "Paused",
};

const PLAN_LABELS: Record<ClientPlan, string> = {
  starter: "Starter",
  shield: "Shield",
  enterprise: "Enterprise",
  custom: "Custom",
};

export default function ClientsPage() {
  const authReady = useAuthReady();
  const router = useRouter();
  const { clients, setClients } = useCRMStore();
  const [loading, setLoading] = useState(clients.length === 0);
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<ClientStatus | "all">("all");
  const [churnFilter, setChurnFilter] = useState<ChurnRisk | "all">("all");

  const highChurnCount = useMemo(
    () => clients.filter((c) => c.churn_risk_score === "high").length,
    [clients]
  );

  useEffect(() => {
    if (!authReady) return;
    const load = async () => {
      const hasData = useCRMStore.getState().clients.length > 0;
      if (!hasData) setLoading(true);
      try {
        const result = await clientsApi.list();
        if (result.success && result.data) {
          setClients(result.data);
        } else if (!hasData) {
          toast({ title: "Failed to load clients", variant: "destructive" });
        }
      } catch {
        if (!hasData) toast({ title: "Network error", variant: "destructive" });
      } finally {
        setLoading(false);
      }
    };
    load();
  }, [authReady, setClients]);

  const filtered = useMemo(() => {
    return clients.filter((c) => {
      if (statusFilter !== "all" && c.status !== statusFilter) return false;
      if (churnFilter !== "all" && c.churn_risk_score !== churnFilter) return false;
      if (search) {
        const q = search.toLowerCase();
        const name = c.prospect?.company_name?.toLowerCase() ?? "";
        const domain = c.prospect?.domain?.toLowerCase() ?? "";
        const plan = c.plan?.toLowerCase() ?? "";
        if (!name.includes(q) && !domain.includes(q) && !plan.includes(q)) return false;
      }
      return true;
    });
  }, [clients, search, statusFilter, churnFilter]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-3 px-4 py-3 border-b border-border flex-shrink-0">
        <div className="flex-1">
          <h1 className="text-base font-semibold text-text-primary">
            Clients
            {highChurnCount > 0 && (
              <Badge variant="destructive" className="ml-2 text-xs">
                {highChurnCount} high churn risk
              </Badge>
            )}
          </h1>
          <p className="text-xs text-text-dim">{filtered.length} clients</p>
        </div>

        {/* Status filter */}
        <div className="flex items-center gap-1">
          {(["all", "active", "past_due", "churned"] as const).map((s) => (
            <button
              key={s}
              onClick={() => setStatusFilter(s)}
              className={cn(
                "px-2.5 py-1 rounded-md text-xs font-medium transition-all",
                statusFilter === s
                  ? "bg-accent/15 text-accent-light border border-accent/25"
                  : "text-text-dim hover:text-text-secondary hover:bg-surface-2"
              )}
            >
              {s === "all" ? "All" : STATUS_LABELS[s]}
            </button>
          ))}
        </div>

        <div className="w-48">
          <Input
            placeholder="Search clients..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-8 text-xs"
          />
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {loading ? (
          <div className="flex items-center justify-center py-20">
            <Spinner size="lg" />
          </div>
        ) : filtered.length === 0 ? (
          <EmptyState
            icon={Users}
            title="No clients found"
            description="Clients appear here after closing deals."
            className="mt-16"
          />
        ) : (
          <div className="p-4">
            <div className="rounded-xl border border-border overflow-hidden bg-surface-1">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border bg-surface-2">
                    <th className="text-left text-xs font-medium text-text-dim px-4 py-3">Company</th>
                    <th className="text-left text-xs font-medium text-text-dim px-4 py-3">Plan</th>
                    <th className="text-left text-xs font-medium text-text-dim px-4 py-3">MRR</th>
                    <th className="text-left text-xs font-medium text-text-dim px-4 py-3">Status</th>
                    <th className="text-left text-xs font-medium text-text-dim px-4 py-3 hidden lg:table-cell">Churn Risk</th>
                    <th className="text-left text-xs font-medium text-text-dim px-4 py-3 hidden xl:table-cell">Close Date</th>
                    <th className="text-left text-xs font-medium text-text-dim px-4 py-3 hidden xl:table-cell">Rep</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((client, i) => (
                    <tr
                      key={client.id}
                      onClick={() => router.push(`/clients/${client.id}`)}
                      className={cn(
                        "cursor-pointer hover:bg-surface-2 transition-colors",
                        i !== filtered.length - 1 && "border-b border-border"
                      )}
                    >
                      <td className="px-4 py-3">
                        <span className="text-sm font-medium text-text-primary">
                          {client.prospect?.company_name ?? "Unknown"}
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <Badge variant="secondary" className="text-xs capitalize">
                          {PLAN_LABELS[client.plan]}
                        </Badge>
                      </td>
                      <td className="px-4 py-3">
                        <span className="text-sm font-semibold text-text-primary">
                          {formatCurrency(client.mrr)}/mo
                        </span>
                      </td>
                      <td className="px-4 py-3">
                        <Badge
                          variant={
                            client.status === "active" ? "success" :
                            client.status === "past_due" ? "warning" : "destructive"
                          }
                          className="text-xs"
                        >
                          {STATUS_LABELS[client.status]}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 hidden lg:table-cell">
                        <span className={cn("text-xs font-medium px-2 py-0.5 rounded-md capitalize", churnRiskColor(client.churn_risk_score))}>
                          {client.churn_risk_score}
                        </span>
                      </td>
                      <td className="px-4 py-3 hidden xl:table-cell">
                        <span className="text-xs text-text-dim">{formatDate(client.close_date)}</span>
                      </td>
                      <td className="px-4 py-3 hidden xl:table-cell">
                        <span className="text-xs text-text-secondary">
                          {client.closing_rep?.name ?? "—"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
