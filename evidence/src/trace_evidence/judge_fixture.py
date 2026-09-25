"""Deterministic Judge-Ready Fixtures for TRACE P1 Forensic Evaluation.

Contains three independently testable scenarios with documented ground truth:
1. Scenario A: Complete shuffled reconstruction
   - 10 blocks (header, 5 objects, xref, trailer, startxref, eof)
   - Permuted deterministically.
   - P1 reconstructs original PDF byte-for-byte matching ground-truth hash.
   - Forensic recovery state: 'COMPLETE AND VERIFIED'
2. Scenario B: Missing-fragment partial reconstruction
   - Missing Object 4 (Font) and Trailer blocks.
   - P1 identifies exact missing structural elements.
   - Produces authentic partial byte artifact.
   - Never claims complete recovery or 100% coverage.
   - Forensic recovery state: 'PARTIAL'
3. Scenario C: Corrupted-fragment detection
   - Object 2 bytes are deliberately altered/damaged.
   - P1 detects structural and integrity failure.
   - Never accepts corrupted artifact as verified.
   - Forensic recovery state: 'CORRUPTED'
"""

from __future__ import annotations

import json
from pathlib import Path

from .constants import (
    BLOCK_SIZE,
    KIND_EOF,
    KIND_HEADER,
    KIND_OBJECT,
    KIND_STARTXREF,
    KIND_TRAILER,
    KIND_XREF,
    PADDING_BYTE,
    PDF_EOF,
    PDF_HEADER,
    RECOVERY_COMPLETE_VERIFIED,
    RECOVERY_CORRUPTED,
    RECOVERY_PARTIAL,
)
from .dataset import (
    _build_startxref,
    _build_trailer,
    _build_xref,
    _pad_left,
    _pad_right,
    split_blocks,
)
from .hashing import sha256_bytes

JUDGE_VISIBLE_TEXT = "TRACE FORENSIC RECONSTRUCTION BENCHMARK - JUDGE EVALUATION"
JUDGE_BLOCK_COUNT = 10
JUDGE_OBJECT_COUNT = 5


def _judge_object_bodies(text: str = JUDGE_VISIBLE_TEXT) -> list[bytes]:
    """Five PDF objects including text stream and font resource."""
    stream_content = f"BT\n/F1 16 Tf\n50 350 Td\n({text}) Tj\nET\n".encode("ascii")
    stream_obj = (
        f"5 0 obj\n<< /Length {len(stream_content)} >>\nstream\n".encode("ascii")
        + stream_content
        + b"endstream\nendobj\n"
    )
    return [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 400] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n",
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n",
        stream_obj,
    ]


def build_judge_pdf(text: str = JUDGE_VISIBLE_TEXT) -> bytes:
    """Build a deterministic PDF with visible text content across 10 padded 256-byte blocks."""
    objects = _judge_object_bodies(text)
    object_count = len(objects)
    object_offsets = [(index + 1) * BLOCK_SIZE for index in range(object_count)]
    xref_offset = (object_count + 1) * BLOCK_SIZE

    units = [_pad_right(PDF_HEADER)]
    units.extend(_pad_right(body) for body in objects)
    units.append(_pad_right(_build_xref(object_offsets)))
    units.append(_pad_right(_build_trailer(object_count)))
    units.append(_pad_right(_build_startxref(xref_offset)))
    units.append(_pad_left(PDF_EOF))

    if len(units) != JUDGE_BLOCK_COUNT:
        raise ValueError(
            f"expected {JUDGE_BLOCK_COUNT} units, built {len(units)}"
        )

    return b"".join(units)


def write_judge_dataset(out_dir: str | Path) -> dict:
    """Write the judge ground truth, 3 scenario evidence blobs, and manifest."""
    out = Path(out_dir)
    groundtruth_dir = out / "groundtruth"
    evidence_dir = out / "evidence"
    groundtruth_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    pdf = build_judge_pdf()
    blocks = split_blocks(pdf)
    pdf_sha256 = sha256_bytes(pdf)

    # 1. Write ground truth PDF
    pdf_path = groundtruth_dir / "judge_groundtruth.pdf"
    pdf_path.write_bytes(pdf)

    # Scenario A: Complete shuffled reconstruction
    # Deterministic permutation of all 10 blocks: [5, 2, 8, 1, 9, 3, 0, 7, 4, 6]
    permutation_a = [5, 2, 8, 1, 9, 3, 0, 7, 4, 6]
    blob_a = b"".join(blocks[idx] for idx in permutation_a)
    blob_a_path = evidence_dir / "judge_complete_shuffled.bin"
    blob_a_path.write_bytes(blob_a)

    # Scenario B: Missing-fragment partial reconstruction
    # Remove block 8 (Startxref) and block 9 (EOF)
    # Remaining 8 blocks: [0, 1, 2, 3, 4, 5, 6, 7]
    # Deterministic permutation: [5, 2, 1, 7, 3, 0, 4, 6]
    permutation_b = [5, 2, 1, 7, 3, 0, 4, 6]
    blob_b = b"".join(blocks[idx] for idx in permutation_b)
    blob_b_path = evidence_dir / "judge_missing_fragment.bin"
    blob_b_path.write_bytes(blob_b)

    # Scenario C: Corrupted-fragment detection
    # Alter block 1 (Catalog object) bytes to introduce deliberate syntax and integrity corruption
    corrupted_blocks = list(blocks)
    corrupted_block_1 = _pad_right(
        b"1 0 obj\n<< /Type /Catalog /Pages 99 0 R /CorruptedPayload true >>\nendobj\n"
    )
    corrupted_blocks[1] = corrupted_block_1
    permutation_c = [5, 2, 8, 1, 9, 3, 0, 7, 4, 6]
    blob_c = b"".join(corrupted_blocks[idx] for idx in permutation_c)
    blob_c_path = evidence_dir / "judge_corrupted_fragment.bin"
    blob_c_path.write_bytes(blob_c)

    # Document manifest
    manifest = {
        "dataset_name": "TRACE Judge Forensic Evaluation Benchmark",
        "description": "Standardized benchmark with 3 independently testable forensic scenarios",
        "block_size_bytes": BLOCK_SIZE,
        "ground_truth": {
            "name": "judge_groundtruth.pdf",
            "path": "groundtruth/judge_groundtruth.pdf",
            "size_bytes": len(pdf),
            "sha256": pdf_sha256,
            "visible_text": JUDGE_VISIBLE_TEXT,
            "block_count": len(blocks),
        },
        "scenarios": {
            "scenario_a_complete_shuffled": {
                "name": "judge_complete_shuffled.bin",
                "path": "evidence/judge_complete_shuffled.bin",
                "description": "All 10 blocks present in shuffled order. Must reconstruct original byte-for-byte.",
                "size_bytes": len(blob_a),
                "sha256": sha256_bytes(blob_a),
                "permutation": permutation_a,
                "expected_recovery_state": RECOVERY_COMPLETE_VERIFIED,
                "expected_byte_coverage": "100.0%",
                "expected_placed_fragments": 10,
                "expected_total_fragments": 10,
            },
            "scenario_b_missing_fragment": {
                "name": "judge_missing_fragment.bin",
                "path": "evidence/judge_missing_fragment.bin",
                "description": "Evidence missing Startxref pointer and EOF terminator. Must produce authentic partial reconstruction without claiming 100% coverage.",
                "size_bytes": len(blob_b),
                "sha256": sha256_bytes(blob_b),
                "permutation": permutation_b,
                "missing_original_indices": [8, 9],
                "missing_elements": [
                    "missing structural fragment: startxref pointer",
                    "missing structural fragment: EOF terminator (%%EOF)",
                ],
                "expected_recovery_state": RECOVERY_PARTIAL,
                "expected_byte_coverage": "80.0%",
                "expected_placed_fragments": 8,
                "expected_total_fragments": 8,
            },
            "scenario_c_corrupted_fragment": {
                "name": "judge_corrupted_fragment.bin",
                "path": "evidence/judge_corrupted_fragment.bin",
                "description": "Evidence contains damaged Object 1 block. Engine must detect corruption and refuse verification.",
                "size_bytes": len(blob_c),
                "sha256": sha256_bytes(blob_c),
                "permutation": permutation_c,
                "corrupted_original_index": 1,
                "corruption_details": "Object 1 catalog body overwritten with invalid references and payload",
                "expected_recovery_state": RECOVERY_CORRUPTED,
                "expected_is_verified": False,
            },
        },
    }

    manifest_path = out / "manifest_judge_fixture.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    return {
        "groundtruth_pdf": str(pdf_path),
        "blob_a": str(blob_a_path),
        "blob_b": str(blob_b_path),
        "blob_c": str(blob_c_path),
        "manifest": str(manifest_path),
        "data": manifest,
    }
