"""Session/report lifecycle: the orchestration the API exposes.

Flow::

    submit
      -> validate and parse the submitted bundle (frozen canonicalization rules 5 and 14)
      -> enforce the frozen trace.evidence_bundle/1.0 root contract (M0-DEC-06)
      -> stage ``recovery``    (P1 slot)
      -> stage ``intelligence`` (P2 slot, given the recovered bundle or the submitted one)
      -> report envelope        (the frozen report_id derivation, when a case_id is supplied)
      -> store the session

Rules this pipeline keeps:

* every stage outcome is stored, with its warnings, its failure and its provenance;
* the session status is derived from the stages and never assumed: ``complete`` requires every
  stage to be ``ok``, ``failed`` requires every stage to have failed, anything else is
  ``partial``, and a ``partial``/``failed`` session always explains itself;
* a service that raises is converted into a failed stage with a reason: an engine bug never
  becomes an HTTP 500 and never disappears;
* the evidence bundle and the report body pass through opaquely. P3 models neither, so no P1
  or P2 field is invented, renamed or dropped;
* ``audit.outputs_hash`` is withheld, with a warning, while the P2 report schema is unfrozen:
  the M0 material defines that hash over *the report*, and its body is not yet defined, so any
  hash produced now would not mean what the contract says it means;
* the submitted evidence is never written to disk, and the session says so.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import replace
from typing import Any

from app.config import Settings
from app.contract.assumptions import ORIGIN_COMPUTED, ORIGIN_OBSERVED
from app.contract.canonical import (
    CanonicalizationError,
    DuplicateKeyError,
    bundle_sha256,
    parse_json_strict,
)
from app.contract.canonical import report_id as derive_report_id
from app.contract.evidence_bundle import validate_evidence_bundle_root
from app.errors import (
    BundleContractViolationError,
    BundleNotJSONError,
    EvidenceTooLargeError,
    InvalidInputError,
)
from app.services.interfaces import (
    FAILURE_CODE_ENGINE_CONTRACT_VIOLATION,
    FAILURE_CODE_ENGINE_FAILED,
    ORIGIN_UNAVAILABLE_VALUE,
    STAGE_INTELLIGENCE,
    STAGE_RECOVERY,
    ProvenanceDeclaration,
    SessionRecord,
    SessionStatus,
    SessionStore,
    StageFailure,
    StageRequest,
    StageResult,
    StageStatus,
    StageWarning,
    WARNING_DUPLICATE_FRAGMENT_IDS,
    WARNING_ENGINE_FAILED,
    WARNING_EVIDENCE_NOT_PERSISTED,
    WARNING_OUTPUTS_HASH_UNAVAILABLE,
    WARNING_PARTIAL_RESULT,
    WARNING_REPORT_ID_UNAVAILABLE,
    WARNING_SESSION_PERSISTENCE_FAILED,
    utc_now,
)
from app.services.evidence import duplicate_fragment_ids
from app.services.registry import EngineSlot, EngineWiring
from app.services.session_store import SessionPersistenceError
from app.services.unavailable import SUBJECT_INTELLIGENCE, SUBJECT_RECOVERY

#: Which bundle the P2 stage was given. Recorded on the stage so it is never ambiguous.
ENGINE_BUNDLE_NOTE = "analysed the bundle produced by the P1 recovery engine"
SUBMITTED_BUNDLE_NOTE = "analysed the bundle as submitted, because no P1 engine output exists"

_STAGE_SUBJECTS: Mapping[str, str] = {
    STAGE_RECOVERY: SUBJECT_RECOVERY,
    STAGE_INTELLIGENCE: SUBJECT_INTELLIGENCE,
}


def new_session_id() -> str:
    """A P3 session identifier: random hex, safe as a file name.

    These identifiers are P3's own bookkeeping. They are not part of the M0 identifier
    vocabulary and are never used inside an EvidenceRef.
    """
    return uuid.uuid4().hex


class SessionPipeline:
    """Owns the lifecycle of one settings snapshot: settings, wiring, storage."""

    def __init__(self, *, settings: Settings, wiring: EngineWiring, store: SessionStore) -> None:
        self._settings = settings
        self._wiring = wiring
        self._store = store

    @property
    def settings(self) -> Settings:
        return self._settings

    @property
    def wiring(self) -> EngineWiring:
        return self._wiring

    @property
    def store(self) -> SessionStore:
        return self._store

    def get(self, session_id: str) -> SessionRecord | None:
        return self._store.get(session_id)

    def list(self, *, limit: int, offset: int) -> tuple[tuple[SessionRecord, ...], int]:
        return self._store.list(limit=limit, offset=offset)

    def submit(
        self,
        *,
        evidence: bytes,
        case_id: str | None = None,
        options: Mapping[str, Any] | None = None,
    ) -> SessionRecord:
        """Run one session end to end. Raises ``APIError`` only for request problems."""
        if not isinstance(evidence, bytes):
            raise InvalidInputError("evidence must be submitted as bytes")
        if len(evidence) > self._settings.max_evidence_bytes:
            raise EvidenceTooLargeError(
                "the submitted bundle is %d bytes, above the configured limit of %d bytes"
                % (len(evidence), self._settings.max_evidence_bytes),
                detail="TRACE_MAX_EVIDENCE_BYTES=%d" % self._settings.max_evidence_bytes,
            )
        if case_id is not None and (not isinstance(case_id, str) or not case_id.strip()):
            raise InvalidInputError("case_id must be a non-empty string when it is supplied")
        if options is not None and not isinstance(options, Mapping):
            raise InvalidInputError("options must be a JSON object")
        normalised_case_id = case_id.strip() if isinstance(case_id, str) else None
        options_payload = dict(options) if isinstance(options, Mapping) else {}

        bundle = self._parse_bundle(evidence)
        self._require_root_contract(bundle)
        # Snapshot taken before any engine runs: the session holds exactly what was
        # submitted, and no service can mutate it afterwards.
        held_bundle = deepcopy(bundle)
        canonical_hash = self._canonical_hash(bundle)
        submitted_at = utc_now()
        session_id = new_session_id()
        evidence_sha256 = hashlib.sha256(evidence).hexdigest()

        request = StageRequest(
            session_id=session_id,
            case_id=normalised_case_id,
            module_version=self._settings.module_version,
            evidence=bundle,
            evidence_sha256=evidence_sha256,
            bundle_sha256=canonical_hash,
            options=options_payload,
        )

        recovery = self._run_stage(self._wiring.recovery, request)
        # P2 consumes the Evidence Bundle. If the P1 engine produced one, that bundle is used;
        # otherwise the submitted bundle is, and the stage records which one it analysed.
        if recovery.status is StageStatus.OK:
            intelligence_request = replace(request, evidence=recovery.data)
            intelligence_note = ENGINE_BUNDLE_NOTE
        else:
            intelligence_request = request
            intelligence_note = SUBMITTED_BUNDLE_NOTE
        intelligence = self._run_stage(self._wiring.intelligence, intelligence_request)
        if intelligence.note is None:
            intelligence = replace(intelligence, note=intelligence_note)

        stages = (recovery, intelligence)
        status = self._session_status(stages)
        notices: list[StageWarning] = []
        report_body = intelligence.data if intelligence.status is StageStatus.OK else None

        report_id_value: str | None = None
        generated_utc = None
        audit: dict[str, Any] | None = None
        if report_body is not None:
            generated_utc = utc_now()
            if normalised_case_id:
                report_id_value = derive_report_id(
                    normalised_case_id, canonical_hash, self._settings.module_version
                )
            else:
                notices.append(
                    StageWarning(
                        WARNING_REPORT_ID_UNAVAILABLE,
                        "the frozen report_id derivation requires a case_id, which was not "
                        "supplied, so no report_id was derived",
                        detail=(
                            "report_id = 'RPT-' + sha256('trace.intelligence_report/1.0' | "
                            "case_id | bundle_sha256 | module_version)[:12]"
                        ),
                    )
                )
            notices.append(
                StageWarning(
                    WARNING_OUTPUTS_HASH_UNAVAILABLE,
                    "audit.outputs_hash is withheld while the P2 report schema is unfrozen",
                    detail=(
                        "the M0 material defines outputs_hash over the report itself, and the "
                        "report body is not yet defined, so a hash produced now would not mean "
                        "what the contract says it means"
                    ),
                )
            )
            audit = {
                "runtime_ms": round((generated_utc - submitted_at).total_seconds() * 1000.0, 3),
                "provider_calls": None,
                "outputs_hash": None,
            }

        if status is SessionStatus.PARTIAL:
            notices.append(
                StageWarning(
                    WARNING_PARTIAL_RESULT,
                    "the session is partial: at least one stage produced no engine output",
                    detail=", ".join(
                        "%s=%s" % (stage.stage, stage.status.value) for stage in stages
                    ),
                )
            )
        duplicates = duplicate_fragment_ids(bundle)
        if duplicates:
            notices.append(
                StageWarning(
                    WARNING_DUPLICATE_FRAGMENT_IDS,
                    "the supplied bundle carries fragment records that share a fragment_id; "
                    "references to those ids fail the exactly-one-record grounding rule",
                    detail=", ".join(duplicates[:5])
                    + (
                        ", and %d more" % (len(duplicates) - 5)
                        if len(duplicates) > 5
                        else ""
                    ),
                )
            )
        notices.append(
            StageWarning(
                WARNING_EVIDENCE_NOT_PERSISTED,
                "the submitted evidence is held in memory for this process only and is not "
                "written to disk",
                detail="TRACE_PERSIST_SESSIONS=%s" % self._settings.persist_sessions,
            )
        )

        record = SessionRecord(
            session_id=session_id,
            status=status,
            submitted_at=submitted_at,
            completed_at=utc_now(),
            case_id=normalised_case_id,
            evidence_bytes=len(evidence),
            evidence_sha256=evidence_sha256,
            evidence_persisted=False,
            bundle_sha256=canonical_hash,
            mock_data=self._wiring.mock_data,
            records=(
                ProvenanceDeclaration(
                    subject="session.submitted_evidence",
                    origin=ORIGIN_OBSERVED,
                    produced_at=submitted_at,
                    confidence=1.0,
                    confidence_basis=(
                        "raw submitted bytes were read as received for session %s" % session_id
                    ),
                ),
                ProvenanceDeclaration(
                    subject="session.bundle_sha256",
                    origin=ORIGIN_COMPUTED,
                    produced_at=submitted_at,
                    confidence=1.0,
                    confidence_basis=(
                        "SHA-256 over the trace-cj/1.0 canonical form of the submitted bundle"
                    ),
                ),
                ProvenanceDeclaration(
                    subject="session.evidence_bundle_root",
                    origin=ORIGIN_COMPUTED,
                    produced_at=submitted_at,
                    confidence=1.0,
                    confidence_basis=(
                        "the frozen root contract of trace.evidence_bundle/1.0 was checked "
                        "field by field against the submitted bundle"
                    ),
                ),
            ),
            notices=tuple(notices),
            stages=stages,
            report=dict(report_body) if report_body is not None else None,
            report_id=report_id_value,
            generated_utc=generated_utc,
            audit=audit,
            reproducibility={
                "bundle_sha256": canonical_hash,
                "module_version": self._settings.module_version,
                "prompt_version": None,
                "knowledge_version": None,
                "provider": None,
                "model": None,
            },
            options=options_payload,
            evidence_bundle=held_bundle,
        )
        return self._persist(record)

    def _persist(self, record: SessionRecord) -> SessionRecord:
        """Store the session. A storage failure is reported, never hidden."""
        try:
            self._store.save(record)
            return record
        except SessionPersistenceError as exc:
            warning = StageWarning(
                WARNING_SESSION_PERSISTENCE_FAILED,
                "the session could not be stored and may not be retrievable later",
                detail=str(exc),
            )
            stored = replace(record, notices=record.notices + (warning,))
            try:
                self._store.save(stored)
            except SessionPersistenceError:
                # The store commits to memory before it writes the file, so the session is
                # still retrievable in this process, and the warning above says so.
                pass
            return stored

    def _parse_bundle(self, evidence: bytes) -> Mapping[str, Any]:
        """Parse the submitted bundle, enforcing the frozen canonicalization rules."""
        try:
            text = evidence.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise BundleNotJSONError(
                "the submitted bundle is not UTF-8 text", detail=str(exc)
            ) from exc
        try:
            parsed = parse_json_strict(text)
        except DuplicateKeyError as exc:
            raise BundleContractViolationError(
                "the submitted bundle violates canonicalization rule 5: %s" % exc,
                detail=str(exc),
            ) from exc
        except CanonicalizationError as exc:
            raise BundleContractViolationError(
                "the submitted bundle violates canonicalization rule 14: %s" % exc,
                detail=str(exc),
            ) from exc
        except json.JSONDecodeError as exc:
            raise BundleNotJSONError(
                "the submitted bundle is not valid JSON: %s" % exc.msg,
                detail="line %d column %d" % (exc.lineno, exc.colno),
            ) from exc
        except ValueError as exc:
            raise BundleNotJSONError(
                "the submitted bundle is not valid JSON", detail=str(exc)
            ) from exc
        if not isinstance(parsed, Mapping):
            raise BundleContractViolationError(
                "the bundle root must be a JSON object",
                detail=(
                    "P3 does not model bundle internals; it requires a canonicalizable JSON "
                    "object at the root"
                ),
            )
        return parsed

    @staticmethod
    def _require_root_contract(bundle: Mapping[str, Any]) -> None:
        """Enforce the frozen trace.evidence_bundle/1.0 root contract (M0-DEC-06).

        A violation is a request problem, not a server error: the session is rejected with
        422 ``bundle_contract_violation`` and the field-level problems stated in the detail.
        """
        problems = validate_evidence_bundle_root(bundle)
        if not problems:
            return
        shown = "; ".join(problems[:5])
        if len(problems) > 5:
            shown += "; and %d more" % (len(problems) - 5)
        raise BundleContractViolationError(
            "the submitted bundle violates the frozen trace.evidence_bundle/1.0 root contract",
            detail=shown,
        )

    def _canonical_hash(self, bundle: Mapping[str, Any]) -> str:
        try:
            return bundle_sha256(bundle)
        except CanonicalizationError as exc:
            raise BundleContractViolationError(
                "the submitted bundle cannot be canonicalized under trace-cj/1.0: %s" % exc,
                detail=str(exc),
            ) from exc

    def _run_stage(self, slot: EngineSlot, request: StageRequest) -> StageResult:
        """Run one stage and time it. Nothing a service does can escape as an exception."""
        started_at = utc_now()
        try:
            result = slot.service.analyse(request)
        except Exception as exc:  # a service that raises is still reported, never swallowed
            result = self._stage_failure(
                slot,
                FAILURE_CODE_ENGINE_FAILED,
                "the %s service raised %s" % (slot.stage, type(exc).__name__),
                detail=str(exc),
                produced_at=started_at,
            )
        finished_at = utc_now()
        if result.stage != slot.stage:
            result = self._stage_failure(
                slot,
                FAILURE_CODE_ENGINE_CONTRACT_VIOLATION,
                "the %s slot answered for stage %r" % (slot.stage, result.stage),
                detail="a service must return a StageResult for the stage it serves",
                produced_at=finished_at,
            )
        return replace(
            result,
            started_at=result.started_at or started_at,
            finished_at=result.finished_at or finished_at,
        )

    @staticmethod
    def _stage_failure(
        slot: EngineSlot,
        code: str,
        message: str,
        *,
        detail: str | None,
        produced_at: Any,
    ) -> StageResult:
        return StageResult(
            stage=slot.stage,
            status=StageStatus.FAILED,
            engine=slot.declaration,
            warnings=(StageWarning(WARNING_ENGINE_FAILED, message, detail=detail),),
            failure=StageFailure(code, message, detail=detail),
            provenance=(
                ProvenanceDeclaration(
                    subject=_STAGE_SUBJECTS[slot.stage],
                    origin=ORIGIN_UNAVAILABLE_VALUE,
                    produced_at=produced_at,
                ),
            ),
            note=detail,
        )

    @staticmethod
    def _session_status(stages: tuple[StageResult, ...]) -> SessionStatus:
        """Derived from the stages, never assumed."""
        statuses = [stage.status for stage in stages]
        if statuses and all(status is StageStatus.OK for status in statuses):
            return SessionStatus.COMPLETE
        if statuses and all(status is StageStatus.FAILED for status in statuses):
            return SessionStatus.FAILED
        return SessionStatus.PARTIAL
