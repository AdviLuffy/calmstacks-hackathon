"""Session/report storage.

Two implementations, both small and both honest about failure:

* :class:`InMemorySessionStore` keeps records for the life of the process. Used by default
  (``TRACE_PERSIST_SESSIONS`` is off) so the API never writes to the repository.
* :class:`FileSessionStore` adds one JSON file per session under ``Settings.session_root``,
  written atomically. It raises :class:`SessionPersistenceError` on a damaged or unreadable
  file rather than skipping it, so a lost session is always visible.

Serialization is P3-owned and explicit. Unknown keys in a stored file are preserved on read
in the sense that they are reported as an error instead of being dropped silently: a stored
session that this version cannot interpret is refused, not quietly repaired.
"""
from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

from app.contract.assumptions import AssumptionViolation
from app.services.interfaces import (
    EngineDeclaration,
    ProvenanceDeclaration,
    SessionRecord,
    SessionStatus,
    StageFailure,
    StageResult,
    StageStatus,
    StageWarning,
)

#: Session identifiers P3 generates and accepts: hex only, so a stored file name is safe.
_SAFE_ID_CHARACTERS = set("0123456789abcdef")


class SessionPersistenceError(RuntimeError):
    """A session could not be stored or read back. Never swallowed by the store itself."""


def is_valid_session_id(session_id: object) -> bool:
    """True for a P3 session identifier (hex, non-empty, no path separators)."""
    return (
        isinstance(session_id, str)
        and 1 <= len(session_id) <= 64
        and all(character in _SAFE_ID_CHARACTERS for character in session_id)
    )


def _isoformat(value: datetime | None) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else None


def _parse_datetime(value: Any, label: str) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise SessionPersistenceError("stored %s is not a timestamp string" % label)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise SessionPersistenceError("stored %s is not a valid timestamp" % label) from exc
    if parsed.utcoffset() is None:
        raise SessionPersistenceError("stored %s is not timezone-aware" % label)
    return parsed


def serialize_session(record: SessionRecord) -> dict[str, Any]:
    """The exact JSON shape P3 writes and reads. Nothing is added or dropped.

    ``SessionRecord.evidence_bundle`` is deliberately absent from this shape: the submitted
    evidence is never written to disk, so a session reloaded from a file serves its evidence
    endpoints as explicitly unavailable with a stated reason instead of as an empty success.
    """
    return {
        "session_id": record.session_id,
        "status": record.status.value,
        "submitted_at": _isoformat(record.submitted_at),
        "completed_at": _isoformat(record.completed_at),
        "case_id": record.case_id,
        "evidence_bytes": record.evidence_bytes,
        "evidence_sha256": record.evidence_sha256,
        "evidence_persisted": record.evidence_persisted,
        "bundle_sha256": record.bundle_sha256,
        "mock_data": record.mock_data,
        "records": [
            {
                "subject": item.subject,
                "origin": item.origin,
                "produced_at": _isoformat(item.produced_at),
                "confidence": item.confidence,
                "confidence_basis": item.confidence_basis,
            }
            for item in record.records
        ],
        "notices": [
            {
                "code": notice.code,
                "message": notice.message,
                "detail": notice.detail,
                "stage": notice.stage,
            }
            for notice in record.notices
        ],
        "stages": [serialize_stage(stage) for stage in record.stages],
        "report": record.report,
        "report_id": record.report_id,
        "generated_utc": _isoformat(record.generated_utc),
        "audit": record.audit,
        "reproducibility": record.reproducibility,
        "options": dict(record.options),
    }


def serialize_stage(stage: StageResult) -> dict[str, Any]:
    """One stage, including its warnings, its failure and its provenance."""
    return {
        "stage": stage.stage,
        "status": stage.status.value,
        "engine": stage.engine.as_mapping() if stage.engine else None,
        "note": stage.note,
        "started_at": _isoformat(stage.started_at),
        "finished_at": _isoformat(stage.finished_at),
        "data": stage.data,
        "synthetic_preview": stage.synthetic_preview,
        "warnings": [
            {
                "code": warning.code,
                "message": warning.message,
                "detail": warning.detail,
                "stage": warning.stage,
            }
            for warning in stage.warnings
        ],
        "failure": (
            {
                "code": stage.failure.code,
                "message": stage.failure.message,
                "detail": stage.failure.detail,
                "stage": stage.failure.stage,
            }
            if stage.failure
            else None
        ),
        "provenance": [
            {
                "subject": item.subject,
                "origin": item.origin,
                "produced_at": _isoformat(item.produced_at),
                "confidence": item.confidence,
                "confidence_basis": item.confidence_basis,
            }
            for item in stage.provenance
        ],
    }


def _provenance_from_payload(payload: Any, label: str) -> ProvenanceDeclaration:
    if not isinstance(payload, Mapping):
        raise SessionPersistenceError("stored %s provenance row is not an object" % label)
    produced_at = _parse_datetime(payload.get("produced_at"), "%s produced_at" % label)
    if produced_at is None:
        raise SessionPersistenceError("stored %s provenance row has no produced_at" % label)
    try:
        return ProvenanceDeclaration(
            subject=payload.get("subject") if isinstance(payload.get("subject"), str) else "",
            origin=payload.get("origin") if isinstance(payload.get("origin"), str) else "",
            produced_at=produced_at,
            confidence=payload.get("confidence"),
            confidence_basis=payload.get("confidence_basis"),
        )
    except AssumptionViolation as exc:
        raise SessionPersistenceError(
            "stored %s provenance row violates A4: %s" % (label, exc)
        ) from exc
    except ValueError as exc:
        raise SessionPersistenceError(
            "stored %s provenance row is invalid: %s" % (label, exc)
        ) from exc


def _warning_from_payload(payload: Any, label: str) -> StageWarning:
    if not isinstance(payload, Mapping):
        raise SessionPersistenceError("stored %s warning is not an object" % label)
    try:
        return StageWarning(
            code=str(payload.get("code") or ""),
            message=str(payload.get("message") or ""),
            detail=payload.get("detail"),
            stage=payload.get("stage"),
        )
    except ValueError as exc:
        raise SessionPersistenceError("stored %s warning is invalid: %s" % (label, exc)) from exc


def _failure_from_payload(payload: Any, label: str) -> StageFailure | None:
    if payload is None:
        return None
    if not isinstance(payload, Mapping):
        raise SessionPersistenceError("stored %s failure is not an object" % label)
    try:
        return StageFailure(
            code=str(payload.get("code") or ""),
            message=str(payload.get("message") or ""),
            detail=payload.get("detail"),
            stage=payload.get("stage"),
        )
    except ValueError as exc:
        raise SessionPersistenceError("stored %s failure is invalid: %s" % (label, exc)) from exc


def _engine_from_payload(payload: Any, label: str) -> EngineDeclaration | None:
    if payload is None:
        return None
    if not isinstance(payload, Mapping):
        raise SessionPersistenceError("stored %s engine is not an object" % label)
    try:
        return EngineDeclaration(
            name=str(payload.get("name") or ""),
            version=str(payload.get("version") or ""),
            run_id=str(payload.get("run_id") or ""),
        )
    except AssumptionViolation as exc:
        raise SessionPersistenceError(
            "stored %s engine declaration violates A10: %s" % (label, exc)
        ) from exc


def deserialize_stage(payload: Any, label: str = "stage") -> StageResult:
    """Rebuild one stage. A payload this version cannot interpret is refused, not repaired."""
    if not isinstance(payload, Mapping):
        raise SessionPersistenceError("stored %s is not an object" % label)
    try:
        status = StageStatus(str(payload.get("status") or ""))
    except ValueError as exc:
        raise SessionPersistenceError("stored %s has an unknown status" % label) from exc
    data = payload.get("data")
    preview = payload.get("synthetic_preview")
    try:
        return StageResult(
            stage=str(payload.get("stage") or ""),
            status=status,
            data=dict(data) if isinstance(data, Mapping) else data,
            synthetic_preview=dict(preview) if isinstance(preview, Mapping) else preview,
            engine=_engine_from_payload(payload.get("engine"), label),
            warnings=tuple(
                _warning_from_payload(item, label) for item in (payload.get("warnings") or [])
            ),
            failure=_failure_from_payload(payload.get("failure"), label),
            provenance=tuple(
                _provenance_from_payload(item, label)
                for item in (payload.get("provenance") or [])
            ),
            note=payload.get("note"),
            started_at=_parse_datetime(payload.get("started_at"), "%s started_at" % label),
            finished_at=_parse_datetime(payload.get("finished_at"), "%s finished_at" % label),
        )
    except SessionPersistenceError:
        raise
    except (TypeError, ValueError) as exc:
        raise SessionPersistenceError("stored %s is invalid: %s" % (label, exc)) from exc


def deserialize_session(payload: Any) -> SessionRecord:
    """Rebuild a session record from :func:`serialize_session` output."""
    if not isinstance(payload, Mapping):
        raise SessionPersistenceError("a stored session must be a JSON object")
    session_id = payload.get("session_id")
    if not is_valid_session_id(session_id):
        raise SessionPersistenceError("stored session_id is not a P3 session identifier")
    try:
        status = SessionStatus(str(payload.get("status") or ""))
    except ValueError as exc:
        raise SessionPersistenceError("stored session has an unknown status") from exc
    submitted_at = _parse_datetime(payload.get("submitted_at"), "submitted_at")
    if submitted_at is None:
        raise SessionPersistenceError("stored session has no submitted_at")

    report = payload.get("report")
    audit = payload.get("audit")
    reproducibility = payload.get("reproducibility")
    options = payload.get("options")
    return SessionRecord(
        session_id=session_id,
        status=status,
        submitted_at=submitted_at,
        completed_at=_parse_datetime(payload.get("completed_at"), "completed_at"),
        case_id=payload.get("case_id"),
        evidence_bytes=int(payload.get("evidence_bytes") or 0),
        evidence_sha256=payload.get("evidence_sha256"),
        evidence_persisted=bool(payload.get("evidence_persisted")),
        bundle_sha256=payload.get("bundle_sha256"),
        mock_data=bool(payload.get("mock_data")),
        records=tuple(
            _provenance_from_payload(item, "session") for item in (payload.get("records") or [])
        ),
        notices=tuple(
            _warning_from_payload(item, "session notice")
            for item in (payload.get("notices") or [])
        ),
        stages=tuple(
            deserialize_stage(item, "stage %d" % index)
            for index, item in enumerate(payload.get("stages") or [])
        ),
        report=dict(report) if isinstance(report, Mapping) else report,
        report_id=payload.get("report_id"),
        generated_utc=_parse_datetime(payload.get("generated_utc"), "generated_utc"),
        audit=dict(audit) if isinstance(audit, Mapping) else audit,
        reproducibility=(
            dict(reproducibility) if isinstance(reproducibility, Mapping) else reproducibility
        ),
        options=dict(options) if isinstance(options, Mapping) else {},
    )


class InMemorySessionStore:
    """Keeps sessions in process memory, newest first. The default store."""

    def __init__(self) -> None:
        self._records: dict[str, SessionRecord] = {}

    def save(self, record: SessionRecord) -> None:
        if not isinstance(record, SessionRecord):
            raise SessionPersistenceError("only SessionRecord values can be stored")
        if not is_valid_session_id(record.session_id):
            raise SessionPersistenceError(
                "session_id %r is not a P3 session identifier" % (record.session_id,)
            )
        self._records[record.session_id] = record

    def get(self, session_id: str) -> SessionRecord | None:
        if not isinstance(session_id, str):
            return None
        return self._records.get(session_id)

    def list(self, *, limit: int, offset: int) -> tuple[tuple[SessionRecord, ...], int]:
        ordered = sorted(
            self._records.values(),
            key=lambda item: (item.submitted_at, item.session_id),
            reverse=True,
        )
        total = len(ordered)
        start = max(int(offset), 0)
        stop = start + max(int(limit), 0)
        return tuple(ordered[start:stop]), total

    def delete(self, session_id: str) -> bool:
        return self._records.pop(session_id, None) is not None

    def close(self) -> None:
        return None

    def __len__(self) -> int:
        return len(self._records)

    def __contains__(self, session_id: object) -> bool:
        return isinstance(session_id, str) and session_id in self._records


class FileSessionStore(InMemorySessionStore):
    """One JSON file per session, plus memory. A damaged file is reported, never skipped.

    ``load_errors`` lists every stored file this process refused, and the API surfaces those
    in ``/api/health`` and ``/api/meta``. ``get`` raises for an identifier whose file was
    refused, so a lost session is visible instead of looking like "never existed".

    ``save`` commits to memory *before* writing the file: a failing disk must not make a
    session disappear from the process that just accepted it. The caller is told the write
    failed through :class:`SessionPersistenceError`.
    """

    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root = Path(root)
        self.load_errors: tuple[str, ...] = ()
        self._damaged: dict[str, str] = {}
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise SessionPersistenceError(
                "session directory %s could not be created: %s" % (self.root, exc)
            ) from exc
        self._load()

    def path_for(self, session_id: str) -> Path:
        """The file that backs one session. An invalid identifier cannot escape the root."""
        if not is_valid_session_id(session_id):
            raise SessionPersistenceError(
                "session_id %r is not a P3 session identifier" % (session_id,)
            )
        return self.root / ("%s.json" % session_id)

    def _load(self) -> None:
        errors: list[str] = []
        damaged: dict[str, str] = {}
        for path in sorted(self.root.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                record = deserialize_session(payload)
            except (OSError, json.JSONDecodeError, SessionPersistenceError) as exc:
                problem = "stored session file %s could not be read: %s" % (path.name, exc)
                errors.append(problem)
                damaged[path.stem] = problem
                continue
            super().save(record)
        self._damaged = damaged
        self.load_errors = tuple(errors)

    def save(self, record: SessionRecord) -> None:
        super().save(record)
        path = self.path_for(record.session_id)
        payload = serialize_session(record)
        temporary = path.with_name(path.name + ".tmp")
        try:
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            os.replace(temporary, path)
        except OSError as exc:
            raise SessionPersistenceError(
                "session %s could not be written to %s: %s" % (record.session_id, path, exc)
            ) from exc

    def get(self, session_id: str) -> SessionRecord | None:
        if isinstance(session_id, str) and session_id in self._damaged:
            raise SessionPersistenceError(self._damaged[session_id])
        return super().get(session_id)

    def delete(self, session_id: str) -> bool:
        removed = super().delete(session_id)
        try:
            self.path_for(session_id).unlink(missing_ok=True)
        except SessionPersistenceError:
            raise
        except OSError as exc:
            raise SessionPersistenceError(
                "session %s file could not be removed: %s" % (session_id, exc)
            ) from exc
        return removed
