"""Evidence endpoints: the held bundle root, its fragments and artifacts, and grounding.

The bundle is held in memory for the process that accepted it and is never written to
disk, so a session reloaded from storage serves these endpoints with an explicit
``evidence_unavailable`` (409) that states the reason instead of an empty success. Every
response reports frozen facts only: root contract fields, array counts, fragment ids and
tri-state grounding results. Bundle interiors travel opaquely and are never modelled.
"""
from __future__ import annotations

from collections.abc import Mapping

from fastapi import APIRouter, Path

from app.dependencies import PipelineDep
from app.errors import (
    ArtifactNotFoundError,
    EvidenceUnavailableError,
    FragmentAmbiguousError,
    FragmentNotFoundError,
    SessionNotFoundError,
    SessionStorageError,
)
from app.schemas.common import project_warnings
from app.schemas.evidence import (
    ArtifactListResponse,
    ArtifactView,
    EvidenceBundleRoot,
    FragmentListResponse,
    FragmentView,
    GroundRequest,
    GroundResponse,
    project_bundle_root,
    project_fragment,
    project_grounding,
)
from app.services.evidence import (
    BundleEvidenceResolver,
    bundle_array,
    fragment_records,
)
from app.services.interfaces import SessionRecord
from app.services.session_store import SessionPersistenceError

router = APIRouter(tags=["evidence"])


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


def _bundle(record: SessionRecord) -> Mapping[str, object]:
    """The held bundle, or an explicit 409 when this process does not have it."""
    bundle = record.evidence_bundle
    if bundle is None:
        raise EvidenceUnavailableError(
            "the submitted evidence for this session is not available in this process",
            detail=(
                "the bundle is held in memory only and is never written to disk; a session "
                "reloaded from storage cannot serve its evidence"
            ),
            warnings=record.warnings,
        )
    return bundle


@router.get(
    "/sessions/{session_id}/evidence",
    response_model=EvidenceBundleRoot,
    summary="The frozen root of this session's held Evidence Bundle",
)
def get_bundle_root(session_id: str, pipeline: PipelineDep) -> EvidenceBundleRoot:
    record = _require(pipeline, session_id)
    return project_bundle_root(record, _bundle(record))


@router.get(
    "/sessions/{session_id}/evidence/fragments",
    response_model=FragmentListResponse,
    summary="Every fragment record of the held bundle, with its frozen fragment_id",
)
def list_fragments(session_id: str, pipeline: PipelineDep) -> FragmentListResponse:
    record = _require(pipeline, session_id)
    bundle = _bundle(record)
    fragments = bundle_array(bundle, "fragments") or []
    return FragmentListResponse(
        session_id=session_id,
        fragments=tuple(
            project_fragment(record, bundle, index) for index in range(len(fragments))
        ),
        total=len(fragments),
        warnings=project_warnings(record.warnings),
    )


@router.get(
    "/sessions/{session_id}/evidence/fragments/{fragment_id}",
    response_model=FragmentView,
    summary="One fragment record under the frozen exactly-one-record rule",
)
def get_fragment(
    session_id: str,
    fragment_id: str,
    pipeline: PipelineDep,
) -> FragmentView:
    record = _require(pipeline, session_id)
    bundle = _bundle(record)
    matches = fragment_records(bundle, fragment_id)
    if not matches:
        raise FragmentNotFoundError(
            "no fragment record carries fragment_id %r" % fragment_id,
            warnings=record.warnings,
        )
    if len(matches) > 1:
        raise FragmentAmbiguousError(
            "%d fragment records carry fragment_id %r" % (len(matches), fragment_id),
            detail=(
                "the frozen rule requires exactly one record; "
                "preference and order never decide"
            ),
            warnings=record.warnings,
        )
    fragments = bundle_array(bundle, "fragments") or []
    index = next(
        position
        for position, fragment in enumerate(fragments)
        if fragment is matches[0]
    )
    return project_fragment(record, bundle, index)


@router.get(
    "/sessions/{session_id}/evidence/artifacts",
    response_model=ArtifactListResponse,
    summary="Every artifact record of the held bundle, opaque as submitted",
)
def list_artifacts(session_id: str, pipeline: PipelineDep) -> ArtifactListResponse:
    record = _require(pipeline, session_id)
    bundle = _bundle(record)
    artifacts = bundle_array(bundle, "artifacts") or []
    return ArtifactListResponse(
        session_id=session_id,
        artifacts=tuple(
            ArtifactView(index=index, record=artifacts[index])
            for index in range(len(artifacts))
        ),
        total=len(artifacts),
        warnings=project_warnings(record.warnings),
    )


@router.get(
    "/sessions/{session_id}/evidence/artifacts/{index}",
    response_model=ArtifactView,
    summary="One artifact record by its array position",
)
def get_artifact(
    session_id: str,
    pipeline: PipelineDep,
    index: int = Path(..., ge=0, description="Zero-based position in the artifacts array"),
) -> ArtifactView:
    record = _require(pipeline, session_id)
    bundle = _bundle(record)
    artifacts = bundle_array(bundle, "artifacts") or []
    if index >= len(artifacts):
        raise ArtifactNotFoundError(
            "artifact index %d is outside the %d artifact record(s) of this bundle"
            % (index, len(artifacts)),
            warnings=record.warnings,
        )
    return ArtifactView(index=index, record=artifacts[index])


@router.post(
    "/sessions/{session_id}/refs/ground",
    response_model=GroundResponse,
    summary="Ground EvidenceRefs against this session's held bundle",
)
def ground_refs(
    session_id: str,
    payload: GroundRequest,
    pipeline: PipelineDep,
) -> GroundResponse:
    record = _require(pipeline, session_id)
    bundle = _bundle(record)
    results = BundleEvidenceResolver(bundle).resolve_all(payload.refs)
    return GroundResponse(
        session_id=session_id,
        results=tuple(project_grounding(result) for result in results),
        grounded_count=sum(1 for result in results if result.is_grounded),
        all_grounded=all(result.is_grounded for result in results),
        warnings=project_warnings(record.warnings),
    )


