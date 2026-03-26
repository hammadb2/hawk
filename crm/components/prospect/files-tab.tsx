"use client";

import { useState } from "react";
import { Upload, FileText, Video, File, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Badge } from "@/components/ui/badge";
import { formatDate } from "@/lib/utils";

interface FileItem {
  id: string;
  name: string;
  type: "pdf" | "loom" | "document";
  url: string;
  uploadedAt: string;
  viewedAt?: string;
}

interface FilesTabProps {
  prospectId: string;
}

export function FilesTab({ prospectId }: FilesTabProps) {
  const [files] = useState<FileItem[]>([]);

  const handleUpload = () => {
    // In production: trigger file upload
  };

  if (files.length === 0) {
    return (
      <div className="space-y-4">
        <EmptyState
          icon={File}
          title="No files yet"
          description="Upload PDF reports, documents, or Loom video links."
          action={{ label: "Upload File", onClick: handleUpload }}
        />
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between mb-3">
        <p className="text-xs font-medium text-text-dim uppercase tracking-wide">
          {files.length} File{files.length !== 1 ? "s" : ""}
        </p>
        <Button variant="secondary" size="sm" onClick={handleUpload} className="gap-1.5 h-7 text-xs">
          <Upload className="w-3 h-3" />
          Upload
        </Button>
      </div>

      {files.map((file) => {
        const Icon = file.type === "pdf" ? FileText : file.type === "loom" ? Video : File;

        return (
          <div
            key={file.id}
            className="flex items-center gap-3 p-3 rounded-xl border border-border bg-surface-2"
          >
            <div className="w-8 h-8 rounded-lg bg-surface-3 border border-border flex items-center justify-center flex-shrink-0">
              <Icon className="w-4 h-4 text-text-dim" />
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-text-primary truncate">{file.name}</p>
              <div className="flex items-center gap-2 mt-0.5">
                <span className="text-2xs text-text-dim">{formatDate(file.uploadedAt)}</span>
                {file.viewedAt && (
                  <Badge variant="success" className="text-2xs">Viewed</Badge>
                )}
              </div>
            </div>
            <a
              href={file.url}
              target="_blank"
              rel="noopener noreferrer"
              className="p-1.5 rounded text-text-dim hover:text-text-primary hover:bg-surface-3 transition-all"
            >
              <ExternalLink className="w-3.5 h-3.5" />
            </a>
          </div>
        );
      })}
    </div>
  );
}
