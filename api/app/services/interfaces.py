"""P3 service interfaces: the boundary between the API and the P1/P2 engines.

This module is deliberately free of FastAPI and Pydantic. A teammate can implement a
:class:`RecoveryService` or an :class:`IntelligenceService` without importing the API
framework, and the API stays importable with no teammate code present at all.

Frozen M0 rules are enforced at construction time here, so an engine cannot hand the API a
declaration or a provenance record that violates the contract:

* A10  a connected engine declares ``name``, ``version`` and ``run_id``.
* A4   confidence is optional, capped per origin, and always accompanied by a basis of at
       least 8 characters.
* D-3  ``ai_assisted`` output is INFERRED and capped at 0.70; ``unavailable`` carries no
       confidence at all.
* A7   ``produced_at``, ``started_at``, ``finished_at``, ``submitted_at`` and
       ``completed_at`` are API bookkeeping values (D-4 exempt list), not evidence
       timestamps, so the analysis clock is allowed for them and only for them.
* A13/A16 belong to the P1/P2 blocks that carry ``write_blocked`` and ``path_hint``. Those
  blocks pass through this layer untouched and are validated by
  :mod:`app.contract.assumptions`, which this module never re-invents.

Truthfulness invariants the API relies on:

* a stage that produced no engine output is never marked ``ok``;
* ``synthetic_preview`` may only be set by a stage whose status is ``mock``, so placeholder
  data can never be mistaken for engine output;
* every ``mock`` stage carries at least one warning, and every ``failed`` stage carries a
  :class:`StageFailure`. There is no silent failure path.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Protocol

from app.contract.assumptions import (
    DATA_ORIGINS,
    ORIGIN_AI_ASSISTED,
    ORIGIN_COMPUTED,
    ORIGIN_OBSERVED,
    ORIGIN_UNAVAILABLE,
    AssumptionViolation,
    validate_confidence,
    validate_engine_info,
)

# ---------------------------------------------------------------------------------
# Pipeline stages. Two engines exist in this system, so two stages exist.
# ---------------------------------------------------------------------------------
STAGE_RECOVERY = "recovery"
STAGE_INTELLIGENCE = "intelligence"
STAGE_NAMES: tuple[str, ...] = (STAGE_RECOVERY, STAGE_INTELLIGENCE)

#: Origins re-exported from the M0 contract so P3 code never spells them by hand.
ORIGINS: tuple[str, ...] = DATA_ORIGINS
ORIGIN_OBSERVED_VALUE = ORIGIN_OBSERVED
ORIGIN_COMPUTED_VALUE = ORIGIN_COMPUTED
ORIGIN_AI_ASSISTED_VALUE = ORIGIN_AI_ASSISTED
ORIGIN_UNAVAILABLE_VALUE = ORIGIN_UNAVAILABLE


def utc_now() -> datetime:
    """The analysis clock, used only for the D-4 exempt bookkeeping fields."""
    return datetime.now(timezone.utc)


class StageStatus(str, Enum):
    """Outcome of one pipeline stage. ``ok`` means real engine output exists."""

    OK = "ok"
    MOCK = "mock"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"
    SKIPPED = "skipped"


class SessionStatus(str, Enum):
    """Session lifecycle. A session is never reported as ``complete`` with a gap."""

    SUBMITTED = "submitted"
    PROCESSING = "processing"
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


# ---------------------------------------------------------------------------------
# Failure and warning codes. They are P3-owned vocabulary: no M0 value is reused for a
# meaning it does not have, and no new engine semantics are implied by them.
# ---------------------------------------------------------------------------------
FAILURE_CODE_ENGINE_UNAVAILABLE = "engine_unavailable"
FAILURE_CODE_ENGINE_FAILED = "engine_failed"
FAILURE_CODE_ENGINE_DECLARATION_INVALID = "engine_declaration_invalid"
FAILURE_CODE_ENGINE_CONTRACT_VIOLATION = "engine_contract_violation"
FAILURE_CODE_ENGINE_MOCK = "engine_mock"
FAILURE_CODE_STAGE_SKIPPED = "stage_skipped"

WARNING_ENGINE_MOCK_IN_USE = "engine_mock_in_use"
WARNING_SYNTHETIC_DATA_PRESENT = "synthetic_data_present"
WARNING_ENGINE_UNAVAILABLE = "engine_unavailable"
WARNING_ENGINE_FAILED = "engine_failed"
WARNING_STAGE_SKIPPED = "stage_skipped"
WARNING_PARTIAL_RESULT = "partial_result"
WARNING_REPORT_ID_UNAVAILABLE = "report_id_unavailable"
WARNING_OUTPUTS_HASH_UNAVAILABLE = "outputs_hash_unavailable"
WARNING_EVIDENCE_NOT_PERSISTED = "evidence_not_persisted"
WARNING_SESSION_PERSISTENCE_FAILED = "session_persistence_failed"
WARNING_CONFIG_INVALID = "config_value_invalid_ignored"
#: The supplied bundle carries fragment records that share a fragment_id, so references to
#: those ids cannot satisfy the frozen exactly-one-record grounding rule.
WARNING_DUPLICATE_FRAGMENT_IDS = "duplicate_fragment_ids"


@dataclass(frozen=True)
class EngineDeclaration:
    """A10: what a connected engine must declare about itself."""

    name: str
    version: str
    run_id: str

    def __post_init__(self) -> None:
        try:
            validate_engine_info(name=self.name, version=self.version, run_id=self.run_id)
        except AssumptionViolation as exc:  # A10
            raise AssumptionViolation("engine declaration rejected: %s" % exc) from exc

    def as_mapping(self) -> dict[str, str]:
        return {"name": self.name, "version": self.version, "run_id": self.run_id}


@dataclass(frozen=True)
class StageWarning:
    """A non-fatal problem raised while a stage ran. ``stage`` is set by the pipeline."""

    code: str
    message: str
    detail: str | None = None
    stage: str | None = None

    def __post_init__(self) -> None:
        for label, value in (("code", self.code), ("message", self.message)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("a StageWarning requires a non-empty %s" % label)


@dataclass(frozen=True)
class StageFailure:
    """A stage that did not produce the value it was supposed to produce.

    Every non-``ok``, non-``mock`` stage outcome carries one of these, so a missing value
    can never arrive at a client without an explanation.
    """

    code: str
    message: str
    detail: str | None = None
    stage: str | None = None

    def __post_init__(self) -> None:
        for label, value in (("code", self.code), ("message", self.message)):
            if not isinstance(value, str) or not value.strip():
                raise ValueError("a StageFailure requires a non-empty %s" % label)


@dataclass(frozen=True)
class ProvenanceDeclaration:
    """One A4 provenance record. A4 is enforced here, not merely documented."""

    subject: str
    origin: str
    produced_at: datetime
    confidence: float | None = None
    confidence_basis: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.subject, str) or not self.subject.strip():
            raise ValueError("a provenance record requires a non-empty subject")
        if self.origin not in ORIGINS:
            raise ValueError(
                "unknown provenance origin %r; expected one of %s" % (self.origin, ORIGINS)
            )
        if not isinstance(self.produced_at, datetime) or self.produced_at.utcoffset() is None:
            raise ValueError(
                "produced_at is API bookkeeping (D-4) and must still be timezone-aware"
            )
        validate_confidence(
            origin=self.origin,
            confidence=self.confidence,
            confidence_basis=self.confidence_basis,
        )


@dataclass(frozen=True)
class StageRequest:
    """What a stage is given. ``options`` is opaque and never interpreted by P3."""

    session_id: str
    case_id: str | None = None
    module_version: str = ""
    evidence: Mapping[str, Any] | None = None
    evidence_sha256: str | None = None
    bundle_sha256: str | None = None
    options: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.session_id, str) or not self.session_id:
            raise ValueError("a StageRequest requires a session_id")
        if self.evidence is not None and not isinstance(self.evidence, Mapping):
            raise ValueError("evidence must be a mapping or None")


@dataclass(frozen=True)
class StageResult:
    """What a stage hands back. The invariants here are what keep the API truthful.

    * ``status=ok`` requires a declared engine and real ``data``.
    * ``status=mock`` requires a ``synthetic_preview``, at least one warning and a stated
      failure, and may never carry ``data``: placeholder values never occupy a real field.
    * ``status=failed``, ``unavailable`` and ``skipped`` each require a
      :class:`StageFailure`, so no missing value arrives without an explanation.
    * ``synthetic_preview`` is only legal for a mock stage.
    """

    stage: str
    status: StageStatus
    data: Mapping[str, Any] | None = None
    synthetic_preview: Mapping[str, Any] | None = None
    engine: EngineDeclaration | None = None
    warnings: tuple[StageWarning, ...] = ()
    failure: StageFailure | None = None
    provenance: tuple[ProvenanceDeclaration, ...] = ()
    note: str | None = None
    #: Bookkeeping timestamps (A7/D-4 exempt). The pipeline fills them in; a service may
    #: leave them empty and nothing is invented on its behalf.
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.stage not in STAGE_NAMES:
            raise ValueError("unknown stage %r; expected one of %s" % (self.stage, STAGE_NAMES))
        if not isinstance(self.status, StageStatus):
            raise ValueError("status must be a StageStatus")
        if self.data is not None and not isinstance(self.data, Mapping):
            raise ValueError("stage data must be a mapping or None")
        if self.synthetic_preview is not None and not isinstance(
            self.synthetic_preview, Mapping
        ):
            raise ValueError("synthetic_preview must be a mapping or None")

        if self.status is StageStatus.OK:
            if self.engine is None:
                raise ValueError("A10: status=ok requires a declared engine")
            if self.data is None:
                raise ValueError("status=ok requires real engine data")
            if self.failure is not None:
                raise ValueError("status=ok must not carry a failure")
        elif self.status is StageStatus.MOCK:
            if self.data is not None:
                raise ValueError("a mock stage must not occupy the real data field")
            if self.synthetic_preview is None:
                raise ValueError("a mock stage must supply a synthetic_preview")
            if not self.warnings:
                raise ValueError("a mock stage must warn that its data is synthetic")
            if self.failure is None:
                raise ValueError("a mock stage must state that no real engine ran")
        else:
            if self.failure is None:
                raise ValueError(
                    "status=%s must explain itself with a StageFailure" % self.status.value
                )
            if self.synthetic_preview is not None:
                raise ValueError("only a mock stage may carry a synthetic_preview")

        # The pipeline owns the stage label, so warnings and failures must agree with it.
        object.__setattr__(
            self,
            "warnings",
            tuple(
                replace(warning, stage=warning.stage or self.stage) for warning in self.warnings
            ),
        )
        if self.failure is not None and not self.failure.stage:
            object.__setattr__(self, "failure", replace(self.failure, stage=self.stage))


@dataclass(frozen=True)
class SessionRecord:
    """One investigator session: lifecycle state, stage outcomes and the report body."""

    session_id: str
    status: SessionStatus
    submitted_at: datetime
    completed_at: datetime | None = None
    case_id: str | None = None
    evidence_bytes: int = 0
    evidence_sha256: str | None = None
    evidence_persisted: bool = False
    bundle_sha256: str | None = None
    mock_data: bool = False
    stages: tuple[StageResult, ...] = ()
    report: Mapping[str, Any] | None = None
    report_id: str | None = None
    generated_utc: datetime | None = None
    audit: Mapping[str, Any] | None = None
    reproducibility: Mapping[str, Any] | None = None
    #: P3's own provenance rows (the submission and P3's derivations from it).
    records: tuple[ProvenanceDeclaration, ...] = ()
    #: Session-level warnings that belong to no single stage (report id, persistence, ...).
    notices: tuple[StageWarning, ...] = ()
    options: Mapping[str, Any] = field(default_factory=dict)
    #: The submitted Evidence Bundle as parsed, held in memory for this process only. It is
    #: deliberately never serialized (the submitted evidence is never written to disk), so a
    #: session reloaded from storage serves its evidence endpoints as explicitly unavailable
    #: with a stated reason instead of as an empty success.
    evidence_bundle: Mapping[str, Any] | None = None

    @property
    def warnings(self) -> tuple[StageWarning, ...]:
        """Session notices first, then every stage warning, in stage order."""
        return self.notices + tuple(
            warning for stage in self.stages for warning in stage.warnings
        )

    @property
    def failures(self) -> tuple[StageFailure, ...]:
        """Every stage failure. A session with failures is never reported as complete."""
        return tuple(stage.failure for stage in self.stages if stage.failure is not None)

    @property
    def provenance(self) -> tuple[ProvenanceDeclaration, ...]:
        """P3's own rows first, then each stage's rows, in stage order."""
        return self.records + tuple(
            row for stage in self.stages for row in stage.provenance
        )

    @property
    def report_available(self) -> bool:
        return self.report is not None

    def stage(self, name: str) -> StageResult | None:
        for result in self.stages:
            if result.stage == name:
                return result
        return None


class RecoveryService(Protocol):
    """P1 integration. ``analyse`` must return a :class:`StageResult` for stage recovery."""

    @property
    def declaration(self) -> EngineDeclaration | None: ...

    def analyse(self, request: StageRequest) -> StageResult: ...


class IntelligenceService(Protocol):
    """P2 integration. ``analyse`` returns a :class:`StageResult` for stage intelligence."""

    @property
    def declaration(self) -> EngineDeclaration | None: ...

    def analyse(self, request: StageRequest) -> StageResult: ...


class SessionStore(Protocol):
    """Session/report storage. A stored session must never be lost or half-written."""

    def save(self, record: SessionRecord) -> None: ...

    def get(self, session_id: str) -> SessionRecord | None: ...

    def list(self, *, limit: int, offset: int) -> tuple[tuple[SessionRecord, ...], int]: ...

    def delete(self, session_id: str) -> bool: ...

    def close(self) -> None: ...



