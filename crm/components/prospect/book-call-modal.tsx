"use client";

import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Calendar, ExternalLink, Copy, CheckCheck } from "lucide-react";
import { toast } from "@/components/ui/toast";
import type { Prospect } from "@/types/crm";

// Cal.com embed — replace with your actual Cal.com username/link
const CAL_USERNAME = process.env.NEXT_PUBLIC_CAL_USERNAME || "hawk-sales";
const CAL_EVENT_TYPE = "discovery-call";

interface BookCallModalProps {
  open: boolean;
  onClose: () => void;
  prospect: Prospect | null;
}

export function BookCallModal({ open, onClose, prospect }: BookCallModalProps) {
  const [copied, setCopied] = useState(false);

  if (!prospect) return null;

  // Pre-fill cal.com with prospect's company name and domain
  const calParams = new URLSearchParams({
    name: prospect.company_name,
    notes: `Domain: ${prospect.domain}${prospect.industry ? ` | Industry: ${prospect.industry}` : ""}`,
  });
  const calUrl = `https://cal.com/${CAL_USERNAME}/${CAL_EVENT_TYPE}?${calParams.toString()}`;

  const handleCopyLink = async () => {
    await navigator.clipboard.writeText(calUrl);
    setCopied(true);
    toast({ title: "Booking link copied" });
    setTimeout(() => setCopied(false), 2000);
  };

  const handleOpenExternal = () => {
    window.open(calUrl, "_blank", "noopener,noreferrer");
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-3xl w-full p-0 overflow-hidden">
        <DialogHeader className="px-6 pt-6 pb-4 border-b border-surface-3">
          <DialogTitle className="flex items-center gap-2 text-text-primary">
            <Calendar className="w-4 h-4 text-accent" />
            Book Discovery Call
          </DialogTitle>
          <DialogDescription className="text-text-secondary text-sm mt-1">
            Scheduling with{" "}
            <span className="font-medium text-text-primary">{prospect.company_name}</span>
            {" "}({prospect.domain})
          </DialogDescription>
        </DialogHeader>

        {/* Cal.com embed */}
        <div className="relative" style={{ height: "560px" }}>
          <iframe
            src={calUrl}
            className="w-full h-full border-0"
            style={{ background: "#07060C" }}
            title={`Book call with ${prospect.company_name}`}
            sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-top-navigation"
          />
        </div>

        {/* Footer actions */}
        <div className="px-6 py-4 border-t border-surface-3 flex items-center justify-between gap-3">
          <p className="text-xs text-text-dim">
            Cal.com booking — link pre-filled with prospect details
          </p>
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              onClick={handleCopyLink}
              className="gap-1.5 text-text-secondary"
            >
              {copied ? (
                <CheckCheck className="w-3.5 h-3.5 text-green" />
              ) : (
                <Copy className="w-3.5 h-3.5" />
              )}
              Copy link
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={handleOpenExternal}
              className="gap-1.5 text-text-secondary"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              Open in new tab
            </Button>
            <Button variant="secondary" size="sm" onClick={onClose}>
              Close
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
