"""Services that declare an absence instead of inventing a result.

Used when an engine is not configured, not importable, or explicitly disabled. The stage
reports ``unavailable``: no data is produced, no confidence is invented (A4 forbids a
confidence on an unavailable value), and a warning plus a failure record the reason. The
pipeline therefore cannot treat a missing engine as a success.
"""
from __future__ import annotations

from app.services.interfaces import (
    FAILURE_CODE_ENGINE_UNAVAILABLE,
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
    WARNING_ENGINE_UNAVAILABLE,
    utc_now,
)

#: Provenance subjects used by the pipeline. P3-owned labels, not evidence field names.
SUBJECT_RECOVERY = "recovery.bundle"
SUBJECT_INTELLIGENCE = "intelligence.report"


class _UnavailableService:
    """Shared behaviour: report the absence, with its reason, and nothing else."""

    stage: str = ""
    subject: str = ""
    #: A10: nothing is connected, so nothing may declare itself as an engine.
    declaration: EngineDeclaration | None = None

    def __init__(self, reason: str) -> None:
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError("an unavailable service requires a stated reason")
        self.reason = reason

    @property
    def message(self) -> str:
        return "no %s engine is connected: %s" % (self.stage, self.reason)

    def analyse(self, request: StageRequest) -> StageResult:
        return StageResult(
            stage=self.stage,
            status=StageStatus.UNAVAILABLE,
            engine=None,
            warnings=(StageWarning(WARNING_ENGINE_UNAVAILABLE, self.message),),
            failure=StageFailure(
                FAILURE_CODE_ENGINE_UNAVAILABLE, self.message, detail=self.reason
            ),
            provenance=(
                ProvenanceDeclaration(
                    subject=self.subject,
                    origin=ORIGIN_UNAVAILABLE_VALUE,
                    produced_at=utc_now(),
                ),
            ),
            note=self.reason,
        )


class UnavailableRecoveryService(_UnavailableService):
    """P1 integration slot with nothing behind it."""

    stage = STAGE_RECOVERY
    subject = SUBJECT_RECOVERY


class UnavailableIntelligenceService(_UnavailableService):
    """P2 integration slot with nothing behind it."""

    stage = STAGE_INTELLIGENCE
    subject = SUBJECT_INTELLIGENCE
