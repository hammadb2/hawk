"""Unit tests for the one-click incident-report helper (priority list #34).

Exercises :mod:`services.portal_incident_report` with a stubbed Supabase
REST endpoint. Covers:

1. The "no portal client linked" short-circuit (HTTP 400).
2. The happy path returns a case id, SLA deadline, and the per-channel
   fan-out statuses.
3. OpenPhone being unconfigured flags the SMS as ``skipped`` but the
   incident still persists and the endpoint still returns 200.
4. Resend being unconfigured tags the email status as
   ``skipped:no_resend_key`` without raising.
"""
from __future__ import annotations

import pathlib
import sys
from collections.abc import Iterator
from typing import Any

import pytest

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_BACKEND = _REPO_ROOT / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


class _FakeResponse:
    def __init__(self, status_code: int = 200, json_body: Any = None, text: str = "") -> None:
        self.status_code = status_code
        self._json = json_body if json_body is not None else []
        self.text = text

    def json(self) -> Any:
        return self._json

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise AssertionError(f"HTTP {self.status_code}: {self.text}")


@pytest.fixture
def stub_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    from services import portal_incident_report

    monkeypatch.setattr(portal_incident_report, "SUPABASE_URL", "https://stub.supabase.co")
    monkeypatch.setattr(portal_incident_report, "SERVICE_KEY", "stub-service-key")
    monkeypatch.setattr(portal_incident_report, "DEFAULT_SLA_MINUTES", 60)
    yield


def _default_get(url: str, **kwargs: Any) -> _FakeResponse:
    # clients context lookup
    if "/rest/v1/clients" in url:
        return _FakeResponse(
            status_code=200,
            json_body=[{
                "id": "cid-42",
                "company_name": "Acme Dental",
                "domain": "acme-dental.example",
                "guarantee_status": "active",
                "guarantee_checklist_critical_ok": True,
                "guarantee_checklist_high_ok": True,
                "guarantee_checklist_subscription_ok": True,
            }],
        )
    # CEO profile lookup
    if "/rest/v1/profiles" in url:
        return _FakeResponse(
            status_code=200,
            json_body=[{"id": "ceo-profile-uuid", "role": "ceo"}],
        )
    return _FakeResponse(status_code=404, text="unexpected GET")


def test_report_incident_raises_when_no_client_linked(
    monkeypatch: pytest.MonkeyPatch, stub_env: None
) -> None:
    from fastapi import HTTPException
    from services import portal_incident_report

    monkeypatch.setattr(portal_incident_report, "get_client_id_for_portal_user", lambda _uid: None)

    with pytest.raises(HTTPException) as exc:
        portal_incident_report.report_incident(
            uid="auth-uid-1", user_email="user@acme-dental.example", description=""
        )
    assert exc.value.status_code == 400
    assert "No portal client" in str(exc.value.detail)


def test_report_incident_happy_path_returns_case_id_and_sla(
    monkeypatch: pytest.MonkeyPatch, stub_env: None
) -> None:
    from services import portal_incident_report

    monkeypatch.setattr(portal_incident_report, "get_client_id_for_portal_user", lambda _uid: "cid-42")

    post_calls: list[dict[str, Any]] = []
    patch_calls: list[dict[str, Any]] = []

    def _fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        post_calls.append({"url": url, "json": kwargs.get("json")})
        if "/rest/v1/client_incident_reports" in url:
            return _FakeResponse(
                status_code=201,
                json_body=[
                    {
                        "id": "11111111-2222-3333-4444-555555555555",
                        "client_id": "cid-42",
                    }
                ],
            )
        if "/rest/v1/crm_support_tickets" in url:
            return _FakeResponse(
                status_code=201, json_body=[{"id": "ticket-uuid-7"}]
            )
        return _FakeResponse(status_code=500, text="unexpected POST")

    def _fake_patch(url: str, **kwargs: Any) -> _FakeResponse:
        patch_calls.append({"url": url, "json": kwargs.get("json")})
        return _FakeResponse(status_code=204)

    monkeypatch.setattr(portal_incident_report.httpx, "get", _default_get)
    monkeypatch.setattr(portal_incident_report.httpx, "post", _fake_post)
    monkeypatch.setattr(portal_incident_report.httpx, "patch", _fake_patch)

    # Stub side-effects: OpenPhone + Resend report success.
    monkeypatch.setattr(
        portal_incident_report, "send_ceo_sms", lambda *_a, **_kw: {"ok": True, "data": {}}
    )
    monkeypatch.setattr(
        portal_incident_report, "send_resend", lambda **_kw: {"id": "resend-123"}
    )

    out = portal_incident_report.report_incident(
        uid="auth-uid-2", user_email="user@acme-dental.example", description="suspicious login"
    )

    assert out["ok"] is True
    assert out["case_id"].startswith("HAWK-")
    assert out["ceo_sms_status"] == "sent"
    assert out["client_email_status"] == "sent"
    assert out["support_ticket_id"] == "ticket-uuid-7"
    assert out["sla_minutes"] == 60
    assert out["guarantee_status"] == "active"
    assert out["guarantee_conditions_met"] is True

    # Incident row got posted with the expected columns.
    inc_post = next(c for c in post_calls if "client_incident_reports" in c["url"])
    assert inc_post["json"]["client_id"] == "cid-42"
    assert inc_post["json"]["reported_by_user_id"] == "auth-uid-2"
    assert inc_post["json"]["description"] == "suspicious login"
    # Status patch ran with all three fields populated.
    assert patch_calls, "expected a status patch after fan-out"
    assert set(patch_calls[0]["json"].keys()) == {
        "ceo_sms_status",
        "client_email_status",
        "support_ticket_id",
    }


def test_report_incident_tolerates_openphone_unconfigured(
    monkeypatch: pytest.MonkeyPatch, stub_env: None
) -> None:
    from services import portal_incident_report

    monkeypatch.setattr(portal_incident_report, "get_client_id_for_portal_user", lambda _uid: "cid-42")

    monkeypatch.setattr(portal_incident_report.httpx, "get", _default_get)
    monkeypatch.setattr(
        portal_incident_report.httpx,
        "post",
        lambda url, **kw: _FakeResponse(
            status_code=201,
            json_body=[{"id": "inc-id-99"}] if "client_incident_reports" in url else [{"id": "tkt-9"}],
        ),
    )
    monkeypatch.setattr(portal_incident_report.httpx, "patch", lambda *_a, **_kw: _FakeResponse(204))

    monkeypatch.setattr(
        portal_incident_report,
        "send_ceo_sms",
        lambda *_a, **_kw: {"skipped": True, "reason": "openphone_not_configured"},
    )
    monkeypatch.setattr(portal_incident_report, "send_resend", lambda **_kw: {"id": "resend-456"})

    out = portal_incident_report.report_incident(
        uid="auth-uid-3", user_email="user@acme-dental.example", description=""
    )

    assert out["ok"] is True
    assert out["ceo_sms_status"] == "skipped:openphone_not_configured"
    assert out["client_email_status"] == "sent"


def test_report_incident_tolerates_support_ticket_mirror_crash(
    monkeypatch: pytest.MonkeyPatch, stub_env: None
) -> None:
    """Transport-level errors in the ticket-mirror step must not crash the endpoint
    after the incident row has already been persisted."""
    import httpx

    from services import portal_incident_report

    monkeypatch.setattr(portal_incident_report, "get_client_id_for_portal_user", lambda _uid: "cid-42")

    def _flaky_get(url: str, **kwargs: Any) -> _FakeResponse:
        if "/rest/v1/profiles" in url:
            raise httpx.ConnectError("simulated transport failure")
        return _default_get(url, **kwargs)

    monkeypatch.setattr(portal_incident_report.httpx, "get", _flaky_get)
    monkeypatch.setattr(
        portal_incident_report.httpx,
        "post",
        lambda url, **kw: _FakeResponse(
            status_code=201,
            json_body=[{"id": "inc-crash-1"}] if "client_incident_reports" in url else [{"id": "x"}],
        ),
    )
    patch_calls: list[dict[str, Any]] = []
    monkeypatch.setattr(
        portal_incident_report.httpx,
        "patch",
        lambda url, **kw: (patch_calls.append({"url": url, "json": kw.get("json")}) or _FakeResponse(204)),
    )
    monkeypatch.setattr(portal_incident_report, "send_ceo_sms", lambda *_a, **_kw: {"ok": True})
    monkeypatch.setattr(portal_incident_report, "send_resend", lambda **_kw: {"id": "resend-ok"})

    out = portal_incident_report.report_incident(
        uid="auth-uid-crash", user_email="user@acme-dental.example", description=""
    )

    # Endpoint still returns the receipt — the incident is persisted.
    assert out["ok"] is True
    assert out["ceo_sms_status"] == "sent"
    assert out["client_email_status"] == "sent"
    assert out["support_ticket_id"] is None
    # Status patch still runs so the row isn't left with pending values.
    assert patch_calls, "expected status patch to still run even when mirror fails"


def test_report_incident_tolerates_resend_unconfigured(
    monkeypatch: pytest.MonkeyPatch, stub_env: None
) -> None:
    from services import portal_incident_report

    monkeypatch.setattr(portal_incident_report, "get_client_id_for_portal_user", lambda _uid: "cid-42")
    monkeypatch.setattr(portal_incident_report.httpx, "get", _default_get)
    monkeypatch.setattr(
        portal_incident_report.httpx,
        "post",
        lambda url, **kw: _FakeResponse(
            status_code=201,
            json_body=[{"id": "inc-id-50"}] if "client_incident_reports" in url else [{"id": "tkt-50"}],
        ),
    )
    monkeypatch.setattr(portal_incident_report.httpx, "patch", lambda *_a, **_kw: _FakeResponse(204))
    monkeypatch.setattr(portal_incident_report, "send_ceo_sms", lambda *_a, **_kw: {"ok": True})
    monkeypatch.setattr(portal_incident_report, "send_resend", lambda **_kw: {"skipped": True})

    out = portal_incident_report.report_incident(
        uid="auth-uid-4", user_email="user@acme-dental.example", description=""
    )

    assert out["client_email_status"] == "skipped:no_resend_key"
    assert out["ceo_sms_status"] == "sent"


def test_report_incident_returns_guarantee_suspended_when_conditions_unmet(
    monkeypatch: pytest.MonkeyPatch, stub_env: None
) -> None:
    from services import portal_incident_report

    monkeypatch.setattr(portal_incident_report, "get_client_id_for_portal_user", lambda _uid: "cid-42")

    def _suspended_get(url: str, **kwargs: Any) -> _FakeResponse:
        if "/rest/v1/clients" in url:
            return _FakeResponse(
                status_code=200,
                json_body=[{
                    "id": "cid-42",
                    "company_name": "Acme Dental",
                    "domain": "acme-dental.example",
                    "guarantee_status": "suspended",
                    "guarantee_checklist_critical_ok": False,
                    "guarantee_checklist_high_ok": True,
                    "guarantee_checklist_subscription_ok": True,
                }],
            )
        if "/rest/v1/profiles" in url:
            return _FakeResponse(status_code=200, json_body=[{"id": "ceo-uuid", "role": "ceo"}])
        return _FakeResponse(status_code=404, text="unexpected GET")

    monkeypatch.setattr(portal_incident_report.httpx, "get", _suspended_get)
    monkeypatch.setattr(
        portal_incident_report.httpx,
        "post",
        lambda url, **kw: _FakeResponse(
            status_code=201,
            json_body=[{"id": "inc-susp-1"}] if "client_incident_reports" in url else [{"id": "tkt-s"}],
        ),
    )
    monkeypatch.setattr(portal_incident_report.httpx, "patch", lambda *_a, **_kw: _FakeResponse(204))
    monkeypatch.setattr(portal_incident_report, "send_ceo_sms", lambda *_a, **_kw: {"ok": True})
    monkeypatch.setattr(portal_incident_report, "send_resend", lambda **_kw: {"id": "resend-s"})

    out = portal_incident_report.report_incident(
        uid="auth-uid-susp", user_email="user@acme-dental.example", description="ransomware"
    )

    assert out["ok"] is True
    assert out["guarantee_status"] == "suspended"
    assert out["guarantee_conditions_met"] is False
