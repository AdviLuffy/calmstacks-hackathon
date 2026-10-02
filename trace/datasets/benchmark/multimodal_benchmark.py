"""Advanced Multimodal & Real-World Benchmark Runner for TRACE Phase 10.

Evaluates the Phase 9 AdvancedMultimodalReconstructionEngine across:
1. Controlled corruptions of real-world intact PDFs (with verified ground truth).
2. Genuinely damaged PDFs from SafeDocs / public corpora (honest qualitative diagnostics without fabricated ground truth).
Reports granular metrics across parsing, structural repair, text, tables, figures, equations,
page layouts, authentic recovery %, and AI-inferred content.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from trace.datasets.benchmark.runner import RecoveryBenchmarkRunner
from trace.datasets.schemas.ground_truth import GroundTruthRecord
from trace.datasets.schemas.real_world import (
    ControlledCorruptionRecord,
    GenuinelyDamagedRecord,
    RealWorldDocumentRecord,
)
from trace.reconstruction.engine import AdvancedMultimodalReconstructionEngine

logger = logging.getLogger(__name__)

_LATEST_BENCHMARK_CACHE: Optional[Dict[str, Any]] = None


def compute_text_jaccard(text_a: Sequence[str], text_b: Sequence[str]) -> float:
    """Compute token-level Jaccard similarity between two sets of text strings."""
    tokens_a = set(" ".join(text_a).lower().split())
    tokens_b = set(" ".join(text_b).lower().split())
    if not tokens_a and not tokens_b:
        return 1.0
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a.intersection(tokens_b)
    union = tokens_a.union(tokens_b)
    return round(len(intersection) / len(union), 3)


class MultimodalBenchmarkRunner:
    """Reproducible benchmark runner for multimodal and real-world forensic reconstruction."""

    def __init__(
        self,
        engine: Optional[AdvancedMultimodalReconstructionEngine] = None,
        base_runner: Optional[RecoveryBenchmarkRunner] = None,
    ) -> None:
        self.engine = engine or AdvancedMultimodalReconstructionEngine()
        self.base_runner = base_runner or RecoveryBenchmarkRunner()

    def evaluate_controlled_sample(
        self,
        original_pdf_bytes: bytes,
        corrupted_pdf_bytes: bytes,
        ground_truth: GroundTruthRecord,
        doc_record: Optional[RealWorldDocumentRecord] = None,
    ) -> Dict[str, Any]:
        """Evaluate multimodal reconstruction on a controlled corruption with verified ground truth."""
        orig_size = len(original_pdf_bytes)
        corr_size = len(corrupted_pdf_bytes)

        # Run Phase 9 Multimodal Reconstruction
        recon_result = self.engine.reconstruct(
            evidence_bytes=corrupted_pdf_bytes,
            case_id=ground_truth.sample_id,
            document_title=doc_record.title if doc_record else "Benchmark Sample",
        )

        norm_doc = recon_result.normalized_document
        recon_report = recon_result.report

        # 1. Structural Repair & Validity
        parser_valid = False
        reconstructed_page_count = 0
        try:
            import pymupdf
            doc_parsed = pymupdf.open(stream=recon_result.reconstructed_pdf_bytes, filetype="pdf")
            parser_valid = len(doc_parsed) > 0
            reconstructed_page_count = len(doc_parsed)
            doc_parsed.close()
        except Exception:
            parser_valid = False

        # 2. Text Reconstruction Similarity
        orig_texts = ground_truth.original_text
        recovered_elements = norm_doc.get_all_elements_by_type("text_block")
        recovered_texts = [str(el.content) for el in recovered_elements]
        text_jaccard = compute_text_jaccard(orig_texts, recovered_texts)

        # 3. Table Reconstruction Metrics
        orig_tables_cnt = ground_truth.original_inventory.tables_count
        recovered_tables = norm_doc.get_all_elements_by_type("table")
        table_recovery_rate = (
            min(1.0, len(recovered_tables) / orig_tables_cnt) if orig_tables_cnt > 0 else 1.0
        )

        # 4. Equation Reconstruction Metrics
        orig_eqs_cnt = ground_truth.original_inventory.equations_count
        recovered_eqs = norm_doc.get_all_elements_by_type("equation")
        equation_recovery_rate = (
            min(1.0, len(recovered_eqs) / orig_eqs_cnt) if orig_eqs_cnt > 0 else 1.0
        )

        # 5. Image & Figure Metrics
        orig_imgs_cnt = ground_truth.original_inventory.images_count
        recovered_imgs = norm_doc.get_all_elements_by_type("image") + norm_doc.get_all_elements_by_type("figure")
        image_recovery_rate = (
            min(1.0, len(recovered_imgs) / orig_imgs_cnt) if orig_imgs_cnt > 0 else 1.0
        )

        # 6. Page Count Preservation
        orig_pages = ground_truth.original_inventory.pages_count
        page_preservation_ratio = (
            min(1.0, reconstructed_page_count / orig_pages) if orig_pages > 0 else 1.0
        )

        # 7. Forensic Provenance Honesty
        prov = recon_report.provenance
        auth_bytes = recon_report.authentic_bytes_recovered
        auth_byte_pct = (auth_bytes / orig_size * 100.0) if orig_size > 0 else 0.0

        return {
            "sample_id": ground_truth.sample_id,
            "has_verified_ground_truth": True,
            "original_size_bytes": orig_size,
            "corrupted_size_bytes": corr_size,
            "authentic_bytes_recovered": auth_bytes,
            "authentic_byte_recovery_pct": round(auth_byte_pct, 2),
            "parser_valid": parser_valid,
            "reconstructed_page_count": reconstructed_page_count,
            "original_page_count": orig_pages,
            "page_preservation_ratio": round(page_preservation_ratio, 3),
            "text_jaccard_similarity": text_jaccard,
            "original_tables_count": orig_tables_cnt,
            "recovered_tables_count": len(recovered_tables),
            "table_recovery_rate": round(table_recovery_rate, 3),
            "original_equations_count": orig_eqs_cnt,
            "recovered_equations_count": len(recovered_eqs),
            "equation_recovery_rate": round(equation_recovery_rate, 3),
            "original_images_count": orig_imgs_cnt,
            "recovered_images_count": len(recovered_imgs),
            "image_recovery_rate": round(image_recovery_rate, 3),
            "provenance_breakdown": prov.to_dict(),
            "ai_inferred_percentage": prov.ai_inferred_percentage,
            "unrecoverable_regions_count": recon_report.unrecoverable_regions_count,
        }

    def evaluate_genuinely_damaged_sample(
        self,
        damaged_pdf_bytes: bytes,
        record: GenuinelyDamagedRecord,
    ) -> Dict[str, Any]:
        """Evaluate recovery on genuinely damaged PDF without fabricating unverified ground truth."""
        size_bytes = len(damaged_pdf_bytes)

        recon_result = self.engine.reconstruct(
            evidence_bytes=damaged_pdf_bytes,
            case_id=record.sample_id,
            document_title=f"Damaged Corpus: {record.sample_id}",
        )

        norm_doc = recon_result.normalized_document
        recon_report = recon_result.report

        parser_valid = False
        reconstructed_page_count = 0
        try:
            import pymupdf
            doc_parsed = pymupdf.open(stream=recon_result.reconstructed_pdf_bytes, filetype="pdf")
            parser_valid = len(doc_parsed) > 0
            reconstructed_page_count = len(doc_parsed)
            doc_parsed.close()
        except Exception:
            parser_valid = False

        # CRITICAL FORENSIC RULE: Do not invent ground-truth recovery percentages
        return {
            "sample_id": record.sample_id,
            "has_verified_ground_truth": False,
            "source_name": record.source_name,
            "observed_damage_classes": record.observed_damage_classes,
            "input_size_bytes": size_bytes,
            "authentic_bytes_recovered": recon_report.authentic_bytes_recovered,
            "parser_valid": parser_valid,
            "reconstructed_page_count": reconstructed_page_count,
            "text_blocks_count": recon_report.text_blocks_count,
            "tables_count": recon_report.tables_count,
            "figures_count": recon_report.figures_count,
            "equations_count": recon_report.equations_count,
            "unrecoverable_regions_count": recon_report.unrecoverable_regions_count,
            "provenance_breakdown": recon_report.provenance.to_dict(),
            "evaluation_note": "Qualitative forensic assessment only — authentic ground truth unavailable.",
        }

    def run_full_benchmark(
        self,
        controlled_samples: List[Tuple[bytes, bytes, GroundTruthRecord]],
        genuinely_damaged_samples: List[Tuple[bytes, GenuinelyDamagedRecord]],
        registry_meta: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Run complete multimodal benchmark and compile comprehensive report."""
        controlled_results: List[Dict[str, Any]] = []
        for orig_b, corr_b, gt in controlled_samples:
            res = self.evaluate_controlled_sample(orig_b, corr_b, gt)
            controlled_results.append(res)

        genuine_results: List[Dict[str, Any]] = []
        for dam_b, rec in genuinely_damaged_samples:
            res = self.evaluate_genuinely_damaged_sample(dam_b, rec)
            genuine_results.append(res)

        # Aggregate controlled statistics
        n_ctrl = len(controlled_results)
        ctrl_summary = {}
        if n_ctrl > 0:
            ctrl_summary = {
                "total_controlled_samples": n_ctrl,
                "avg_authentic_byte_recovery_pct": round(sum(r["authentic_byte_recovery_pct"] for r in controlled_results) / n_ctrl, 2),
                "avg_text_jaccard_similarity": round(sum(r["text_jaccard_similarity"] for r in controlled_results) / n_ctrl, 3),
                "avg_table_recovery_rate": round(sum(r["table_recovery_rate"] for r in controlled_results) / n_ctrl, 3),
                "avg_equation_recovery_rate": round(sum(r["equation_recovery_rate"] for r in controlled_results) / n_ctrl, 3),
                "avg_image_recovery_rate": round(sum(r["image_recovery_rate"] for r in controlled_results) / n_ctrl, 3),
                "parser_validity_rate": round((sum(1 for r in controlled_results if r["parser_valid"]) / n_ctrl) * 100.0, 2),
                "avg_ai_inferred_pct": round(sum(r["ai_inferred_percentage"] for r in controlled_results) / n_ctrl, 2),
            }

        # Aggregate genuinely damaged statistics
        n_gen = len(genuine_results)
        gen_summary = {}
        if n_gen > 0:
            gen_summary = {
                "total_genuinely_damaged_samples": n_gen,
                "parser_validity_rate": round((sum(1 for r in genuine_results if r["parser_valid"]) / n_gen) * 100.0, 2),
                "total_text_blocks_salvaged": sum(r["text_blocks_count"] for r in genuine_results),
                "total_tables_salvaged": sum(r["tables_count"] for r in genuine_results),
                "total_equations_salvaged": sum(r["equations_count"] for r in genuine_results),
            }

        return {
            "benchmark_version": "1.0.0",
            "controlled_benchmark_summary": ctrl_summary,
            "genuinely_damaged_summary": gen_summary,
            "controlled_results": controlled_results,
            "genuinely_damaged_results": genuine_results,
            "registry_metadata": registry_meta or {},
        }

    def run_benchmark(
        self,
        samples_per_doc: int = 2,
        max_docs: int = 5,
        save_results: bool = True,
        results_path: Optional[Union[str, Path]] = None,
    ) -> Dict[str, Any]:
        """Convenience method that curates docs, corrupts them, runs benchmark, and saves results."""
        from trace.datasets.real_world.curator import SampleDatasetCurator
        from trace.datasets.real_world.controlled_corruptor import ControlledCorruptor
        from trace.datasets.real_world.genuine_damaged import GenuinelyDamagedCorpusManager
        from trace.datasets.schemas.corruption import CorruptionSeverity

        curator = SampleDatasetCurator()
        curated_info = curator.curate_sample_dataset(count=max_docs)
        doc_paths = curated_info.get("document_paths", {})
        doc_records = [
            RealWorldDocumentRecord.model_validate(r)
            for r in curated_info.get("records", [])
        ][:max_docs]

        corruptor = ControlledCorruptor()
        splits = corruptor.assign_document_splits(doc_records)

        controlled_samples: List[Tuple[bytes, bytes, GroundTruthRecord]] = []
        severities = [
            CorruptionSeverity.LEVEL_1,
            CorruptionSeverity.LEVEL_2,
            CorruptionSeverity.LEVEL_3,
        ][:samples_per_doc]

        for doc in doc_records:
            doc_path_str = doc_paths.get(doc.document_id)
            if not doc_path_str:
                continue
            p = Path(doc_path_str)
            if not p.is_file():
                continue
            orig_bytes = p.read_bytes()
            split = splits.get(doc.document_id, "test")
            corruptions = corruptor.generate_corruptions_for_document(
                doc_record=doc,
                original_pdf_bytes=orig_bytes,
                split=split,
                severities=severities,
            )
            for ctrl_rec, corr_bytes in corruptions:
                gt_path = Path(ctrl_rec.ground_truth_reference)
                if gt_path.is_file():
                    gt = GroundTruthRecord.model_validate_json(gt_path.read_text(encoding="utf-8"))
                    controlled_samples.append((orig_bytes, corr_bytes, gt))

        # Genuine damaged samples
        damaged_mgr = GenuinelyDamagedCorpusManager()
        damaged_samples: List[Tuple[bytes, GenuinelyDamagedRecord]] = []
        for d_rec in damaged_mgr.list_samples():
            d_bytes = damaged_mgr.get_sample_bytes(d_rec.sample_id)
            if d_bytes:
                damaged_samples.append((d_bytes, d_rec))

        results = self.run_full_benchmark(
            controlled_samples=controlled_samples,
            genuinely_damaged_samples=damaged_samples,
            registry_meta={
                "total_registry_docs": len(curator.registry_mgr.registry.documents),
                "evaluated_intact_docs": len(doc_records),
                "samples_per_doc": samples_per_doc,
            },
        )

        global _LATEST_BENCHMARK_CACHE
        _LATEST_BENCHMARK_CACHE = results

        if save_results:
            try:
                out_file = (
                    Path(results_path)
                    if results_path
                    else Path("evidence/datasets/benchmark/multimodal_latest.json")
                )
                out_file.parent.mkdir(parents=True, exist_ok=True)
                out_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
            except OSError:
                try:
                    tmp_out = Path("/tmp/trace_benchmark/multimodal_latest.json")
                    tmp_out.parent.mkdir(parents=True, exist_ok=True)
                    tmp_out.write_text(json.dumps(results, indent=2), encoding="utf-8")
                except Exception:
                    pass

        return results

    @staticmethod
    def load_latest_results(path: Optional[Union[str, Path]] = None) -> Optional[Dict[str, Any]]:
        """Load latest cached multimodal benchmark results from memory or disk if available."""
        global _LATEST_BENCHMARK_CACHE
        if _LATEST_BENCHMARK_CACHE is not None:
            return _LATEST_BENCHMARK_CACHE

        for candidate in [
            Path(path) if path else None,
            Path("evidence/datasets/benchmark/multimodal_latest.json"),
            Path("/tmp/trace_benchmark/multimodal_latest.json"),
        ]:
            if candidate and candidate.is_file():
                try:
                    data = json.loads(candidate.read_text(encoding="utf-8"))
                    _LATEST_BENCHMARK_CACHE = data
                    return data
                except Exception:
                    pass
        return None


