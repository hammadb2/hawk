"use client";

import { useCallback, useState } from "react";

interface Props {
  onUpload: (file: File) => void;
}

const ACCEPTED = ".jpg,.jpeg,.png,.pdf";
const MAX_SIZE = 10 * 1024 * 1024; // 10 MB

export function OnboardingFileUpload({ onUpload }: Props) {
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");
  const [fileName, setFileName] = useState("");

  const validate = useCallback((file: File): boolean => {
    setError("");
    const ext = file.name.split(".").pop()?.toLowerCase() || "";
    if (!["jpg", "jpeg", "png", "pdf"].includes(ext)) {
      setError("Only JPG, PNG, or PDF files are accepted.");
      return false;
    }
    if (file.size > MAX_SIZE) {
      setError("File must be under 10 MB.");
      return false;
    }
    return true;
  }, []);

  function handleFile(file: File) {
    if (validate(file)) {
      setFileName(file.name);
      onUpload(file);
    }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }

  function onFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
  }

  return (
    <div className="space-y-3">
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`flex flex-col items-center justify-center rounded-lg border-2 border-dashed p-8 transition ${
          dragging ? "border-signal bg-signal/5" : "border-ink-700 bg-[#161625]"
        }`}
      >
        <svg className="mb-3 h-8 w-8 text-ink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
        </svg>
        <p className="text-sm text-ink-200">Drag &amp; drop your government ID here</p>
        <p className="mt-1 text-xs text-ink-200">JPG, PNG, or PDF — max 10 MB</p>
        <label className="mt-4 cursor-pointer rounded-lg bg-ink-700 px-4 py-2 text-sm text-ink-100 hover:bg-ink-600 transition">
          Browse files
          <input type="file" accept={ACCEPTED} onChange={onFileSelect} className="hidden" />
        </label>
      </div>
      {fileName && <p className="text-xs text-signal">Selected: {fileName}</p>}
      {error && <p className="text-xs text-red">{error}</p>}
    </div>
  );
}
