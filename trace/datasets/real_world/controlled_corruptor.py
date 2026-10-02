"""Controlled Corruption Generator for Real-World PDFs (TRACE Phase 10).

Applies TRACE's ForensicCorruptionEngine to intact real-world and canonical documents,
enforcing strict document-level split isolation (zero document leakage across train/val/test),
preserving exact original byte integrity, and generating detailed ground-truth provenance.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from trace.datasets.corruption.engine import ForensicCorruptionEngine
from trace.datasets.exporters.dataset_exporter import DatasetExporter
from trace.datasets.schemas.corruption import CorruptionSeverity
from trace.datasets.schemas.real_world import (
    ControlledCorruptionRecord,
    RealWorldDocumentRecord,
)

logger = logging.getLogger(__name__)

DEFAULT_CORRUPTED_OUTPUT_DIR = Path(__file__).resolve().parent / "data" / "controlled_corruptions"


class ControlledCorruptor:
    """Generates controlled damaged variants of real-world documents with ground truth."""

    def __init__(
        self,
        output_dir: Optional[Union[str, Path]] = None,
    ) -> None:
        if output_dir:
            self.output_dir = Path(output_dir)
        elif os.environ.get("VERCEL"):
            self.output_dir = Path("/tmp/trace_data/controlled_corruptions")
        else:
            self.output_dir = DEFAULT_CORRUPTED_OUTPUT_DIR

        try:
            self.output_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            self.output_dir = Path("/tmp/trace_data/controlled_corruptions")
            self.output_dir.mkdir(parents=True, exist_ok=True)

        self.exporter = DatasetExporter()

    def compute_sha256(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def assign_document_splits(
        self,
        documents: List[RealWorldDocumentRecord],
        train_ratio: float = 0.50,
        val_ratio: float = 0.20,
        test_ratio: float = 0.20,
        hard_test_ratio: float = 0.10,
    ) -> Dict[str, str]:
        """Assign splits strictly at the DOCUMENT level to prevent any document data leakage."""
        sorted_docs = sorted(documents, key=lambda d: d.document_id)
        n = len(sorted_docs)
        if n == 0:
            return {}

        n_train = max(1, int(n * train_ratio))
        n_val = max(1, int(n * val_ratio))
        n_test = max(1, int(n * test_ratio))

        splits: Dict[str, str] = {}
        for idx, doc in enumerate(sorted_docs):
            if idx < n_train:
                splits[doc.document_id] = "train"
            elif idx < n_train + n_val:
                splits[doc.document_id] = "validation"
            elif idx < n_train + n_val + n_test:
                splits[doc.document_id] = "test"
            else:
                splits[doc.document_id] = "hard_test"

        return splits

    def generate_corruptions_for_document(
        self,
        doc_record: RealWorldDocumentRecord,
        original_pdf_bytes: bytes,
        split: str = "test",
        severities: Optional[List[CorruptionSeverity]] = None,
        base_seed: int = 1000,
    ) -> List[Tuple[ControlledCorruptionRecord, bytes]]:
        """Generate multiple controlled corruptions for a single document within its assigned split."""
        if not original_pdf_bytes:
            raise ValueError("original_pdf_bytes cannot be empty")

        active_severities = severities or [
            CorruptionSeverity.LEVEL_1,
            CorruptionSeverity.LEVEL_2,
            CorruptionSeverity.LEVEL_3,
            CorruptionSeverity.LEVEL_4,
        ]

        orig_sha = self.compute_sha256(original_pdf_bytes)
        corrupted_outputs: List[Tuple[ControlledCorruptionRecord, bytes]] = []

        split_dir = self.output_dir / split
        split_dir.mkdir(parents=True, exist_ok=True)

        for s_idx, sev in enumerate(active_severities, start=1):
            seed = base_seed + (s_idx * 17)
            engine = ForensicCorruptionEngine(seed=seed)
            sample_id = f"{doc_record.document_id}_c{s_idx:02d}_{sev.name.lower()}"

            corrupted_bytes, manifest, ground_truth = engine.corrupt(
                source_pdf=original_pdf_bytes,
                sample_id=sample_id,
                severity=sev,
                seed=seed,
            )

            corr_sha = self.compute_sha256(corrupted_bytes)
            # Determine if this operation destroys all content or preserves some
            preserves_content = sev.value <= 3 and len(corrupted_bytes) > 256

            # Export using DatasetExporter
            sample_dir = self.exporter.export_sample(
                target_dir=split_dir,
                split="",
                sample_id=sample_id,
                original_pdf=original_pdf_bytes,
                corrupted_pdf=corrupted_bytes,
                manifest=manifest,
                ground_truth=ground_truth,
            )

            gt_ref = str(sample_dir / "ground_truth.json")

            ctrl_record = ControlledCorruptionRecord(
                corruption_sample_id=sample_id,
                source_document_id=doc_record.document_id,
                source_sha256=orig_sha,
                corrupted_sha256=corr_sha,
                operation_type=manifest.primary_corruption_type.value if hasattr(manifest, "primary_corruption_type") else "multi_corruption",
                parameters={"severity": sev.value, "operations_count": len(manifest.operations)},
                seed=seed,
                original_size_bytes=len(original_pdf_bytes),
                corrupted_size_bytes=len(corrupted_bytes),
                preserves_content=preserves_content,
                split=split,
                ground_truth_reference=gt_ref,
                created_at="2026-10-01T23:00:00Z",
            )
            corrupted_outputs.append((ctrl_record, corrupted_bytes))

        return corrupted_outputs
