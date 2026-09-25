"""Deterministic development doubles for the P1/P2 slots.

A mock never pretends to be an engine. It returns ``status=mock`` with ``data=None`` and a
``synthetic_preview`` that holds only metadata P3 already knows, so:

* the real data field stays empty and cannot be mistaken for engine output;
* no fragment, artifact, claim or finding is fabricated, because inventing those would
  invent P1/P2 structure that has not been frozen;
* the preview is fully deterministic from ``TRACE_MOCK_SEED``, so UI work is repeatable;
* every mock stage warns and states a failure, and every row it produces carries the
  ``unavailable`` origin, so no consumer can read it as observed or computed.
"""
from __future__ import annotations

from app.services.interfaces import (
    FAILURE_CODE_ENGINE_MOCK,
    ORIGIN_UNAVAILABLE_VALUE,
    STAGE_INTELLIGENCE,
    STAGE_RECOVERY,
    EngineDeclaration,
    ProvenanceDeclaration,
    StageFailure,
    StageRequest,
    StageResult,
    StageStatus,
    StageWarning,
    WARNING_ENGINE_MOCK_IN_USE,
    WARNING_SYNTHETIC_DATA_PRESENT,
    utc_now,
)
from app.services.unavailable import SUBJECT_INTELLIGENCE, SUBJECT_RECOVERY

MOCK_ENGINE_NAME_RECOVERY = "trace-mock-recovery"
MOCK_ENGINE_NAME_INTELLIGENCE = "trace-mock-intelligence"
MOCK_ENGINE_VERSION = "0.0.0"
MOCK_NOTE = (
    "synthetic placeholder for UI development; no engine processed any evidence"
)


class _MockService:
    """Shared behaviour: a deterministic placeholder, clearly marked as placeholder."""

    stage: str = ""
    subject: str = ""
    engine_name: str = ""

    def __init__(self, *, seed: int) -> None:
        if isinstance(seed, bool) or not isinstance(seed, int):
            raise ValueError("the mock seed must be an integer")
        self.seed = seed
        self.declaration = EngineDeclaration(
            name=self.engine_name,
            version=MOCK_ENGINE_VERSION,
            run_id="mock-%d" % seed,
        )

    def preview(self, request: StageRequest) -> dict[str, object]:
        """Only values P3 already holds. No evidence structure is fabricated."""
        return {
            "synthetic": True,
            "stage": self.stage,
            "engine": self.declaration.name,
            "seed": self.seed,
            "note": MOCK_NOTE,
            "session_id": request.session_id,
            "case_id": request.case_id,
            "evidence_sha256": request.evidence_sha256,
            "bundle_sha256": request.bundle_sha256,
            "options": dict(request.options),
            "placeholder": "no engine output exists while a mock is wired in",
        }

    def analyse(self, request: StageRequest) -> StageResult:
        return StageResult(
            stage=self.stage,
            status=StageStatus.MOCK,
            data=None,
            synthetic_preview=self.preview(request),
            engine=self.declaration,
            warnings=(
                StageWarning(
                    WARNING_ENGINE_MOCK_IN_USE,
                    "engine %r is a mock and processed no evidence" % self.declaration.name,
                ),
                StageWarning(
                    WARNING_SYNTHETIC_DATA_PRESENT,
                    "synthetic_preview holds placeholder values, not engine output",
                ),
            ),
            failure=StageFailure(
                FAILURE_CODE_ENGINE_MOCK,
                "no real %s engine processed this session" % self.stage,
                detail=MOCK_NOTE,
            ),
            provenance=(
                ProvenanceDeclaration(
                    subject=self.subject,
                    origin=ORIGIN_UNAVAILABLE_VALUE,
                    produced_at=utc_now(),
                ),
            ),
            note=MOCK_NOTE,
        )


class MockRecoveryService(_MockService):
    """Stand-in for the P1 slot."""

    stage = STAGE_RECOVERY
    subject = SUBJECT_RECOVERY
    engine_name = MOCK_ENGINE_NAME_RECOVERY


class MockIntelligenceService(_MockService):
    """Stand-in for the P2 slot."""

    stage = STAGE_INTELLIGENCE
    subject = SUBJECT_INTELLIGENCE
    engine_name = MOCK_ENGINE_NAME_INTELLIGENCE
