"use client";

import { useEffect, useRef } from "react";
import { X, ExternalLink } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { ProfileHeader } from "./profile-header";
import { Timeline } from "./timeline";
import { ScanResultsTab } from "./scan-results-tab";
import { EmailsTab } from "./emails-tab";
import { NotesTab } from "./notes-tab";
import { FilesTab } from "./files-tab";
import { useCRMStore } from "@/store/crm-store";
import { cn } from "@/lib/utils";
import Link from "next/link";

export function ProspectDrawer() {
  const { selectedProspect, drawerOpen, setDrawerOpen, setSelectedProspect } = useCRMStore();
  const drawerRef = useRef<HTMLDivElement>(null);

  // Close on Escape
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && drawerOpen) {
        handleClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [drawerOpen]);

  const handleClose = () => {
    setDrawerOpen(false);
    setTimeout(() => setSelectedProspect(null), 300);
  };

  return (
    <>
      {/* Backdrop */}
      {drawerOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm"
          onClick={handleClose}
        />
      )}

      {/* Drawer */}
      <div
        ref={drawerRef}
        className={cn(
          "fixed top-0 right-0 z-50 h-full w-full max-w-xl bg-surface-1 border-l border-border shadow-2xl transition-transform duration-300 ease-out flex flex-col",
          drawerOpen ? "translate-x-0" : "translate-x-full"
        )}
      >
        {/* Drawer header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-border flex-shrink-0">
          <span className="text-sm font-medium text-text-secondary">Prospect</span>
          <div className="flex items-center gap-1">
            {selectedProspect && (
              <Link
                href={`/prospects/${selectedProspect.id}`}
                className="flex items-center gap-1 text-xs text-accent-light hover:text-accent transition-colors mr-2"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                Full profile
              </Link>
            )}
            <Button variant="ghost" size="icon-sm" onClick={handleClose}>
              <X className="w-4 h-4" />
            </Button>
          </div>
        </div>

        {/* Content */}
        {selectedProspect ? (
          <div className="flex-1 overflow-y-auto">
            <ProfileHeader
              prospect={selectedProspect}
            />

            <div className="px-4 py-3">
              <Tabs defaultValue="overview">
                <TabsList className="w-full grid grid-cols-5">
                  <TabsTrigger value="overview" className="text-xs">Overview</TabsTrigger>
                  <TabsTrigger value="timeline" className="text-xs">Timeline</TabsTrigger>
                  <TabsTrigger value="scans" className="text-xs">Scans</TabsTrigger>
                  <TabsTrigger value="emails" className="text-xs">Emails</TabsTrigger>
                  <TabsTrigger value="notes" className="text-xs">Notes</TabsTrigger>
                </TabsList>

                <TabsContent value="overview">
                  <div className="space-y-4">
                    {/* Overview details */}
                    <div className="rounded-xl border border-border bg-surface-2 divide-y divide-border">
                      {[
                        { label: "Industry", value: selectedProspect.industry ?? "—" },
                        { label: "City", value: selectedProspect.city ?? "—" },
                        { label: "Province", value: selectedProspect.province ?? "—" },
                        { label: "Source", value: selectedProspect.source },
                        { label: "Consent Basis", value: selectedProspect.consent_basis ?? "implied" },
                      ].map(({ label, value }) => (
                        <div key={label} className="flex items-center justify-between px-3 py-2.5">
                          <span className="text-xs text-text-dim">{label}</span>
                          <span className="text-xs font-medium text-text-primary capitalize">{value}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </TabsContent>

                <TabsContent value="timeline">
                  <Timeline prospectId={selectedProspect.id} />
                </TabsContent>

                <TabsContent value="scans">
                  <ScanResultsTab prospectId={selectedProspect.id} />
                </TabsContent>

                <TabsContent value="emails">
                  <EmailsTab prospectId={selectedProspect.id} />
                </TabsContent>

                <TabsContent value="notes">
                  <NotesTab prospectId={selectedProspect.id} />
                </TabsContent>
              </Tabs>
            </div>
          </div>
        ) : (
          <div className="flex-1 flex items-center justify-center">
            <p className="text-text-dim text-sm">No prospect selected</p>
          </div>
        )}
      </div>
    </>
  );
}
