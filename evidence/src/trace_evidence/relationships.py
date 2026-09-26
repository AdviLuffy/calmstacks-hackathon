"""Internal candidate relationship derivation for PDF fragments.

INTERNAL ONLY. This module produces in-memory value objects. Nothing here is
serialized: there is no relationship record type in the frozen contract, no
EvidenceRef root for relationships, and no identifier format for them, so
relationships never enter the Evidence Bundle.

Two hard rules govern everything here:

1. A relationship is a **candidate**. ``Relationship.__post_init__`` refuses any
   label other than ``candidate``, so "proven" / "definitive" cannot be emitted.
2. ``byte_contiguity`` is **always False** for this fixture. The evidence blob is
   a shuffled concatenation carrying no physical-adjacency evidence, so A5
   applies: when it is uncertain, it must be false. ``byte_contiguity`` is a
   property rather than a field precisely so it cannot be set True by accident.

LIMITATION - READ THIS BEFORE REUSING THE RULES
-----------------------------------------------
The ``object_ascending_chain`` rule orders object fragments by **ascending
object number**. That is a *fixture-specific deterministic heuristic*, NOT a
guarantee of PDF semantics: the PDF specification does not require objects to
appear in the file in ascending object-number order. This rule happens to hold
for the synthetic fixture because that fixture was authored objects-first in
ascending order, and it is stated here so the rule is never mistaken for general
PDF ordering. Ordering from the cross-reference table's declared offsets is a
separate, stronger check and is deliberately NOT implemented here.

Ambiguity is never resolved by guessing: duplicate kinds, duplicate object
numbers, gaps in the object-number sequence and unplaceable ``unknown``
fragments all produce an ``UnresolvedJoin`` entry naming the candidates that were
considered, instead of a silently chosen edge.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .constants import (
    KIND_EOF,
    KIND_HEADER,
    KIND_OBJECT,
    KIND_STARTXREF,
    KIND_TRAILER,
    KIND_UNKNOWN,
    KIND_XREF,
    LABEL_CANDIDATE,
)
from .dna import (
    FragmentProfile,
    TOKEN_EOF,
    TOKEN_STARTXREF,
    TOKEN_TRAILER,
    TOKEN_XREF,
)

__all__ = [
    "RULE_HEADER_TO_FIRST_OBJECT",
    "RULE_OBJECT_ASCENDING_CHAIN",
    "RULE_LAST_OBJECT_TO_XREF",
    "RULE_XREF_TO_TRAILER",
    "RULE_TRAILER_TO_STARTXREF",
    "RULE_STARTXREF_TO_EOF",
    "RULE_UNPLACED_KIND",
    "Relationship",
    "UnresolvedJoin",
    "RelationshipAnalysis",
    "derive_relationships",
]

# Internal rule identifiers. These are implementation details, not contract
# vocabulary, which is why they live here rather than in constants.py.
RULE_HEADER_TO_FIRST_OBJECT = "header_to_first_object"
RULE_OBJECT_ASCENDING_CHAIN = "object_ascending_chain"
RULE_LAST_OBJECT_TO_XREF = "last_object_to_xref"
RULE_XREF_TO_TRAILER = "xref_to_trailer"
RULE_TRAILER_TO_STARTXREF = "trailer_to_startxref"
RULE_STARTXREF_TO_EOF = "startxref_to_eof"
RULE_UNPLACED_KIND = "unplaced_kind"


@dataclass(frozen=True)
class Relationship:
    """A candidate ordering relationship between two fragments.

    Internal value object: never serialized, never placed in the bundle. It has
    deliberately **no identifier** - the contract freezes no relationship ID
    format and no EvidenceRef root for relationships, so identity is the ``key``
    tuple ``(from_fragment_id, to_fragment_id, rule)``.
    """

    from_fragment_id: str
    to_fragment_id: str
    rule: str
    label: str = LABEL_CANDIDATE
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.from_fragment_id == self.to_fragment_id:
            raise ValueError("a fragment cannot be related to itself")
        if self.label != LABEL_CANDIDATE:
            raise ValueError(
                "relationships are candidate-only: label must be "
                f"{LABEL_CANDIDATE!r}, got {self.label!r}"
            )
        if not self.evidence:
            raise ValueError("a relationship must carry the evidence that justifies it")

    @property
    def key(self) -> tuple[str, str, str]:
        """Natural identity of the relationship. Not an invented ID format."""
        return (self.from_fragment_id, self.to_fragment_id, self.rule)

    @property
    def byte_contiguity(self) -> bool:
        """Always ``False`` here.

        Establishing physical adjacency in the source is the only basis for a
        definitive join (A5), and the evidence blob carries no such evidence -
        the fragment order in the blob is a shuffle, and the true adjacency lives
        only in ground truth outside the bundle. A property, not a field, so no
        caller can flip it to ``True``.
        """
        return False

    @property
    def is_definitive(self) -> bool:
        """Never definitive for this fixture, because ``byte_contiguity`` is False."""
        return self.byte_contiguity


@dataclass(frozen=True)
class UnresolvedJoin:
    """An ambiguity the rules refused to resolve by guessing.

    Internal value object: never serialized. Recorded instead of an edge, and
    instead of dropping the observation silently.
    """

    rule: str
    reason: str
    candidate_fragment_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class RelationshipAnalysis:
    """Result of one derivation pass. Internal; never serialized."""

    relationships: tuple[Relationship, ...]
    unresolved: tuple[UnresolvedJoin, ...]
    unplaced_fragment_ids: tuple[str, ...]
    missing_elements: tuple[str, ...] = ()
    conflicting_fragment_ids: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        """True when every fragment was placed and nothing stayed ambiguous."""
        return not self.unresolved and not self.unplaced_fragment_ids


def _group_by_kind(profiles) -> dict[str, list[FragmentProfile]]:
    grouped: dict[str, list[FragmentProfile]] = {}
    for profile in profiles:
        grouped.setdefault(profile.kind, []).append(profile)
    return grouped


def _ids(profiles) -> tuple[str, ...]:
    """Canonical, order-independent candidate list for an ambiguity report."""
    return tuple(sorted(profile.fragment_id for profile in profiles))


def _edge(rule: str, source: FragmentProfile, target: FragmentProfile, evidence) -> Relationship:
    return Relationship(
        from_fragment_id=source.fragment_id,
        to_fragment_id=target.fragment_id,
        rule=rule,
        evidence=tuple(evidence),
    )


def _expect_one(rule: str, kind: str, profiles, unresolved: list) -> FragmentProfile | None:
    """Return the single profile of ``kind``, or record why it is ambiguous."""
    if len(profiles) == 1:
        return profiles[0]
    unresolved.append(
        UnresolvedJoin(
            rule=rule,
            reason=f"expected exactly one {kind!r} fragment, found {len(profiles)}",
            candidate_fragment_ids=_ids(profiles),
        )
    )
    return None


def _duplicated_numbers(numbers: list[int]) -> list[int]:
    seen: set[int] = set()
    duplicated: list[int] = []
    for number in numbers:
        if number in seen and number not in duplicated:
            duplicated.append(number)
        seen.add(number)
    return duplicated


def _missing_numbers(numbers: list[int]) -> list[int]:
    if len(numbers) < 2:
        return []
    present = set(numbers)
    return [
        number
        for number in range(numbers[0], numbers[-1] + 1)
        if number not in present
    ]

def _object_chain(objects, unresolved: list) -> list[Relationship]:
    """Order object fragments by ascending object number, or refuse to.

    FIXTURE-SPECIFIC HEURISTIC. The PDF specification does not require objects
    to appear in ascending object-number order, so this rule is not a general
    PDF ordering guarantee. It is deterministic, and it holds for the synthetic
    fixture because that fixture was authored that way. When the number sequence
    is ambiguous - a number claimed by two fragments, or a gap - no edge is
    emitted for the affected pair and the conflict is recorded instead.
    """
    numbers = [profile.object_number for profile in objects]
    duplicated = _duplicated_numbers(numbers)
    missing = _missing_numbers(sorted(numbers))

    if duplicated or missing:
        unresolved.append(
            UnresolvedJoin(
                rule=RULE_OBJECT_ASCENDING_CHAIN,
                reason=(
                    "object-number sequence is not a clean ascending chain: "
                    f"duplicated={duplicated}, missing={missing}; no object edge "
                    "chosen (ascending object number is a fixture heuristic, not "
                    "a PDF ordering guarantee, and an ambiguous sequence is never "
                    "resolved by guessing)"
                ),
                candidate_fragment_ids=_ids(objects),
            )
        )
        return []

    ordered = sorted(objects, key=lambda profile: profile.object_number)
    edges = []
    for earlier, later in zip(ordered, ordered[1:]):
        edges.append(
            _edge(
                RULE_OBJECT_ASCENDING_CHAIN,
                earlier,
                later,
                (
                    f"object_number {earlier.object_number} precedes "
                    f"{later.object_number} under the ascending-number heuristic",
                    "heuristic only: the PDF specification does not require objects "
                    "to appear in ascending object-number order",
                ),
            )
        )
    return edges


def _first_object(objects, unresolved: list) -> FragmentProfile | None:
    """Lowest-numbered object, or None when that choice would be a guess."""
    if len(objects) == 1:
        return objects[0]
    numbers = [profile.object_number for profile in objects]
    if len(objects) > 1 and not _duplicated_numbers(numbers):
        return min(objects, key=lambda profile: profile.object_number)
    unresolved.append(
        UnresolvedJoin(
            rule=RULE_HEADER_TO_FIRST_OBJECT,
            reason=(
                "cannot name a unique first object: "
                f"found {len(objects)} object fragment(s)"
            ),
            candidate_fragment_ids=_ids(objects),
        )
    )
    return None


def _last_object(objects, unresolved: list) -> FragmentProfile | None:
    """Highest-numbered object, or None when that choice would be a guess."""
    if len(objects) == 1:
        return objects[0]
    numbers = [profile.object_number for profile in objects]
    if len(objects) > 1 and not _duplicated_numbers(numbers):
        return max(objects, key=lambda profile: profile.object_number)
    unresolved.append(
        UnresolvedJoin(
            rule=RULE_LAST_OBJECT_TO_XREF,
            reason=(
                "cannot name a unique last object: "
                f"found {len(objects)} object fragment(s)"
            ),
            candidate_fragment_ids=_ids(objects),
        )
    )
    return None


def derive_relationships(profiles: Sequence[FragmentProfile]) -> RelationshipAnalysis:
    """Derive candidate ordering edges from structural profiles.

    Takes profiles only. Opens no files, reads no manifest and consults no blob
    position: a fragment's location in the evidence blob is a shuffle and is not
    evidence of order.

    Returns candidate edges plus every ambiguity the rules refused to resolve.
    The result is an in-memory value object with no serialization path.
    """
    grouped = _group_by_kind(profiles)
    unresolved: list[UnresolvedJoin] = []
    edges: list[Relationship] = []

    headers = grouped.get(KIND_HEADER, [])
    objects = grouped.get(KIND_OBJECT, [])
    xrefs = [p for p in profiles if p.kind == KIND_XREF or (not p.is_object and TOKEN_XREF in p.tokens)]
    trailers = [p for p in profiles if p.kind == KIND_TRAILER or (not p.is_object and TOKEN_TRAILER in p.tokens)]
    startxrefs = [p for p in profiles if p.kind == KIND_STARTXREF or (not p.is_object and TOKEN_STARTXREF in p.tokens)]
    eofs = [p for p in profiles if p.kind == KIND_EOF or (not p.is_object and TOKEN_EOF in p.tokens)]

    header = _expect_one(RULE_HEADER_TO_FIRST_OBJECT, KIND_HEADER, headers, unresolved)
    xref = _expect_one(RULE_XREF_TO_TRAILER, KIND_XREF, xrefs, unresolved)
    trailer = _expect_one(RULE_TRAILER_TO_STARTXREF, KIND_TRAILER, trailers, unresolved)
    startxref = _expect_one(RULE_STARTXREF_TO_EOF, KIND_STARTXREF, startxrefs, unresolved)
    eof = _expect_one(RULE_STARTXREF_TO_EOF, KIND_EOF, eofs, unresolved)

    if xref is None:
        # last_object_to_xref depends on the same uniqueness and must say so
        # itself, rather than silently inheriting another rule's failure.
        _expect_one(RULE_LAST_OBJECT_TO_XREF, KIND_XREF, xrefs, unresolved)

    if header is not None:
        first_object = _first_object(objects, unresolved)
        if first_object is not None:
            edges.append(
                _edge(
                    RULE_HEADER_TO_FIRST_OBJECT,
                    header,
                    first_object,
                    (
                        "exactly one header fragment",
                        f"target object_number={first_object.object_number} is the "
                        "lowest object number present",
                    ),
                )
            )

    if objects:
        edges.extend(_object_chain(objects, unresolved))

    if xref is not None:
        last_object = _last_object(objects, unresolved)
        if last_object is not None:
            edges.append(
                _edge(
                    RULE_LAST_OBJECT_TO_XREF,
                    last_object,
                    xref,
                    (
                        f"source object_number={last_object.object_number} is the "
                        "highest object number present",
                        "exactly one xref fragment",
                    ),
                )
            )

    _append_section_edges(xref, trailer, startxref, eof, edges)
    _record_unknowns(profiles, edges, unresolved)

    # Detailed missing elements and conflicts detection
    missing_elements: list[str] = []
    conflicting_fragment_ids: list[str] = []

    if len(headers) == 0:
        missing_elements.append("missing structural fragment: header (%PDF-)")
    elif len(headers) > 1:
        conflicting_fragment_ids.extend(p.fragment_id for p in headers)

    if not objects:
        missing_elements.append("missing structural fragments: object definitions (obj)")
    else:
        numbers = [p.object_number for p in objects]
        duplicated = _duplicated_numbers(numbers)
        if duplicated:
            for d in duplicated:
                conflicting_fragment_ids.extend(p.fragment_id for p in objects if p.object_number == d)
        missing = _missing_numbers(sorted(numbers))
        for m in missing:
            missing_elements.append(f"missing object: {m}")

    if len(xrefs) == 0:
        missing_elements.append("missing structural fragment: cross-reference table (xref)")
    elif len(xrefs) > 1:
        conflicting_fragment_ids.extend(p.fragment_id for p in xrefs)

    if len(trailers) == 0:
        missing_elements.append("missing structural fragment: trailer dictionary")
    elif len(trailers) > 1:
        conflicting_fragment_ids.extend(p.fragment_id for p in trailers)

    if len(startxrefs) == 0:
        missing_elements.append("missing structural fragment: startxref pointer")
    elif len(startxrefs) > 1:
        conflicting_fragment_ids.extend(p.fragment_id for p in startxrefs)

    if len(eofs) == 0:
        missing_elements.append("missing structural fragment: EOF terminator (%%EOF)")
    elif len(eofs) > 1:
        conflicting_fragment_ids.extend(p.fragment_id for p in eofs)

    return _analysis(
        profiles,
        edges,
        unresolved,
        missing_elements=tuple(missing_elements),
        conflicting_fragment_ids=tuple(sorted(set(conflicting_fragment_ids))),
    )


def _append_section_edges(xref, trailer, startxref, eof, edges) -> None:
    if xref is not None and trailer is not None and xref.fragment_id != trailer.fragment_id:
        edges.append(
            _edge(
                RULE_XREF_TO_TRAILER,
                xref,
                trailer,
                ("exactly one xref fragment", "exactly one trailer fragment"),
            )
        )
    if trailer is not None and startxref is not None and trailer.fragment_id != startxref.fragment_id:
        edges.append(
            _edge(
                RULE_TRAILER_TO_STARTXREF,
                trailer,
                startxref,
                ("exactly one trailer fragment", "exactly one startxref fragment"),
            )
        )
    if startxref is not None and eof is not None and startxref.fragment_id != eof.fragment_id:
        edges.append(
            _edge(
                RULE_STARTXREF_TO_EOF,
                startxref,
                eof,
                ("exactly one startxref fragment", "exactly one eof fragment"),
            )
        )


def _record_unknowns(profiles, edges, unresolved) -> None:
    placed = {
        fragment_id
        for edge in edges
        for fragment_id in (edge.from_fragment_id, edge.to_fragment_id)
    }
    for profile in profiles:
        if profile.fragment_id in placed or profile.kind != KIND_UNKNOWN:
            continue
        unresolved.append(
            UnresolvedJoin(
                rule=RULE_UNPLACED_KIND,
                reason="unknown kind is never placed by a structural rule",
                candidate_fragment_ids=(profile.fragment_id,),
            )
        )


def _analysis(
    profiles,
    edges,
    unresolved,
    missing_elements: tuple[str, ...] = (),
    conflicting_fragment_ids: tuple[str, ...] = (),
) -> RelationshipAnalysis:
    placed = {
        fragment_id
        for edge in edges
        for fragment_id in (edge.from_fragment_id, edge.to_fragment_id)
    }
    unplaced = tuple(
        sorted(
            profile.fragment_id
            for profile in profiles
            if profile.fragment_id not in placed
        )
    )
    ordered_edges = tuple(sorted(edges, key=lambda edge: edge.key))
    ordered_unresolved = tuple(
        sorted(
            unresolved,
            key=lambda item: (item.rule, item.reason, item.candidate_fragment_ids),
        )
    )
    return RelationshipAnalysis(
        relationships=ordered_edges,
        unresolved=ordered_unresolved,
        unplaced_fragment_ids=unplaced,
        missing_elements=missing_elements,
        conflicting_fragment_ids=conflicting_fragment_ids,
    )

