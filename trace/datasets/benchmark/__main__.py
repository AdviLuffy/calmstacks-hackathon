"""CLI entrypoint for running TRACE recovery benchmark over a forensic dataset.

Usage:
    python -m trace.datasets.benchmark --dataset var/datasets
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from trace.datasets.benchmark.runner import RecoveryBenchmarkRunner


def main() -> int:
    parser = argparse.ArgumentParser(description="TRACE Forensic Recovery Benchmark Runner")
    parser.add_argument("--dataset", type=str, default="var/datasets", help="Path to dataset root directory")
    parser.add_argument("--output", type=str, help="Optional path to write benchmark report JSON")

    args = parser.parse_args()
    target = Path(args.dataset)

    print(f"[*] Running recovery benchmark over dataset at: {target}")
    runner = RecoveryBenchmarkRunner()
    report = runner.evaluate_dataset(target)

    print("\n================== TRACE BENCHMARK REPORT ==================")
    for split, summary in report.get("summary_by_split", {}).items():
        print(f"\n[Split: {split.upper()}] (Samples: {summary['sample_count']})")
        print(f"  * Avg Authentic Byte Recovery : {summary['avg_byte_recovery_pct']}%")
        print(f"  * Avg Object Recovery         : {summary['avg_object_recovery_pct']}%")
        print(f"  * Avg Stream Decompression    : {summary['avg_stream_decompression_pct']}%")
        print(f"  * Avg Text String Recovery    : {summary['avg_text_recovery_pct']}%")
        print(f"  * Avg Page Tree Recovery      : {summary['avg_page_recovery_pct']}%")
        print(f"  * PDF Parser Validity Rate    : {summary['parser_validity_rate']}%")
    print("============================================================\n")

    if args.output:
        out_p = Path(args.output)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        out_p.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(f"[+] Full benchmark report saved to: {out_p}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
