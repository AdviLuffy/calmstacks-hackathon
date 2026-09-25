"""Session store: round-trip, damaged files, and a disk failure that stays visible."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from app.services.interfaces import (
    ProvenanceDeclaration,
    SessionRecord,
    SessionStatus,
    StageFailure,
    StageResult,
    StageStatus,
    StageWarning,
)
from app.services.session_store import (
    FileSessionStore,
    InMemorySessionStore,
    SessionPersistenceError,
    deserialize_session,
    is_valid_session_id,
    serialize_session,
)


def _record(session_id: str = "ab12") -> SessionRecord:
    submitted = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)
    return SessionRecord(
        session_id=session_id,
        status=SessionStatus.PARTIAL,
        submitted_at=submitted,
        completed_at=submitted,
        case_id="CASE",
        evidence_bytes=4,
        evidence_sha256="e" * 64,
        evidence_persisted=False,
        bundle_sha256="b" * 64,
        mock_data=False,
        records=(
            ProvenanceDeclaration(
                subject="session.submitted_evidence",
                origin="observed",
                produced_at=submitted,
                confidence=1.0,
                confidence_basis="raw submitted bytes were read as received",
            ),
        ),
        notices=(StageWarning("evidence_not_persisted", "not written", detail="TRACE_PERSIST_SESSIONS=False"),),
        stages=(
            StageResult(
                stage="recovery",
                status=StageStatus.FAILED,
                warnings=(StageWarning("engine_failed", "boom", detail="detail"),),
                failure=StageFailure("engine_failed", "boom", detail="detail"),
                note="why",
            ),
        ),
        report={"opaque": True},
        report_id="RPT-" + "a" * 12,
        generated_utc=submitted,
        audit={"runtime_ms": 1.5, "provider_calls": None, "outputs_hash": None},
        reproducibility={"bundle_sha256": "b" * 64, "module_version": "0.1.0"},
        options={"keep": True},
    )


def test_memory_store_round_trip_and_paging():
    store = InMemorySessionStore()
    first = _record("aa")
    second = _record("bb")
    store.save(first)
    store.save(second)
    assert store.get("aa").case_id == "CASE"
    assert store.get("missing") is None
    page, total = store.list(limit=1, offset=0)
    assert total == 2
    assert page[0].session_id == "bb"
    assert store.delete("aa") is True
    assert store.get("aa") is None
    assert store.delete("aa") is False


def test_serialize_round_trip_keeps_warnings_failures_and_opaque_report():
    original = _record()
    restored = deserialize_session(serialize_session(original))
    assert restored.session_id == original.session_id
    assert restored.status is SessionStatus.PARTIAL
    assert restored.warnings[0].code == "evidence_not_persisted"
    assert restored.stages[0].failure.code == "engine_failed"
    assert restored.report == {"opaque": True}
    assert restored.audit["outputs_hash"] is None
    assert restored.options == {"keep": True}
    assert restored.provenance[0].origin == "observed"


def test_invalid_session_ids_are_rejected():
    assert is_valid_session_id("abc123") is True
    assert is_valid_session_id("../etc/passwd") is False
    assert is_valid_session_id("") is False
    store = InMemorySessionStore()
    with pytest.raises(SessionPersistenceError):
        store.save(_record("not hex!"))


def test_file_store_round_trip_and_damaged_file_is_visible(tmp_path):
    store = FileSessionStore(tmp_path)
    store.save(_record("cd34"))
    store.close()

    reloaded = FileSessionStore(tmp_path)
    assert reloaded.get("cd34").report == {"opaque": True}
    assert (tmp_path / "cd34.json").is_file()
    assert not list(tmp_path.glob("*.tmp"))

    (tmp_path / "ee56.json").write_text("{not json", encoding="utf-8")
    damaged = FileSessionStore(tmp_path)
    assert damaged.load_errors
    assert "ee56.json" in damaged.load_errors[0]
    with pytest.raises(SessionPersistenceError):
        damaged.get("ee56")
    assert damaged.get("cd34") is not None


def test_uninterpretable_stored_session_is_refused_not_repaired(tmp_path):
    payload = serialize_session(_record("ff00"))
    payload["status"] = "not-a-status"
    (tmp_path / "ff00.json").write_text(json.dumps(payload), encoding="utf-8")
    store = FileSessionStore(tmp_path)
    assert store.load_errors
    with pytest.raises(SessionPersistenceError):
        store.get("ff00")


def test_naive_timestamp_is_refused():
    payload = serialize_session(_record())
    payload["submitted_at"] = "2026-09-25T12:00:00"
    with pytest.raises(SessionPersistenceError, match="timezone-aware"):
        deserialize_session(payload)


def test_disk_write_failure_keeps_the_session_in_memory(tmp_path, monkeypatch):
    store = FileSessionStore(tmp_path)

    def explode(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr("app.services.session_store.os.replace", explode)
    with pytest.raises(SessionPersistenceError, match="could not be written"):
        store.save(_record("0011"))
    assert store.get("0011").session_id == "0011"
