"use client";

import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ProfileHeader } from "./profile-header";
import { Timeline } from "./timeline";
import { ScanResultsTab } from "./scan-results-tab";
import { EmailsTab } from "./emails-tab";
import { NotesTab } from "./notes-tab";
import { FilesTab } from "./files-tab";
import { useCRMStore } from "@/store/crm-store";
import { useEffect } from "react";
import type { Prospect } from "@/types/crm";

interface ProspectProfilePageProps {
  initialProspect: Prospect;
}

export function ProspectProfilePage({ initialProspect }: ProspectProfilePageProps) {
  const { updateProspect, prospects } = useCRMStore();

  // Get latest from store if available
  const prospect = prospects.find((p) => p.id === initialProspect.id) ?? initialProspect;

  return (
    <div className="max-w-4xl mx-auto p-4">
      <div className="mb-4">
        <Link
          href="/prospects"
          className="flex items-center gap-1.5 text-sm text-text-dim hover:text-text-secondary transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Back to Prospects
        </Link>
      </div>

      <div className="rounded-2xl border border-border bg-surface-1 overflow-hidden">
        <ProfileHeader prospect={prospect} />

        <div className="p-4">
          <Tabs defaultValue="overview">
            <TabsList>
              <TabsTrigger value="overview">Overview</TabsTrigger>
              <TabsTrigger value="timeline">Timeline</TabsTrigger>
              <TabsTrigger value="scans">Scan Results</TabsTrigger>
              <TabsTrigger value="emails">Emails</TabsTrigger>
              <TabsTrigger value="notes">Notes</TabsTrigger>
              <TabsTrigger value="files">Files</TabsTrigger>
            </TabsList>

            <TabsContent value="overview">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-2">
                <div className="rounded-xl border border-border bg-surface-2 divide-y divide-border">
                  {[
                    { label: "Domain", value: prospect.domain },
                    { label: "Industry", value: prospect.industry ?? "—" },
                    { label: "City", value: prospect.city ?? "—" },
                    { label: "Province", value: prospect.province ?? "—" },
                    { label: "Source", value: prospect.source },
                    { label: "Consent Basis", value: prospect.consent_basis ?? "implied" },
                  ].map(({ label, value }) => (
                    <div key={label} className="flex items-center justify-between px-3 py-2.5">
                      <span className="text-xs text-text-dim">{label}</span>
                      <span className="text-xs font-medium text-text-primary capitalize">{value}</span>
                    </div>
                  ))}
                </div>

                <div className="rounded-xl border border-border bg-surface-2 divide-y divide-border">
                  {[
                    { label: "HAWK Score", value: prospect.hawk_score?.toString() ?? "Not scanned" },
                    { label: "Is Hot", value: prospect.is_hot ? "Yes" : "No" },
                    { label: "Assigned Rep", value: prospect.assigned_rep?.name ?? "Unassigned" },
                    { label: "Created", value: new Date(prospect.created_at).toLocaleDateString() },
                    { label: "Last Activity", value: new Date(prospect.last_activity_at).toLocaleDateString() },
                  ].map(({ label, value }) => (
                    <div key={label} className="flex items-center justify-between px-3 py-2.5">
                      <span className="text-xs text-text-dim">{label}</span>
                      <span className="text-xs font-medium text-text-primary">{value}</span>
                    </div>
                  ))}
                </div>
              </div>
            </TabsContent>

            <TabsContent value="timeline">
              <Timeline prospectId={prospect.id} />
            </TabsContent>

            <TabsContent value="scans">
              <ScanResultsTab prospectId={prospect.id} />
            </TabsContent>

            <TabsContent value="emails">
              <EmailsTab prospectId={prospect.id} />
            </TabsContent>

            <TabsContent value="notes">
              <NotesTab prospectId={prospect.id} />
            </TabsContent>

            <TabsContent value="files">
              <FilesTab prospectId={prospect.id} />
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </div>
  );
}
