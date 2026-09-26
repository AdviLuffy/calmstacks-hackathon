"""Reconstruction engine and PDF structural validation tests.

Ground truth (synthetic.pdf and manifest.json) is accessed only inside tests for
byte-exact comparison (oracle check). The production reconstruction module never
reads ground truth, files, or manifests.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from trace_evidence import constants as c
from trace_evidence import reconstruction as recon
from trace_evidence.dataset import build_synthetic_pdf
from trace_evidence.dna import FragmentProfile, profile_fragment
from trace_evidence.hashing import sha256_bytes
from trace_evidence.models import Fragment, make_fragment_id
from trace_evidence.relationships import (
    RULE_HEADER_TO_FIRST_OBJECT,
    RULE_OBJECT_ASCENDING_CHAIN,
    Relationship,
    derive_relationships,
)
from trace_evidence.scanning import scan_media

BLOCK = c.BLOCK_SIZE


def _blob_path(dataset_dir: Path, seed: int) -> Path:
    return dataset_dir / "evidence" / f"blob_{seed}.bin"


def _blocks(data: bytes) -> list[bytes]:
    return [data[start:start + BLOCK] for start in range(0, len(data), BLOCK)]


@pytest.fixture()
def scanned_evidence(dataset_dir, default_seed):
    blob_path = _blob_path(dataset_dir, default_seed)
    scan = scan_media(blob_path)
    raw_blocks = _blocks(blob_path.read_bytes())
    profiles = tuple(
        profile_fragment(fragment, block)
        for fragment, block in zip(scan.fragments, raw_blocks)
    )
    fragment_bytes = {
        fragment.fragment_id: block
        for fragment, block in zip(scan.fragments, raw_blocks)
    }
    analysis = derive_relationships(profiles)
    return scan, profiles, fragment_bytes, analysis


def test_reconstruction_happy_path_on_fixture(scanned_evidence):
    scan, profiles, fragment_bytes, analysis = scanned_evidence
    result = recon.reconstruct(
        analysis=analysis,
        profiles=profiles,
        fragment_bytes=fragment_bytes,
        fragments=scan.fragments,
    )

    assert result.status == c.STATUS_STRUCTURALLY_VALID
    assert result.validation.is_valid is True
    assert result.complete is True
    assert len(result.fragment_order) == 8
    assert len(result.relationships_used) == 7
    assert result.validation.startxref_offset == 1024
    assert result.validation.object_offsets == ((1, 256), (2, 512), (3, 768))


def test_reconstruction_byte_exact_oracle_comparison(dataset_dir, scanned_evidence):
    """Oracle check: ground truth is read strictly inside this test."""
    scan, profiles, fragment_bytes, analysis = scanned_evidence
    groundtruth_pdf = (dataset_dir / "groundtruth" / "synthetic.pdf").read_bytes()

    result = recon.reconstruct(
        analysis=analysis,
        profiles=profiles,
        fragment_bytes=fragment_bytes,
        fragments=scan.fragments,
    )

    assert result.raw_bytes == groundtruth_pdf
    assert sha256_bytes(result.raw_bytes) == "1ba5d499d667001095a9fefa4d57551538f742824bb2e2de1feae5e224d64caf"


def test_relationships_used_remain_candidate_only_and_non_contiguous(scanned_evidence):
    scan, profiles, fragment_bytes, analysis = scanned_evidence
    result = recon.reconstruct(
        analysis=analysis,
        profiles=profiles,
        fragment_bytes=fragment_bytes,
        fragments=scan.fragments,
    )

    assert len(result.relationships_used) == 7
    for rel in result.relationships_used:
        assert rel.label == c.LABEL_CANDIDATE
        assert rel.byte_contiguity is False
        assert rel.is_definitive is False


def test_missing_header_yields_incomplete(scanned_evidence):
    scan, profiles, fragment_bytes, analysis = scanned_evidence
    without_header = tuple(p for p in profiles if p.kind != c.KIND_HEADER)
    analysis_no_header = derive_relationships(without_header)

    result = recon.reconstruct(
        analysis=analysis_no_header,
        profiles=without_header,
        fragment_bytes=fragment_bytes,
    )

    assert result.status == c.STATUS_INCOMPLETE
    assert result.complete is False
    assert result.raw_bytes == b""
    assert any("no header" in w for w in result.warnings)


def test_duplicate_headers_yields_incomplete(scanned_evidence):
    scan, profiles, fragment_bytes, analysis = scanned_evidence
    header = next(p for p in profiles if p.kind == c.KIND_HEADER)
    dup_header = FragmentProfile(
        fragment_id="FRG-dupheader00001-9000-9256",
        byte_range=(9000, 9256),
        kind=c.KIND_HEADER,
    )
    with_dup = profiles + (dup_header,)
    analysis_dup = derive_relationships(with_dup)

    result = recon.reconstruct(
        analysis=analysis_dup,
        profiles=with_dup,
        fragment_bytes=dict(fragment_bytes, **{dup_header.fragment_id: b"%PDF-1.4\n".ljust(BLOCK, b" ")}),
    )

    assert result.status == c.STATUS_INCOMPLETE
    assert result.complete is False
    assert result.raw_bytes == b""
    assert any("multiple header" in w for w in result.warnings)


def test_branching_and_cycles_halt_without_infinite_loop():
    p_header = FragmentProfile("FRG-head-0-256", (0, 256), c.KIND_HEADER)
    p_obj1 = FragmentProfile("FRG-obj1-256-512", (256, 512), c.KIND_OBJECT, object_number=1)
    p_obj2 = FragmentProfile("FRG-obj2-512-768", (512, 768), c.KIND_OBJECT, object_number=2)

    # Branching: header relates to both obj1 and obj2
    rel_branch1 = Relationship(p_header.fragment_id, p_obj1.fragment_id, RULE_HEADER_TO_FIRST_OBJECT, evidence=("e1",))
    rel_branch2 = Relationship(p_header.fragment_id, p_obj2.fragment_id, RULE_HEADER_TO_FIRST_OBJECT, evidence=("e2",))
    chain, edges, warnings = recon.walk_candidate_chain(
        (rel_branch1, rel_branch2),
        (p_header, p_obj1, p_obj2),
    )
    assert chain == ()
    assert any("ambiguous branching" in w for w in warnings)

    # Cycle: header -> obj1 -> header
    rel_c1 = Relationship(p_header.fragment_id, p_obj1.fragment_id, RULE_HEADER_TO_FIRST_OBJECT, evidence=("e1",))
    rel_c2 = Relationship(p_obj1.fragment_id, p_header.fragment_id, RULE_OBJECT_ASCENDING_CHAIN, evidence=("e2",))
    chain, edges, warnings = recon.walk_candidate_chain(
        (rel_c1, rel_c2),
        (p_header, p_obj1),
    )
    assert any("cycle detected" in w for w in warnings)


def test_incomplete_chain_does_not_present_as_valid(scanned_evidence):
    scan, profiles, fragment_bytes, analysis = scanned_evidence
    # Artificially remove object 2 to break the chain
    sub_profiles = tuple(p for p in profiles if p.object_number != 2)
    sub_analysis = derive_relationships(sub_profiles)

    result = recon.reconstruct(
        analysis=sub_analysis,
        profiles=sub_profiles,
        fragment_bytes=fragment_bytes,
    )

    assert result.status == c.STATUS_INCOMPLETE
    assert result.validation.is_valid is False
    assert result.complete is False
    assert len(result.raw_bytes) < len(build_synthetic_pdf())


def test_structural_validator_detects_malformed_offsets():
    pdf = build_synthetic_pdf()

    # Valid check first
    valid_res = recon.validate_pdf_structure(pdf)
    assert valid_res.is_valid is True
    assert valid_res.status == c.STATUS_STRUCTURALLY_VALID

    # Missing header
    no_hdr = recon.validate_pdf_structure(b" " * 10 + pdf[10:])
    assert no_hdr.is_valid is False
    assert any("header" in e for e in no_hdr.errors)

    # Missing EOF
    no_eof = recon.validate_pdf_structure(pdf.replace(b"%%EOF", b"XXXXX"))
    assert no_eof.is_valid is False
    assert any("%%EOF" in e for e in no_eof.errors)

    # Out of bounds startxref
    bad_startxref = pdf.replace(b"startxref\n1024\n", b"startxref\n9999\n")
    bad_res = recon.validate_pdf_structure(bad_startxref)
    assert bad_res.is_valid is False
    assert any("out of bounds" in e for e in bad_res.errors)

    # Corrupted object offset in xref table (pointing to empty spaces instead of object)
    corrupted_xref = pdf.replace(b"0000000256 00000 n", b"0000000050 00000 n")
    corrupt_res = recon.validate_pdf_structure(corrupted_xref)
    assert corrupt_res.is_valid is False
    assert any("header not found at declared offset" in e for e in corrupt_res.errors)


def test_tamper_detection_in_fragment_bytes(scanned_evidence):
    scan, profiles, fragment_bytes, analysis = scanned_evidence
    tampered_bytes = dict(fragment_bytes)
    first_id = scan.fragments[0].fragment_id
    tampered_bytes[first_id] = b"X" * BLOCK

    with pytest.raises(ValueError, match="content digest mismatch"):
        recon.reconstruct(
            analysis=analysis,
            profiles=profiles,
            fragment_bytes=tampered_bytes,
            fragments=scan.fragments,
        )


def test_reconstruction_has_no_filesystem_or_oracle_dependency():
    source = inspect.getsource(recon)

    assert "import json" not in source
    assert "pathlib" not in source
    assert "open(" not in source
    assert "from .dataset" not in source
    assert "manifest.json" not in source
    assert list(inspect.signature(recon.reconstruct).parameters) == [
        "analysis",
        "profiles",
        "fragment_bytes",
        "fragments",
    ]


def test_scrambled_evidence_reconstruction_with_combined_tail():
    """Test reconstruction of structure-aligned scrambled evidence with combined xref/trailer/startxref/EOF tail block."""
    repo_datasets = Path(__file__).resolve().parents[1] / "datasets"
    scrambled_file = repo_datasets / "evidence" / "TRACE_Scrambled_Evidence.bin"
    gt_file = repo_datasets / "groundtruth" / "TRACE_Scramble_Test_GroundTruth.pdf"
    if not scrambled_file.is_file() or not gt_file.is_file():
        pytest.skip("Scrambled test pack not present")

    raw_scrambled = scrambled_file.read_bytes()
    gt_bytes = gt_file.read_bytes()
    expected_sha256 = sha256_bytes(gt_bytes)

    scan = scan_media(scrambled_file)
    blocks = [raw_scrambled[i:i + BLOCK] for i in range(0, len(raw_scrambled), BLOCK)]
    profiles = tuple(profile_fragment(f, b) for f, b in zip(scan.fragments, blocks))
    fragment_bytes = {f.fragment_id: b for f, b in zip(scan.fragments, blocks)}

    analysis = derive_relationships(profiles)
    assert analysis.complete is True
    assert analysis.unplaced_fragment_ids == ()
    assert analysis.unresolved == ()

    result = recon.reconstruct(
        analysis=analysis,
        profiles=profiles,
        fragment_bytes=fragment_bytes,
        fragments=scan.fragments,
    )

    assert result.complete is True
    assert result.status == recon.STATUS_STRUCTURALLY_VALID
    assert result.unplaced_fragment_ids == ()
    assert len(result.fragment_order) == 7
    assert result.validation.is_valid is True
    assert sha256_bytes(result.raw_bytes) == expected_sha256
    assert result.raw_bytes == gt_bytes

