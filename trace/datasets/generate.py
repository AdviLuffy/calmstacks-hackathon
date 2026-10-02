"""CLI entrypoint for generating synthetic forensic datasets or corrupted samples.

Usage:
    python -m trace.datasets.generate --output var/sample_001 --seed 12345 --severity 3
    python -m trace.datasets.generate --build-dataset var/my_dataset --samples 12
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from trace.datasets.corruption.engine import ForensicCorruptionEngine
from trace.datasets.exporters.dataset_exporter import DatasetExporter
from trace.datasets.generators.document_generator import SyntheticDocumentGenerator
from trace.datasets.schemas.corruption import CorruptionSeverity


def main() -> int:
    parser = argparse.ArgumentParser(description="TRACE Forensic Dataset & Corruption Generator")
    parser.add_argument("--input", type=str, help="Path to input clean PDF (if omitted, synthetic PDF is generated)")
    parser.add_argument("--output", type=str, default="var/datasets/sample_000001", help="Output directory path")
    parser.add_argument("--seed", type=int, default=12345, help="Deterministic random seed")
    parser.add_argument("--severity", type=int, choices=[0, 1, 2, 3, 4], default=2, help="Corruption severity level (0-4)")
    parser.add_argument("--size", type=str, choices=["SMALL", "MEDIUM", "LARGE"], default="SMALL", help="Document size")
    parser.add_argument("--build-dataset", type=str, help="Generate partitioned train/val/test/hard_test dataset at path")
    parser.add_argument("--samples", type=int, default=12, help="Total samples when building full dataset")

    args = parser.parse_args()

    if args.build_dataset:
        print(f"[*] Building full forensic dataset at: {args.build_dataset} (samples={args.samples}, seed={args.seed})")
        exporter = DatasetExporter()
        res = exporter.generate_and_export_dataset(
            output_dir=Path(args.build_dataset),
            base_seed=args.seed,
        )
        print(f"[+] Dataset successfully created: {res['total_samples']} samples across splits {res['splits']}.")
        print(f"[+] Index written to: {res['index_path']}")
        return 0

    output_path = Path(args.output)
    output_path.mkdir(parents=True, exist_ok=True)

    if args.input:
        in_path = Path(args.input)
        if not in_path.is_file():
            print(f"[-] Error: input file not found: {args.input}", file=sys.stderr)
            return 1
        clean_pdf = in_path.read_bytes()
    else:
        print(f"[*] Generating deterministic synthetic PDF (size={args.size}, seed={args.seed})...")
        doc_gen = SyntheticDocumentGenerator()
        clean_pdf = doc_gen.generate(seed=args.seed, doc_size=args.size)

    severity_enum = CorruptionSeverity(args.severity)
    print(f"[*] Applying forensic corruption (severity={severity_enum.name}, seed={args.seed})...")
    engine = ForensicCorruptionEngine(seed=args.seed)
    sample_id = output_path.name
    corrupted_pdf, manifest, ground_truth = engine.corrupt(
        source_pdf=clean_pdf,
        sample_id=sample_id,
        severity=severity_enum,
        seed=args.seed,
    )

    exporter = DatasetExporter()
    sample_dir = exporter.export_sample(
        target_dir=output_path.parent,
        split="",
        sample_id=sample_id,
        original_pdf=clean_pdf,
        corrupted_pdf=corrupted_pdf,
        manifest=manifest,
        ground_truth=ground_truth,
    )

    print(f"[+] Successfully exported corrupted sample bundle to: {sample_dir}")
    print(f"    - Original size: {len(clean_pdf)} bytes (SHA: {manifest.source_sha256[:12]}...)")
    print(f"    - Corrupted size: {len(corrupted_pdf)} bytes (SHA: {manifest.corrupted_sha256[:12]}...)")
    print(f"    - Operations applied: {len(manifest.operations)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
