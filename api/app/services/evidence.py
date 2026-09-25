"""Evidence Bundle access and EvidenceRef grounding against a supplied bundle.

This module is P3's integration boundary for the frozen ``trace.evidence_bundle/1.0``
document. It reads only what the freeze authorizes: the root fields and, for fragments,
the ``fragment_id`` field the fragment amendment freezes. Everything else in the bundle
stays opaque: no P1 interior, no P2 field, no invented identifier.

The frozen fragment rules, enforced exactly here:

* a ``fragments[FRG-<16 lowercase hex>-<start>-<end>]`` reference (or a reference in the
  pre-existing generic shape) must resolve to EXACTLY ONE fragment record in the supplied
  bundle;
* zero matches are grounding failures (``evidence_ref_instance_id_not_found``);
* multiple matches are grounding failures (``evidence_ref_multiple_matches``): two records
  sharing a fragment_id never resolve by preference, exception or order;
* a trailing field path of up to two segments stays ``unverifiable`` (D-2: the field
  namespace is still not frozen), and non-fragment collections are withheld as
  ``instance_id_namespace_not_frozen`` because the freeze does not fix an id field for
  them -- membership is never assumed from an invented field name.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from app.contract.evidence_ref import (
    EVIDENCE_REF_COLLECTIONS,
    GROUNDING_REASON_CASE_BLOCK_ABSENT,
    GROUNDING_REASON_FIELD_NAMESPACE_NOT_FROZEN,
    GROUNDING_REASON_INSTANCE_ID_NOT_FOUND,
    GROUNDING_REASON_INSTANCE_ID_NAMESPACE_NOT_FROZEN,
    GROUNDING_REASON_MULTIPLE_MATCHES,
    GROUNDING_REASON_SYNTAX_INVALID,
    GroundingResult,
    GroundingStatus,
    InvalidEvidenceRefError,
    parse_evidence_ref,
)

#: The frozen field name the fragment amendment gives every fragment record.
FRAGMENT_ID_FIELD = "fragment_id"

#: Root references, which the frozen root contract makes present in every accepted bundle.
_ROOT_TOKENS = frozenset({"bundle", "case"})

#: Collections whose array the freeze makes present-or-absent but whose id field it does
#: not fix: membership cannot be verified without inventing a contract field.
_NON_FRAGMENT_COLLECTIONS = frozenset(set(EVIDENCE_REF_COLLECTIONS) - {"fragments"})


def _result_for(
    parsed: Any,
    status: GroundingStatus,
    reason: str | None = None,
    detail: str | None = None,
) -> GroundingResult:
    return GroundingResult(
        ref=parsed.raw,
        status=status,
        reason=reason,
        detail=detail,
        root=parsed.root,
        collection=parsed.collection,
        instance_id=parsed.instance_id,
        segments=parsed.segments,
    )


def fragment_records(bundle: Mapping[str, Any], fragment_id: str) -> tuple[Any, ...]:
    """Every fragment record whose ``fragment_id`` is ``fragment_id``, in bundle order.

    Records without a usable string ``fragment_id`` never match; they are never repaired,
    never assigned an id and never counted as a match.
    """
    fragments = bundle.get("fragments")
    if not isinstance(fragments, Sequence) or isinstance(fragments, (str, bytes)):
        return ()
    return tuple(
        record
        for record in fragments
        if isinstance(record, Mapping)
        and record.get(FRAGMENT_ID_FIELD) == fragment_id
    )


def duplicate_fragment_ids(bundle: Mapping[str, Any]) -> tuple[str, ...]:
    """Fragment ids carried by more than one record, sorted: each is a grounding failure."""
    fragments = bundle.get("fragments")
    if not isinstance(fragments, Sequence) or isinstance(fragments, (str, bytes)):
        return ()
    counts: dict[str, int] = {}
    for record in fragments:
        if isinstance(record, Mapping):
            record_id = record.get(FRAGMENT_ID_FIELD)
            if isinstance(record_id, str):
                counts[record_id] = counts.get(record_id, 0) + 1
    return tuple(sorted(record_id for record_id, count in counts.items() if count > 1))


def bundle_array(bundle: Mapping[str, Any], name: str) -> list[Any] | None:
    """The named frozen array field, or None when the optional field is absent."""
    value = bundle.get(name)
    return value if isinstance(value, list) else None


class BundleEvidenceResolver:
    """Grounds EvidenceRefs against one supplied Evidence Bundle.

    Syntax comes from the single normative validator (D-1, as amended by the frozen Option A
    fragment amendment). Grounding then decides on frozen facts only: the reference kind, the
    presence of the root blocks, and the fragment records' ``fragment_id`` values. A ref is
    never grounded by preference: exactly one match resolves, zero and multiple do not.
    """

    def __init__(self, bundle: Mapping[str, Any]) -> None:
        if not isinstance(bundle, Mapping):
            raise ValueError("a BundleEvidenceResolver requires the bundle mapping")
        self._bundle = bundle

    @property
    def bundle(self) -> Mapping[str, Any]:
        return self._bundle

    def resolve(self, ref: str) -> GroundingResult:
        try:
            parsed = parse_evidence_ref(ref)
        except InvalidEvidenceRefError as exc:
            return GroundingResult(
                ref=ref if isinstance(ref, str) else repr(ref),
                status=GroundingStatus.UNRESOLVED,
                reason=GROUNDING_REASON_SYNTAX_INVALID,
                detail=str(exc),
            )

        if parsed.root in _ROOT_TOKENS:
            # The frozen root contract requires ``case`` in every accepted bundle and makes
            # ``bundle`` the document itself, so root references are always present.
            if parsed.has_trailing_segments:
                return _result_for(
                    parsed,
                    GroundingStatus.UNVERIFIABLE,
                    GROUNDING_REASON_FIELD_NAMESPACE_NOT_FROZEN,
                )
            return _result_for(parsed, GroundingStatus.RESOLVED)

        if parsed.collection in _NON_FRAGMENT_COLLECTIONS:
            # The freeze does not fix an id field for these collections (D-2): membership
            # cannot be checked without inventing a contract field, so the reference is
            # withheld with a reason and never resolved by assumption.
            if parsed.has_trailing_segments:
                return _result_for(
                    parsed,
                    GroundingStatus.UNVERIFIABLE,
                    GROUNDING_REASON_FIELD_NAMESPACE_NOT_FROZEN,
                )
            return _result_for(
                parsed,
                GroundingStatus.UNVERIFIABLE,
                GROUNDING_REASON_INSTANCE_ID_NAMESPACE_NOT_FROZEN,
            )

        # fragments: the one collection whose id field the freeze does fix.
        if parsed.has_trailing_segments:
            return _result_for(
                parsed,
                GroundingStatus.UNVERIFIABLE,
                GROUNDING_REASON_FIELD_NAMESPACE_NOT_FROZEN,
            )

        matches = fragment_records(self._bundle, parsed.instance_id or "")
        if len(matches) == 1:
            return _result_for(parsed, GroundingStatus.RESOLVED)
        if not matches:
            return _result_for(
                parsed,
                GroundingStatus.UNRESOLVED,
                GROUNDING_REASON_INSTANCE_ID_NOT_FOUND,
            )
        return _result_for(
            parsed,
            GroundingStatus.UNRESOLVED,
            GROUNDING_REASON_MULTIPLE_MATCHES,
            detail=(
                "%d fragment records carry fragment_id %r; the frozen rule requires "
                "exactly one" % (len(matches), parsed.instance_id)
            ),
        )

    def resolve_all(self, refs: Sequence[str]) -> tuple[GroundingResult, ...]:
        return tuple(self.resolve(ref) for ref in refs)

