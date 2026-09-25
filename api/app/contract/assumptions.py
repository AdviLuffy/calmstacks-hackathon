"""Executable enforcement of the frozen M0 assumptions.

A4  Confidence is ordinal reliability of the derivation, NOT the probability that a
    finding is true. D-3 (authorized) treats ``ai_assisted`` output as INFERRED, so AI
    output carries a hard ceiling of 0.70 while OBSERVED and COMPUTED carry 1.0.
    ``confidence_basis`` is mandatory and must be at least 8 characters. Confidence is
    never synthesised and never inflated.
A5  ``byte_contiguity`` is the sole basis for a definitive join. If it is uncertain it
    must be false, and a join may only be marked definitive when it is true.
A6  Evidence timestamps are UTC with Z. Local offsets are not permitted. Timestamp
    source and precision are mandatory.
A7  Scoped by D-4: all *evidence-derived* times originate from the media/evidence and
    never from the analysis machine clock. API bookkeeping timestamps are explicitly
    exempt; see ``A7_ANALYSIS_CLOCK_EXEMPT_FIELDS``.
A10 A connected engine must declare engine.name, engine.version and engine.run_id.
A13 ``write_blocked`` must be stated truthfully, including when it is false.
A16 ``path_hint`` may be null and must never be fabricated.

This module deliberately depends on nothing from the API schema layer, so it can be
reused by P1 and P2 without importing FastAPI or Pydantic.
"""
from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Any, Final

# ---------------------------------------------------------------------------------
# Provenance origins (identical to the API schema vocabulary).
# ---------------------------------------------------------------------------------
ORIGIN_OBSERVED: Final[str] = "observed"
ORIGIN_COMPUTED: Final[str] = "computed"
ORIGIN_AI_ASSISTED: Final[str] = "ai_assisted"
ORIGIN_UNAVAILABLE: Final[str] = "unavailable"
DATA_ORIGINS: Final[tuple[str, ...]] = (
    ORIGIN_OBSERVED,
    ORIGIN_COMPUTED,
    ORIGIN_AI_ASSISTED,
    ORIGIN_UNAVAILABLE,
)

# ---------------------------------------------------------------------------------
# A4 / D-3 confidence rules.
# ---------------------------------------------------------------------------------
INFERRED_CONFIDENCE_MAX: Final[float] = 0.70
OBSERVED_CONFIDENCE_MAX: Final[float] = 1.0
COMPUTED_CONFIDENCE_MAX: Final[float] = 1.0
CONFIDENCE_BASIS_MIN_LENGTH: Final[int] = 8

#: D-3: AI output is INFERRED output for the M0 confidence rules.
AI_ASSISTED_IS_INFERRED: Final[bool] = True

#: A4/D-3 ceilings per origin. ``None`` means no confidence is permitted at all.
CONFIDENCE_CEILINGS: Final[dict[str, float | None]] = {
    ORIGIN_OBSERVED: OBSERVED_CONFIDENCE_MAX,
    ORIGIN_COMPUTED: COMPUTED_CONFIDENCE_MAX,
    ORIGIN_AI_ASSISTED: INFERRED_CONFIDENCE_MAX,
    ORIGIN_UNAVAILABLE: None,
}

# ---------------------------------------------------------------------------------
# A7 / D-4 timestamp scope.
# ---------------------------------------------------------------------------------
#: Timestamp fields that ARE governed by A7: they must originate from the evidence.
A7_EVIDENCE_TIMESTAMP_PATHS: Final[tuple[str, ...]] = (
    "evidence.timestamps[].value_utc",
    "fragment.timestamps[].value_utc",
    "artifact.timestamps[].value_utc",
    "timeline_events[].ts_utc",
)

#: Timestamp fields that are NOT governed by A7 (D-4): they are API bookkeeping values.
#: They may use the analysis system clock because the API contract requires them.
A7_ANALYSIS_CLOCK_EXEMPT_FIELDS: Final[tuple[str, ...]] = (
    "session.submitted_at",
    "session.completed_at",
    "provenance.produced_at",
    "pipeline_stage.started_at",
    "pipeline_stage.finished_at",
)

#: A6 requires these on every evidence-derived timestamp. Their value vocabularies are
#: not frozen by the M0 material, so only presence and non-emptiness are enforced.
TIMESTAMP_SOURCE_IS_MANDATORY: Final[bool] = True
TIMESTAMP_PRECISION_IS_MANDATORY: Final[bool] = True


class AssumptionViolation(ValueError):
    """A value violates a frozen M0 assumption."""


def confidence_max_for_origin(origin: str) -> float | None:
    """Return the A4/D-3 ceiling for a provenance origin.

    Raises ``AssumptionViolation`` for an unknown origin so an unrecognised value can
    never slip through unchecked.
    """
    if origin not in CONFIDENCE_CEILINGS:
        raise AssumptionViolation(
            "unknown provenance origin %r; expected one of %s" % (origin, DATA_ORIGINS)
        )
    return CONFIDENCE_CEILINGS[origin]


def validate_confidence(
    *, origin: str, confidence: float | None, confidence_basis: str | None
) -> None:
    """Enforce A4 and D-3 for one provenance record.

    A missing confidence is always allowed: it means the producer did not report one and
    the API refuses to synthesise it. A confidence that IS present must satisfy the
    ceiling for its origin and must carry a substantial confidence_basis.
    """
    ceiling = confidence_max_for_origin(origin)

    if origin == ORIGIN_UNAVAILABLE:
        if confidence is not None:
            raise AssumptionViolation(
                "A4/step6: an unavailable value must not carry a confidence"
            )
        if confidence_basis is not None:
            raise AssumptionViolation(
                "A4/step6: an unavailable value must not carry a confidence_basis"
            )
        return

    if confidence is None:
        if confidence_basis is not None:
            raise AssumptionViolation(
                "A4: confidence_basis was supplied without a confidence"
            )
        return

    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise AssumptionViolation("A4: confidence must be a number within [0, 1]")

    numeric = float(confidence)
    if numeric != numeric:
        raise AssumptionViolation("A4: confidence must not be NaN")
    if not 0.0 <= numeric <= 1.0:
        raise AssumptionViolation("A4: confidence must be within [0, 1]")
    if ceiling is not None and numeric > ceiling:
        raise AssumptionViolation(
            "A4/D-3: %s confidence must not exceed %.2f (got %r)" % (origin, ceiling, confidence)
        )
    if confidence_basis is None:
        raise AssumptionViolation(
            "A4: confidence_basis is mandatory when a confidence is present"
        )
    if not isinstance(confidence_basis, str):
        raise AssumptionViolation("A4: confidence_basis must be a string")
    if len(confidence_basis.strip()) < CONFIDENCE_BASIS_MIN_LENGTH:
        raise AssumptionViolation(
            "A4: confidence_basis must contain at least %d characters"
            % CONFIDENCE_BASIS_MIN_LENGTH
        )


def combine_confidence(values: Iterable[float | None]) -> float | None:
    """Reduce several confidences without ever inflating one (A4).

    Uses the minimum, so aggregation can only reduce confidence. Returns None when no
    input reported a confidence, which is how the API represents "not reported".
    """
    reported = [float(value) for value in values if value is not None]
    return min(reported) if reported else None


# ---------------------------------------------------------------------------------
# A5 join basis.
# ---------------------------------------------------------------------------------
def validate_join_basis(*, byte_contiguity: Any, definitive: Any) -> None:
    """Enforce A5: byte contiguity is the sole basis for a definitive join."""
    if not isinstance(byte_contiguity, bool):
        raise AssumptionViolation(
            "A5: byte_contiguity must be true or false; if it is uncertain it must be false"
        )
    if not isinstance(definitive, bool):
        raise AssumptionViolation("A5: definitive must be true or false")
    if definitive and not byte_contiguity:
        raise AssumptionViolation(
            "A5: byte_contiguity is the sole basis for a definitive join"
        )


# ---------------------------------------------------------------------------------
# A6 evidence timestamps.
# ---------------------------------------------------------------------------------
def validate_evidence_timestamp(*, value_utc: Any, source: Any, precision: Any) -> None:
    """Enforce A6 for one evidence-derived timestamp."""
    if not isinstance(value_utc, datetime):
        raise AssumptionViolation("A6: an evidence timestamp requires a value_utc datetime")
    if value_utc.tzinfo is None or value_utc.utcoffset() is None:
        raise AssumptionViolation(
            "A6: evidence timestamps must be timezone-aware UTC; a naive timestamp has no "
            "defined offset"
        )
    if value_utc.utcoffset().total_seconds() != 0:
        raise AssumptionViolation(
            "A6: local offsets are not permitted; evidence timestamps must be UTC"
        )
    if not isinstance(source, str) or not source.strip():
        raise AssumptionViolation("A6: timestamp source is mandatory")
    if not isinstance(precision, str) or not precision.strip():
        raise AssumptionViolation("A6: timestamp precision is mandatory")


# ---------------------------------------------------------------------------------
# A10 connected engines.
# ---------------------------------------------------------------------------------
def validate_engine_info(*, name: Any, version: Any, run_id: Any) -> None:
    """Enforce A10 for a connected engine."""
    for label, value in (
        ("engine.name", name),
        ("engine.version", version),
        ("engine.run_id", run_id),
    ):
        if not isinstance(value, str) or not value.strip():
            raise AssumptionViolation(
                "A10: %s must be present and non-empty for a connected engine" % label
            )


# ---------------------------------------------------------------------------------
# A13 and A16 truthfulness.
# ---------------------------------------------------------------------------------
def validate_write_blocked(write_blocked: Any) -> None:
    """Enforce A13: write_blocked must be stated truthfully, including when false."""
    if not isinstance(write_blocked, bool):
        raise AssumptionViolation("A13: write_blocked must be stated as true or false")


def validate_path_hint(path_hint: Any) -> None:
    """Enforce A16: path_hint may be null and must never be fabricated."""
    if path_hint is None:
        return
    if not isinstance(path_hint, str) or not path_hint.strip():
        raise AssumptionViolation(
            "A16: path_hint must be null or a non-empty string; it must never be fabricated"
        )