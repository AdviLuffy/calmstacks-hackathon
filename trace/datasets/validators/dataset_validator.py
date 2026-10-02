"""Dataset Validator ensuring integrity, schema conformance, and split isolation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Set

from trace.datasets.schemas.corruption import CorruptionManifest
from trace.datasets.schemas.ground_truth import GroundTruthRecord


class DatasetValidator:
    """Rigorous validator checking dataset integrity, hashes, schemas, and split hygiene."""

    @staticmethod
    def sha256_file(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def validate_sample(self, sample_dir: Path) -> Dict[str, Any]:
        """Validate a single sample directory bundle."""
        sample_dir = Path(sample_dir)
        issues: List[str] = []

        orig_path = sample_dir / "original.pdf"
        corr_path = sample_dir / "corrupted.pdf"
        man_path = sample_dir / "manifest.json"
        gt_path = sample_dir / "ground_truth.json"

        # Check required files
        for p in [orig_path, corr_path, man_path, gt_path]:
            if not p.is_file():
                issues.append(f"Missing required file: {p.name}")

        if issues:
            return {"valid": False, "sample_dir": str(sample_dir), "issues": issues}

        orig_bytes = orig_path.read_bytes()
        corr_bytes = corr_path.read_bytes()
        orig_sha = hashlib.sha256(orig_bytes).hexdigest()
        corr_sha = hashlib.sha256(corr_bytes).hexdigest()

        # Parse Manifest
        try:
            man_data = json.loads(man_path.read_text(encoding="utf-8"))
            manifest = CorruptionManifest.model_validate(man_data)
        except Exception as exc:
            issues.append(f"Manifest schema validation failure: {exc}")
            manifest = None

        # Parse Ground Truth
        try:
            gt_data = json.loads(gt_path.read_text(encoding="utf-8"))
            ground_truth = GroundTruthRecord.model_validate(gt_data)
        except Exception as exc:
            issues.append(f"Ground truth schema validation failure: {exc}")
            ground_truth = None

        # Hash validations
        if manifest:
            if manifest.source_sha256 != orig_sha:
                issues.append(f"Original file SHA256 mismatch with manifest: {orig_sha} vs {manifest.source_sha256}")
            if manifest.corrupted_sha256 != corr_sha:
                issues.append(f"Corrupted file SHA256 mismatch with manifest: {corr_sha} vs {manifest.corrupted_sha256}")

            # Verify corruption offsets
            for op in manifest.operations:
                if op.offset_start < 0 or op.offset_end < op.offset_start:
                    issues.append(f"Invalid offset bounds in op {op.operation_id}: [{op.offset_start}, {op.offset_end}]")

        if ground_truth:
            if ground_truth.original_sha256 != orig_sha:
                issues.append(f"Original file SHA256 mismatch with ground truth: {orig_sha} vs {ground_truth.original_sha256}")
            if ground_truth.corrupted_sha256 != corr_sha:
                issues.append(f"Corrupted file SHA256 mismatch with ground truth: {corr_sha} vs {ground_truth.corrupted_sha256}")

        return {
            "valid": len(issues) == 0,
            "sample_id": sample_dir.name,
            "sample_dir": str(sample_dir),
            "issues": issues,
            "original_size": len(orig_bytes),
            "corrupted_size": len(corr_bytes),
        }

    def validate_dataset(self, dataset_root: Path) -> Dict[str, Any]:
        """Validate entire dataset hierarchy, split separation, and index consistency."""
        dataset_root = Path(dataset_root)
        report: Dict[str, Any] = {
            "valid": True,
            "dataset_root": str(dataset_root),
            "total_samples": 0,
            "splits": {},
            "issues": [],
            "samples_report": [],
        }

        if not dataset_root.is_dir():
            report["valid"] = False
            report["issues"].append(f"Dataset root does not exist: {dataset_root}")
            return report

        seen_sample_ids: Set[str] = set()
        seen_source_hashes: Dict[str, str] = {}  # source_sha256 -> split

        expected_splits = ["train", "validation", "test", "hard_test"]
        for split in expected_splits:
            split_dir = dataset_root / split
            if not split_dir.is_dir():
                continue

            sample_dirs = [d for d in split_dir.iterdir() if d.is_dir()]
            report["splits"][split] = len(sample_dirs)

            for sdir in sample_dirs:
                report["total_samples"] += 1
                sample_res = self.validate_sample(sdir)
                report["samples_report"].append(sample_res)

                if not sample_res["valid"]:
                    report["valid"] = False
                    report["issues"].extend(
                        [f"[{sdir.name}] {iss}" for iss in sample_res["issues"]]
                    )

                # Check unique IDs
                sid = sdir.name
                if sid in seen_sample_ids:
                    report["valid"] = False
                    report["issues"].append(f"Duplicate sample ID detected: {sid}")
                seen_sample_ids.add(sid)

                # Check split leakage (same source document in multiple splits)
                man_path = sdir / "manifest.json"
                if man_path.is_file():
                    try:
                        m_data = json.loads(man_path.read_text(encoding="utf-8"))
                        src_hash = m_data.get("source_sha256")
                        if src_hash:
                            if src_hash in seen_source_hashes and seen_source_hashes[src_hash] != split:
                                report["valid"] = False
                                report["issues"].append(
                                    f"Data leakage detected! Same source document {src_hash[:10]} found in both '{seen_source_hashes[src_hash]}' and '{split}'."
                                )
                            seen_source_hashes[src_hash] = split
                    except Exception:
                        pass

        # Check dataset_index.jsonl if present
        index_path = dataset_root / "dataset_index.jsonl"
        if index_path.is_file():
            try:
                lines = index_path.read_text(encoding="utf-8").splitlines()
                indexed_ids = set()
                for line in lines:
                    if line.strip():
                        entry = json.loads(line)
                        indexed_ids.add(entry.get("sample_id"))
                if indexed_ids != seen_sample_ids:
                    report["issues"].append(
                        f"Index mismatch: {len(indexed_ids)} indexed vs {len(seen_sample_ids)} disk samples."
                    )
            except Exception as exc:
                report["issues"].append(f"Failed to read dataset_index.jsonl: {exc}")

        report["valid"] = len(report["issues"]) == 0
        return report
