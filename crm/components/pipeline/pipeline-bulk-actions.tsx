"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { toast } from "@/components/ui/toast";
import { downloadCSV, formatCurrency } from "@/lib/utils";
import { ESTIMATED_PIPELINE_VALUE_PER_PROSPECT, LOST_REASON_OPTIONS } from "@/lib/pipeline-constants";
import { prospectsApi } from "@/lib/api";
import type { Prospect, LostReasonData } from "@/types/crm";

interface PipelineBulkActionsProps {
  bulkMode: boolean;
  onBulkModeChange: (next: boolean) => void;
  selectedIds: Set<string>;
  onClearSelection: () => void;
  selectedProspects: Prospect[];
  reassignOptions: { id: string; name: string }[];
  canReassign: boolean;
  onProspectsUpdated: () => void;
  updateProspect: (id: string, updates: Partial<Prospect>) => void;
}

export function PipelineBulkActions({
  bulkMode,
  onBulkModeChange,
  selectedIds,
  onClearSelection,
  selectedProspects,
  reassignOptions,
  canReassign,
  onProspectsUpdated,
  updateProspect,
}: PipelineBulkActionsProps) {
  const [lostOpen, setLostOpen] = useState(false);
  const [reassignOpen, setReassignOpen] = useState(false);
  const [reason, setReason] = useState("");
  const [lostNotes, setLostNotes] = useState("");
  const [reassignTo, setReassignTo] = useState("");
  const [working, setWorking] = useState(false);

  const n = selectedIds.size;
  const isOther = reason === "Other (requires note)";
  const canSubmitLost = reason && (!isOther || lostNotes.trim().length > 0);

  const handleExportCsv = () => {
    if (selectedProspects.length === 0) return;
    downloadCSV(
      selectedProspects.map((p) => ({
        company_name: p.company_name,
        domain: p.domain,
        stage: p.stage,
        city: p.city ?? "",
        industry: p.industry ?? "",
        hawk_score: p.hawk_score ?? "",
        source: p.source,
        assigned_rep: p.assigned_rep?.name ?? "",
        last_activity_at: p.last_activity_at,
      })),
      `hawk-pipeline-export-${new Date().toISOString().slice(0, 10)}.csv`
    );
    toast({ title: `Exported ${selectedProspects.length} rows`, variant: "success" });
  };

  const handleBulkLost = async () => {
    if (!canSubmitLost || selectedProspects.length === 0) return;
    const data: LostReasonData = {
      reason,
      notes: lostNotes.trim() || null,
      reactivate_at: null,
    };
    setWorking(true);
    try {
      let ok = 0;
      for (const p of selectedProspects) {
        const res = await prospectsApi.moveLost(p.id, data);
        if (res.success) {
          ok++;
          updateProspect(p.id, {
            stage: "lost",
            lost_reason: data.reason,
            lost_notes: data.notes,
            reactivate_at: null,
          });
        }
      }
      toast({
        title: ok === selectedProspects.length ? "Marked as lost" : "Partially completed",
        description: `${ok} of ${selectedProspects.length} updated.`,
        variant: ok === selectedProspects.length ? "success" : "default",
      });
      setLostOpen(false);
      setReason("");
      setLostNotes("");
      onClearSelection();
      onProspectsUpdated();
    } finally {
      setWorking(false);
    }
  };

  const handleBulkReassign = async () => {
    if (!reassignTo || selectedProspects.length === 0) return;
    setWorking(true);
    try {
      let ok = 0;
      for (const p of selectedProspects) {
        const res = await prospectsApi.reassign(p.id, reassignTo);
        if (res.success && res.data) {
          ok++;
          updateProspect(p.id, { assigned_rep_id: reassignTo, assigned_rep: res.data.assigned_rep });
        }
      }
      toast({
        title: "Reassignment complete",
        description: `${ok} of ${selectedProspects.length} prospects updated.`,
        variant: "success",
      });
      setReassignOpen(false);
      setReassignTo("");
      onClearSelection();
      onProspectsUpdated();
    } finally {
      setWorking(false);
    }
  };

  const handleBulkScan = async () => {
    if (selectedProspects.length === 0) return;
    setWorking(true);
    try {
      let ok = 0;
      for (const p of selectedProspects) {
        const res = await prospectsApi.runScan(p.id);
        if (res.success) ok++;
      }
      toast({
        title: "Scan requests sent",
        description: `${ok} of ${selectedProspects.length} completed without error.`,
        variant: "default",
      });
      onProspectsUpdated();
    } finally {
      setWorking(false);
    }
  };

  return (
    <>
      <div className="flex flex-wrap items-center gap-2 px-4 py-2 border-b border-border bg-surface-2/40 flex-shrink-0">
        <label className="flex items-center gap-2 text-xs text-text-secondary cursor-pointer select-none">
          <Checkbox
            checked={bulkMode}
            onCheckedChange={(c) => {
              onBulkModeChange(c === true);
              if (!c) onClearSelection();
            }}
          />
          Bulk select
        </label>
        {bulkMode && n > 0 && (
          <>
            <span className="text-xs text-text-dim">
              {n} selected · est. {formatCurrency(n * ESTIMATED_PIPELINE_VALUE_PER_PROSPECT)} pipeline
            </span>
            <Button type="button" variant="secondary" size="sm" className="h-7 text-xs" onClick={onClearSelection}>
              Clear
            </Button>
            <Button type="button" variant="secondary" size="sm" className="h-7 text-xs" onClick={handleExportCsv}>
              Export CSV
            </Button>
            {canReassign && (
              <Button
                type="button"
                variant="secondary"
                size="sm"
                className="h-7 text-xs"
                onClick={() => setReassignOpen(true)}
              >
                Reassign
              </Button>
            )}
            <Button type="button" variant="secondary" size="sm" className="h-7 text-xs" onClick={() => setLostOpen(true)}>
              Mark lost
            </Button>
            <Button
              type="button"
              variant="secondary"
              size="sm"
              className="h-7 text-xs"
              disabled={working}
              onClick={() => void handleBulkScan()}
            >
              Run scan
            </Button>
          </>
        )}
      </div>

      <Dialog open={lostOpen} onOpenChange={setLostOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Mark {selectedProspects.length} as lost</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <Select value={reason} onValueChange={setReason}>
              <SelectTrigger>
                <SelectValue placeholder="Lost reason *" />
              </SelectTrigger>
              <SelectContent>
                {LOST_REASON_OPTIONS.map((r) => (
                  <SelectItem key={r} value={r}>
                    {r}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Textarea
              placeholder={isOther ? "Notes required *" : "Optional notes"}
              value={lostNotes}
              onChange={(e) => setLostNotes(e.target.value)}
              rows={3}
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="secondary" size="sm" onClick={() => setLostOpen(false)}>
              Cancel
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={!canSubmitLost || working}
              onClick={() => void handleBulkLost()}
            >
              {working ? "Saving…" : "Confirm"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={reassignOpen} onOpenChange={setReassignOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Reassign {selectedProspects.length} prospects</DialogTitle>
          </DialogHeader>
          <Select value={reassignTo} onValueChange={setReassignTo}>
            <SelectTrigger>
              <SelectValue placeholder="Choose rep" />
            </SelectTrigger>
            <SelectContent>
              {reassignOptions.map((u) => (
                <SelectItem key={u.id} value={u.id}>
                  {u.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <DialogFooter>
            <Button type="button" variant="secondary" size="sm" onClick={() => setReassignOpen(false)}>
              Cancel
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={!reassignTo || working}
              onClick={() => void handleBulkReassign()}
            >
              {working ? "Saving…" : "Reassign"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
