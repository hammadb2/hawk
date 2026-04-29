"""ARIA Phase 12 — File and image intelligence via OpenAI Vision.

Analyzes uploaded images and files using OpenAI's vision capabilities.
Supports security screenshots, network diagrams, compliance documents, etc.
"""

from __future__ import annotations

import base64
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()


def analyze_image(
    image_bytes: bytes,
    prompt: str = "Analyze this image in the context of cybersecurity and business operations.",
    mime_type: str = "image/png",
) -> dict[str, Any]:
    """Analyze an image using OpenAI Vision API.

    Returns {"analysis": "...", "key_findings": [...]} on success.
    """
    if not OPENAI_API_KEY:
        return {"error": "OpenAI API key not configured"}

    try:
        from openai import OpenAI

        client = OpenAI(api_key=OPENAI_API_KEY)
        model = os.environ.get("OPENAI_MODEL", "gpt-4o").strip() or "gpt-4o"

        b64 = base64.b64encode(image_bytes).decode("utf-8")
        data_url = f"data:{mime_type};base64,{b64}"

        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are ARIA, the AI operations assistant for Hawk Security. "
                        "You are analyzing an uploaded image. Provide a clear, actionable analysis "
                        "relevant to cybersecurity operations, business metrics, or compliance. "
                        "Be concise and identify key findings."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
                    ],
                },
            ],
            max_tokens=1500,
            temperature=0.3,
        )

        analysis = (response.choices[0].message.content or "").strip()
        return {"analysis": analysis}
    except Exception as exc:
        logger.exception("Image analysis failed: %s", exc)
        return {"error": str(exc)}


def analyze_document_text(
    text_content: str,
    doc_type: str = "general",
    prompt: str | None = None,
) -> dict[str, Any]:
    """Analyze extracted text from a document using OpenAI.

    doc_type: general, contract, compliance, report, email_thread
    """
    if not OPENAI_API_KEY:
        return {"error": "OpenAI API key not configured"}

    type_prompts = {
        "contract": "Analyze this contract for key terms, obligations, risks, and compliance with the US regulatory angle relevant to the counterparty (HIPAA Security Rule for dental / medical, FTC Safeguards Rule for CPA / tax, ABA Formal Opinion 24-514 for legal).",
        "compliance": "Review this compliance document and identify gaps, risks, and recommendations for a US cybersecurity firm serving small professional practices (HIPAA / FTC Safeguards / ABA Opinion 24-514).",
        "report": "Summarize this report with key metrics, trends, and actionable insights.",
        "email_thread": "Analyze this email thread for sentiment, key requests, and recommended follow-up actions.",
        "general": "Analyze this document and provide a summary with key findings and recommended actions.",
    }

    try:
        from services.openai_chat import chat_text_sync

        analysis = chat_text_sync(
            api_key=OPENAI_API_KEY,
            system=(
                "You are ARIA, the AI operations assistant for Hawk Security. "
                "You are analyzing a document. Be concise, professional, and actionable."
            ),
            user_messages=[{
                "role": "user",
                "content": (
                    f"{prompt or type_prompts.get(doc_type, type_prompts['general'])}\n\n"
                    f"Document content:\n{text_content[:15000]}"
                ),
            }],
            max_tokens=2000,
            task="reasoning",
        )
        return {"analysis": analysis, "doc_type": doc_type}
    except Exception as exc:
        logger.exception("Document analysis failed: %s", exc)
        return {"error": str(exc)}
