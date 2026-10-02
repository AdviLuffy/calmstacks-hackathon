"""Dataset Exporter and Index Generator for TRACE.

Exports partitioned datasets across train, validation, test, and hard_test splits
with sample packages and a compact metadata index (dataset_index.jsonl).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from trace.datasets.corruption.engine import ForensicCorruptionEngine
from trace.datasets.generators.document_generator import SyntheticDocumentGenerator
from trace.datasets.schemas.corruption import CorruptionManifest, CorruptionSeverity
from trace.datasets.schemas.ground_truth import GroundTruthRecord


class DatasetExporter:
    """Exports structured datasets with split isolation and metadata indexing."""

    def __init__(self, base_output_dir: Optional[Path] = None) -> None:
        self.base_output_dir = base_output_dir or Path("var/datasets")

    def export_sample(
        self,
        target_dir: Path,
        split: str,
        sample_id: str,
        original_pdf: bytes,
        corrupted_pdf: bytes,
        manifest: CorruptionManifest,
        ground_truth: GroundTruthRecord,
    ) -> Path:
        """Write an individual sample bundle (original, corrupted, manifest, ground_truth)."""
        sample_dir = target_dir / split / sample_id
        sample_dir.mkdir(parents=True, exist_ok=True)

        # 1. Original PDF
        (sample_dir / "original.pdf").write_bytes(original_pdf)

        # 2. Corrupted PDF
        (sample_dir / "corrupted.pdf").write_bytes(corrupted_pdf)

        # 3. Manifest JSON
        (sample_dir / "manifest.json").write_text(
            json.dumps(manifest.model_dump(), indent=2), encoding="utf-8"
        )

        # 4. Ground Truth JSON
        (sample_dir / "ground_truth.json").write_text(
            json.dumps(ground_truth.model_dump(), indent=2), encoding="utf-8"
        )

        return sample_dir

    def generate_and_export_dataset(
        self,
        output_dir: Path,
        samples_per_split: Optional[Dict[str, int]] = None,
        base_seed: int = 12345,
    ) -> Dict[str, Any]:
        """Generate a complete dataset across train, validation, test, and hard_test."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        splits_config = samples_per_split or {
            "train": 6,
            "validation": 2,
            "test": 2,
            "hard_test": 2,
        }

        doc_gen = SyntheticDocumentGenerator()
        corr_engine = ForensicCorruptionEngine(seed=base_seed)

        index_entries: List[Dict[str, Any]] = []
        sample_counter = 1

        sizes_cycle = ["SMALL", "MEDIUM", "LARGE"]

        for split, count in splits_config.items():
            for i in range(count):
                sample_id = f"sample_{sample_counter:06d}"
                doc_size = sizes_cycle[(sample_counter - 1) % len(sizes_cycle)]
                doc_seed = base_seed + sample_counter * 101

                # Generate clean document
                page_target = 2 if doc_size == "SMALL" else (5 if doc_size == "MEDIUM" else 11)
                clean_pdf = doc_gen.generate(page_count=page_target, seed=doc_seed, doc_size=doc_size)

                # Determine severity: hard_test gets LEVEL_4, others vary
                if split == "hard_test":
                    severity = CorruptionSeverity.LEVEL_4
                elif split == "test":
                    severity = CorruptionSeverity.LEVEL_3 if (i % 2 == 1) else CorruptionSeverity.LEVEL_2
                elif split == "validation":
                    severity = CorruptionSeverity.LEVEL_2 if (i % 2 == 1) else CorruptionSeverity.LEVEL_1
                else:  # train
                    severity = CorruptionSeverity((i % 4) + 1)

                # Apply deterministic corruption
                corrupted_pdf, manifest, ground_truth = corr_engine.corrupt(
                    source_pdf=clean_pdf,
                    sample_id=sample_id,
                    severity=severity,
                    seed=doc_seed + 7,
                )

                # Export sample package
                sample_path = self.export_sample(
                    target_dir=output_dir,
                    split=split,
                    sample_id=sample_id,
                    original_pdf=clean_pdf,
                    corrupted_pdf=corrupted_pdf,
                    manifest=manifest,
                    ground_truth=ground_truth,
                )

                # Create compact index entry
                entry = {
                    "sample_id": sample_id,
                    "split": split,
                    "doc_size": doc_size,
                    "page_count": page_target,
                    "original_path": str((sample_path / "original.pdf").as_posix()),
                    "corrupted_path": str((sample_path / "corrupted.pdf").as_posix()),
                    "manifest_path": str((sample_path / "manifest.json").as_posix()),
                    "ground_truth_path": str((sample_path / "ground_truth.json").as_posix()),
                    "original_sha256": ground_truth.original_sha256,
                    "corrupted_sha256": ground_truth.corrupted_sha256,
                    "original_size_bytes": ground_truth.original_size_bytes,
                    "corrupted_size_bytes": ground_truth.corrupted_size_bytes,
                    "severity_level": severity.value,
                    "operations_count": len(manifest.operations),
                    "corruption_types": [op.type.value for op in manifest.operations],
                    "seed": doc_seed + 7,
                }
                index_entries.append(entry)
                sample_counter += 1

        # Write dataset_index.jsonl
        index_file = output_dir / "dataset_index.jsonl"
        with index_file.open("w", encoding="utf-8") as f:
            for e in index_entries:
                f.write(json.dumps(e) + "\n")

        return {
            "dataset_root": str(output_dir),
            "total_samples": len(index_entries),
            "splits": {s: sum(1 for e in index_entries if e["split"] == s) for s in splits_config},
            "index_path": str(index_file),
        }
