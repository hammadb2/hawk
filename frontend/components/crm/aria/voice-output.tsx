"use client";

import { useCallback, useRef, useState } from "react";
import { CRM_API_BASE_URL } from "@/lib/crm/api-url";

interface VoiceOutputProps {
  text: string;
  accessToken: string;
}

export function VoiceOutput({ text, accessToken }: VoiceOutputProps) {
  const [playing, setPlaying] = useState(false);
  const [loading, setLoading] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  const play = useCallback(async () => {
    if (playing && audioRef.current) {
      audioRef.current.pause();
      setPlaying(false);
      return;
    }

    setLoading(true);
    try {
      const r = await fetch(`${CRM_API_BASE_URL}/api/crm/ai/voice/synthesize`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${accessToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ text, voice: "nova" }),
      });

      if (r.ok) {
        const data = await r.json();
        if (data.audio_base64) {
          const audio = new Audio(`data:audio/mp3;base64,${data.audio_base64}`);
          audioRef.current = audio;
          audio.onended = () => setPlaying(false);
          await audio.play();
          setPlaying(true);
        }
      }
    } catch (err) {
      console.error("TTS failed:", err);
    }
    setLoading(false);
  }, [text, accessToken, playing]);

  return (
    <button
      onClick={() => void play()}
      disabled={loading}
      className="ml-2 inline-flex items-center rounded-md p-1 text-slate-400 hover:text-emerald-600 transition"
      title={playing ? "Stop" : "Listen"}
    >
      {loading ? (
        <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
      ) : playing ? (
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 10h6v4H9z" />
        </svg>
      ) : (
        <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M15.536 8.464a5 5 0 010 7.072M17.95 6.05a8 8 0 010 11.9M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M12 18v3m-3 0h6M11 5a3 3 0 016 0v6a3 3 0 01-6 0V5z"
          />
        </svg>
      )}
    </button>
  );
}
