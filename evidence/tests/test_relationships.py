"""Candidate relationship derivation.

Ground truth (manifest.json) is read only inside tests, and only to cross-check
that the derived edges match the fixture's authored order. The production module
is never given the manifest, and it must not open files.

The ascending object-number rule is a fixture-specific deterministic heuristic.
These tests assert it holds for THIS fixture. They do not assert that it holds
for arbitrary PDFs, and the module documents that limitation.
"""

import dataclasses
import inspect
import json
from pathlib import Path

import pytest

from trace_evidence import constants as c
from trace_evidence import relationships as rel
from trace_evidence.dna import FragmentProfile, profile_fragment
from trace_evidence.relationships import (
    RULE_HEADER_TO_FIRST_OBJECT,
    RULE_LAST_OBJECT_TO_XREF,
    RULE_OBJECT_ASCENDING_CHAIN,
    RULE_STARTXREF_TO_EOF,
    RULE_TRAILER_TO_STARTXREF,
    RULE_UNPLACED_KIND,
    RULE_XREF_TO_TRAILER,
    Relationship,
    derive_relationships,
)
from trace_evidence.scanning import scan_media

BLOCK = c.BLOCK_SIZE

EXPECTED_RULES = (
    RULE_HEADER_TO_FIRST_OBJECT,
    RULE_OBJECT_ASCENDING_CHAIN,
    RULE_OBJECT_ASCENDING_CHAIN,
    RULE_LAST_OBJECT_TO_XREF,
    RULE_XREF_TO_TRAILER,
    RULE_TRAILER_TO_STARTXREF,
    RULE_STARTXREF_TO_EOF,
)


def _blob_path(dataset_dir: Path, seed: int) -> Path:
    return dataset_dir / "evidence" / f"blob_{seed}.bin"


def _blocks(data: bytes) -> list[bytes]:
    return [data[start:start + BLOCK] for start in range(0, len(data), BLOCK)]


def _profile(fragment_id: str, kind: str, object_number: int | None = None) -> FragmentProfile:
    start = abs(hash(fragment_id)) % 10_000
    return FragmentProfile(
        fragment_id=fragment_id,
        byte_range=(start, start + BLOCK),
        kind=kind,
        object_number=object_number,
    )


@pytest.fixture()
def profiles(dataset_dir, default_seed):
    blob_path = _blob_path(dataset_dir, default_seed)
    scan = scan_media(blob_path)
    blocks = _blocks(blob_path.read_bytes())
    return tuple(
        profile_fragment(fragment, block)
        for fragment, block in zip(scan.fragments, blocks)
    )


@pytest.fixture()
def analysis(profiles):
    return derive_relationships(profiles)


def _chain_kinds(analysis, profiles) -> list[tuple]:
    """Walk the candidate edges and return (kind, object_number) in edge order.

    This is a test observation of the edge set. It is not a reconstruction.
    """
    by_id = {profile.fragment_id: profile for profile in profiles}
    outgoing = {edge.from_fragment_id: edge for edge in analysis.relationships}
    incoming = {edge.to_fragment_id for edge in analysis.relationships}
    starts = [edge.from_fragment_id for edge in analysis.relationships if edge.from_fragment_id not in incoming]
    assert len(starts) == 1

    order = []
    current = starts[0]
    while current in outgoing:
        profile = by_id[current]
        order.append((profile.kind, profile.object_number))
        current = outgoing[current].to_fragment_id
    last = by_id[current]
    order.append((last.kind, last.object_number))
    return order


def test_fixture_yields_one_candidate_chain(analysis, profiles):
    assert len(analysis.relationships) == 7
    assert analysis.complete is True
    assert analysis.unresolved == ()
    assert analysis.unplaced_fragment_ids == ()
    assert _chain_kinds(analysis, profiles) == [
        (c.KIND_HEADER, None),
        (c.KIND_OBJECT, 1),
        (c.KIND_OBJECT, 2),
        (c.KIND_OBJECT, 3),
        (c.KIND_XREF, None),
        (c.KIND_TRAILER, None),
        (c.KIND_STARTXREF, None),
        (c.KIND_EOF, None),
    ]
    assert tuple(sorted(edge.rule for edge in analysis.relationships)) == tuple(
        sorted(EXPECTED_RULES)
    )


def test_startxref_and_xref_are_not_collapsed(analysis, profiles):
    by_id = {profile.fragment_id: profile for profile in profiles}
    joined_kinds = {
        (by_id[edge.from_fragment_id].kind, by_id[edge.to_fragment_id].kind)
        for edge in analysis.relationships
    }

    assert (c.KIND_XREF, c.KIND_TRAILER) in joined_kinds
    assert (c.KIND_TRAILER, c.KIND_STARTXREF) in joined_kinds
    assert (c.KIND_STARTXREF, c.KIND_XREF) not in joined_kinds
    assert (c.KIND_XREF, c.KIND_STARTXREF) not in joined_kinds


def test_fixture_edges_match_authored_adjacency_and_only_in_the_test(dataset_dir, analysis, profiles):
    """Oracle check. The manifest is read here, never by the production module.

    Adjacency is true of THIS fixture because it was authored in ascending object
    order. That is not a claim about arbitrary PDFs.
    """
    manifest = json.loads((dataset_dir / "manifest.json").read_text(encoding="utf-8"))
    by_offset = {item["blob_offset"]: item for item in manifest["fragments"]}
    by_id = {profile.fragment_id: profile for profile in profiles}

    for edge in analysis.relationships:
        source = by_offset[by_id[edge.from_fragment_id].byte_range[0]]
        target = by_offset[by_id[edge.to_fragment_id].byte_range[0]]
        assert target["original_index"] - source["original_index"] == 1


def test_relationship_invariants():
    relationship = Relationship(
        from_fragment_id="FRG-0000000000000001-0-256",
        to_fragment_id="FRG-0000000000000002-256-512",
        rule=RULE_HEADER_TO_FIRST_OBJECT,
        evidence=("test evidence",),
    )
    assert relationship.label == c.LABEL_CANDIDATE
    assert relationship.byte_contiguity is False
    assert relationship.is_definitive is False
    assert relationship.key == (
        "FRG-0000000000000001-0-256",
        "FRG-0000000000000002-256-512",
        RULE_HEADER_TO_FIRST_OBJECT,
    )


def test_relationship_rejects_self_loop():
    with pytest.raises(ValueError, match="cannot be related to itself"):
        Relationship(
            from_fragment_id="FRG-0000000000000001-0-256",
            to_fragment_id="FRG-0000000000000001-0-256",
            rule=RULE_HEADER_TO_FIRST_OBJECT,
            evidence=("test evidence",),
        )


def test_relationship_rejects_non_candidate_label():
    for label in ("proven", "verified", "definitive", ""):
        with pytest.raises(ValueError, match="candidate-only"):
            Relationship(
                from_fragment_id="FRG-0000000000000001-0-256",
                to_fragment_id="FRG-0000000000000002-256-512",
                rule=RULE_HEADER_TO_FIRST_OBJECT,
                label=label,
                evidence=("test evidence",),
            )


def test_relationship_rejects_empty_evidence():
    with pytest.raises(ValueError, match="must carry the evidence"):
        Relationship(
            from_fragment_id="FRG-0000000000000001-0-256",
            to_fragment_id="FRG-0000000000000002-256-512",
            rule=RULE_HEADER_TO_FIRST_OBJECT,
            evidence=(),
        )


def test_unresolved_missing_header(profiles):
    without_header = tuple(p for p in profiles if p.kind != c.KIND_HEADER)
    result = derive_relationships(without_header)

    assert result.complete is False
    assert any(u.rule == RULE_HEADER_TO_FIRST_OBJECT for u in result.unresolved)


def test_unresolved_duplicate_headers(profiles):
    header = next(p for p in profiles if p.kind == c.KIND_HEADER)
    dup_header = _profile("FRG-dupheader00001-9000-9256", c.KIND_HEADER)
    with_dup = profiles + (dup_header,)
    result = derive_relationships(with_dup)

    assert result.complete is False
    unresolved_header = [u for u in result.unresolved if u.rule == RULE_HEADER_TO_FIRST_OBJECT]
    assert len(unresolved_header) == 1
    assert set(unresolved_header[0].candidate_fragment_ids) == {
        header.fragment_id,
        dup_header.fragment_id,
    }


def test_unresolved_missing_xref(profiles):
    without_xref = tuple(p for p in profiles if p.kind != c.KIND_XREF)
    result = derive_relationships(without_xref)

    assert result.complete is False
    unresolved_rules = [u.rule for u in result.unresolved]
    assert unresolved_rules.count(RULE_XREF_TO_TRAILER) == 1
    assert unresolved_rules.count(RULE_LAST_OBJECT_TO_XREF) == 1


def test_unresolved_duplicate_xrefs(profiles):
    xref = next(p for p in profiles if p.kind == c.KIND_XREF)
    dup_xref = _profile("FRG-dupxref0000001-9000-9256", c.KIND_XREF)
    with_dup = profiles + (dup_xref,)
    result = derive_relationships(with_dup)

    assert result.complete is False
    unresolved_xref = [u for u in result.unresolved if u.rule == RULE_XREF_TO_TRAILER]
    assert len(unresolved_xref) == 1
    assert set(unresolved_xref[0].candidate_fragment_ids) == {
        xref.fragment_id,
        dup_xref.fragment_id,
    }
    unresolved_last_obj = [u for u in result.unresolved if u.rule == RULE_LAST_OBJECT_TO_XREF]
    assert len(unresolved_last_obj) == 1
    assert set(unresolved_last_obj[0].candidate_fragment_ids) == {
        xref.fragment_id,
        dup_xref.fragment_id,
    }


def test_unresolved_missing_trailer(profiles):
    without_trailer = tuple(p for p in profiles if p.kind != c.KIND_TRAILER)
    result = derive_relationships(without_trailer)

    assert result.complete is False
    assert any(u.rule == RULE_TRAILER_TO_STARTXREF for u in result.unresolved)


def test_unresolved_duplicate_trailers(profiles):
    dup_trailer = _profile("FRG-duptrailer0001-9000-9256", c.KIND_TRAILER)
    with_dup = profiles + (dup_trailer,)
    result = derive_relationships(with_dup)

    assert result.complete is False
    assert any(u.rule == RULE_TRAILER_TO_STARTXREF for u in result.unresolved)


def test_unresolved_missing_startxref(profiles):
    without_startxref = tuple(p for p in profiles if p.kind != c.KIND_STARTXREF)
    result = derive_relationships(without_startxref)

    assert result.complete is False
    assert any(u.rule == RULE_STARTXREF_TO_EOF for u in result.unresolved)


def test_unresolved_missing_eof(profiles):
    without_eof = tuple(p for p in profiles if p.kind != c.KIND_EOF)
    result = derive_relationships(without_eof)

    assert result.complete is False
    assert any(u.rule == RULE_STARTXREF_TO_EOF for u in result.unresolved)


def test_unresolved_duplicate_object_numbers(profiles):
    non_objects = [p for p in profiles if p.kind != c.KIND_OBJECT]
    dup_objects = [
        _profile("FRG-obj1-1000-1256", c.KIND_OBJECT, object_number=1),
        _profile("FRG-obj2a-1256-1512", c.KIND_OBJECT, object_number=2),
        _profile("FRG-obj2b-1512-1768", c.KIND_OBJECT, object_number=2),
    ]
    result = derive_relationships(tuple(non_objects + dup_objects))

    assert result.complete is False
    assert any(u.rule == RULE_OBJECT_ASCENDING_CHAIN for u in result.unresolved)
    assert any(u.rule == RULE_HEADER_TO_FIRST_OBJECT for u in result.unresolved)
    assert any(u.rule == RULE_LAST_OBJECT_TO_XREF for u in result.unresolved)
    rule_counts = [u.rule for u in result.unresolved]
    assert rule_counts.count(RULE_HEADER_TO_FIRST_OBJECT) == 1
    assert rule_counts.count(RULE_LAST_OBJECT_TO_XREF) == 1
    assert rule_counts.count(RULE_OBJECT_ASCENDING_CHAIN) == 1


def test_unresolved_object_number_gap(profiles):
    non_objects = [p for p in profiles if p.kind != c.KIND_OBJECT]
    gap_objects = [
        _profile("FRG-obj1-1000-1256", c.KIND_OBJECT, object_number=1),
        _profile("FRG-obj3-1256-1512", c.KIND_OBJECT, object_number=3),
    ]
    result = derive_relationships(tuple(non_objects + gap_objects))

    assert result.complete is False
    chain_unresolved = [u for u in result.unresolved if u.rule == RULE_OBJECT_ASCENDING_CHAIN]
    assert len(chain_unresolved) == 1
    assert "missing=[2]" in chain_unresolved[0].reason

    # Header and xref edges still connect cleanly to 1 and 3
    rules = [e.rule for e in result.relationships]
    assert RULE_HEADER_TO_FIRST_OBJECT in rules
    assert RULE_LAST_OBJECT_TO_XREF in rules
    assert RULE_OBJECT_ASCENDING_CHAIN not in rules


def test_single_object_pdf(profiles):
    non_objects = [p for p in profiles if p.kind != c.KIND_OBJECT]
    single_obj = [_profile("FRG-obj1-1000-1256", c.KIND_OBJECT, object_number=1)]
    result = derive_relationships(tuple(non_objects + single_obj))

    assert result.complete is True
    assert result.unresolved == ()
    assert len(result.relationships) == 5
    rules = [e.rule for e in result.relationships]
    assert rules.count(RULE_HEADER_TO_FIRST_OBJECT) == 1
    assert rules.count(RULE_LAST_OBJECT_TO_XREF) == 1
    assert rules.count(RULE_OBJECT_ASCENDING_CHAIN) == 0


def test_zero_objects_pdf(profiles):
    non_objects = [p for p in profiles if p.kind != c.KIND_OBJECT]
    result = derive_relationships(tuple(non_objects))

    assert result.complete is False
    unresolved_rules = [u.rule for u in result.unresolved]
    assert RULE_HEADER_TO_FIRST_OBJECT in unresolved_rules
    assert RULE_LAST_OBJECT_TO_XREF in unresolved_rules


def test_unknown_kind_is_unplaced_and_reported(profiles):
    unknown = _profile("FRG-unknown0000001-9000-9256", c.KIND_UNKNOWN)
    result = derive_relationships(profiles + (unknown,))

    assert result.complete is False
    assert unknown.fragment_id in result.unplaced_fragment_ids
    assert any(
        u.rule == RULE_UNPLACED_KIND and unknown.fragment_id in u.candidate_fragment_ids
        for u in result.unresolved
    )


def test_derive_relationships_is_order_invariant(profiles):
    forward = derive_relationships(profiles)
    reversed_profiles = tuple(reversed(profiles))
    backward = derive_relationships(reversed_profiles)

    assert forward.relationships == backward.relationships
    assert forward.unresolved == backward.unresolved
    assert forward.unplaced_fragment_ids == backward.unplaced_fragment_ids


def test_relationships_has_no_filesystem_or_oracle_dependency():
    source = inspect.getsource(rel)

    assert "import json" not in source
    assert "pathlib" not in source
    assert "open(" not in source
    assert "from .dataset" not in source
    assert "manifest.json" not in source
    assert list(inspect.signature(rel.derive_relationships).parameters) == ["profiles"]
