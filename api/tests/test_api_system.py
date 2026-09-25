"""``GET /api/health`` and ``GET /api/meta``: what the API says about itself must be true."""
from __future__ import annotations

from app.contract.assumptions import DATA_ORIGINS
from app.contract.canonical import CANONICALIZATION_PROFILE
from app.services.interfaces import (
    STAGE_RECOVERY,
    SessionStatus,
    WARNING_CONFIG_INVALID,
    WARNING_SESSION_PERSISTENCE_FAILED,
)
from app.services.pending_contract import FROZEN_STATUS, PENDING_CONTRACT_ITEMS
from app.services.session_store import FileSessionStore
from p3_helpers import FakeEngine, make_settings, make_wiring, mock_slot, real_slot


def test_health_reports_versions_and_engine_slots(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "degraded"  # nothing is wired in the default test application
    assert payload["ready"] is False
    assert payload["api_version"] == "0.1.0"
    assert payload["contract_version"] == "1.0"
    assert payload["canonicalization_profile"] == CANONICALIZATION_PROFILE
    assert set(payload["engines"]) == {"recovery", "intelligence"}
    assert payload["engines"]["recovery"]["resolved_mode"] == "unavailable"
    assert payload["engines"]["recovery"]["available"] is False
    assert payload["engines"]["recovery"]["note"]


def test_health_is_ok_only_when_a_real_engine_is_wired(make_client):
    wiring = make_wiring(recovery=real_slot(STAGE_RECOVERY, FakeEngine(stage=STAGE_RECOVERY)))
    payload = make_client(wiring=wiring).get("/api/health").json()
    assert payload["status"] == "ok"
    assert payload["ready"] is True
    assert payload["engines"]["recovery"]["declaration"] == "fake-engine 1.2.3 (run run-1)"
    assert payload["mock_data"] is False


def test_health_reports_that_synthetic_data_is_in_play(make_client):
    wiring = make_wiring(recovery=mock_slot(STAGE_RECOVERY))
    payload = make_client(wiring=wiring).get("/api/health").json()
    assert payload["mock_data"] is True
    assert payload["engines"]["recovery"]["resolved_mode"] == "mock"
    assert payload["engines"]["recovery"]["available"] is False


def test_configuration_problems_are_repeated_by_health(make_client):
    settings = make_settings(
        config_warnings=("TRACE_AI_MODE='nonsense' is not one of ('auto', 'real'); 'auto' used.",)
    )
    payload = make_client(settings=settings).get("/api/health").json()
    assert [warning["code"] for warning in payload["warnings"]] == [WARNING_CONFIG_INVALID]
    assert payload["warnings"][0]["detail"].startswith("TRACE_AI_MODE=")


def test_meta_exposes_the_frozen_vocabulary(client):
    payload = client.get("/api/meta").json()
    assert payload["canonicalization_profile"] == CANONICALIZATION_PROFILE
    assert payload["report_schema_id"] == "trace.intelligence_report/1.0"
    assert payload["report_schema_frozen"] is False
    assert tuple(payload["data_origins"]) == DATA_ORIGINS
    assert payload["confidence_ceilings"]["observed"] == 1.0
    assert payload["confidence_ceilings"]["ai_assisted"] == 0.70
    assert payload["confidence_ceilings"]["unavailable"] is None
    assert "session.submitted_at" in payload["bookkeeping_timestamp_fields"]
    assert tuple(payload["session_statuses"]) == tuple(
        status.value for status in SessionStatus
    )


def test_meta_repeats_the_p1_contract_registry(client):
    payload = client.get("/api/meta").json()
    assert [item["decision_id"] for item in payload["decisions"]][:5] == [
        "M0-DEC-01",
        "M0-DEC-02",
        "M0-DEC-03",
        "M0-DEC-04",
        "M0-DEC-05",
    ]
    recorded = {item["ambiguity_id"]: item for item in payload["ambiguities"]}
    assert "M0-AMB-07" in recorded
    assert "M0-AMB-07" not in payload["blocking_ambiguity_ids"]
    assert recorded["M0-AMB-07"]["blocking"] is False
    assert "M0-DEC-06" in recorded["M0-AMB-07"]["resolution"]


def test_meta_records_the_pending_amendment_as_frozen_and_implemented(client):
    """A receipt, not a grammar: the freeze happened and the receipt reports that state."""
    items = client.get("/api/meta").json()["pending_contract_items"]
    assert [item["item_id"] for item in items] == [
        item.item_id for item in PENDING_CONTRACT_ITEMS
    ]
    receipt = items[0]
    assert receipt["status"] == FROZEN_STATUS
    assert receipt["implemented"] is True
    assert "M0-AMB-07" in " ".join(receipt["recorded_in"])
    # The receipt must not smuggle in a second identifier format.
    assert "FRG-" not in str(receipt)


def test_meta_reports_storage_problems(make_client, tmp_path):
    (tmp_path / "deadbeef.json").write_text("{not json", encoding="utf-8")
    payload = make_client(store=FileSessionStore(tmp_path)).get("/api/meta").json()
    assert any(
        warning["code"] == WARNING_SESSION_PERSISTENCE_FAILED for warning in payload["warnings"]
    )
