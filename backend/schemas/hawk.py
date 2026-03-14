from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any


class HawkChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    scan_id: str | None = None
    conversation_history: list[dict[str, Any]] = Field(default_factory=list)


class HawkChatResponse(BaseModel):
    reply: str
    trigger_rescan: str | None = None  # check_name if [TRIGGER_RESCAN:check_name]
