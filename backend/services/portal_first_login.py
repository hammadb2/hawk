"""First-portal-login bookkeeping for priority list #32.

The ``clients.last_portal_login_at`` column has existed in the schema
(20260405000001_crm_phase2_client_portal.sql) since Phase 2 but was
never written anywhere in the codebase. We reuse it as the "has this
portal account been seen before?" signal: null → first login, set →
subsequent login. The :func:`mark_first_portal_login` helper stamps it
to ``now()`` the first time the client lands on ``/portal/welcome`` so
the PortalGate redirect is one-shot per account.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

import httpx
from fastapi import HTTPException

from config import SUPABASE_URL
from services.portal_bootstrap import _headers, get_client_id_for_portal_user

logger = logging.getLogger(__name__)

SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def mark_first_portal_login(uid: str) -> dict[str, str]:
    """Stamp ``clients.last_portal_login_at`` to now for the signed-in portal user.

    Idempotent: the frontend calls this on every mount of ``/portal/welcome``
    but PortalGate only redirects there when ``last_portal_login_at IS NULL``,
    so subsequent calls are no-ops from the UX side. We still update the
    timestamp server-side so ops can see the most recent login.
    """
    if not SUPABASE_URL:
        raise HTTPException(status_code=503, detail="Supabase not configured on API")

    cid = get_client_id_for_portal_user(uid)
    if not cid:
        raise HTTPException(status_code=400, detail="No portal client linked to this account")

    now = datetime.now(timezone.utc).isoformat()
    r = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/clients",
        headers=_headers(),
        params={"id": f"eq.{cid}"},
        json={"last_portal_login_at": now},
        timeout=20.0,
    )
    if r.status_code >= 400:
        logger.error(
            "mark_first_portal_login clients patch: %s %s",
            r.status_code,
            r.text[:500],
        )
        raise HTTPException(status_code=502, detail="Could not record portal login") from None

    return {"ok": "true", "last_portal_login_at": now}
