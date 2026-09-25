"""Build the reproducible synthetic dataset used by the engine tests and demo.

Usage (Windows):

    py tools/make_dataset.py
    py tools/make_dataset.py --seed 1337 --out datasets

Usage (Linux / macOS):

    python tools/make_dataset.py
    python tools/make_dataset.py --seed 1337 --out datasets
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
from trace_evidence.dataset import write_dataset, write_visible_dataset  # noqa: E402
from trace_evidence.hashing import sha256_file  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the deterministic synthetic PDF dataset and shuffled evidence blob."
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=constants.DEFAULT_SEED,
        help=f"shuffle seed (default: {constants.DEFAULT_SEED})",
    )
    parser.add_argument(
        "--visible",
        action="store_true",
        help="build visible-text synthetic PDF dataset with visible text reading 'TRACE FORENSIC RECONSTRUCTION TEST'",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=PROJECT_ROOT / "datasets",
        help="output directory (default: evidence/datasets)",
    )
    args = parser.parse_args(argv)

    if args.visible:
        seed = args.seed if args.seed != constants.DEFAULT_SEED else 2026
        result = write_visible_dataset(args.out, seed=seed)
    else:
        result = write_dataset(args.out, seed=args.seed)
    manifest = result["manifest"]

    print(f"dataset written to : {result['dataset_dir']}")
    print(f"seed               : {manifest['seed']}")
    print(f"block size         : {manifest['block_size']} bytes")
    print(f"fragment count     : {manifest['fragment_count']}")
    print(f"block count        : {manifest['original']['block_count']}")
    print(
        f"original (pdf)     : {manifest['original']['name']}  "
        f"{manifest['original']['size']} bytes  "
        f"sha256={manifest['original']['sha256']}"
    )
    print(
        f"blob               : {manifest['blob']['name']}  "
        f"{manifest['blob']['size']} bytes  "
        f"sha256={manifest['blob']['sha256']}"
    )
    print(f"manifest sha256    : {sha256_file(result['manifest_path'])}")
    print(f"permutation        : {manifest['permutation']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
