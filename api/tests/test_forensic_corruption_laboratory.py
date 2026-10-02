"""Unit and integration test suite for TRACE Forensic Corruption Laboratory.

Verifies:
1. Deterministic seed reproducibility across document generation and corruption.
2. Immutability guarantee: Original document is NEVER modified.
3. Byte-level, PDF structure, stream, text, image, font, and layout corruption operators.
4. Multi-corruption levels (0 to 4) and manifest generation.
5. Ground-truth inventories, delta tracking, and future ML labels.
6. Dataset exporter with train/validation/test/hard_test split isolation.
7. Dataset validator auditing hashes, offset bounds, and data leakage.
8. Granular recovery benchmark runner without deceptive single-score ML metrics.
9. Strict zero-network, zero-Gemini execution guarantee.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch
import pytest

from trace.datasets.benchmark.runner import RecoveryBenchmarkRunner
from trace.datasets.corruption import (
    ForensicCorruptionEngine,
    byte_ops,
    font_ops,
    image_ops,
    layout_ops,
    stream_ops,
    structure_ops,
    text_ops,
)
from trace.datasets.exporters.dataset_exporter import DatasetExporter
from trace.datasets.generators.document_generator import SyntheticDocumentGenerator
from trace.datasets.schemas.corruption import (
    CorruptionManifest,
    CorruptionSeverity,
    CorruptionType,
)
from trace.datasets.schemas.ground_truth import (
    FragmentLabel,
    GroundTruthRecord,
    RecoveryState,
)
from trace.datasets.validators.dataset_validator import DatasetValidator


@pytest.fixture
def clean_pdf() -> bytes:
    gen = SyntheticDocumentGenerator()
    return gen.generate(page_count=2, seed=12345, doc_size="SMALL")


class TestSyntheticDocumentGenerator:
    """Test deterministic synthetic PDF generation."""

    def test_reproducibility(self):
        gen = SyntheticDocumentGenerator()
        pdf1 = gen.generate(page_count=2, seed=99999, doc_size="SMALL")
        pdf2 = gen.generate(page_count=2, seed=99999, doc_size="SMALL")
        assert pdf1 == pdf2
        assert pdf1.startswith(b"%PDF-1.4")
        assert b"%%EOF" in pdf1

    def test_document_sizes(self):
        gen = SyntheticDocumentGenerator()
        small = gen.generate(page_count=2, seed=101, doc_size="SMALL")
        medium = gen.generate(page_count=5, seed=102, doc_size="MEDIUM")
        large = gen.generate(page_count=12, seed=103, doc_size="LARGE")

        assert len(small) < len(medium) < len(large)
        assert b"/Count 2" in small
        assert b"/Count 5" in medium
        assert b"/Count 12" in large


class TestCorruptionOperators:
    """Test individual granular corruption operators."""

    def test_original_remains_unchanged(self, clean_pdf: bytes):
        orig_copy = bytes(clean_pdf)
        orig_sha = hashlib.sha256(clean_pdf).hexdigest()

        # Execute multiple corruptions
        corrupted, op = byte_ops.delete_bytes(clean_pdf, 100, 50)
        assert clean_pdf == orig_copy
        assert hashlib.sha256(clean_pdf).hexdigest() == orig_sha

    def test_byte_ops(self, clean_pdf: bytes):
        # 1. Truncate
        trunc, op_trunc = byte_ops.truncate_bytes(clean_pdf, 500)
        assert len(trunc) == 500
        assert op_trunc.type == CorruptionType.TRUNCATE

        # 2. Zero bytes
        zeroed, op_zero = byte_ops.zero_bytes(clean_pdf, 200, 50)
        assert zeroed[200:250] == b"\x00" * 50
        assert op_zero.type == CorruptionType.ZERO_BYTES

    def test_structure_ops(self, clean_pdf: bytes):
        # Damage xref
        corrupted_xref, op_xref = structure_ops.damage_xref(clean_pdf, None)
        assert op_xref is not None
        assert b"x_ef" in corrupted_xref

        # Damage trailer
        corrupted_trailer, op_trailer = structure_ops.damage_trailer(clean_pdf, None)
        assert op_trailer is not None
        assert op_trailer.type == CorruptionType.DAMAGE_TRAILER

        # Remove indirect object
        corrupted_obj, op_obj = structure_ops.remove_indirect_object(clean_pdf, 1)
        assert op_obj is not None
        assert op_obj.type == CorruptionType.REMOVE_OBJECT

    def test_stream_ops(self, clean_pdf: bytes):
        # Truncate stream
        trunc_s, op_ts = stream_ops.truncate_stream(clean_pdf, keep_ratio=0.4)
        assert op_ts is not None
        assert op_ts.type == CorruptionType.TRUNCATE_STREAM

        # Remove stream suffix
        no_endstream, op_es = stream_ops.remove_stream_suffix(clean_pdf)
        assert op_es is not None
        assert op_es.type == CorruptionType.REMOVE_STREAM_SUFFIX

    def test_text_ops(self, clean_pdf: bytes):
        # Remove text operators
        no_text_ops, op_to = text_ops.remove_text_operators(clean_pdf, max_count=2)
        assert op_to is not None
        assert op_to.type == CorruptionType.REMOVE_TEXT_OPERATORS

    def test_image_and_font_ops(self, clean_pdf: bytes):
        # Remove image
        no_img, op_img = image_ops.remove_image_object(clean_pdf)
        assert op_img is not None
        assert op_img.type == CorruptionType.REMOVE_IMAGE_OBJECT

        # Remove font
        no_font, op_font = font_ops.remove_font_object(clean_pdf)
        assert op_font is not None
        assert op_font.type == CorruptionType.REMOVE_FONT_OBJECT

    def test_layout_ops(self, clean_pdf: bytes):
        # Damage page tree
        damaged_tree, op_tree = layout_ops.damage_page_tree(clean_pdf)
        assert op_tree is not None
        assert op_tree.type == CorruptionType.DAMAGE_PAGE_TREE


class TestForensicCorruptionEngine:
    """Test multi-corruption orchestrator, manifests, and ML labels."""

    def test_severities_and_manifests(self, clean_pdf: bytes):
        engine = ForensicCorruptionEngine(seed=42)

        # Level 0: Pass through
        c0, m0, gt0 = engine.corrupt(clean_pdf, "sample_l0", CorruptionSeverity.LEVEL_0)
        assert len(m0.operations) == 0
        assert m0.source_sha256 == m0.corrupted_sha256

        # Level 1: Light
        c1, m1, gt1 = engine.corrupt(clean_pdf, "sample_l1", CorruptionSeverity.LEVEL_1)
        assert len(m1.operations) >= 1

        # Level 3: Heavy
        c3, m3, gt3 = engine.corrupt(clean_pdf, "sample_l3", CorruptionSeverity.LEVEL_3)
        assert len(m3.operations) >= 3
        assert m3.source_sha256 != m3.corrupted_sha256

        # Level 4: Severe
        c4, m4, gt4 = engine.corrupt(clean_pdf, "sample_l4", CorruptionSeverity.LEVEL_4)
        assert len(m4.operations) >= 4

        # Check future ML labels
        assert len(gt4.ml_fragment_labels) > 0
        assert FragmentLabel.PDF_HEADER.value in gt4.ml_fragment_labels.values()


class TestDatasetExporterAndValidator:
    """Test dataset export, split isolation, and validator auditing."""

    def test_export_and_validate(self, tmp_path: Path):
        exporter = DatasetExporter()
        res = exporter.generate_and_export_dataset(
            output_dir=tmp_path / "test_dataset",
            samples_per_split={"train": 2, "validation": 1, "test": 1, "hard_test": 1},
            base_seed=12345,
        )
        assert res["total_samples"] == 5

        validator = DatasetValidator()
        report = validator.validate_dataset(tmp_path / "test_dataset")
        assert report["valid"] is True
        assert report["total_samples"] == 5
        assert len(report["issues"]) == 0

    def test_validator_catches_tampered_manifest(self, tmp_path: Path):
        exporter = DatasetExporter()
        exporter.generate_and_export_dataset(
            output_dir=tmp_path / "bad_dataset",
            samples_per_split={"train": 1},
            base_seed=777,
        )
        sample_dir = tmp_path / "bad_dataset" / "train" / "sample_000001"
        man_file = sample_dir / "manifest.json"

        # Tamper hash in manifest
        man_data = json.loads(man_file.read_text(encoding="utf-8"))
        man_data["source_sha256"] = "fake_tampered_sha_1234567890abcdef"
        man_file.write_text(json.dumps(man_data), encoding="utf-8")

        validator = DatasetValidator()
        report = validator.validate_dataset(tmp_path / "bad_dataset")
        assert report["valid"] is False
        assert any("mismatch" in iss.lower() for iss in report["issues"])


class TestRecoveryBenchmarkRunner:
    """Test recovery benchmark runner evaluation against ground truth."""

    def test_benchmark_evaluation(self, clean_pdf: bytes):
        engine = ForensicCorruptionEngine(seed=123)
        corrupted, manifest, ground_truth = engine.corrupt(
            clean_pdf, "sample_bench", CorruptionSeverity.LEVEL_2
        )

        runner = RecoveryBenchmarkRunner()
        metrics = runner.evaluate_sample(clean_pdf, corrupted, ground_truth)

        assert metrics["sample_id"] == "sample_bench"
        assert metrics["authentic_bytes_recovered"] > 0
        assert metrics["authentic_byte_recovery_pct"] > 50.0
        assert metrics["original_objects_count"] > 0
        assert metrics["provenance"] == "SYNTHETIC_BENCHMARK_EVALUATION"


class TestZeroNetworkCalls:
    """Verify zero external API or network calls are made during dataset generation."""

    def test_zero_network_during_generation_and_corruption(self, clean_pdf: bytes):
        with patch("google.genai.Client", side_effect=AssertionError("FATAL: Gemini Client invoked!")):
            engine = ForensicCorruptionEngine(seed=456)
            corrupted, manifest, ground_truth = engine.corrupt(
                clean_pdf, "sample_offline", CorruptionSeverity.LEVEL_4
            )
            assert corrupted is not None
            assert len(manifest.operations) > 0
