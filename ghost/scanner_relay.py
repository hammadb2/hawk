"""
HAWK Scanner Relay — runs on Ghost server (178.104.27.211:8002).
Receives scan requests from the main API, forwards to Specter (10.0.0.2:8002), returns results.
Specter is internal (WireGuard only); only this relay is exposed.
"""

from __future__ import annotations

import os

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

# Specter is on the internal WireGuard network; Ghost reaches it at 10.0.0.2
SPECTER_BASE_URL = os.environ.get("HAWK_SPECTER_URL", "http://10.0.0.2:8002")
SPECTER_TIMEOUT = float(os.environ.get("HAWK_SPECTER_TIMEOUT", "120"))


class ScanRequest(BaseModel):
    domain: str = Field(..., min_length=1, description="Domain to scan")
    scan_id: str | None = Field(None, description="Scan ID for correlation")


app = FastAPI(
    title="HAWK Scanner Relay",
    description="Forwards scan requests to Specter. Do not expose Specter directly.",
    version="1.0.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "scanner-relay"}


@app.post("/scan")
def scan(req: ScanRequest) -> dict:
    """
    Forward scan to Specter and return the full scan response (findings, score, grade).
    """
    url = f"{SPECTER_BASE_URL.rstrip('/')}/scan"
    try:
        with httpx.Client(timeout=SPECTER_TIMEOUT) as client:
            r = client.post(url, json=req.model_dump())
            r.raise_for_status()
            return r.json()
    except httpx.ConnectError as e:
        raise HTTPException(
            status_code=503,
            detail=f"Specter unreachable at {SPECTER_BASE_URL}. Is WireGuard up? {e!s}",
        ) from e
    except httpx.TimeoutException as e:
        raise HTTPException(
            status_code=504,
            detail=f"Specter did not respond within {SPECTER_TIMEOUT}s. Scan may be running; try polling scan status.",
        ) from e
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=e.response.text or str(e),
        ) from e


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)
