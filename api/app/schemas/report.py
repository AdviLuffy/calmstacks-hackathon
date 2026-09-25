"""The report envelope: P3's wrapper around P2's report, never P2's report itself.

Only names the frozen M0 material already fixes are modelled:

* ``report_id`` is the frozen derived identifier (validated against its frozen pattern);
* ``generated_utc`` and the ``audit`` volatile paths (``runtime_ms``,
  ``provider_calls[].latency_ms``, ``outputs_hash``) are named by the M0 material as the
  fields excluded from ``outputs_hash``.

The report body travels as an opaque mapping. P3 never adds, renames or validates a claim,
finding or any other P2 field, so integrating the frozen
``intelligence_report.schema.json`` later changes nothing here.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, model_validator

from app.contract.canonical import DERIVED_REPORT_ID_PATTERN
from app.schemas.common import (
    APIWarning,
    ErrorDetail,
    Reproducibility,
    project_failures,
    project_warnings,
)
from app.schemas.session import PipelineStageView, project_stage
from app.services.interfaces import SessionRecord, SessionStatus


class ReportAudit(BaseModel):
    """P3's audit block. Unknown keys P2 supplies are preserved, never stripped."""

    model_config = ConfigDict(extra="allow")

    runtime_ms: float | None = None
    provider_calls: list[dict[str, Any]] | None = None
    outputs_hash: str | None = None


class ReportEnvelope(BaseModel):
    """The report plus its session context, warnings and failures."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str
    status: SessionStatus
    mock_data: bool
    report_available: bool
    report: dict[str, Any] | None = None
    report_id: str | None = None
    generated_utc: datetime | None = None
    audit: ReportAudit | None = None
    reproducibility: Reproducibility | None = None
    stages: tuple[PipelineStageView, ...] = ()
    warnings: tuple[APIWarning, ...] = ()
    failures: tuple[ErrorDetail, ...] = ()

    @model_validator(mode="after")
    def _report_id_matches_the_frozen_pattern(self) -> "ReportEnvelope":
        if self.report_id is None:
            return self
        if not DERIVED_REPORT_ID_PATTERN:
            raise ValueError("the frozen report_id pattern is missing")
        import re

        if re.fullmatch(DERIVED_REPORT_ID_PATTERN, self.report_id) is None:
            raise ValueError(
                "report_id %r does not match the frozen derived pattern %s"
                % (self.report_id, DERIVED_REPORT_ID_PATTERN)
            )
        return self


def project_report(record: SessionRecord) -> ReportEnvelope:
    """Project a session's report view. Failures and warnings always travel with it."""
    audit = record.audit if isinstance(record.audit, dict) else None
    report = record.report if isinstance(record.report, dict) else None
    return ReportEnvelope(
        session_id=record.session_id,
        status=record.status,
        mock_data=record.mock_data,
        report_available=record.report_available,
        report=dict(report) if report is not None else None,
        report_id=record.report_id,
        generated_utc=record.generated_utc,
        audit=ReportAudit(**audit) if audit is not None else None,
        reproducibility=(
            Reproducibility(**record.reproducibility)
            if isinstance(record.reproducibility, dict)
            else None
        ),
        stages=tuple(project_stage(stage) for stage in record.stages),
        warnings=project_warnings(record.warnings),
        failures=project_failures(record.failures),
    )
