"""Session lifecycle over HTTP: complete, partial, failed, mocked, and refused.

P1's bundle and P2's report body stay opaque. These tests check P3's own lifecycle,
warnings, failures and provenance, never another team's schema.
"""
from __future__ import annotations

from app.contract.canonical import report_id as derive_report_id
from app.services.interfaces import (
    FAILURE_CODE_ENGINE_FAILED,
    FAILURE_CODE_ENGINE_MOCK,
    FAILURE_CODE_ENGINE_UNAVAILABLE,
    STAGE_INTELLIGENCE,
    STAGE_RECOVERY,
    WARNING_ENGINE_MOCK_IN_USE,
    WARNING_EVIDENCE_NOT_PERSISTED,
    WARNING_OUTPUTS_HASH_UNAVAILABLE,
    WARNING_PARTIAL_RESULT,
    WARNING_REPORT_ID_UNAVAILABLE,
    WARNING_SYNTHETIC_DATA_PRESENT,
)
from p3_helpers import (
    ARBITRARY_BUNDLE,
    ARBITRARY_REPORT,
    ExplodingEngine,
    FakeEngine,
    complete_wiring,
    make_bundle,
    make_settings,
    make_wiring,
    mock_slot,
    real_slot,
    unavailable_slot,
    upload,
)


def _stage(payload: dict, name: str) -> dict:
    return next(stage for stage in payload["stages"] if stage["stage"] == name)


def test_complete_session_keeps_both_bodies_opaque(make_client):
    client = make_client(wiring=complete_wiring())
    created = upload(client, ARBITRARY_BUNDLE, case_id="CASE-1", options='{"keep": true}')
    assert created.status_code == 201
    detail = created.json()

    assert detail["status"] == "complete"
    assert detail["case_id"] == "CASE-1"
    assert detail["mock_data"] is False
    assert detail["report_available"] is True
    assert detail["evidence_persisted"] is False
    assert detail["options"] == {"keep": True}
    assert (
        derive_report_id(
            "CASE-1", detail["bundle_sha256"], detail["reproducibility"]["module_version"]
        )
        == detail["report_id"]
    )
    assert {stage["status"] for stage in detail["stages"]} == {"ok"}
    assert all(stage["data_available"] is True for stage in detail["stages"])
    assert all(stage["synthetic"] is False for stage in detail["stages"])
    assert WARNING_EVIDENCE_NOT_PERSISTED in {item["code"] for item in detail["warnings"]}
    assert detail["failures"] == []

    fetched = client.get("/api/sessions/%s" % detail["session_id"])
    assert fetched.status_code == 200
    assert fetched.json()["session_id"] == detail["session_id"]

    report = client.get("/api/sessions/%s/report" % detail["session_id"])
    assert report.status_code == 200
    body = report.json()
    assert body["report"] == ARBITRARY_REPORT
    assert body["report_id"] == detail["report_id"]
    assert body["audit"]["outputs_hash"] is None
    assert WARNING_OUTPUTS_HASH_UNAVAILABLE in {item["code"] for item in body["warnings"]}
    assert "claims" not in body
    assert "findings" not in body


def test_report_id_is_withheld_without_a_case_id(make_client):
    response = upload(make_client(wiring=complete_wiring()), ARBITRARY_BUNDLE)
    detail = response.json()
    assert response.status_code == 201
    assert detail["report_id"] is None
    withheld = next(
        item for item in detail["warnings"] if item["code"] == WARNING_REPORT_ID_UNAVAILABLE
    )
    assert "case_id" in withheld["message"]


def test_partial_session_when_only_recovery_succeeds(make_client):
    wiring = make_wiring(
        recovery=real_slot(
            STAGE_RECOVERY, FakeEngine(stage=STAGE_RECOVERY, payload={"recovered": True})
        ),
        intelligence=unavailable_slot(STAGE_INTELLIGENCE, "P2 is not wired"),
    )
    client = make_client(wiring=wiring)
    detail = upload(client, ARBITRARY_BUNDLE, case_id="CASE-2").json()

    assert detail["status"] == "partial"
    assert detail["report_available"] is False
    assert detail["report_id"] is None
    assert _stage(detail, STAGE_RECOVERY)["status"] == "ok"
    intelligence = _stage(detail, STAGE_INTELLIGENCE)
    assert intelligence["status"] == "unavailable"
    assert intelligence["data_available"] is False
    assert intelligence["failure"]["code"] == FAILURE_CODE_ENGINE_UNAVAILABLE
    assert intelligence["note"] == "P2 is not wired"
    codes = {item["code"] for item in detail["warnings"]}
    assert WARNING_PARTIAL_RESULT in codes
    assert detail["failure_count"] == 1

    session_id = detail["session_id"]
    refused = client.get("/api/sessions/%s/report" % session_id)
    assert refused.status_code == 409
    payload = refused.json()
    assert payload["error"]["code"] == "report_unavailable"
    assert payload["warnings"]


def test_mock_stage_never_looks_like_engine_output(make_client):
    wiring = make_wiring(
        recovery=mock_slot(STAGE_RECOVERY, seed=11),
        intelligence=mock_slot(STAGE_INTELLIGENCE, seed=11),
    )
    detail = upload(make_client(wiring=wiring), ARBITRARY_BUNDLE, case_id="CASE-4").json()

    assert detail["status"] == "partial"
    assert detail["mock_data"] is True
    assert detail["report_available"] is False
    for stage in detail["stages"]:
        assert stage["status"] == "mock"
        assert stage["data_available"] is False
        assert stage["synthetic"] is True
        assert stage["synthetic_preview"]["synthetic"] is True
        assert stage["synthetic_preview"]["seed"] == 11
        assert stage["failure"]["code"] == FAILURE_CODE_ENGINE_MOCK
        codes = {item["code"] for item in stage["warnings"]}
        assert WARNING_ENGINE_MOCK_IN_USE in codes
        assert WARNING_SYNTHETIC_DATA_PRESENT in codes
        assert stage["provenance"][0]["origin"] == "unavailable"
        assert stage["provenance"][0]["confidence"] is None


def test_one_mock_and_one_ok_is_partial(make_client):
    wiring = make_wiring(
        recovery=real_slot(STAGE_RECOVERY, FakeEngine(stage=STAGE_RECOVERY)),
        intelligence=mock_slot(STAGE_INTELLIGENCE),
    )
    detail = upload(make_client(wiring=wiring), ARBITRARY_BUNDLE).json()
    assert detail["status"] == "partial"
    assert _stage(detail, STAGE_RECOVERY)["status"] == "ok"
    assert _stage(detail, STAGE_INTELLIGENCE)["status"] == "mock"
    assert detail["report_available"] is False


def test_sessions_are_listed_newest_first_with_page_metadata(make_client):
    client = make_client(
        settings=make_settings(default_page_limit=1, max_page_limit=2),
        wiring=complete_wiring(),
    )
    first = upload(client, ARBITRARY_BUNDLE, case_id="CASE-A").json()["session_id"]
    second = upload(client, make_bundle(), case_id="CASE-B").json()["session_id"]

    page = client.get("/api/sessions").json()
    assert page["page"] == {"limit": 1, "offset": 0, "total": 2, "returned": 1}
    assert page["sessions"][0]["session_id"] == second
    assert page["sessions"][0]["warning_count"] >= 1

    older = client.get("/api/sessions", params={"limit": 5, "offset": 1}).json()
    assert older["page"]["limit"] == 2  # clamped to the configured maximum
    assert older["sessions"][0]["session_id"] == first


def test_unknown_session_uses_the_error_envelope(client):
    response = client.get("/api/sessions/does-not-exist")
    assert response.status_code == 404
    payload = response.json()
    assert set(payload) == {"error", "warnings"}
    assert payload["error"]["code"] == "session_not_found"
    assert payload["error"]["detail"] is None
    assert isinstance(payload["warnings"], list)


def test_bad_bundle_options_and_media_type_are_refused(make_client):
    client = make_client(settings=make_settings(max_evidence_bytes=8))
    too_big = upload(client, ARBITRARY_BUNDLE)
    assert too_big.status_code == 413
    assert too_big.json()["error"]["code"] == "evidence_too_large"

    client = make_client()
    not_json = upload(client, b"\xff\xfe not utf-8")
    assert not_json.status_code == 400
    assert not_json.json()["error"]["code"] == "bundle_not_json"

    duplicate = upload(client, b'{"a": 1, "a": 2}')
    assert duplicate.status_code == 422
    assert duplicate.json()["error"]["code"] == "bundle_contract_violation"

    array_root = upload(client, [1, 2, 3])
    assert array_root.status_code == 422
    assert array_root.json()["error"]["code"] == "bundle_contract_violation"

    bad_options = upload(client, ARBITRARY_BUNDLE, options="[1]")
    assert bad_options.status_code == 400
    assert bad_options.json()["error"]["code"] == "invalid_input"

    wrong_type = upload(client, ARBITRARY_BUNDLE, content_type="image/png")
    assert wrong_type.status_code == 415
    assert wrong_type.json()["error"]["code"] == "unsupported_media_type"


def test_framework_errors_use_the_same_envelope(client):
    missing = client.get("/api/no-such-route")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "not_found"
    assert "warnings" in missing.json()

    wrong_method = client.put("/api/health")
    assert wrong_method.status_code == 405
    assert wrong_method.json()["error"]["code"] == "method_not_allowed"

    bad_query = client.get("/api/sessions", params={"limit": 0})
    assert bad_query.status_code == 422
    assert bad_query.json()["error"]["code"] == "invalid_input"
    assert "limit" in bad_query.json()["error"]["detail"]


def test_p2_receives_the_recovered_bundle_when_recovery_succeeds(make_client):
    recovery = FakeEngine(stage=STAGE_RECOVERY, name="fake-p1", payload={"from": "p1"})
    intelligence = FakeEngine(
        stage=STAGE_INTELLIGENCE, name="fake-p2", payload=dict(ARBITRARY_REPORT)
    )
    wiring = make_wiring(
        recovery=real_slot(STAGE_RECOVERY, recovery),
        intelligence=real_slot(STAGE_INTELLIGENCE, intelligence),
    )
    upload(make_client(wiring=wiring), ARBITRARY_BUNDLE, case_id="CASE-9")
    assert recovery.requests[0].evidence == ARBITRARY_BUNDLE
    assert intelligence.requests[0].evidence == {"from": "p1"}


def test_all_failed_stages_make_a_failed_session_not_a_500(make_client):
    wiring = make_wiring(
        recovery=real_slot(STAGE_RECOVERY, ExplodingEngine(stage=STAGE_RECOVERY)),
        intelligence=real_slot(STAGE_INTELLIGENCE, ExplodingEngine(stage=STAGE_INTELLIGENCE)),
    )
    response = upload(make_client(wiring=wiring), ARBITRARY_BUNDLE, case_id="CASE-3")
    assert response.status_code == 201
    detail = response.json()
    assert detail["status"] == "failed"
    assert detail["report_available"] is False
    assert {stage["failure"]["code"] for stage in detail["stages"]} == {FAILURE_CODE_ENGINE_FAILED}
    assert all(stage["data_available"] is False for stage in detail["stages"])
