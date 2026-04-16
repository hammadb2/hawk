"""ARIA Phase 8 — Voice input (Whisper) and voice output (TTS) via OpenAI."""

from __future__ import annotations

import io
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()


def transcribe_audio(audio_bytes: bytes, filename: str = "audio.webm") -> dict[str, Any]:
    """Transcribe audio bytes using OpenAI Whisper API.

    Returns {"text": "...", "language": "en"} on success,
    {"error": "..."} on failure.
    """
    if not OPENAI_API_KEY:
        return {"error": "OpenAI API key not configured"}

    try:
        from openai import OpenAI

        client = OpenAI(api_key=OPENAI_API_KEY)
        audio_file = io.BytesIO(audio_bytes)
        audio_file.name = filename

        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="json",
        )
        return {"text": transcript.text, "language": getattr(transcript, "language", "en")}
    except Exception as exc:
        logger.exception("Whisper transcription failed: %s", exc)
        return {"error": str(exc)}


def synthesize_speech(text: str, voice: str = "nova") -> bytes | None:
    """Convert text to speech using OpenAI TTS API.

    Returns raw MP3 audio bytes on success, None on failure.
    Voices: alloy, echo, fable, onyx, nova, shimmer
    """
    if not OPENAI_API_KEY:
        return None

    try:
        from openai import OpenAI

        client = OpenAI(api_key=OPENAI_API_KEY)
        response = client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text[:4096],  # TTS limit
            response_format="mp3",
        )
        return response.content
    except Exception as exc:
        logger.exception("TTS synthesis failed: %s", exc)
        return None
