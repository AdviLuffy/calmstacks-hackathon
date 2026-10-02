"""CLI entrypoint for validating forensic dataset integrity and split isolation.

Usage:
    python -m trace.datasets.validate --dataset var/datasets
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from trace.datasets.validators.dataset_validator import DatasetValidator


def main() -> int:
    parser = argparse.ArgumentParser(description="TRACE Forensic Dataset Validator")
    parser.add_argument("--dataset", type=str, default="var/datasets", help="Path to dataset root directory")

    args = parser.parse_args()
    target = Path(args.dataset)

    print(f"[*] Validating forensic dataset at: {target}")
    validator = DatasetValidator()
    report = validator.validate_dataset(target)

    print(f"[*] Validation completed. Status: {'VALID' if report['valid'] else 'FAILED'}")
    print(f"    - Total samples inspected: {report['total_samples']}")
    print(f"    - Splits breakdown: {report['splits']}")

    if not report["valid"]:
        print(f"[-] {len(report['issues'])} issues detected:", file=sys.stderr)
        for iss in report["issues"][:15]:
            print(f"    * {iss}", file=sys.stderr)
        return 1

    print("[+] All hash verifications, schema checks, offset bounds, and split hygiene PASSED.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
