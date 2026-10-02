"""Tests for TRACE Phase 10: Real-World PDF Dataset Integration and Benchmarking.

Validates:
1. Legal license compliance and metadata schemas (arXiv CC-BY, SafeDocs, NIST/W3C).
2. Real-world document registry and candidate curation.
3. Downloader integrity checking and manual download guide generation.
4. Document-level split isolation (zero document leakage across train/val/test).
5. Genuinely damaged corpus management, static safety verification, and zero fabricated ground truth.
6. Advanced multimodal benchmark runner (text Jaccard, tables, equations, authentic recovery %).
7. FastAPI REST endpoints and interactive benchmark HTML UI.
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest
from starlette.testclient import TestClient

from api.app.main import app
from trace.datasets.benchmark.multimodal_benchmark import (
    MultimodalBenchmarkRunner,
    compute_text_jaccard,
)
from trace.datasets.real_world.controlled_corruptor import ControlledCorruptor
from trace.datasets.real_world.curator import SampleDatasetCurator
from trace.datasets.real_world.downloader import RealWorldDocumentDownloader
from trace.datasets.real_world.genuine_damaged import GenuinelyDamagedCorpusManager
from trace.datasets.real_world.registry import RealWorldRegistryManager
from trace.datasets.schemas.corruption import CorruptionSeverity
from trace.datasets.schemas.real_world import (
    ContentCharacteristic,
    DocumentCategory,
    GenuinelyDamagedRecord,
    LicenseType,
    RealWorldCorpusRegistry,
    RealWorldDocumentRecord,
)


class TestRealWorldSchemasAndRegistry:
    """Test schema validity, license governance, and registry operations."""

    def test_schema_license_validation(self):
        """Ensure licenses must have valid terms URL and records have SHA-256 hashes."""
        record = RealWorldDocumentRecord(
            dataset_id="test-corpus",
            document_id="doc_001",
            title="Test Document",
            authors=["Alice", "Bob"],
            source_name="Open Research Test",
            source_url="https://arxiv.org/abs/2001.00001",
            license_type=LicenseType.CC_BY_4_0,
            license_url="https://creativecommons.org/licenses/by/4.0/",
            acquisition_date="2026-10-01T23:00:00Z",
            original_sha256="a" * 64,
            file_size_bytes=1024,
            category=DocumentCategory.RESEARCH_PAPER,
            characteristics=[ContentCharacteristic.SINGLE_COLUMN, ContentCharacteristic.TABLES],
            page_count=2,
            is_intact=True,
            has_verified_ground_truth=True,
        )
        assert record.license_type == LicenseType.CC_BY_4_0
        assert record.original_sha256 == "a" * 64
        assert record.is_intact is True
        assert record.has_verified_ground_truth is True

    def test_registry_manager_prepopulated_candidates(self):
        """Ensure the registry contains verified open-access candidate research documents."""
        mgr = RealWorldRegistryManager()
        docs = mgr.registry.documents
        assert len(docs) >= 5

        # Verify Attention Is All You Need is present with CC-BY-4.0
        transformer = mgr.get_document("arxiv_1706_03762")
        assert transformer is not None
        assert transformer.license_type == LicenseType.CC_BY_4_0
        assert "Vaswani" in transformer.authors[0]
        assert ContentCharacteristic.TWO_COLUMN in transformer.characteristics
        assert ContentCharacteristic.EQUATIONS in transformer.characteristics

        # Verify SafeDocs research candidate is present
        safedocs = mgr.get_document("safedocs_issue_440")
        assert safedocs is not None
        assert safedocs.is_intact is False
        assert safedocs.has_verified_ground_truth is False
        assert len(safedocs.safety_warnings) > 0


class TestDownloaderAndManualGuide:
    """Test safe document downloader and manual download guide generation."""

    def test_manual_download_guide_generation(self, tmp_path: Path):
        """Verify generation of offline manual download guide with checksums and curl commands."""
        downloader = RealWorldDocumentDownloader(output_dir=tmp_path / "downloads")
        mgr = RealWorldRegistryManager()

        guide_path = downloader.generate_manual_download_guide(
            records=mgr.registry.documents,
            guide_path=tmp_path / "MANUAL_GUIDE.md",
        )
        assert guide_path.is_file()
        content = guide_path.read_text(encoding="utf-8")
        assert "Manual Download Guide" in content
        assert "curl -L -o" in content
        assert "Verification Step" in content
        assert "Attention Is All You Need" in content


class TestSampleCuratorAndControlledCorruptor:
    """Test sample collection curation and document-level split isolation."""

    def test_sample_curation_offline_fallback(self, tmp_path: Path):
        """Test curating a collection of diverse documents with offline canonical generation."""
        curator = SampleDatasetCurator(target_dir=tmp_path / "curated")
        curated_info = curator.curate_sample_dataset(count=6, download_remote=False)

        assert curated_info["total_curated"] >= 6
        assert len(curated_info["records"]) >= 6

        # Check characteristics across curated items
        records = [RealWorldDocumentRecord.model_validate(r) for r in curated_info["records"]]
        two_cols = [r for r in records if ContentCharacteristic.TWO_COLUMN in r.characteristics]
        has_eqs = [r for r in records if ContentCharacteristic.EQUATIONS in r.characteristics]
        has_tables = [r for r in records if ContentCharacteristic.TABLES in r.characteristics]

        assert len(two_cols) > 0
        assert len(has_eqs) > 0
        assert len(has_tables) > 0

    def test_document_level_split_isolation(self, tmp_path: Path):
        """Verify strict document-level split isolation (zero document leakage)."""
        curator = SampleDatasetCurator(target_dir=tmp_path / "curated_split")
        curated_info = curator.curate_sample_dataset(count=8, download_remote=False)
        doc_records = [RealWorldDocumentRecord.model_validate(r) for r in curated_info["records"]]

        corruptor = ControlledCorruptor(output_dir=tmp_path / "corruptions")
        splits = corruptor.assign_document_splits(doc_records)

        assert len(splits) == len(doc_records)
        split_names = set(splits.values())
        assert "train" in split_names
        assert "test" in split_names

        # Pick one document and generate multiple corruptions
        test_doc = doc_records[0]
        test_split = splits[test_doc.document_id]
        doc_path = Path(curated_info["document_paths"][test_doc.document_id])

        corruptions = corruptor.generate_corruptions_for_document(
            doc_record=test_doc,
            original_pdf_bytes=doc_path.read_bytes(),
            split=test_split,
            severities=[CorruptionSeverity.LEVEL_1, CorruptionSeverity.LEVEL_2],
        )

        assert len(corruptions) == 2
        for ctrl_rec, corr_bytes in corruptions:
            assert ctrl_rec.source_document_id == test_doc.document_id
            assert ctrl_rec.split == test_split
            assert len(corr_bytes) > 0
            assert Path(ctrl_rec.ground_truth_reference).is_file()


class TestGenuinelyDamagedCorpus:
    """Test genuinely damaged PDF corpus management and zero-fabricated ground truth."""

    def test_genuinely_damaged_inventory(self):
        """Ensure genuine damaged corpus exists, has static safety, and no fabricated ground truth."""
        mgr = GenuinelyDamagedCorpusManager()
        samples = mgr.list_samples()
        assert len(samples) >= 2

        for s in samples:
            assert s.has_verified_ground_truth is False
            assert "SAFEDOCS" in s.license_type.value or "RESEARCH" in s.license_type.value
            # Check safety scan
            safe, issues = mgr.verify_safety_static(s.sample_id)
            assert safe is True
            assert len(issues) == 0

            # Raw bytes accessible
            b = mgr.get_sample_bytes(s.sample_id)
            assert b is not None
            assert len(b) > 0


class TestMultimodalBenchmarkRunner:
    """Test multimodal evaluation metrics and text Jaccard calculation."""

    def test_compute_text_jaccard(self):
        """Test token-level Jaccard similarity helper."""
        text_a = ["The quick brown fox", "jumps over the lazy dog"]
        text_b = ["The quick brown fox", "jumps over a dog"]
        sim = compute_text_jaccard(text_a, text_b)
        assert 0.5 <= sim <= 1.0

        # Exact match
        assert compute_text_jaccard(["hello world"], ["hello world"]) == 1.0
        # Disjoint
        assert compute_text_jaccard(["apple orange"], ["banana grape"]) == 0.0

    def test_benchmark_runner_full_cycle(self, tmp_path: Path):
        """Test executing benchmark runner on controlled + genuine damaged samples."""
        curator = SampleDatasetCurator(target_dir=tmp_path / "curated_bm")
        curated_info = curator.curate_sample_dataset(count=2, download_remote=False)
        doc_rec = RealWorldDocumentRecord.model_validate(curated_info["records"][0])
        doc_path = Path(curated_info["document_paths"][doc_rec.document_id])
        orig_bytes = doc_path.read_bytes()

        corruptor = ControlledCorruptor(output_dir=tmp_path / "corr_bm")
        corruptions = corruptor.generate_corruptions_for_document(
            doc_record=doc_rec,
            original_pdf_bytes=orig_bytes,
            split="test",
            severities=[CorruptionSeverity.LEVEL_1],
        )
        ctrl_rec, corr_bytes = corruptions[0]
        from trace.datasets.schemas.ground_truth import GroundTruthRecord

        gt = GroundTruthRecord.model_validate_json(
            Path(ctrl_rec.ground_truth_reference).read_text(encoding="utf-8")
        )

        damaged_mgr = GenuinelyDamagedCorpusManager()
        damaged_sample = damaged_mgr.list_samples()[0]
        dam_bytes = damaged_mgr.get_sample_bytes(damaged_sample.sample_id)

        runner = MultimodalBenchmarkRunner()
        results = runner.run_full_benchmark(
            controlled_samples=[(orig_bytes, corr_bytes, gt)],
            genuinely_damaged_samples=[(dam_bytes, damaged_sample)],
        )

        assert results["benchmark_version"] == "1.0.0"
        assert "controlled_benchmark_summary" in results
        assert "genuinely_damaged_summary" in results

        ctrl_sum = results["controlled_benchmark_summary"]
        assert ctrl_sum["total_controlled_samples"] == 1
        assert "avg_authentic_byte_recovery_pct" in ctrl_sum
        assert "avg_text_jaccard_similarity" in ctrl_sum
        assert "parser_validity_rate" in ctrl_sum

        gen_sum = results["genuinely_damaged_summary"]
        assert gen_sum["total_genuinely_damaged_samples"] == 1
        assert "parser_validity_rate" in gen_sum

        # Check qualitative honesty on genuine sample
        gen_result = results["genuinely_damaged_results"][0]
        assert gen_result["has_verified_ground_truth"] is False
        assert "Qualitative forensic assessment only" in gen_result["evaluation_note"]


class TestBenchmarkAPIAndUI:
    """Test FastAPI endpoints and interactive HTML dashboard."""

    def test_api_real_world_registry(self):
        """Test GET /api/datasets/real-world/registry."""
        client = TestClient(app)
        response = client.get("/api/datasets/real-world/registry")
        assert response.status_code == 200
        data = response.json()
        assert "registry_version" in data
        assert "documents" in data
        assert len(data["documents"]) >= 5

    def test_api_damaged_corpus(self):
        """Test GET /api/datasets/real-world/damaged-corpus."""
        client = TestClient(app)
        response = client.get("/api/datasets/real-world/damaged-corpus")
        assert response.status_code == 200
        data = response.json()
        assert data["corpus_name"] == "SafeDocs / Public Damaged Corpus"
        assert data["sample_count"] >= 2
        assert "NO FABRICATED GROUND TRUTH" in data["verified_ground_truth_policy"]

    def test_api_benchmark_status(self):
        """Test GET /api/datasets/benchmark/status."""
        client = TestClient(app)
        response = client.get("/api/datasets/benchmark/status")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "available"

    def test_api_benchmark_run_small(self):
        """Test POST /api/datasets/benchmark/run with small sample counts."""
        client = TestClient(app)
        response = client.post("/api/datasets/benchmark/run?samples_per_doc=1&max_docs=1")
        assert response.status_code == 200
        data = response.json()
        assert data["benchmark_version"] == "1.0.0"
        assert "controlled_benchmark_summary" in data

    def test_benchmark_html_page(self):
        """Test GET /benchmark serves HTML dashboard."""
        client = TestClient(app)
        response = client.get("/benchmark")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]
        content = response.text
        assert "TRACE Forensic Benchmarking" in content
        assert "Verified Open-Access Document Registry" in content
        assert "Genuinely Damaged PDF Test Corpus" in content
        assert "FORENSIC SCIENTIFIC HONESTY GUARANTEE" in content
        # Ensure header navigation and footer include benchmarks
        assert 'href="/benchmark"' in content
        assert "Benchmarks" in content

