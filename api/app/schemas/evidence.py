"""HTTP projections for serving the held Evidence Bundle and grounding EvidenceRefs.

Only frozen facts are modelled: the root fields of ``trace.evidence_bundle/1.0``, the
arrays the freeze names, the ``fragment_id`` field the fragment amendment freezes, and the
tri-state grounding vocabulary from :mod:`app.contract.evidence_ref`. Bundle INTERIORS
travel as opaque mappings: no P1 or P2 field is named, typed, renamed or dropped here.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

from app.contract.evidence_bundle import array_field_counts, root_field_names
from app.contract.evidence_ref import GroundingResult, GroundingStatus
from app.schemas.common import APIWarning, project_warnings
from app.services.evidence import bundle_array
from app.services.interfaces import SessionRecord


class EvidenceBundleRoot(BaseModel):
    """The frozen root of the held bundle, reported as facts rather than modelled deeply."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str
    bundle_sha256: str
    schema_version: str
    bundle_id: str
    generated_utc: str
    root_fields: tuple[str, ...]
    array_counts: dict[str, int | None]
    warnings: tuple[APIWarning, ...] = ()


class FragmentView(BaseModel):
    """One fragment record: its frozen ``fragment_id`` plus the opaque record itself."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    index: int
    fragment_id: str | None
    record: Any


class FragmentListResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str
    fragments: tuple[FragmentView, ...]
    total: int
    warnings: tuple[APIWarning, ...] = ()


class ArtifactView(BaseModel):
    """One artifact array element, opaque exactly as submitted."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    index: int
    record: Any


class ArtifactListResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str
    artifacts: tuple[ArtifactView, ...]
    total: int
    warnings: tuple[APIWarning, ...] = ()


class GroundRequest(BaseModel):
    """References to ground against the session's held bundle."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    refs: tuple[str, ...]

    @field_validator("refs")
    @classmethod
    def _at_least_one(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("at least one EvidenceRef is required")
        return value


class GroundingView(BaseModel):
    """One grounding outcome: status, reason and decomposition, never a verdict upgrade."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ref: str
    status: GroundingStatus
    reason: str | None = None
    detail: str | None = None
    root: str | None = None
    collection: str | None = None
    instance_id: str | None = None
    segments: tuple[str, ...] = ()


class GroundResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    session_id: str
    results: tuple[GroundingView, ...]
    grounded_count: int
    all_grounded: bool
    warnings: tuple[APIWarning, ...] = ()


def project_bundle_root(record: SessionRecord, bundle: Any) -> EvidenceBundleRoot:
    def _string(name: str) -> str:
        value = bundle.get(name)
        return value if isinstance(value, str) else ""

    return EvidenceBundleRoot(
        session_id=record.session_id,
        bundle_sha256=record.bundle_sha256,
        schema_version=_string("schema_version"),
        bundle_id=_string("bundle_id"),
        generated_utc=_string("generated_utc"),
        root_fields=root_field_names(bundle),
        array_counts=array_field_counts(bundle),
        warnings=project_warnings(record.warnings),
    )


def project_fragment(record: SessionRecord, bundle: Any, index: int) -> FragmentView:
    fragments = bundle_array(bundle, "fragments") or []
    fragment = fragments[index]
    fragment_id = fragment.get("fragment_id") if isinstance(fragment, dict) else None
    return FragmentView(
        index=index,
        fragment_id=fragment_id if isinstance(fragment_id, str) else None,
        record=fragment,
    )


def project_grounding(result: GroundingResult) -> GroundingView:
    return GroundingView(
        ref=result.ref,
        status=result.status,
        reason=result.reason,
        detail=result.detail,
        root=result.root,
        collection=result.collection,
        instance_id=result.instance_id,
        segments=result.segments,
    )


__all__ = [
    "ArtifactListResponse",
    "ArtifactView",
    "EvidenceBundleRoot",
    "FragmentListResponse",
    "FragmentView",
    "GroundRequest",
    "GroundResponse",
    "GroundingView",
    "project_bundle_root",
    "project_fragment",
    "project_grounding",
]
