"use client";

import { useCallback, useRef, useState } from "react";
import { CRM_API_BASE_URL } from "@/lib/crm/api-url";

interface VoiceInputProps {
  accessToken: string;
  onTranscription: (text: string) => void;
  disabled?: boolean;
}

export function VoiceInput({ accessToken, onTranscription, disabled }: VoiceInputProps) {
  const [recording, setRecording] = useState(false);
  const [processing, setProcessing] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const startRecording = useCallback(async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
      mediaRecorderRef.current = mediaRecorder;
      chunksRef.current = [];

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        if (blob.size === 0) return;

        setProcessing(true);
        try {
          const formData = new FormData();
          formData.append("audio", blob, "recording.webm");

          const r = await fetch(`${CRM_API_BASE_URL}/api/crm/ai/voice/transcribe`, {
            method: "POST",
            headers: { Authorization: `Bearer ${accessToken}` },
            body: formData,
          });

          if (r.ok) {
            const data = await r.json();
            if (data.text) onTranscription(data.text);
          }
        } catch (err) {
          console.error("Transcription failed:", err);
        }
        setProcessing(false);
      };

      mediaRecorder.start();
      setRecording(true);
    } catch (err) {
      console.error("Microphone access denied:", err);
    }
  }, [accessToken, onTranscription]);

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current && recording) {
      mediaRecorderRef.current.stop();
      setRecording(false);
    }
  }, [recording]);

  return (
    <button
      onClick={recording ? stopRecording : () => void startRecording()}
      disabled={disabled || processing}
      className={`rounded-xl border px-3 py-3 transition ${
        recording
          ? "border-rose-500/40 bg-rose-950/30 text-rose-300 animate-pulse"
          : processing
          ? "border-[#1e1e2e] bg-[#0d0d14] text-slate-500"
          : "border-[#1e1e2e] bg-[#111118] text-slate-400 hover:border-emerald-500/40 hover:text-emerald-400"
      }`}
      title={recording ? "Stop recording" : processing ? "Processing..." : "Voice input"}
    >
      {processing ? (
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
            d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4M12 15a3 3 0 003-3V5a3 3 0 00-6 0v7a3 3 0 003 3z"
          />
        </svg>
      )}
    </button>
  );
}
