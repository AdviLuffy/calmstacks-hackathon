"""Session, stage and report-view projections for the HTTP layer.

The lifecycle words (submitted, processing, complete, partial, failed) and the stage words
(ok, mock, unavailable, failed, skipped) belong to P3's own interface vocabulary, so they are
modelled here. The evidence bundle and the intelligence report body are NOT modelled: they
stay opaque mappings until P1/P2 freeze them.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.common import (
    APIWarning,
    EngineInfo,
    ErrorDetail,
    PageMeta,
    ProvenanceRecord,
    Reproducibility,
    project_engine,
    project_failure,
    project_provenance,
    project_warnings,
)
from app.services.interfaces import (
    STAGE_NAMES,
    SessionRecord,
    SessionStatus,
    StageResult,
    StageStatus,
)


def _runtime_ms(stage: StageResult) -> float | None:
    """Bookkeeping duration (A7/D-4 exempt). None when the service did not time itself."""
    if stage.started_at is None or stage.finished_at is None:
        return None
    return round((stage.finished_at - stage.started_at).total_seconds() * 1000.0, 3)


class PipelineStageView(BaseModel):
    """One stage of one session, with everything a client needs to judge it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: str
    status: StageStatus
    engine: EngineInfo | None = None
    note: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    runtime_ms: float | None = None
    data_available: bool
    synthetic: bool
    synthetic_preview: dict[str, Any] | None = None
    warnings: tuple[APIWarning, ...] = ()
    failure: ErrorDetail | None = None
    provenance: tuple[ProvenanceRecord, ...] = ()


class SessionSummary(BaseModel):
    """The list view of a session: counts, never contents."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str
    status: SessionStatus
    case_id: str | None = None
    evidence_bytes: int
    evidence_sha256: str | None = None
    bundle_sha256: str | None = None
    submitted_at: datetime
    completed_at: datetime | None = None
    mock_data: bool
    report_available: bool
    report_id: str | None = None
    warning_count: int
    failure_count: int


class SessionDetail(SessionSummary):
    """The detail view: every stage, every warning, every failure, every provenance row."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_persisted: bool
    stages: tuple[PipelineStageView, ...] = ()
    warnings: tuple[APIWarning, ...] = ()
    failures: tuple[ErrorDetail, ...] = ()
    provenance: tuple[ProvenanceRecord, ...] = ()
    reproducibility: Reproducibility | None = None
    options: dict[str, Any] = {}


class SessionListResponse(BaseModel):
    """A page of sessions, with the page metadata and any API-level warnings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sessions: tuple[SessionSummary, ...]
    page: PageMeta
    warnings: tuple[APIWarning, ...] = ()


def project_stage(stage: StageResult) -> PipelineStageView:
    """Project one stage. Warnings, failure and provenance are never dropped."""
    return PipelineStageView(
        stage=stage.stage,
        status=stage.status,
        engine=project_engine(stage.engine),
        note=stage.note,
        started_at=stage.started_at,
        finished_at=stage.finished_at,
        runtime_ms=_runtime_ms(stage),
        data_available=stage.data is not None,
        synthetic=stage.synthetic_preview is not None,
        synthetic_preview=(
            dict(stage.synthetic_preview) if stage.synthetic_preview is not None else None
        ),
        warnings=project_warnings(stage.warnings),
        failure=project_failure(stage.failure),
        provenance=project_provenance(stage.provenance),
    )


def project_session_summary(record: SessionRecord) -> SessionSummary:
    return SessionSummary(
        session_id=record.session_id,
        status=record.status,
        case_id=record.case_id,
        evidence_bytes=record.evidence_bytes,
        evidence_sha256=record.evidence_sha256,
        bundle_sha256=record.bundle_sha256,
        submitted_at=record.submitted_at,
        completed_at=record.completed_at,
        mock_data=record.mock_data,
        report_available=record.report_available,
        report_id=record.report_id,
        warning_count=len(record.warnings),
        failure_count=len(record.failures),
    )


def project_reproducibility(record: SessionRecord) -> Reproducibility | None:
    payload = record.reproducibility
    if not isinstance(payload, dict):
        return None
    return Reproducibility(**payload)


def project_session_detail(record: SessionRecord) -> SessionDetail:
    summary = project_session_summary(record)
    return SessionDetail(
        **summary.model_dump(),
        evidence_persisted=record.evidence_persisted,
        stages=tuple(project_stage(stage) for stage in record.stages),
        warnings=project_warnings(record.warnings),
        failures=tuple(
            detail
            for detail in (project_failure(failure) for failure in record.failures)
            if detail is not None
        ),
        provenance=project_provenance(record.provenance),
        reproducibility=project_reproducibility(record),
        options=dict(record.options),
    )


def assert_known_stages() -> tuple[str, ...]:
    """The stage names the pipeline runs, in order."""
    return STAGE_NAMES
