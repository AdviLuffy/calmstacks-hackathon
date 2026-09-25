"""M0 EvidenceRef: frozen syntax, and the tri-state resolver.

The M0 material supplies BOTH a prose grammar and a regex, and declares them
"equivalent". They are not equivalent, which was verified by execution. D-1 (authorized)
therefore makes the REGEX the single normative syntactic validator and records the prose
grammar as non-normative. Both conflicting definitions, and the reason for choosing the
regex, are recorded in :mod:`app.contract.registry`. This module deliberately does NOT
support both definitions: there is exactly one validation path.

D-2 (authorized): the set of legal trailing field names per collection is NOT frozen by
the M0 material, so no field name is invented here. A syntactically valid reference whose
target field cannot be verified resolves to ``unverifiable`` with reason
``evidence_ref_field_namespace_not_frozen``, and grounding fails conservatively.

The ``[n]`` index is the only array-index form accepted. JSON pointers, wildcards and
arbitrary nested collections are not representable by the normative pattern.

Freeze (M0-DEC-06): the Option A amendment is frozen and this module implements it inside
the single normative pattern. The ``fragments`` slot admits the frozen fragment form
``fragments[FRG-<16 lowercase hex>-<start>-<end>]`` (with the pre-existing generic instance
shape kept as an alternative, so M0-DEC-01's language is widened and never replaced). No
second EvidenceRef syntax exists anywhere else: one pattern, one validator. Grounding of a
fragment reference against a supplied Evidence Bundle (exactly one record, zero or multiple
matches being grounding failures) lives in :mod:`app.services.evidence`.
"""
from __future__ import annotations

import re
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

# ---------------------------------------------------------------------------------
# Normative syntax (D-1, amended by the frozen Option A fragment amendment, M0-DEC-06).
# ---------------------------------------------------------------------------------
#: The generic instance-identifier shape M0-DEC-01 froze for the indexed collections.
_GENERIC_INSTANCE_ID = r"[A-Z]{2,6}(?:-[A-Z0-9]{1,12})*-\d{2,10}"

#: The frozen FragmentInstanceId shape (FRG-<16 lowercase hex>-<start>-<end>). Since the
#: Option A freeze it is an alternative INSIDE the fragments slot of the single normative
#: pattern; it is never validated by a second grammar anywhere.
_FRAGMENT_INSTANCE_ID = r"FRG-[0-9a-f]{16}-\d{1,10}-\d{1,10}"

EVIDENCE_REF_PATTERN = (
    r"^(?:bundle|case|"
    r"(?:artifacts|reconstruction_groups|timeline_events|known_file_matches)\["
    + _GENERIC_INSTANCE_ID
    + r"\]|fragments\[(?:"
    + _FRAGMENT_INSTANCE_ID
    + r"|"
    + _GENERIC_INSTANCE_ID
    + r")\])"
    r"(?:\.[a-z][a-z0-9_]*(?:\[\d+\])?){0,2}$"
)

#: The single normative validator pattern.
EVIDENCE_REF_RE = re.compile(EVIDENCE_REF_PATTERN)

#: Named-group view of the same language, used only to decompose an already-validated
#: reference. A test asserts it accepts exactly the same strings as EVIDENCE_REF_RE.
#: The fragments branch carries its own collection group because the parser must label the
#: reference ``fragments`` whatever instance shape matched inside the brackets.
PARSE_PATTERN = (
    r"^(?P<head>bundle|case|"
    r"(?P<collection>artifacts|reconstruction_groups|timeline_events|known_file_matches)\["
    + _GENERIC_INSTANCE_ID
    + r"\]|(?P<fragments_collection>fragments)\[(?:"
    + _FRAGMENT_INSTANCE_ID
    + r"|"
    + _GENERIC_INSTANCE_ID
    + r")\])"
    r"(?P<segments>(?:\.[a-z][a-z0-9_]*(?:\[\d+\])?){0,2})$"
)
PARSE_RE = re.compile(PARSE_PATTERN)

#: D-1: the regex is normative; the prose grammar is not.
REGEX_IS_NORMATIVE = True
PROSE_GRAMMAR_IS_NORMATIVE = False

#: The five indexed collection names.
EVIDENCE_REF_COLLECTIONS = (
    "artifacts",
    "fragments",
    "reconstruction_groups",
    "timeline_events",
    "known_file_matches",
)

#: The two root references.
EVIDENCE_REF_ROOT_TOKENS = ("bundle", "case")

#: Maximum number of trailing segments in any EvidenceRef.
MAX_TRAILING_SEGMENTS = 2

#: The only array-index form permitted in an EvidenceRef.
INDEX_PATTERN = r"\[\d+\]"
INDEX_RE = re.compile(INDEX_PATTERN)

#: The generic instance-id shape implied by M0-DEC-01 (anchored here for reuse). The
#: fragments slot additionally admits the frozen FRG shape via EVIDENCE_REF_PATTERN; a
#: frozen FragmentInstanceId deliberately does NOT match this generic shape.
INSTANCE_ID_PATTERN = r"^[A-Z]{2,6}(-[A-Z0-9]{1,12})*-\d{2,10}$"
INSTANCE_ID_RE = re.compile(INSTANCE_ID_PATTERN)

_SEGMENT_RE = re.compile(r"\.([a-z][a-z0-9_]*)(?:\[(\d+)\])?")


class InvalidEvidenceRefError(ValueError):
    """The string is not a valid EvidenceRef under the normative M0 pattern."""


@dataclass(frozen=True)
class ParsedEvidenceRef:
    """A syntactically valid EvidenceRef, decomposed without interpreting fields."""

    raw: str
    root: str
    collection: str | None
    instance_id: str | None
    segments: tuple[str, ...]
    segment_indexes: tuple[int | None, ...]

    @property
    def has_trailing_segments(self) -> bool:
        return bool(self.segments)

    @property
    def is_root_reference(self) -> bool:
        return self.collection is None


def parse_evidence_ref(raw: str) -> ParsedEvidenceRef:
    """Decompose ``raw``, raising InvalidEvidenceRefError if it is not valid."""
    if not isinstance(raw, str):
        raise InvalidEvidenceRefError("EvidenceRef must be a string, got %s" % type(raw).__name__)
    if EVIDENCE_REF_RE.fullmatch(raw) is None:
        raise InvalidEvidenceRefError(
            "not a valid EvidenceRef under the normative M0 pattern (D-1): %r" % (raw,)
        )
    parse_match = PARSE_RE.fullmatch(raw)
    if parse_match is None:
        # Defensive only: a test asserts the two patterns accept the same language.
        raise InvalidEvidenceRefError(
            "internal error: named-group pattern rejected a reference the normative "
            "pattern accepted: %r" % (raw,)
        )

    head = parse_match.group("head")
    collection = parse_match.group("collection") or parse_match.group("fragments_collection")
    if collection is None:
        root = head
        instance_id = None
    else:
        root = collection
        instance_id = head[head.index("[") + 1 : -1]

    segments: list[str] = []
    indexes: list[int | None] = []
    for segment_match in _SEGMENT_RE.finditer(raw):
        segments.append(segment_match.group(1))
        index_text = segment_match.group(2)
        indexes.append(int(index_text) if index_text is not None else None)

    return ParsedEvidenceRef(
        raw=raw,
        root=root,
        collection=collection,
        instance_id=instance_id,
        segments=tuple(segments),
        segment_indexes=tuple(indexes),
    )


def is_valid_evidence_ref(raw: object) -> bool:
    """True only for a syntactically valid EvidenceRef under the normative pattern."""
    return isinstance(raw, str) and EVIDENCE_REF_RE.fullmatch(raw) is not None


# ---------------------------------------------------------------------------------
# Grounding (D-2): tri-state, conservative, and field-name agnostic.
# ---------------------------------------------------------------------------------
class GroundingStatus(str, Enum):
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    UNVERIFIABLE = "unverifiable"


GROUNDING_REASON_SYNTAX_INVALID = "evidence_ref_syntax_invalid"
GROUNDING_REASON_CASE_BLOCK_ABSENT = "case_block_absent"
GROUNDING_REASON_INSTANCE_ID_NOT_FOUND = "instance_id_not_found"
GROUNDING_REASON_FIELD_NAMESPACE_NOT_FROZEN = "evidence_ref_field_namespace_not_frozen"
#: The frozen exactly-one-record rule: a reference matched more than one supplied record.
GROUNDING_REASON_MULTIPLE_MATCHES = "multiple_matches"
#: The frozen root contract does not fix an id field for this collection, so membership
#: cannot be verified without inventing one; the reference is withheld, never assumed.
GROUNDING_REASON_INSTANCE_ID_NAMESPACE_NOT_FROZEN = "instance_id_namespace_not_frozen"


@dataclass(frozen=True)
class GroundingResult:
    """Outcome of attempting to resolve one EvidenceRef."""

    ref: str
    status: GroundingStatus
    reason: str | None = None
    detail: str | None = None
    root: str | None = None
    collection: str | None = None
    instance_id: str | None = None
    segments: tuple[str, ...] = ()

    @property
    def is_grounded(self) -> bool:
        """Only a fully resolved reference counts as grounded."""
        return self.status is GroundingStatus.RESOLVED


class EvidenceRefResolver(Protocol):
    """Resolves EvidenceRefs against known identifiers."""

    def resolve(self, ref: str) -> GroundingResult: ...

    def resolve_all(self, refs: Sequence[str]) -> tuple[GroundingResult, ...]: ...


def all_grounded(results: Sequence[GroundingResult]) -> bool:
    """Grounding requires every reference to resolve. An empty set is not grounded."""
    return bool(results) and all(result.is_grounded for result in results)


def ungrounded(results: Sequence[GroundingResult]) -> tuple[GroundingResult, ...]:
    """The subset of results that did not resolve (for reporting a reason)."""
    return tuple(result for result in results if not result.is_grounded)


def _result(
    parsed: ParsedEvidenceRef,
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


class SessionEvidenceRefResolver:
    """Resolves references against one session, using only frozen M0 information.

    The resolver never inspects a trailing field name. It decides on exactly four
    facts: the reference is syntactically valid, the reference is a root reference or a
    collection reference, the referenced identifier exists, and whether trailing
    segments are present. Any reference carrying trailing segments is ``unverifiable``,
    because the legal field namespace is not frozen (D-2).
    """

    def __init__(
        self,
        *,
        collection_ids: Mapping[str, Collection[str]] | None = None,
        case_block_present: bool = False,
    ) -> None:
        self._collection_ids: dict[str, frozenset[str]] = {
            name: frozenset(ids) for name, ids in (collection_ids or {}).items()
        }
        self._case_block_present = bool(case_block_present)

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

        if parsed.root == "bundle":
            return _result(parsed, GroundingStatus.RESOLVED)

        if parsed.root == "case":
            if not self._case_block_present:
                return _result(parsed, GroundingStatus.UNRESOLVED, GROUNDING_REASON_CASE_BLOCK_ABSENT)
            if parsed.has_trailing_segments:
                return _result(
                    parsed, GroundingStatus.UNVERIFIABLE, GROUNDING_REASON_FIELD_NAMESPACE_NOT_FROZEN
                )
            return _result(parsed, GroundingStatus.RESOLVED)

        known = self._collection_ids.get(parsed.root or "", frozenset())
        if parsed.instance_id not in known:
            return _result(
                parsed, GroundingStatus.UNRESOLVED, GROUNDING_REASON_INSTANCE_ID_NOT_FOUND
            )
        if parsed.has_trailing_segments:
            return _result(
                parsed, GroundingStatus.UNVERIFIABLE, GROUNDING_REASON_FIELD_NAMESPACE_NOT_FROZEN
            )
        return _result(parsed, GroundingStatus.RESOLVED)

    def resolve_all(self, refs: Sequence[str]) -> tuple[GroundingResult, ...]:
        return tuple(self.resolve(ref) for ref in refs)