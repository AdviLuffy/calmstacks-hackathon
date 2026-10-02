"""Forensic Recovery Benchmark Runner for TRACE.

Compares Original Ground Truth vs Corrupted Evidence vs TRACE Recovery.
Reports unvarnished granular metrics across bytes, objects, streams, text, pages,
and structures without collapsing into deceptive single-score ML metrics.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from trace_evidence.pdf_recovery import GeneralizedPdfRecoveryEngine
from trace.datasets.schemas.ground_truth import GroundTruthRecord


class RecoveryBenchmarkRunner:
    """Benchmark evaluation runner executing deterministic recovery against ground-truth datasets."""

    def evaluate_sample(
        self,
        original_pdf: bytes,
        corrupted_pdf: bytes,
        ground_truth: GroundTruthRecord,
    ) -> Dict[str, Any]:
        """Evaluate TRACE deterministic recovery on a single corrupted sample."""
        orig_size = len(original_pdf)
        corr_size = len(corrupted_pdf)

        # Execute TRACE GeneralizedPdfRecoveryEngine
        engine = GeneralizedPdfRecoveryEngine(corrupted_pdf)
        recovered_bytes, synthesized_items, meta = engine.recover()
        telemetry = engine.telemetry

        # 1. Byte Metrics
        authentic_bytes_recovered = telemetry.authentic_bytes_identified if telemetry else 0
        authentic_byte_recovery_pct = (
            round((authentic_bytes_recovered / orig_size) * 100, 2) if orig_size > 0 else 0.0
        )

        # 2. Object Metrics
        orig_objs = set(ground_truth.original_inventory.object_numbers)
        recovered_obj_nums = set(
            o.object_number for o in (telemetry.recovered_objects if telemetry else [])
        )
        surviving_recovered_objs = orig_objs.intersection(recovered_obj_nums)
        object_recovery_pct = (
            round((len(surviving_recovered_objs) / len(orig_objs)) * 100, 2) if orig_objs else 100.0
        )

        # 3. Stream Metrics
        orig_streams = ground_truth.original_inventory.streams_count
        decompressed_streams = (
            telemetry.successfully_decompressed_streams if telemetry else 0
        )
        stream_decompression_pct = (
            round((decompressed_streams / orig_streams) * 100, 2) if orig_streams > 0 else 100.0
        )

        # 4. Text Metrics
        orig_text_count = len(ground_truth.original_text)
        surviving_strings = list(telemetry.surviving_text_strings) if telemetry else []
        text_recovery_pct = (
            round((len(surviving_strings) / orig_text_count) * 100, 2) if orig_text_count > 0 else 100.0
        )

        # 5. Page Metrics
        orig_pages = ground_truth.original_inventory.pages_count
        recovered_pages = telemetry.pages_discovered if telemetry else 0
        page_recovery_pct = (
            round((recovered_pages / orig_pages) * 100, 2) if orig_pages > 0 else 100.0
        )

        # 6. Syntax Validity Check
        parser_valid = False
        try:
            import pypdf
            import io
            reader = pypdf.PdfReader(io.BytesIO(recovered_bytes), strict=False)
            parser_valid = len(reader.pages) > 0
        except Exception:
            parser_valid = False

        return {
            "sample_id": ground_truth.sample_id,
            "seed": ground_truth.seed,
            "original_size_bytes": orig_size,
            "corrupted_size_bytes": corr_size,
            "authentic_bytes_recovered": authentic_bytes_recovered,
            "authentic_byte_recovery_pct": authentic_byte_recovery_pct,
            "original_objects_count": len(orig_objs),
            "recovered_objects_count": len(recovered_obj_nums),
            "surviving_original_objects_recovered": len(surviving_recovered_objs),
            "object_recovery_pct": object_recovery_pct,
            "original_streams_count": orig_streams,
            "decompressed_streams_count": decompressed_streams,
            "stream_decompression_pct": stream_decompression_pct,
            "original_text_strings_count": orig_text_count,
            "recovered_text_strings_count": len(surviving_strings),
            "text_recovery_pct": text_recovery_pct,
            "original_pages_count": orig_pages,
            "recovered_pages_count": recovered_pages,
            "page_recovery_pct": page_recovery_pct,
            "synthesized_structures_count": len(synthesized_items),
            "output_pdf_size_bytes": len(recovered_bytes),
            "parser_valid": parser_valid,
            "provenance": "SYNTHETIC_BENCHMARK_EVALUATION",
        }

    def evaluate_dataset(self, dataset_root: Path) -> Dict[str, Any]:
        """Run benchmark evaluation over all samples in a dataset directory."""
        dataset_root = Path(dataset_root)
        index_file = dataset_root / "dataset_index.jsonl"

        results_by_split: Dict[str, List[Dict[str, Any]]] = {
            "train": [],
            "validation": [],
            "test": [],
            "hard_test": [],
        }

        if index_file.is_file():
            # Read from index
            lines = index_file.read_text(encoding="utf-8").splitlines()
            for line in lines:
                if not line.strip():
                    continue
                entry = json.loads(line)
                orig_p = Path(entry["original_path"])
                corr_p = Path(entry["corrupted_path"])
                gt_p = Path(entry["ground_truth_path"])

                if orig_p.is_file() and corr_p.is_file() and gt_p.is_file():
                    gt = GroundTruthRecord.model_validate_json(gt_p.read_text(encoding="utf-8"))
                    eval_res = self.evaluate_sample(orig_p.read_bytes(), corr_p.read_bytes(), gt)
                    split = entry.get("split", "test")
                    if split not in results_by_split:
                        results_by_split[split] = []
                    results_by_split[split].append(eval_res)
        else:
            # Discover from subdirectories
            for split in ["train", "validation", "test", "hard_test"]:
                split_dir = dataset_root / split
                if split_dir.is_dir():
                    for sdir in split_dir.iterdir():
                        if sdir.is_dir():
                            orig_p = sdir / "original.pdf"
                            corr_p = sdir / "corrupted.pdf"
                            gt_p = sdir / "ground_truth.json"
                            if orig_p.is_file() and corr_p.is_file() and gt_p.is_file():
                                gt = GroundTruthRecord.model_validate_json(gt_p.read_text(encoding="utf-8"))
                                eval_res = self.evaluate_sample(orig_p.read_bytes(), corr_p.read_bytes(), gt)
                                results_by_split[split].append(eval_res)

        # Aggregate metrics
        summary: Dict[str, Any] = {}
        for split, records in results_by_split.items():
            if not records:
                continue
            n = len(records)
            summary[split] = {
                "sample_count": n,
                "avg_byte_recovery_pct": round(sum(r["authentic_byte_recovery_pct"] for r in records) / n, 2),
                "avg_object_recovery_pct": round(sum(r["object_recovery_pct"] for r in records) / n, 2),
                "avg_stream_decompression_pct": round(sum(r["stream_decompression_pct"] for r in records) / n, 2),
                "avg_text_recovery_pct": round(sum(r["text_recovery_pct"] for r in records) / n, 2),
                "avg_page_recovery_pct": round(sum(r["page_recovery_pct"] for r in records) / n, 2),
                "parser_validity_rate": round((sum(1 for r in records if r["parser_valid"]) / n) * 100, 2),
            }

        return {
            "dataset_root": str(dataset_root),
            "summary_by_split": summary,
            "detailed_results": results_by_split,
            "benchmark_provenance": "SYNTHETIC_BENCHMARK_EVALUATION",
        }
