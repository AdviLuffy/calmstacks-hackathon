"""The error envelope is one shape, and warnings collected before a failure survive it."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.errors import (
    APIError,
    ContractNotFrozenError,
    InvalidInputError,
    ReportUnavailableError,
    code_for_status,
)
from app.main import create_app
from app.services.interfaces import WARNING_CONFIG_INVALID, StageWarning
from p3_helpers import make_settings, make_wiring


def test_api_error_requires_a_message_and_keeps_warnings():
    warning = StageWarning("engine_unavailable", "nothing is wired", stage="recovery")
    error = ReportUnavailableError("no report", detail="recovery=unavailable", warnings=(warning,))
    assert error.code == "report_unavailable"
    assert error.status_code == 409
    assert error.warnings == (warning,)
    try:
        APIError("  ")
    except ValueError:
        pass
    else:
        raise AssertionError("a blank APIError message must be refused")


def test_status_code_fallback_table():
    assert code_for_status(404) == "not_found"
    assert code_for_status(405) == "method_not_allowed"
    assert code_for_status(501) == "contract_not_frozen"
    assert code_for_status(418) == "http_error"


def test_deliberate_error_response_keeps_startup_warnings():
    settings = make_settings(config_warnings=("TRACE_AI_MODE was rejected",))
    application = create_app(settings=settings, wiring=make_wiring())

    probe = APIRouter()

    @probe.get("/boom")
    def boom() -> None:
        raise InvalidInputError("bad case_id", detail="blank")

    @probe.get("/crash")
    def crash() -> None:
        raise RuntimeError("secret traceback")

    @probe.get("/pending")
    def pending() -> None:
        raise ContractNotFrozenError(
            "the fragment EvidenceRef amendment is not frozen",
            detail="pending_p1_freeze",
        )

    application.include_router(probe, prefix="/api")
    client = TestClient(application, raise_server_exceptions=False)

    refused = client.get("/api/boom")
    assert refused.status_code == 400
    payload = refused.json()
    assert payload["error"] == {
        "code": "invalid_input",
        "message": "bad case_id",
        "detail": "blank",
    }
    assert payload["warnings"][0]["code"] == WARNING_CONFIG_INVALID
    assert "TRACE_AI_MODE" in payload["warnings"][0]["detail"]

    crashed = client.get("/api/crash")
    assert crashed.status_code == 500
    body = crashed.json()
    assert body["error"]["code"] == "internal_error"
    assert body["error"]["detail"] is None
    assert "secret traceback" not in crashed.text
    assert body["warnings"][0]["code"] == WARNING_CONFIG_INVALID

    pending_response = client.get("/api/pending")
    assert pending_response.status_code == 501
    assert pending_response.json()["error"]["code"] == "contract_not_frozen"
    assert pending_response.json()["warnings"]
