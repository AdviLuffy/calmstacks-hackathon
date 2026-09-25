"""Integrity and verification tests.

Independent comparison against ground truth occurs only in these tests. The production
integrity module is caller-controlled and contains no filesystem or oracle dependencies.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest

from trace_evidence import constants as c
from trace_evidence import integrity
from trace_evidence.dna import profile_fragment
from trace_evidence.hashing import sha256_bytes
from trace_evidence.models import Fragment, make_fragment_id
from trace_evidence.reconstruction import reconstruct
from trace_evidence.relationships import derive_relationships
from trace_evidence.scanning import scan_media

BLOCK = c.BLOCK_SIZE


def _blob_path(dataset_dir: Path, seed: int) -> Path:
    return dataset_dir / "evidence" / f"blob_{seed}.bin"


def _blocks(data: bytes) -> list[bytes]:
    return [data[start:start + BLOCK] for start in range(0, len(data), BLOCK)]


@pytest.fixture()
def reconstructed_fixture(dataset_dir, default_seed):
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
    result = reconstruct(
        analysis=analysis,
        profiles=profiles,
        fragment_bytes=fragment_bytes,
        fragments=scan.fragments,
    )
    return scan, profiles, result


def test_provenance_mapping_happy_path(reconstructed_fixture):
    scan, _, result = reconstructed_fixture
    provenance = integrity.build_provenance(
        result.fragment_order,
        scan.fragments,
        len(result.raw_bytes),
    )

    assert len(provenance) == 8
    assert provenance[0].output_range == (0, BLOCK)
    assert provenance[-1].output_range == (7 * BLOCK, 8 * BLOCK)

    for i, prov in enumerate(provenance):
        assert prov.output_range == (i * BLOCK, (i + 1) * BLOCK)
        assert prov.size_bytes == BLOCK
        assert prov.size_bytes == prov.output_range[1] - prov.output_range[0]
        assert prov.size_bytes == prov.source_range[1] - prov.source_range[0]

    for prev, curr in zip(provenance, provenance[1:]):
        assert prev.output_range[1] == curr.output_range[0]


def test_verify_integrity_with_original_promotes_to_verified(
    dataset_dir, reconstructed_fixture
):
    scan, _, result = reconstructed_fixture
    groundtruth_pdf = (dataset_dir / "groundtruth" / "synthetic.pdf").read_bytes()

    report = integrity.verify_integrity(
        reconstruction=result,
        fragments=scan.fragments,
        original_bytes=groundtruth_pdf,
    )

    assert report.status == c.STATUS_VERIFIED
    assert report.is_verified is True
    assert report.byte_match is True
    assert report.verified_against_original is True
    assert report.original_sha256 == report.reconstructed_sha256
    assert report.original_sha256 == "1ba5d499d667001095a9fefa4d57551538f742824bb2e2de1feae5e224d64caf"


def test_verify_integrity_without_original_preserves_structurally_valid(
    reconstructed_fixture,
):
    scan, _, result = reconstructed_fixture

    report = integrity.verify_integrity(
        reconstruction=result,
        fragments=scan.fragments,
        original_bytes=None,
    )

    assert report.status == c.STATUS_STRUCTURALLY_VALID
    assert report.is_verified is False
    assert report.verified_against_original is False
    assert report.original_sha256 is None
    assert report.byte_match is None


def test_verify_integrity_with_mismatched_original_reports_failed(
    dataset_dir, reconstructed_fixture
):
    scan, _, result = reconstructed_fixture
    groundtruth_pdf = (dataset_dir / "groundtruth" / "synthetic.pdf").read_bytes()
    corrupted_pdf = groundtruth_pdf[:-50] + b"X" * 50

    report = integrity.verify_integrity(
        reconstruction=result,
        fragments=scan.fragments,
        original_bytes=corrupted_pdf,
    )

    assert report.status == c.STATUS_FAILED
    assert report.is_verified is False
    assert report.byte_match is False
    assert report.verified_against_original is True
    assert any("byte mismatch" in w for w in report.warnings)


def test_verify_integrity_never_promotes_incomplete_reconstruction(
    reconstructed_fixture,
):
    scan, profiles, _ = reconstructed_fixture
    # Build incomplete reconstruction missing fragment 2
    sub_profiles = tuple(p for p in profiles if p.object_number != 2)
    analysis = derive_relationships(sub_profiles)
    fragment_bytes = {
        f.fragment_id: b"A" * BLOCK for f in scan.fragments
    }
    incomplete_result = reconstruct(
        analysis=analysis,
        profiles=sub_profiles,
        fragment_bytes=fragment_bytes,
    )

    assert incomplete_result.status == c.STATUS_INCOMPLETE

    # Supply an original matching partial bytes exactly
    report = integrity.verify_integrity(
        reconstruction=incomplete_result,
        fragments=scan.fragments,
        original_bytes=incomplete_result.raw_bytes,
    )

    # Invariant: must NEVER be promoted to verified
    assert report.status == c.STATUS_INCOMPLETE
    assert report.is_verified is False


def test_provenance_validation_rejects_duplicate_fragments(reconstructed_fixture):
    scan, _, result = reconstructed_fixture
    dup_order = result.fragment_order[:1] + result.fragment_order
    with pytest.raises(ValueError, match="duplicate fragment ID"):
        integrity.build_provenance(dup_order, scan.fragments, 9 * BLOCK)


def test_provenance_validation_rejects_missing_fragment(reconstructed_fixture):
    scan, _, result = reconstructed_fixture
    with pytest.raises(ValueError, match="not found in fragments sequence"):
        integrity.build_provenance(
            ("FRG-nonexistent-0-256",),
            scan.fragments,
            BLOCK,
        )


def test_provenance_validation_rejects_size_mismatch(reconstructed_fixture):
    scan, _, result = reconstructed_fixture
    with pytest.raises(ValueError, match="does not match output size"):
        integrity.build_provenance(
            result.fragment_order,
            scan.fragments,
            len(result.raw_bytes) - 1,
        )


def test_byte_provenance_range_validation():
    digest = "a" * 64
    with pytest.raises(ValueError, match="invalid output_range"):
        integrity.ByteProvenance(
            output_range=(100, 50),
            fragment_id="FRG-1",
            source_range=(0, 50),
            bytes_sha256=digest,
            size_bytes=50,
        )

    with pytest.raises(ValueError, match="output_range span"):
        integrity.ByteProvenance(
            output_range=(0, 100),
            fragment_id="FRG-1",
            source_range=(0, 50),
            bytes_sha256=digest,
            size_bytes=50,
        )


def test_integrity_report_to_dict_serializable(
    dataset_dir, reconstructed_fixture
):
    scan, _, result = reconstructed_fixture
    groundtruth_pdf = (dataset_dir / "groundtruth" / "synthetic.pdf").read_bytes()

    report = integrity.verify_integrity(
        reconstruction=result,
        fragments=scan.fragments,
        original_bytes=groundtruth_pdf,
    )
    payload = report.to_dict()

    assert payload["status"] == c.STATUS_VERIFIED
    assert payload["verified_against_original"] is True
    assert payload["byte_match"] is True
    assert len(payload["provenance"]) == 8
    # Ensure JSON serializable
    assert json.loads(json.dumps(payload)) == payload


def test_integrity_has_no_filesystem_or_oracle_dependency():
    source = inspect.getsource(integrity)

    assert "import json" not in source
    assert "pathlib" not in source
    assert "open(" not in source
    assert "from .dataset" not in source
    assert "manifest.json" not in source
    assert list(inspect.signature(integrity.verify_integrity).parameters) == [
        "reconstruction",
        "fragments",
        "original_bytes",
    ]
