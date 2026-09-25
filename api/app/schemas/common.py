"""HTTP projections of the P3 service vocabulary, plus the shared error payload.

Only frozen things are modelled: the four A4 origins, the A10 engine declaration, the A4
confidence rules, and the six field names the M0 material freezes for the reproducibility
tuple. P1/P2 payloads (evidence bundle internals, claims, findings) are never modelled here
and never validated here: they travel as opaque mappings until their owners freeze them.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from app.contract.assumptions import (
    CONFIDENCE_CEILINGS,
    DATA_ORIGINS,
    validate_confidence,
    validate_engine_info,
)
from app.contract.canonical import CANONICALIZATION_PROFILE, REPORT_SCHEMA_ID
from app.errors import APIError
from app.services.interfaces import (
    EngineDeclaration,
    ProvenanceDeclaration,
    StageFailure,
    StageWarning,
)

#: Fields that are API bookkeeping rather than evidence (A7/D-4). They may use the analysis
#: clock; nothing else in this API may.
BOOKKEEPING_TIMESTAMP_FIELDS: tuple[str, ...] = (
    "session.submitted_at",
    "session.completed_at",
    "provenance.produced_at",
    "pipeline_stage.started_at",
    "pipeline_stage.finished_at",
)


class DataOrigin(str, Enum):
    """The four frozen provenance origins. A test asserts these equal the M0 vocabulary."""

    OBSERVED = "observed"
    COMPUTED = "computed"
    AI_ASSISTED = "ai_assisted"
    UNAVAILABLE = "unavailable"

    @classmethod
    def frozen_values(cls) -> tuple[str, ...]:
        return DATA_ORIGINS


class APIWarning(BaseModel):
    """A non-fatal problem. Every response that carries data carries its warnings."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    message: str
    stage: str | None = None
    origin: DataOrigin | None = None
    detail: str | None = None

    @field_validator("code", "message")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("warnings require a non-empty code and message")
        return value


class ErrorDetail(BaseModel):
    """A deliberate failure, reported instead of being swallowed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str
    message: str
    stage: str | None = None
    detail: str | None = None


class EngineInfo(BaseModel):
    """A10: ``name``, ``version`` and ``run_id`` are mandatory for a connected engine."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str
    version: str
    run_id: str

    @model_validator(mode="after")
    def _enforce_a10(self) -> "EngineInfo":
        validate_engine_info(name=self.name, version=self.version, run_id=self.run_id)
        return self


class ProvenanceRecord(BaseModel):
    """A4: ordinal reliability of a derivation, never a probability that a claim is true."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    subject: str
    origin: DataOrigin
    produced_at: datetime
    confidence: float | None = None
    confidence_basis: str | None = None

    @model_validator(mode="after")
    def _enforce_a4(self) -> "ProvenanceRecord":
        validate_confidence(
            origin=self.origin.value,
            confidence=self.confidence,
            confidence_basis=self.confidence_basis,
        )
        return self


class Reproducibility(BaseModel):
    """The six field names the M0 material freezes for the reproducibility tuple."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    bundle_sha256: str
    module_version: str
    prompt_version: str | None = None
    knowledge_version: str | None = None
    provider: str | None = None
    model: str | None = None


class PageMeta(BaseModel):
    """Pagination metadata for list responses."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    limit: int
    offset: int
    total: int
    returned: int


def project_warning(warning: StageWarning, *, origin: DataOrigin | None = None) -> APIWarning:
    """Convert a service warning. The stage travels with it and is never dropped."""
    return APIWarning(
        code=warning.code,
        message=warning.message,
        stage=warning.stage,
        origin=origin,
        detail=warning.detail,
    )


def project_warnings(warnings: Iterable[StageWarning]) -> tuple[APIWarning, ...]:
    return tuple(project_warning(warning) for warning in warnings)


def project_failure(failure: StageFailure | None) -> ErrorDetail | None:
    if failure is None:
        return None
    return ErrorDetail(
        code=failure.code,
        message=failure.message,
        stage=failure.stage,
        detail=failure.detail,
    )


def project_failures(failures: Iterable[StageFailure]) -> tuple[ErrorDetail, ...]:
    return tuple(
        detail for detail in (project_failure(failure) for failure in failures) if detail
    )


def project_engine(engine: EngineDeclaration | None) -> EngineInfo | None:
    if engine is None:
        return None
    return EngineInfo(name=engine.name, version=engine.version, run_id=engine.run_id)


def project_provenance(
    records: Iterable[ProvenanceDeclaration],
) -> tuple[ProvenanceRecord, ...]:
    return tuple(
        ProvenanceRecord(
            subject=record.subject,
            origin=DataOrigin(record.origin),
            produced_at=record.produced_at,
            confidence=record.confidence,
            confidence_basis=record.confidence_basis,
        )
        for record in records
    )


def api_error_payload(error: APIError) -> dict[str, Any]:
    """The single error envelope. Collected warnings are attached, never dropped."""
    return {
        "error": {
            "code": error.code,
            "message": error.message,
            "detail": error.detail,
        },
        "warnings": [
            project_warning(warning).model_dump(mode="json") for warning in error.warnings
        ],
    }


__all__ = [
    "APIWarning",
    "BOOKKEEPING_TIMESTAMP_FIELDS",
    "CANONICALIZATION_PROFILE",
    "CONFIDENCE_CEILINGS",
    "DataOrigin",
    "EngineInfo",
    "ErrorDetail",
    "PageMeta",
    "ProvenanceRecord",
    "REPORT_SCHEMA_ID",
    "Reproducibility",
    "api_error_payload",
    "project_engine",
    "project_failure",
    "project_failures",
    "project_provenance",
    "project_warning",
    "project_warnings",
]
