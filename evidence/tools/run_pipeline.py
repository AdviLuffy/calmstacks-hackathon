"""Command-line interface for the TRACE P1 Evidence & Reconstruction Pipeline.

Executes the P1-only engine on a raw evidence blob:
1. Carves fragments and emits the Evidence Bundle.
2. Derives structural DNA markers and candidate relationships.
3. Assembles authentic bytes into a reconstructed PDF using structural validation.
4. Generates complete byte provenance and an integrity report.

Usage (Windows PowerShell):

    py tools/run_pipeline.py
    py tools/run_pipeline.py --input datasets/evidence/blob_1337.bin --out datasets/output

Usage (Linux / macOS):

    python tools/run_pipeline.py --input datasets/evidence/blob_1337.bin --out datasets/output
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from trace_evidence import constants  # noqa: E402
from trace_evidence.pipeline import run_pipeline  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="TRACE Subsystem 1 (P1): Evidence Ingestion & Reconstruction Engine"
    )
    parser.add_argument(
        "--input",
        type=Path,
        default=PROJECT_ROOT / "datasets" / "evidence" / f"blob_{constants.DEFAULT_SEED}.bin",
        help=f"path to raw evidence blob (default: datasets/evidence/blob_{constants.DEFAULT_SEED}.bin)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=PROJECT_ROOT / "datasets" / "output",
        help="output directory for generated artifacts (default: datasets/output)",
    )
    parser.add_argument(
        "--block-size",
        type=int,
        default=constants.BLOCK_SIZE,
        help=f"fixed fragment carving size in bytes (default: {constants.BLOCK_SIZE})",
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="optional volatile run identifier (default: auto-generated)",
    )
    args = parser.parse_args(argv)

    if not args.input.is_file():
        print(f"Error: input evidence file not found at {args.input}", file=sys.stderr)
        return 1

    print("=== TRACE P1: Evidence & Reconstruction Engine ===")
    print(f"Input evidence media       : {args.input}")
    print(f"Output directory           : {args.out}")

    result = run_pipeline(
        media_path=args.input,
        run_id=args.run_id,
        block_size=args.block_size,
        out_dir=args.out,
    )

    kinds_count: dict[str, int] = {}
    for p in result.profiles:
        kinds_count[p.kind] = kinds_count.get(p.kind, 0) + 1
    profiles_summary = ", ".join(f"{count} {kind}" for kind, count in sorted(kinds_count.items()))

    print(f"Run ID                     : {result.run_id}")
    print(f"Media size                 : {result.scan.media_size_bytes} bytes (SHA-256: {result.scan.media_sha256[:16]}...)")
    print(f"Carved fragments           : {len(result.scan.fragments)} fragments ({args.block_size} bytes each)")
    print(f"Evidence bundle written    : {result.output_files.get('evidence_bundle', 'None')}")
    print(f"DNA profiles derived       : {profiles_summary}")
    print(f"Candidate relationships    : {len(result.analysis.relationships)} candidate edges ({len(result.analysis.unresolved)} unresolved joins)")
    print(f"Reconstruction status      : {result.reconstruction.status} (PDF self-validation: {'PASSED' if result.reconstruction.validation.is_valid else 'FAILED'})")
    print(f"Reconstructed file written : {result.output_files.get('reconstructed_pdf', 'None')} ({len(result.reconstruction.raw_bytes)} bytes)")
    print(f"Reconstructed SHA-256      : {result.integrity_report.reconstructed_sha256}")
    print(f"Integrity report written   : {result.output_files.get('integrity_report', 'None')}")
    print(f"Provenance coverage        : {len(result.integrity_report.provenance)} fragments ({result.integrity_report.reconstructed_size_bytes}/{result.scan.media_size_bytes} bytes mapped)")
    print(f"Pipeline complete          : {result.is_complete}")
    print("==================================================")

    return 0 if result.is_complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
