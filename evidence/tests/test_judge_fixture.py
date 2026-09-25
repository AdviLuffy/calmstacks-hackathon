"""Automated regression tests for TRACE Judge-Ready Fixtures and P1 Recovery States.

Verifies:
- Scenario A: Complete shuffled reconstruction (byte-for-byte equality, 100% coverage, COMPLETE AND VERIFIED).
- Scenario B: Missing-fragment partial reconstruction (identifies missing fragments, PARTIAL, <100% coverage).
- Scenario C: Corrupted-fragment detection (detects byte/structural mismatch, CORRUPTED, refuses verification).
- Edge cases: Empty input, duplicate fragments, overlapping fragments, fragment tampering.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from trace_evidence import constants as c
from trace_evidence.judge_fixture import build_judge_pdf, write_judge_dataset
from trace_evidence.models import Fragment, make_fragment_id, validate_fragment_collection
from trace_evidence.pipeline import run_pipeline
from trace_evidence.reconstruction import (
    FragmentCorruptionError,
    reconstruct,
)
from trace_evidence.scanning import scan_media

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASET_DIR = REPO_ROOT / "evidence" / "datasets"
GT_PDF_PATH = DATASET_DIR / "groundtruth" / "judge_groundtruth.pdf"
BLOB_A_PATH = DATASET_DIR / "evidence" / "judge_complete_shuffled.bin"
BLOB_B_PATH = DATASET_DIR / "evidence" / "judge_missing_fragment.bin"
BLOB_C_PATH = DATASET_DIR / "evidence" / "judge_corrupted_fragment.bin"
MANIFEST_PATH = DATASET_DIR / "manifest_judge_fixture.json"


@pytest.fixture(scope="module")
def ensure_judge_dataset():
    """Ensure judge dataset files exist before tests run."""
    if not (GT_PDF_PATH.is_file() and BLOB_A_PATH.is_file() and BLOB_B_PATH.is_file() and BLOB_C_PATH.is_file()):
        write_judge_dataset(DATASET_DIR)
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def test_scenario_a_complete_shuffled_reconstruction(ensure_judge_dataset):
    """Scenario A: All 10 shuffled fragments reconstruct byte-for-byte matching ground truth."""
    manifest = ensure_judge_dataset
    gt_bytes = GT_PDF_PATH.read_bytes()

    result = run_pipeline(BLOB_A_PATH, original_bytes=gt_bytes)

    # 1. Byte-for-byte exact equality
    assert result.reconstruction.raw_bytes == gt_bytes
    assert len(result.reconstruction.raw_bytes) == manifest["ground_truth"]["size_bytes"]
    assert result.integrity_report.reconstructed_sha256 == manifest["ground_truth"]["sha256"]

    # 2. Complete placement
    assert len(result.reconstruction.fragment_order) == 10
    assert len(result.reconstruction.unplaced_fragment_ids) == 0
    assert len(result.reconstruction.unresolved) == 0

    # 3. Truthful verification status
    assert result.is_complete is True
    assert result.reconstruction.complete is True
    assert result.integrity_report.is_verified is True
    assert result.integrity_report.byte_match is True
    assert result.integrity_report.status == c.STATUS_VERIFIED
    assert result.recovery_state == c.RECOVERY_COMPLETE_VERIFIED


def test_scenario_b_missing_fragment_partial_reconstruction(ensure_judge_dataset):
    """Scenario B: Missing fragments yield authentic partial artifact without claiming 100% coverage."""
    gt_bytes = GT_PDF_PATH.read_bytes()

    result = run_pipeline(BLOB_B_PATH, original_bytes=gt_bytes)

    # 1. Partial byte assembly is authentic prefix of ground truth
    raw_bytes = result.reconstruction.raw_bytes
    assert len(raw_bytes) == 8 * c.BLOCK_SIZE == 2048
    assert raw_bytes == gt_bytes[:2048]

    # 2. Identified missing structural elements
    missing = result.integrity_report.missing_elements
    assert any("startxref" in elem for elem in missing)
    assert any("EOF" in elem or "eof" in elem for elem in missing)

    # 3. Truthful non-complete, non-verified state
    assert result.is_complete is False
    assert result.reconstruction.complete is False
    assert result.integrity_report.is_verified is False
    assert result.integrity_report.byte_match is False
    assert result.integrity_report.status == c.STATUS_INCOMPLETE
    assert result.recovery_state == c.RECOVERY_PARTIAL

    # 4. Coverage calculation is strictly < 100%
    coverage_ratio = len(raw_bytes) / len(gt_bytes)
    assert coverage_ratio == 0.8
    assert f"{coverage_ratio * 100:.1f}%" == "80.0%"


def test_scenario_c_corrupted_fragment_detection(ensure_judge_dataset):
    """Scenario C: Deliberately altered bytes are detected, reported, and refused verification."""
    gt_bytes = GT_PDF_PATH.read_bytes()

    result = run_pipeline(BLOB_C_PATH, original_bytes=gt_bytes)

    # 1. Never accept altered artifact as verified
    assert result.is_complete is False
    assert result.integrity_report.is_verified is False
    assert result.integrity_report.byte_match is False
    assert result.integrity_report.status == c.STATUS_FAILED
    assert result.recovery_state == c.RECOVERY_CORRUPTED

    # 2. Corruption / mismatch is reported in warnings
    assert any("byte mismatch" in w for w in result.integrity_report.warnings)


def test_empty_evidence_handled_truthfully(tmp_path):
    """Empty evidence file produces UNRECOVERABLE status with zero bytes and no crash."""
    empty_file = tmp_path / "empty_evidence.bin"
    empty_file.write_bytes(b"")

    result = run_pipeline(empty_file)

    assert result.scan.media_size_bytes == 0
    assert len(result.scan.fragments) == 0
    assert result.reconstruction.raw_bytes == b""
    assert len(result.reconstruction.fragment_order) == 0
    assert result.reconstruction.complete is False
    assert result.integrity_report.is_verified is False
    assert result.recovery_state == c.RECOVERY_UNRECOVERABLE


def test_validate_fragment_collection_detects_anomalies():
    """validate_fragment_collection detects duplicate IDs, overlapping ranges, and empty sets."""
    # Empty
    empty_res = validate_fragment_collection(())
    assert len(empty_res) > 0 and "empty" in empty_res[0]

    # Valid set
    d1 = "1" * 64
    d2 = "2" * 64
    f1 = Fragment(fragment_id=make_fragment_id(d1, 0, 256), byte_range=(0, 256), bytes_sha256=d1)
    f2 = Fragment(fragment_id=make_fragment_id(d2, 256, 512), byte_range=(256, 512), bytes_sha256=d2)
    assert validate_fragment_collection((f1, f2)) == ()

    # Duplicate IDs
    anomalies_dup = validate_fragment_collection((f1, f1))
    assert any("duplicate fragment ID" in a for a in anomalies_dup)

    # Overlapping ranges
    d3 = "3" * 64
    f_overlap = Fragment(fragment_id=make_fragment_id(d3, 128, 384), byte_range=(128, 384), bytes_sha256=d3)
    anomalies_overlap = validate_fragment_collection((f1, f_overlap))
    assert any("overlapping fragment ranges" in a for a in anomalies_overlap)


def test_fragment_tamper_raises_corruption_error(ensure_judge_dataset):
    """Direct reconstruct detects tampered fragment bytes and raises FragmentCorruptionError."""
    scan = scan_media(BLOB_A_PATH)
    from trace_evidence.dna import profile_fragment
    from trace_evidence.relationships import derive_relationships

    fragment_bytes = {}
    with open(BLOB_A_PATH, "rb") as h:
        for f in scan.fragments:
            h.seek(f.start)
            fragment_bytes[f.fragment_id] = h.read(f.size_bytes)

    profiles = tuple(profile_fragment(f, fragment_bytes[f.fragment_id]) for f in scan.fragments)
    analysis = derive_relationships(profiles)

    # Tamper with first block
    first_fid = scan.fragments[0].fragment_id
    tampered_bytes = dict(fragment_bytes)
    tampered_bytes[first_fid] = b"TAMPERED" + b" " * 248

    with pytest.raises(FragmentCorruptionError, match="content digest mismatch"):
        reconstruct(
            analysis=analysis,
            profiles=profiles,
            fragment_bytes=tampered_bytes,
            fragments=scan.fragments,
        )
