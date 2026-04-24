"use client";

import { useCallback, useRef, useState } from "react";
import { CRM_API_BASE_URL } from "@/lib/crm/api-url";

interface FileUploadProps {
  accessToken: string;
  onAnalysis: (result: { filename: string; analysis: string }) => void;
  disabled?: boolean;
}

const ACCEPTED_TYPES = [
  "image/png",
  "image/jpeg",
  "image/gif",
  "image/webp",
  "application/pdf",
  "text/plain",
  "text/csv",
];

const MAX_SIZE = 10 * 1024 * 1024; // 10MB

export function FileUpload({ accessToken, onAnalysis, disabled }: FileUploadProps) {
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileSelect = useCallback(
    async (file: File) => {
      if (!ACCEPTED_TYPES.includes(file.type) && !file.name.endsWith(".pdf") && !file.name.endsWith(".txt")) {
        onAnalysis({ filename: file.name, analysis: "Unsupported file type. Please upload an image, PDF, or text file." });
        return;
      }
      if (file.size > MAX_SIZE) {
        onAnalysis({ filename: file.name, analysis: "File too large. Maximum size is 10MB." });
        return;
      }

      setUploading(true);

      try {
        if (file.type.startsWith("image/") || file.type === "application/pdf") {
          // Image and PDF analysis via vision (base64 encoded)
          const reader = new FileReader();
          const base64 = await new Promise<string>((resolve, reject) => {
            reader.onload = () => resolve(reader.result as string);
            reader.onerror = () => reject(new Error("Failed to read file"));
            reader.readAsDataURL(file);
          });

          const label = file.type === "application/pdf" ? "PDF document" : "image";
          const r = await fetch(`${CRM_API_BASE_URL}/api/crm/ai/analyze-file`, {
            method: "POST",
            headers: {
              Authorization: `Bearer ${accessToken}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              content: `Analyze this uploaded ${label}: ${file.name}`,
              image_data: base64,
            }),
          });

          if (r.ok) {
            const data = await r.json();
            onAnalysis({ filename: file.name, analysis: data.reply || "Analysis complete." });
          } else {
            onAnalysis({ filename: file.name, analysis: `${label} analysis failed. Please try again.` });
          }
        } else {
          // Text/CSV analysis via document function
          const text = await file.text();
          const docType = file.name.endsWith(".csv") ? "report" : "general";

          const r = await fetch(`${CRM_API_BASE_URL}/api/crm/ai/analyze-file`, {
            method: "POST",
            headers: {
              Authorization: `Bearer ${accessToken}`,
              "Content-Type": "application/json",
            },
            body: JSON.stringify({
              content: `Analyze this ${docType} document "${file.name}":\n\n${text.slice(0, 8000)}`,
            }),
          });

          if (r.ok) {
            const data = await r.json();
            onAnalysis({ filename: file.name, analysis: data.reply || "Analysis complete." });
          } else {
            onAnalysis({ filename: file.name, analysis: "Document analysis failed. Please try again." });
          }
        }
      } catch (err) {
        console.error("File upload failed:", err);
        onAnalysis({ filename: file.name, analysis: "Upload failed. Please try again." });
      }

      setUploading(false);
    },
    [accessToken, onAnalysis],
  );

  return (
    <>
      <input
        ref={fileInputRef}
        type="file"
        className="hidden"
        accept={ACCEPTED_TYPES.join(",")}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) void handleFileSelect(file);
          e.target.value = "";
        }}
      />
      <button
        onClick={() => fileInputRef.current?.click()}
        disabled={disabled || uploading}
        className={`rounded-xl border px-3 py-3 transition ${
          uploading
            ? "border-[#1e1e2e] bg-[#0d0d14] text-ink-0"
            : "border-[#1e1e2e] bg-[#111118] text-ink-200 hover:border-signal/40 hover:text-signal"
        }`}
        title={uploading ? "Uploading..." : "Upload file for analysis"}
      >
        {uploading ? (
          <svg className="h-5 w-5 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
        ) : (
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M15.172 7l-6.586 6.586a2 2 0 102.828 2.828l6.414-6.586a4 4 0 00-5.656-5.656l-6.415 6.585a6 6 0 108.486 8.486L20.5 13"
            />
          </svg>
        )}
      </button>
    </>
  );
}
