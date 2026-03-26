"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  ExternalLink,
  Scan,
  Phone,
  Calendar,
  Star,
  MoreHorizontal,
  ArrowRight,
  UserX,
  TrendingUp,
  Copy,
  Loader2,
  UserCog,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { HawkScoreRing } from "@/components/ui/hawk-score-ring";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { stageBgColor, stageLabel, cn } from "@/lib/utils";
import { prospectsApi } from "@/lib/api";
import { toast } from "@/components/ui/toast";
import { useCRMStore } from "@/store/crm-store";
import { LogCallModal } from "./log-call-modal";
import { LostModal } from "@/components/pipeline/lost-modal";
import { CloseWonModal } from "@/components/pipeline/close-won-modal";
import { canReassignProspect } from "@/lib/auth";
import type { Prospect, PipelineStage } from "@/types/crm";

const STAGES: PipelineStage[] = [
  "new", "scanned", "loom_sent", "replied", "call_booked", "proposal_sent", "closed_won", "lost"
];

interface ProfileHeaderProps {
  prospect: Prospect;
  onScanComplete?: () => void;
}

export function ProfileHeader({ prospect, onScanComplete }: ProfileHeaderProps) {
  const router = useRouter();
  const { user, updateProspect } = useCRMStore();
  const [scanning, setScanning] = useState(false);
  const [hotLoading, setHotLoading] = useState(false);
  const [logCallOpen, setLogCallOpen] = useState(false);
  const [lostOpen, setLostOpen] = useState(false);
  const [closeWonOpen, setCloseWonOpen] = useState(false);

  const handleStageChange = async (stage: PipelineStage) => {
    if (stage === "lost") { setLostOpen(true); return; }
    if (stage === "closed_won") { setCloseWonOpen(true); return; }

    const result = await prospectsApi.move(prospect.id, stage);
    if (result.success) {
      updateProspect(prospect.id, { stage });
      toast({ title: `Moved to ${stageLabel(stage)}`, variant: "success" });
    } else {
      toast({ title: result.error || "Failed to update stage", variant: "destructive" });
    }
  };

  const handleRunScan = async () => {
    setScanning(true);
    try {
      const result = await prospectsApi.runScan(prospect.id);
      if (result.success && result.data) {
        updateProspect(prospect.id, { hawk_score: result.data.hawk_score ?? undefined });
        toast({ title: "Scan completed", variant: "success" });
        onScanComplete?.();
      } else {
        toast({ title: result.error || "Scan failed", variant: "destructive" });
      }
    } catch {
      toast({ title: "Network error", variant: "destructive" });
    } finally {
      setScanning(false);
    }
  };

  const handleToggleHot = async () => {
    setHotLoading(true);
    try {
      const result = await prospectsApi.markHot(prospect.id, !prospect.is_hot);
      if (result.success) {
        updateProspect(prospect.id, { is_hot: !prospect.is_hot });
        toast({
          title: prospect.is_hot ? "Removed from hot leads" : "Marked as hot",
          variant: prospect.is_hot ? "default" : "success",
        });
      }
    } catch {
      toast({ title: "Network error", variant: "destructive" });
    } finally {
      setHotLoading(false);
    }
  };

  const handleCopyLink = () => {
    const url = `${window.location.origin}/prospects/${prospect.id}`;
    navigator.clipboard.writeText(url);
    toast({ title: "Link copied", variant: "success" });
  };

  return (
    <>
      <div className="p-4 border-b border-border">
        <div className="flex items-start gap-3 mb-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-0.5">
              {prospect.is_hot && (
                <Star className="w-4 h-4 text-yellow fill-yellow flex-shrink-0" />
              )}
              <h2 className="text-base font-semibold text-text-primary truncate">
                {prospect.company_name}
              </h2>
            </div>
            <a
              href={`https://${prospect.domain}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-text-dim hover:text-accent-light transition-colors flex items-center gap-1"
            >
              {prospect.domain}
              <ExternalLink className="w-3 h-3" />
            </a>
          </div>
          <HawkScoreRing score={prospect.hawk_score} size="md" />
        </div>

        {/* Stage selector */}
        <div className="mb-3">
          <Select value={prospect.stage} onValueChange={(v) => handleStageChange(v as PipelineStage)}>
            <SelectTrigger className="h-7 text-xs w-auto min-w-[140px]">
              <div className={cn("px-1.5 py-0.5 rounded text-xs font-medium", stageBgColor(prospect.stage))}>
                {stageLabel(prospect.stage)}
              </div>
            </SelectTrigger>
            <SelectContent>
              {STAGES.map((stage) => (
                <SelectItem key={stage} value={stage}>
                  <span className={cn("text-xs font-medium px-1.5 py-0.5 rounded", stageBgColor(stage))}>
                    {stageLabel(stage)}
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* Action buttons */}
        <div className="flex items-center gap-2 flex-wrap">
          <Button
            variant="secondary"
            size="sm"
            onClick={handleRunScan}
            disabled={scanning}
            className="gap-1.5 h-8 text-xs"
          >
            {scanning ? (
              <><Loader2 className="w-3 h-3 animate-spin" /> Scanning...</>
            ) : (
              <><Scan className="w-3 h-3" /> Run Scan</>
            )}
          </Button>

          <Button
            variant="secondary"
            size="sm"
            onClick={() => setLogCallOpen(true)}
            className="gap-1.5 h-8 text-xs"
          >
            <Phone className="w-3 h-3" />
            Log Call
          </Button>

          <Button
            variant="secondary"
            size="sm"
            onClick={handleToggleHot}
            disabled={hotLoading}
            className={cn("gap-1.5 h-8 text-xs", prospect.is_hot && "text-yellow border-yellow/30")}
          >
            <Star className={cn("w-3 h-3", prospect.is_hot && "fill-yellow text-yellow")} />
            {prospect.is_hot ? "Hot" : "Mark Hot"}
          </Button>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="secondary" size="icon" className="h-8 w-8">
                <MoreHorizontal className="w-3.5 h-3.5" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={() => router.push(`/prospects/${prospect.id}`)}>
                <ExternalLink className="w-3.5 h-3.5" />
                Open full profile
              </DropdownMenuItem>
              <DropdownMenuItem onClick={handleCopyLink}>
                <Copy className="w-3.5 h-3.5" />
                Copy link
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              {user && canReassignProspect(user) && (
                <DropdownMenuItem>
                  <UserCog className="w-3.5 h-3.5" />
                  Reassign
                </DropdownMenuItem>
              )}
              <DropdownMenuItem onClick={() => setLostOpen(true)} destructive>
                <UserX className="w-3.5 h-3.5" />
                Mark Lost
              </DropdownMenuItem>
              <DropdownMenuItem onClick={() => setCloseWonOpen(true)}>
                <TrendingUp className="w-3.5 h-3.5" />
                Convert to Client
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>
      </div>

      <LogCallModal
        open={logCallOpen}
        onClose={() => setLogCallOpen(false)}
        prospect={prospect}
      />
      <LostModal
        open={lostOpen}
        onClose={() => setLostOpen(false)}
        prospect={prospect}
      />
      <CloseWonModal
        open={closeWonOpen}
        onClose={() => setCloseWonOpen(false)}
        prospect={prospect}
      />
    </>
  );
}
