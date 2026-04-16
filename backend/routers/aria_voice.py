"""ARIA Phase 8 — Voice input/output endpoints."""

from __future__ import annotations

import base64
import logging
from typing import Any

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from routers.crm_ai_command import require_supabase_uid, _require_ai_access

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/crm/ai", tags=["aria-voice"])


@router.post("/voice/transcribe")
async def transcribe_voice(
    audio: UploadFile = File(...),
    uid: str = Depends(require_supabase_uid),
) -> dict[str, Any]:
    """Transcribe uploaded audio to text using OpenAI Whisper."""
    _require_ai_access(uid)

    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file")

    if len(audio_bytes) > 25 * 1024 * 1024:  # 25MB limit
        raise HTTPException(status_code=400, detail="Audio file too large (max 25MB)")

    from services.aria_voice import transcribe_audio

    result = transcribe_audio(audio_bytes, filename=audio.filename or "audio.webm")
    if "error" in result:
        raise HTTPException(status_code=500, detail=result["error"])

    return result


class TTSRequest(BaseModel):
    text: str
    voice: str = "nova"


@router.post("/voice/synthesize")
def synthesize_voice(
    body: TTSRequest,
    uid: str = Depends(require_supabase_uid),
) -> dict[str, str]:
    """Convert text to speech using OpenAI TTS. Returns base64-encoded MP3."""
    _require_ai_access(uid)

    if not body.text.strip():
        raise HTTPException(status_code=400, detail="Empty text")

    if body.voice not in ("alloy", "echo", "fable", "onyx", "nova", "shimmer"):
        raise HTTPException(status_code=400, detail="Invalid voice. Options: alloy, echo, fable, onyx, nova, shimmer")

    from services.aria_voice import synthesize_speech

    audio_bytes = synthesize_speech(body.text, voice=body.voice)
    if not audio_bytes:
        raise HTTPException(status_code=500, detail="TTS synthesis failed")

    return {"audio_base64": base64.b64encode(audio_bytes).decode("utf-8"), "format": "mp3"}
