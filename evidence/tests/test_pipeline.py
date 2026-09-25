"""End-to-end pipeline integration tests.

Ground truth (synthetic.pdf, manifest.json) is accessed only inside tests for
oracle comparison. The production pipeline module reads only the input evidence blob.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from trace_evidence import constants as c
from trace_evidence import pipeline as pipeline_module
from trace_evidence.pipeline import PipelineResult, run_pipeline
from trace_evidence.hashing import sha256_bytes

BLOCK = c.BLOCK_SIZE
REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / "shared" / "schemas"


def _blob_path(dataset_dir: Path, seed: int) -> Path:
    return dataset_dir / "evidence" / f"blob_{seed}.bin"


def _load_schema(filename: str) -> dict:
    return json.loads((SCHEMA_DIR / filename).read_text(encoding="utf-8"))


@pytest.fixture()
def pipeline_result(dataset_dir, default_seed):
    """Run the full pipeline against the synthetic fixture blob."""
    blob_path = _blob_path(dataset_dir, default_seed)
    return run_pipeline(media_path=blob_path)


@pytest.fixture()
def pipeline_result_with_output(dataset_dir, default_seed, tmp_path):
    """Run the full pipeline with artifact output."""
    blob_path = _blob_path(dataset_dir, default_seed)
    out_dir = tmp_path / "output"
    return run_pipeline(media_path=blob_path, out_dir=out_dir), out_dir


def test_pipeline_runs_to_completion_on_fixture(pipeline_result):
    assert pipeline_result.is_complete is True
    assert pipeline_result.reconstruction.status == c.STATUS_STRUCTURALLY_VALID
    assert pipeline_result.reconstruction.complete is True
    assert pipeline_result.integrity_report.status == c.STATUS_STRUCTURALLY_VALID
    assert len(pipeline_result.scan.fragments) == 8
    assert len(pipeline_result.profiles) == 8
    assert len(pipeline_result.analysis.relationships) == 7
    assert pipeline_result.analysis.unresolved == ()


def test_pipeline_status_is_structurally_valid_not_verified_without_oracle(pipeline_result):
    """Without original_bytes, status must remain structurally_valid, never verified."""
    assert pipeline_result.integrity_report.status == c.STATUS_STRUCTURALLY_VALID
    assert pipeline_result.integrity_report.is_verified is False
    assert pipeline_result.integrity_report.verified_against_original is False
    assert pipeline_result.integrity_report.byte_match is None


def test_pipeline_byte_exact_oracle_comparison(dataset_dir, default_seed):
    """Oracle check: ground truth is read only here inside the test."""
    blob_path = _blob_path(dataset_dir, default_seed)
    groundtruth_pdf = (dataset_dir / "groundtruth" / "synthetic.pdf").read_bytes()

    result = run_pipeline(
        media_path=blob_path,
        original_bytes=groundtruth_pdf,
    )

    assert result.integrity_report.status == c.STATUS_VERIFIED
    assert result.integrity_report.is_verified is True
    assert result.integrity_report.byte_match is True
    assert result.integrity_report.reconstructed_sha256 == sha256_bytes(groundtruth_pdf)
    assert result.integrity_report.reconstructed_sha256 == (
        "1ba5d499d667001095a9fefa4d57551538f742824bb2e2de1feae5e224d64caf"
    )


def test_pipeline_provenance_covers_all_reconstructed_bytes(pipeline_result):
    provenance = pipeline_result.integrity_report.provenance
    total = pipeline_result.integrity_report.reconstructed_size_bytes

    assert len(provenance) == 8
    assert provenance[0].output_range[0] == 0
    assert provenance[-1].output_range[1] == total

    for prev, curr in zip(provenance, provenance[1:]):
        assert prev.output_range[1] == curr.output_range[0], "provenance gap detected"

    for prov in provenance:
        assert prov.size_bytes == BLOCK
        frag_id = prov.fragment_id
        assert any(f.fragment_id == frag_id for f in pipeline_result.scan.fragments)


def test_pipeline_candidate_relationships_invariants(pipeline_result):
    for rel in pipeline_result.analysis.relationships:
        assert rel.label == c.LABEL_CANDIDATE
        assert rel.byte_contiguity is False
        assert rel.is_definitive is False

    for rel in pipeline_result.reconstruction.relationships_used:
        assert rel.label == c.LABEL_CANDIDATE
        assert rel.byte_contiguity is False


def test_pipeline_writes_evidence_bundle_and_validates_schema(
    pipeline_result_with_output,
):
    result, out_dir = pipeline_result_with_output
    bundle_path = Path(result.output_files["evidence_bundle"])

    assert bundle_path.exists()
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))

    fragment_schema = _load_schema("fragment.schema.json")
    bundle_schema = _load_schema("evidence_bundle.schema.json")
    registry = Registry().with_resources(
        [
            (fragment_schema["$id"], Resource.from_contents(fragment_schema, default_specification=DRAFT202012)),
            (bundle_schema["$id"], Resource.from_contents(bundle_schema, default_specification=DRAFT202012)),
        ]
    )
    validator = Draft202012Validator(bundle_schema, registry=registry)
    validator.validate(bundle)

    assert bundle["x-canonicalization"] == "trace-cj/1.0"
    assert set(bundle.keys()) == {"x-canonicalization", "engine", "media", "fragments", "warnings"}
    assert len(bundle["fragments"]) == 8


def test_pipeline_writes_reconstructed_pdf(pipeline_result_with_output):
    result, out_dir = pipeline_result_with_output
    recon_path = Path(result.output_files["reconstructed_pdf"])

    assert recon_path.exists()
    assert recon_path.stat().st_size == 2048
    assert sha256_bytes(recon_path.read_bytes()) == (
        "1ba5d499d667001095a9fefa4d57551538f742824bb2e2de1feae5e224d64caf"
    )


def test_pipeline_writes_integrity_report(pipeline_result_with_output):
    result, out_dir = pipeline_result_with_output
    report_path = Path(result.output_files["integrity_report"])

    assert report_path.exists()
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["status"] == c.STATUS_STRUCTURALLY_VALID
    assert report["verified_against_original"] is False
    assert len(report["provenance"]) == 8
    assert report["reconstructed_size_bytes"] == 2048
    # JSON must be deserializable round-trip
    assert json.loads(json.dumps(report)) == report


def test_pipeline_rejects_missing_input():
    with pytest.raises(FileNotFoundError):
        run_pipeline(media_path="/does/not/exist.bin")


def test_pipeline_reads_only_the_evidence_blob_not_oracle(pipeline_result_with_output):
    """Verify the pipeline output directory contains no groundtruth data."""
    result, out_dir = pipeline_result_with_output
    bundle = json.loads(Path(result.output_files["evidence_bundle"]).read_text(encoding="utf-8"))
    payload = json.dumps(bundle)

    for oracle_token in ("permutation", "original_index", "source_offset", "groundtruth",
                         "ground_truth", "object_number", "synthetic.pdf"):
        assert oracle_token not in payload, f"oracle token {oracle_token!r} found in bundle"


def test_pipeline_has_no_filesystem_or_oracle_dependency():
    source = inspect.getsource(pipeline_module)

    assert "manifest.json" not in source
    assert "synthetic.pdf" not in source
    assert "groundtruth" not in source
    assert "from .dataset" not in source
    assert list(inspect.signature(run_pipeline).parameters) == [
        "media_path", "run_id", "block_size", "out_dir", "original_bytes"
    ]
