"""Internal reconstruction and PDF structural self-validation engine.

INTERNAL ONLY. This module assembles original fragment bytes by walking candidate
relationships deterministically, starting from the PDF header. Nothing here is
serialized, no relationship is marked proven, and byte_contiguity is strictly
maintained as False.

Honesty invariants:
1. Never fabricate, pad, or synthesize bytes. Output is only ever a concatenation
   of authentic carved fragment bytes.
2. Incomplete or ambiguous chains are reported as incomplete and are never presented
   as valid reconstructed PDFs.
3. PDF structural validity is assessed using the format's own internal grammar
   (header, EOF, startxref, xref table, and object offsets) - never by consulting
   the ground-truth manifest or external oracle data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping, Sequence

from .constants import (
    KIND_EOF,
    KIND_HEADER,
    LABEL_CANDIDATE,
    STATUS_FAILED,
    STATUS_INCOMPLETE,
    STATUS_STRUCTURALLY_VALID,
)
from .dna import FragmentProfile, TOKEN_EOF
from .hashing import sha256_bytes
from .models import Fragment
from .relationships import Relationship, RelationshipAnalysis, UnresolvedJoin

__all__ = [
    "StructureValidationResult",
    "ReconstructionResult",
    "walk_candidate_chain",
    "validate_pdf_structure",
    "reconstruct",
]

_PDF_HEADER_PREFIX = b"%PDF-"
_PDF_EOF_TOKEN = b"%%EOF"
_STARTXREF_RE = re.compile(rb"\bstartxref[ \t\r\n]+(\d+)\b")
_XREF_SUBSECTION_RE = re.compile(rb"^xref[ \t\r\n]+(\d+)[ \t]+(\d+)[ \t\r\n]+")
_XREF_ENTRY_RE = re.compile(rb"^(\d{10})[ \t]+(\d{5})[ \t]+([nf])[ \t\r\n]+")


@dataclass(frozen=True)
class StructureValidationResult:
    """Outcome of validating a reconstructed PDF using its own internal structure."""

    is_valid: bool
    status: str
    startxref_offset: int | None = None
    object_offsets: tuple[tuple[int, int], ...] = ()
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class ReconstructionResult:
    """Outcome of walking candidate relationships and assembling fragment bytes."""

    raw_bytes: bytes
    fragment_order: tuple[str, ...]
    relationships_used: tuple[Relationship, ...]
    validation: StructureValidationResult
    status: str
    warnings: tuple[str, ...] = ()
    unresolved: tuple[UnresolvedJoin, ...] = ()
    unplaced_fragment_ids: tuple[str, ...] = ()

    @property
    def complete(self) -> bool:
        """True only if structurally valid with no unresolved joins or missing fragments.

        Informational warnings alone do not turn a structurally valid result into
        incomplete, but unresolved joins or unplaced fragments strictly prevent
        completeness.
        """
        return (
            self.status == STATUS_STRUCTURALLY_VALID
            and self.validation.is_valid
            and not self.unplaced_fragment_ids
            and not self.unresolved
        )


def walk_candidate_chain(
    relationships: Sequence[Relationship],
    profiles: Sequence[FragmentProfile],
) -> tuple[tuple[str, ...], tuple[Relationship, ...], tuple[str, ...]]:
    """Walk candidate relationships sequentially from the PDF header fragment.

    Enforces that:
    1. Every relationship is candidate-only with byte_contiguity=False.
    2. Exactly one header fragment initiates the traversal.
    3. Traversal is deterministic and refuses to guess on branching, convergence,
       or cycles.
    """
    for rel in relationships:
        if rel.label != LABEL_CANDIDATE:
            raise ValueError(
                f"relationships must be candidate-only, found {rel.label!r}"
            )
        if rel.byte_contiguity:
            raise ValueError("byte_contiguity must remain False without physical adjacency")

    by_id = {p.fragment_id: p for p in profiles}
    headers = [p for p in profiles if p.kind == KIND_HEADER]

    if not headers:
        return ((), (), ("cannot walk candidate chain: no header fragment found",))
    if len(headers) > 1:
        return (
            (),
            (),
            (
                "cannot walk candidate chain: multiple header fragments found "
                "(ambiguous start)",
            ),
        )

    start_id = headers[0].fragment_id

    outgoing: dict[str, list[Relationship]] = {}
    incoming: dict[str, list[Relationship]] = {}
    for rel in relationships:
        outgoing.setdefault(rel.from_fragment_id, []).append(rel)
        incoming.setdefault(rel.to_fragment_id, []).append(rel)

    for from_id, edges in outgoing.items():
        if len(edges) > 1:
            return (
                (),
                (),
                (
                    f"ambiguous branching: fragment {from_id} has {len(edges)} "
                    "outgoing candidate edges",
                ),
            )

    for to_id, edges in incoming.items():
        if len(edges) > 1:
            return (
                (),
                (),
                (
                    f"ambiguous convergence: fragment {to_id} has {len(edges)} "
                    "incoming candidate edges",
                ),
            )

    chain = [start_id]
    visited = {start_id}
    edges_used: list[Relationship] = []
    current_id = start_id
    warnings: list[str] = []

    while current_id in outgoing:
        edge = outgoing[current_id][0]
        next_id = edge.to_fragment_id

        if next_id in visited:
            warnings.append(f"cycle detected: fragment {next_id} was revisited")
            break
        if next_id not in by_id:
            warnings.append(f"edge targets unknown fragment {next_id}")
            break

        visited.add(next_id)
        chain.append(next_id)
        edges_used.append(edge)
        current_id = next_id

    if chain:
        last_profile = by_id[chain[-1]]
        if last_profile.kind != KIND_EOF and TOKEN_EOF not in last_profile.tokens:
            warnings.append(
                f"chain ended at kind {last_profile.kind!r} instead of {KIND_EOF!r}"
            )

    unplaced = [p.fragment_id for p in profiles if p.fragment_id not in visited]
    if unplaced:
        warnings.append(f"{len(unplaced)} fragment(s) remain unplaced")

    return tuple(chain), tuple(edges_used), tuple(warnings)


def validate_pdf_structure(data: bytes) -> StructureValidationResult:
    """Validate a reconstructed byte sequence against the PDF format's own grammar.

    Performs structural inspection on the reconstructed bytes directly:
    1. Leading '%PDF-' header magic.
    2. Trailing '%%EOF' terminator token.
    3. Valid 'startxref' token and bounds-checked xref table offset.
    4. Structural parsing of the xref section and entries.
    5. Verification that all declared object offsets actually point to their
       respective '<num> <gen> obj' definitions.
    """
    errors: list[str] = []

    if not data.startswith(_PDF_HEADER_PREFIX):
        errors.append("data does not begin with PDF header (%PDF-)")

    trimmed = data.rstrip(b" \t\r\n")
    if not trimmed.endswith(_PDF_EOF_TOKEN):
        errors.append("data does not terminate with %%EOF marker")

    startxref_match = _STARTXREF_RE.search(data)
    if not startxref_match:
        errors.append("missing or malformed startxref token")
        return StructureValidationResult(
            is_valid=False,
            status=STATUS_FAILED,
            errors=tuple(errors),
        )

    xref_offset = int(startxref_match.group(1))
    if xref_offset < 0 or xref_offset >= len(data):
        errors.append(
            f"startxref offset {xref_offset} is out of bounds [0, {len(data)})"
        )
        return StructureValidationResult(
            is_valid=False,
            status=STATUS_FAILED,
            startxref_offset=xref_offset,
            errors=tuple(errors),
        )

    xref_chunk = data[xref_offset:]
    if not xref_chunk.startswith(b"xref"):
        errors.append(
            f"bytes at startxref offset {xref_offset} do not begin with 'xref'"
        )
        return StructureValidationResult(
            is_valid=False,
            status=STATUS_FAILED,
            startxref_offset=xref_offset,
            errors=tuple(errors),
        )

    subsection_match = _XREF_SUBSECTION_RE.match(xref_chunk)
    if not subsection_match:
        errors.append("malformed xref subsection header")
        return StructureValidationResult(
            is_valid=False,
            status=STATUS_FAILED,
            startxref_offset=xref_offset,
            errors=tuple(errors),
        )

    first_obj = int(subsection_match.group(1))
    count = int(subsection_match.group(2))

    entries_data = xref_chunk[subsection_match.end():]
    pos = 0
    object_offsets: list[tuple[int, int]] = []

    for i in range(count):
        obj_num = first_obj + i
        entry_match = _XREF_ENTRY_RE.match(entries_data[pos:])
        if not entry_match:
            errors.append(f"malformed xref entry at index {i} for object {obj_num}")
            break

        pos += entry_match.end()
        offset = int(entry_match.group(1))
        state = entry_match.group(3).decode("ascii")

        if state == "n":
            object_offsets.append((obj_num, offset))
            if offset < 0 or offset >= len(data):
                errors.append(
                    f"object {obj_num} offset {offset} is out of bounds [0, {len(data)})"
                )
            else:
                obj_pattern = rf"^{obj_num}[ \t]+\d+[ \t]+obj\b".encode("ascii")
                if not re.match(obj_pattern, data[offset:]):
                    errors.append(
                        f"object {obj_num} header not found at declared offset {offset}"
                    )

    is_valid = len(errors) == 0
    return StructureValidationResult(
        is_valid=is_valid,
        status=STATUS_STRUCTURALLY_VALID if is_valid else STATUS_FAILED,
        startxref_offset=xref_offset,
        object_offsets=tuple(object_offsets),
        errors=tuple(errors),
    )


def reconstruct(
    analysis: RelationshipAnalysis,
    profiles: Sequence[FragmentProfile],
    fragment_bytes: Mapping[str, bytes],
    fragments: Sequence[Fragment] | None = None,
) -> ReconstructionResult:
    """Reconstruct original bytes from candidate relationships and validate structure.

    Inputs are strictly internal engine data structures. No ground truth or manifest
    data is consulted.
    """
    chain, edges_used, walk_warnings = walk_candidate_chain(
        analysis.relationships, profiles
    )

    if fragments is not None:
        fragments_by_id = {f.fragment_id: f for f in fragments}
        for fid in chain:
            frag = fragments_by_id.get(fid)
            if frag is not None and fid in fragment_bytes:
                block = fragment_bytes[fid]
                if sha256_bytes(block) != frag.bytes_sha256:
                    raise ValueError(
                        f"content digest mismatch for fragment {fid}: expected "
                        f"{frag.bytes_sha256}, got {sha256_bytes(block)}"
                    )
                if len(block) != frag.size_bytes:
                    raise ValueError(
                        f"content size mismatch for fragment {fid}: expected "
                        f"{frag.size_bytes}, got {len(block)}"
                    )

    # Honest byte assembly: never fabricate, pad, or synthesize
    raw_bytes = b"".join(fragment_bytes.get(fid, b"") for fid in chain)

    all_warnings = list(walk_warnings)
    unplaced_ids = tuple(
        sorted(p.fragment_id for p in profiles if p.fragment_id not in chain)
    )

    by_id = {p.fragment_id: p for p in profiles}
    chain_complete = (
        len(chain) == len(profiles)
        and not unplaced_ids
        and not analysis.unresolved
        and bool(chain)
        and by_id[chain[0]].kind == KIND_HEADER
        and by_id[chain[-1]].kind == KIND_EOF
    )

    if not chain_complete:
        val = StructureValidationResult(
            is_valid=False,
            status=STATUS_INCOMPLETE,
            errors=tuple(all_warnings) or ("reconstruction is incomplete",),
        )
        return ReconstructionResult(
            raw_bytes=raw_bytes,
            fragment_order=chain,
            relationships_used=edges_used,
            validation=val,
            status=STATUS_INCOMPLETE,
            warnings=tuple(all_warnings),
            unresolved=analysis.unresolved,
            unplaced_fragment_ids=unplaced_ids,
        )

    # Run structural self-validation on complete byte sequence
    val = validate_pdf_structure(raw_bytes)
    return ReconstructionResult(
        raw_bytes=raw_bytes,
        fragment_order=chain,
        relationships_used=edges_used,
        validation=val,
        status=val.status,
        warnings=tuple(all_warnings),
        unresolved=analysis.unresolved,
        unplaced_fragment_ids=unplaced_ids,
    )
