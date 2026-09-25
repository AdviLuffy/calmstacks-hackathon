"""Reproducible synthetic dataset: a deterministic PDF, split and shuffled.

Design notes
------------
* ``build_synthetic_pdf`` authors the PDF byte by byte. There is no timestamp
  and no randomness, so identical bytes are produced on every machine.
* The PDF is built from ``EXPECTED_FRAGMENT_COUNT`` structural units; each unit
  is padded with PDF-legal whitespace to exactly ``BLOCK_SIZE`` bytes. That is
  what lets the file be split into fixed-size blocks whose boundaries fall
  between structural units.
* The evidence blob is the same blocks in a different order, concatenated with
  no metadata at all. It is derived *only* from the PDF bytes and the seed.
* ``write_dataset`` also writes ``manifest.json``. That manifest is ground truth
  for tests; the engine itself never reads it.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from . import __version__
from .constants import (
    BLOCK_SIZE,
    DATASET_FORMAT_VERSION,
    DEFAULT_SEED,
    EXPECTED_FRAGMENT_COUNT,
    KIND_EOF,
    KIND_HEADER,
    KIND_OBJECT,
    KIND_STARTXREF,
    KIND_TRAILER,
    KIND_XREF,
    OBJECT_COUNT,
    PADDING_BYTE,
    PDF_EOF,
    PDF_HEADER,
)
from .hashing import content_id, sha256_bytes

__all__ = [
    "build_synthetic_pdf",
    "split_blocks",
    "keyed_permutation",
    "shuffle_fragments",
    "build_manifest",
    "write_dataset",
    "VISIBLE_OBJECT_COUNT",
    "VISIBLE_EXPECTED_FRAGMENT_COUNT",
    "VISIBLE_TEXT_CONTENT",
    "VISIBLE_DEFAULT_SEED",
    "build_visible_text_pdf",
    "write_visible_dataset",
    "write_visible_missing_dataset",
]

VISIBLE_OBJECT_COUNT = 5
VISIBLE_EXPECTED_FRAGMENT_COUNT = 10
VISIBLE_TEXT_CONTENT = "TRACE FORENSIC RECONSTRUCTION TEST"
VISIBLE_DEFAULT_SEED = 2026


def _object_bodies() -> list[bytes]:
    """The three PDF objects, in file order."""
    return [
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>\nendobj\n",
    ]


def _pad_right(content: bytes) -> bytes:
    """Pad a structural unit on the right so it fills exactly one block."""
    if len(content) > BLOCK_SIZE:
        raise ValueError(
            f"structural unit of {len(content)} bytes does not fit in BLOCK_SIZE={BLOCK_SIZE}"
        )
    return content + PADDING_BYTE * (BLOCK_SIZE - len(content))


def _pad_left(content: bytes) -> bytes:
    """Pad on the left, so the file still *ends* with the padded unit."""
    if len(content) > BLOCK_SIZE:
        raise ValueError(
            f"structural unit of {len(content)} bytes does not fit in BLOCK_SIZE={BLOCK_SIZE}"
        )
    return PADDING_BYTE * (BLOCK_SIZE - len(content)) + content


def _build_xref(object_offsets: list[int]) -> bytes:
    """Cross-reference table: the free entry plus one entry per object.

    Each entry is exactly 20 bytes, as the PDF format requires.
    """
    lines = [
        b"xref\n",
        f"0 {len(object_offsets) + 1}\n".encode("ascii"),
        b"0000000000 65535 f \n",
    ]
    for offset in object_offsets:
        lines.append(f"{offset:010d} 00000 n \n".encode("ascii"))
    return b"".join(lines)


def _build_trailer(object_count: int) -> bytes:
    return f"trailer\n<< /Size {object_count + 1} /Root 1 0 R >>\n".encode("ascii")


def _build_startxref(xref_offset: int) -> bytes:
    return f"startxref\n{xref_offset}\n".encode("ascii")


def build_synthetic_pdf() -> bytes:
    """Build the ground-truth PDF.

    Deterministic by construction: no clock, no randomness, no locale or
    filesystem dependency.
    """
    objects = _object_bodies()
    object_count = len(objects)
    object_offsets = [(index + 1) * BLOCK_SIZE for index in range(object_count)]
    xref_offset = (object_count + 1) * BLOCK_SIZE

    units = [_pad_right(PDF_HEADER)]
    units.extend(_pad_right(body) for body in objects)
    units.append(_pad_right(_build_xref(object_offsets)))
    units.append(_pad_right(_build_trailer(object_count)))
    units.append(_pad_right(_build_startxref(xref_offset)))
    units.append(_pad_left(PDF_EOF))

    if len(units) != EXPECTED_FRAGMENT_COUNT:
        raise ValueError(
            f"expected {EXPECTED_FRAGMENT_COUNT} structural units, built {len(units)}"
        )

    return b"".join(units)


def split_blocks(pdf: bytes) -> list[bytes]:
    """Split the PDF into fixed-size fragments (blocks)."""
    if len(pdf) % BLOCK_SIZE != 0:
        raise ValueError(
            f"pdf length {len(pdf)} is not a multiple of BLOCK_SIZE={BLOCK_SIZE}"
        )
    return [pdf[start:start + BLOCK_SIZE] for start in range(0, len(pdf), BLOCK_SIZE)]


def keyed_permutation(count: int, seed: int) -> list[int]:
    """Deterministic permutation of ``range(count)`` derived from ``seed``.

    A keyed sort over SHA-256 digests is used instead of a PRNG so the ordering
    can never drift between Python versions. If the ordering happens to be the
    identity, it is rotated once so the blob is always a genuine shuffle.
    """
    if count < 0:
        raise ValueError("count must be >= 0")

    order = sorted(
        range(count),
        key=lambda index: hashlib.sha256(f"{seed}:{index}".encode("ascii")).digest(),
    )

    if count > 1 and order == list(range(count)):
        order = order[1:] + order[:1]

    return order


def shuffle_fragments(pdf: bytes, seed: int) -> tuple[bytes, list[int]]:
    """Return ``(blob, permutation)``.

    ``blob`` is the PDF's blocks concatenated in a seed-dependent order, carrying
    no metadata whatsoever. ``permutation`` is ground truth: which original block
    ended up at which blob position.
    """
    blocks = split_blocks(pdf)
    permutation = keyed_permutation(len(blocks), seed)
    blob = b"".join(blocks[index] for index in permutation)
    return blob, permutation


def _original_kinds() -> list[str]:
    """The structural kind of every original block, in original order."""
    return (
        [KIND_HEADER]
        + [KIND_OBJECT] * OBJECT_COUNT
        + [KIND_XREF, KIND_TRAILER, KIND_STARTXREF, KIND_EOF]
    )


def build_manifest(pdf: bytes, blob: bytes, permutation: list[int], seed: int) -> dict:
    """Build the ground-truth manifest for the dataset.

    Written for tests only. The engine must never take it as input.
    """
    kinds = _original_kinds()
    blocks = split_blocks(pdf)

    fragments = []
    for position, original_index in enumerate(permutation):
        digest = sha256_bytes(blocks[original_index])
        fragments.append(
            {
                "fragment_id": content_id("frag", digest),
                "blob_offset": position * BLOCK_SIZE,
                "length": BLOCK_SIZE,
                "sha256": digest,
                "source_offset": original_index * BLOCK_SIZE,
                "original_index": original_index,
                "kind": kinds[original_index],
                "object_number": (
                    original_index if 1 <= original_index <= OBJECT_COUNT else None
                ),
            }
        )

    return {
        "dataset_format_version": DATASET_FORMAT_VERSION,
        "generator": {"name": "trace-evidence", "version": __version__},
        "seed": seed,
        "block_size": BLOCK_SIZE,
        "fragment_count": len(permutation),
        "original": {
            "name": "synthetic.pdf",
            "path": "groundtruth/synthetic.pdf",
            "size": len(pdf),
            "sha256": sha256_bytes(pdf),
            "block_count": len(blocks),
        },
        "blob": {
            "name": f"blob_{seed}.bin",
            "path": f"evidence/blob_{seed}.bin",
            "size": len(blob),
            "sha256": sha256_bytes(blob),
        },
        "permutation": list(permutation),
        "fragments": fragments,
    }


def write_dataset(out_dir: str | Path, seed: int = DEFAULT_SEED) -> dict:
    """Write the ground truth, the evidence blob and the manifest under ``out_dir``."""
    out = Path(out_dir)
    groundtruth_dir = out / "groundtruth"
    evidence_dir = out / "evidence"
    groundtruth_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    pdf = build_synthetic_pdf()
    blob, permutation = shuffle_fragments(pdf, seed)
    manifest = build_manifest(pdf, blob, permutation, seed)

    pdf_path = groundtruth_dir / manifest["original"]["name"]
    blob_path = evidence_dir / manifest["blob"]["name"]
    manifest_path = out / "manifest.json"

    pdf_path.write_bytes(pdf)
    blob_path.write_bytes(blob)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    return {
        "dataset_dir": str(out),
        "pdf_path": str(pdf_path),
        "blob_path": str(blob_path),
        "manifest_path": str(manifest_path),
        "manifest": manifest,
    }


def _visible_object_bodies(text: str = VISIBLE_TEXT_CONTENT) -> list[bytes]:
    """The five PDF objects for visible text rendering, in file order."""
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


def build_visible_text_pdf(text: str = VISIBLE_TEXT_CONTENT) -> bytes:
    """Build a deterministic PDF with visible text content.

    Contains catalog, pages tree, page descriptor, Helvetica font resource,
    and a stream containing text rendering operators.
    """
    objects = _visible_object_bodies(text)
    object_count = len(objects)
    object_offsets = [(index + 1) * BLOCK_SIZE for index in range(object_count)]
    xref_offset = (object_count + 1) * BLOCK_SIZE

    units = [_pad_right(PDF_HEADER)]
    units.extend(_pad_right(body) for body in objects)
    units.append(_pad_right(_build_xref(object_offsets)))
    units.append(_pad_right(_build_trailer(object_count)))
    units.append(_pad_right(_build_startxref(xref_offset)))
    units.append(_pad_left(PDF_EOF))

    if len(units) != VISIBLE_EXPECTED_FRAGMENT_COUNT:
        raise ValueError(
            f"expected {VISIBLE_EXPECTED_FRAGMENT_COUNT} structural units, built {len(units)}"
        )

    return b"".join(units)


def write_visible_dataset(
    out_dir: str | Path,
    seed: int = VISIBLE_DEFAULT_SEED,
    text: str = VISIBLE_TEXT_CONTENT,
) -> dict:
    """Write the visible ground truth, evidence blob and manifest under ``out_dir``."""
    out = Path(out_dir)
    groundtruth_dir = out / "groundtruth"
    evidence_dir = out / "evidence"
    groundtruth_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    pdf = build_visible_text_pdf(text)
    blob, permutation = shuffle_fragments(pdf, seed)

    kinds = (
        [KIND_HEADER]
        + [KIND_OBJECT] * VISIBLE_OBJECT_COUNT
        + [KIND_XREF, KIND_TRAILER, KIND_STARTXREF, KIND_EOF]
    )
    blocks = split_blocks(pdf)
    fragments = []
    for position, original_index in enumerate(permutation):
        digest = sha256_bytes(blocks[original_index])
        fragments.append(
            {
                "fragment_id": content_id("frag", digest),
                "blob_offset": position * BLOCK_SIZE,
                "length": BLOCK_SIZE,
                "sha256": digest,
                "source_offset": original_index * BLOCK_SIZE,
                "original_index": original_index,
                "kind": kinds[original_index],
                "object_number": (
                    original_index if 1 <= original_index <= VISIBLE_OBJECT_COUNT else None
                ),
            }
        )

    manifest = {
        "dataset_format_version": DATASET_FORMAT_VERSION,
        "generator": {"name": "trace-evidence", "version": __version__},
        "seed": seed,
        "block_size": BLOCK_SIZE,
        "fragment_count": len(permutation),
        "text_content": text,
        "original": {
            "name": "visible_text.pdf",
            "path": "groundtruth/visible_text.pdf",
            "size": len(pdf),
            "sha256": sha256_bytes(pdf),
            "block_count": len(blocks),
        },
        "blob": {
            "name": "blob_visible_text.bin",
            "path": "evidence/blob_visible_text.bin",
            "size": len(blob),
            "sha256": sha256_bytes(blob),
        },
        "permutation": list(permutation),
        "fragments": fragments,
    }

    pdf_path = groundtruth_dir / manifest["original"]["name"]
    blob_path = evidence_dir / manifest["blob"]["name"]
    manifest_path = out / "manifest_visible_text.json"

    pdf_path.write_bytes(pdf)
    blob_path.write_bytes(blob)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    return {
        "dataset_dir": str(out),
        "pdf_path": str(pdf_path),
        "blob_path": str(blob_path),
        "manifest_path": str(manifest_path),
        "manifest": manifest,
    }


def write_visible_missing_dataset(
    out_dir: str | Path,
    seed: int = VISIBLE_DEFAULT_SEED,
    text: str = VISIBLE_TEXT_CONTENT,
) -> dict:
    """Write the missing-fragment evidence blob derived directly from the working synthetic fixture.

    Removes fragments 8 (startxref) and 9 (eof) from the 10-fragment visible text fixture,
    leaving 8 blocks (2048 bytes) covering Header, Objects 1-5, Xref, and Trailer.
    """
    out = Path(out_dir)
    groundtruth_dir = out / "groundtruth"
    evidence_dir = out / "evidence"
    groundtruth_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    pdf = build_visible_text_pdf(text)
    full_blob, permutation = shuffle_fragments(pdf, seed)
    blocks = split_blocks(pdf)

    # Filter out blocks 8 (startxref) and 9 (eof)
    missing_indices = {8, 9}
    missing_permutation = [idx for idx in permutation if idx not in missing_indices]
    missing_blob = b"".join(blocks[idx] for idx in missing_permutation)

    kinds = (
        [KIND_HEADER]
        + [KIND_OBJECT] * VISIBLE_OBJECT_COUNT
        + [KIND_XREF, KIND_TRAILER, KIND_STARTXREF, KIND_EOF]
    )

    fragments = []
    for position, original_index in enumerate(missing_permutation):
        digest = sha256_bytes(blocks[original_index])
        fragments.append(
            {
                "fragment_id": content_id("frag", digest),
                "blob_offset": position * BLOCK_SIZE,
                "length": BLOCK_SIZE,
                "sha256": digest,
                "source_offset": original_index * BLOCK_SIZE,
                "original_index": original_index,
                "kind": kinds[original_index],
                "object_number": (
                    original_index if 1 <= original_index <= VISIBLE_OBJECT_COUNT else None
                ),
            }
        )

    manifest = {
        "dataset_format_version": DATASET_FORMAT_VERSION,
        "generator": {"name": "trace-evidence", "version": __version__},
        "seed": seed,
        "block_size": BLOCK_SIZE,
        "fragment_count": len(missing_permutation),
        "missing_fragment_count": len(missing_indices),
        "missing_original_indices": sorted(list(missing_indices)),
        "text_content": text,
        "original": {
            "name": "visible_text.pdf",
            "path": "groundtruth/visible_text.pdf",
            "size": len(pdf),
            "sha256": sha256_bytes(pdf),
            "block_count": len(blocks),
        },
        "blob": {
            "name": "blob_visible_text_missing.bin",
            "path": "evidence/blob_visible_text_missing.bin",
            "size": len(missing_blob),
            "sha256": sha256_bytes(missing_blob),
        },
        "permutation": list(missing_permutation),
        "fragments": fragments,
    }

    pdf_path = groundtruth_dir / manifest["original"]["name"]
    blob_path = evidence_dir / manifest["blob"]["name"]
    manifest_path = out / "manifest_visible_text_missing.json"

    pdf_path.write_bytes(pdf)
    blob_path.write_bytes(missing_blob)
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    return {
        "dataset_dir": str(out),
        "pdf_path": str(pdf_path),
        "blob_path": str(blob_path),
        "manifest_path": str(manifest_path),
        "manifest": manifest,
    }

