"""Session lifecycle endpoints.

``POST /api/sessions`` runs the pipeline; the read endpoints project the stored record. The
report endpoint serves P2's report body inside a P3 envelope, and when there is no body it
fails with an explicit reason instead of returning an empty report.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, File, Form, Query, UploadFile, status

from app.dependencies import PipelineDep, SettingsDep
from app.errors import (
    InvalidInputError,
    ReportUnavailableError,
    SessionNotFoundError,
    SessionStorageError,
    UnsupportedMediaError,
)
from app.schemas.common import PageMeta
from app.schemas.report import ReportEnvelope, project_report
from app.schemas.session import (
    SessionDetail,
    SessionListResponse,
    project_session_detail,
    project_session_summary,
)
from app.services.interfaces import SessionRecord
from app.services.session_store import SessionPersistenceError

router = APIRouter(tags=["sessions"])

#: Upload media types P3 accepts for the bundle. A browser usually sends the first two.
ACCEPTED_UPLOAD_TYPES: tuple[str, ...] = (
    "application/json",
    "text/json",
    "text/plain",
    "application/octet-stream",
)


def _decode_options(raw: str | None) -> dict[str, Any]:
    """Opaque investigator options. P3 reads the JSON, never the keys."""
    if raw is None or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise InvalidInputError(
            "options must be valid JSON",
            detail="line %d column %d" % (exc.lineno, exc.colno),
        ) from exc
    if not isinstance(parsed, dict):
        raise InvalidInputError("options must be a JSON object")
    return parsed


def _require(pipeline: PipelineDep, session_id: str) -> SessionRecord:
    try:
        record = pipeline.get(session_id)
    except SessionPersistenceError as exc:
        raise SessionStorageError(
            "this session is stored but could not be read", detail=str(exc)
        ) from exc
    if record is None:
        raise SessionNotFoundError("no session with id %r" % session_id)
    return record


@router.post(
    "/sessions",
    response_model=SessionDetail,
    status_code=status.HTTP_201_CREATED,
    summary="Submit an evidence bundle and run the pipeline",
)
async def create_session(
    pipeline: PipelineDep,
    file: UploadFile = File(..., description="Evidence Bundle JSON, as produced by P1 tooling"),
    case_id: str | None = Form(None, description="Case identifier, needed for report_id"),
    options: str | None = Form(None, description="Optional JSON object, passed through opaquely"),
) -> SessionDetail:
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    if content_type and content_type not in ACCEPTED_UPLOAD_TYPES:
        raise UnsupportedMediaError(
            "unsupported upload media type %r" % (file.content_type,),
            detail="accepted: %s" % ", ".join(ACCEPTED_UPLOAD_TYPES),
        )
    evidence = await file.read()
    record = pipeline.submit(
        evidence=evidence, case_id=case_id, options=_decode_options(options)
    )
    return project_session_detail(record)


@router.get("/sessions", response_model=SessionListResponse, summary="List sessions")
def list_sessions(
    pipeline: PipelineDep,
    settings: SettingsDep,
    limit: int | None = Query(None, ge=1, description="Page size; clamped to the configured maximum"),
    offset: int = Query(0, ge=0, description="Sessions to skip"),
) -> SessionListResponse:
    effective = settings.default_page_limit if limit is None else min(limit, settings.max_page_limit)
    records, total = pipeline.list(limit=effective, offset=offset)
    return SessionListResponse(
        sessions=tuple(project_session_summary(record) for record in records),
        page=PageMeta(
            limit=effective,
            offset=offset,
            total=total,
            returned=len(records),
        ),
    )


@router.get(
    "/sessions/{session_id}",
    response_model=SessionDetail,
    summary="One session, with its stages, warnings, failures and provenance",
)
def get_session(session_id: str, pipeline: PipelineDep) -> SessionDetail:
    return project_session_detail(_require(pipeline, session_id))


@router.get(
    "/sessions/{session_id}/report",
    response_model=ReportEnvelope,
    summary="The report for one session, with its session context",
)
def get_report(session_id: str, pipeline: PipelineDep) -> ReportEnvelope:
    record = _require(pipeline, session_id)
    if not record.report_available:
        failures = ", ".join(
            "%s=%s" % (failure.stage, failure.code) for failure in record.failures
        )
        raise ReportUnavailableError(
            "this session has no report body",
            detail=failures or "no failure was recorded for this session",
            warnings=record.warnings,
        )
    return project_report(record)
