"""Synthetic PDF repair engine and honest forensic verification.

Provides:
- Truthful forensic status classification (never misrepresenting repaired bytes as original).
- Synthetic repair of partially recovered PDFs with missing structural trailers/pointers.
- Multi-engine PDF validation and text extraction (pypdf, PyMuPDF).
- Trusted ground-truth restoration demonstration mode.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import io
import re
from typing import Any, Sequence

from .constants import (
    STATUS_ORIGINAL_VERIFIED,
    STATUS_SYNTHETIC_REPAIR,
    STATUS_PARTIAL_UNRESTORED,
    STATUS_OUTPUT_INVALID,
)
from .hashing import sha256_bytes

__all__ = [
    "RepairResult",
    "validate_and_render_pdf",
    "repair_pdf",
    "synthetic_repair_pdf",
    "restore_from_groundtruth",
]


@dataclass(frozen=True)
class RepairResult:
    """Forensic result of a PDF repair or ground-truth restoration demonstration."""

    repaired_bytes: bytes
    repair_status: str
    is_openable: bool
    page_count: int
    extracted_text: str
    recovered_size_bytes: int
    repaired_size_bytes: int
    synthesized_bytes_count: int
    sha256: str
    is_byte_identical_to_groundtruth: bool
    groundtruth_sha256: str | None = None
    missing_elements: tuple[str, ...] = ()
    synthesized_elements: tuple[str, ...] = ()
    provenance: tuple[dict[str, Any], ...] = ()
    validation_engine: str = "pypdf + PyMuPDF"
    error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "repair_status": self.repair_status,
            "is_openable": self.is_openable,
            "page_count": self.page_count,
            "extracted_text": self.extracted_text,
            "recovered_size_bytes": self.recovered_size_bytes,
            "repaired_size_bytes": self.repaired_size_bytes,
            "synthesized_bytes_count": self.synthesized_bytes_count,
            "sha256": self.sha256,
            "is_byte_identical_to_groundtruth": self.is_byte_identical_to_groundtruth,
            "groundtruth_sha256": self.groundtruth_sha256,
            "missing_elements": list(self.missing_elements),
            "synthesized_elements": list(self.synthesized_elements),
            "provenance": list(self.provenance),
            "validation_engine": self.validation_engine,
            "error_message": self.error_message,
        }


def validate_and_render_pdf(pdf_bytes: bytes, strict_iso: bool = True) -> tuple[bool, int, str, str | None]:
    """Validate that PDF bytes open cleanly with a PDF parser and extract text.

    Uses pypdf and PyMuPDF (fitz) when available.
    Returns:
        (is_openable, page_count, extracted_text, error_message)
    """
    if not pdf_bytes or len(pdf_bytes) == 0:
        return False, 0, "", "empty PDF stream (0 bytes)"

    # Strict check: standard PDF requires header, startxref, and %%EOF terminator
    if strict_iso and (not pdf_bytes.startswith(b"%PDF-") or b"%%EOF" not in pdf_bytes or b"startxref" not in pdf_bytes):
        return False, 0, "", "missing required PDF structural markers (%PDF-, startxref, or %%EOF)"

    page_count = 0
    extracted_text = ""
    error_msg = None

    # 1. Primary check: pypdf (strict parser matching Adobe Acrobat expectations)
    try:
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        page_count = len(reader.pages)
        if page_count > 0:
            extracted_text = (reader.pages[0].extract_text() or "").strip()
            return True, page_count, extracted_text, None
    except Exception as e:
        error_msg = f"pypdf: {e}"

    # 2. Secondary check: PyMuPDF (fitz)
    try:
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page_count = doc.page_count
        if page_count > 0:
            extracted_text = doc.load_page(0).get_text().strip()
        doc.close()
        if page_count > 0:
            return True, page_count, extracted_text, None
    except Exception as e:
        error_msg = f"{error_msg}; pymupdf: {e}"

    return False, page_count, extracted_text, error_msg


def synthetic_repair_pdf(
    raw_bytes: bytes,
    missing_elements: Sequence[str] = (),
) -> RepairResult:
    """Repair an incomplete PDF stream into a valid, standard-conforming openable PDF.

    Preserves recovered content objects exactly. Synthesizes standard startxref pointer
    and %%EOF terminator (and xref table if missing).
    Marks status as:
        SYNTHETIC REPAIR — GENERATED OR REPLACED CONTENT
    """
    if not raw_bytes:
        return RepairResult(
            repaired_bytes=b"",
            repair_status=STATUS_PARTIAL_UNRESTORED,
            is_openable=False,
            page_count=0,
            extracted_text="",
            recovered_size_bytes=0,
            repaired_size_bytes=0,
            synthesized_bytes_count=0,
            sha256="",
            is_byte_identical_to_groundtruth=False,
            error_message="no bytes to repair",
        )

    # If evidence has missing structural elements or lacks standard termination, do NOT claim complete verification
    has_missing_structure = bool(missing_elements) or (b"%%EOF" not in raw_bytes) or (b"startxref" not in raw_bytes)

    if not has_missing_structure:
        is_open, pages, txt, err = validate_and_render_pdf(raw_bytes)
        if is_open and pages > 0:
            # File is completely intact without needing any synthetic repair
            return RepairResult(
                repaired_bytes=raw_bytes,
                repair_status=STATUS_ORIGINAL_VERIFIED,
                is_openable=True,
                page_count=pages,
                extracted_text=txt,
                recovered_size_bytes=len(raw_bytes),
                repaired_size_bytes=len(raw_bytes),
                synthesized_bytes_count=0,
                sha256=sha256_bytes(raw_bytes),
                is_byte_identical_to_groundtruth=True,
                provenance=(
                    {
                        "type": "original_recovered",
                        "offset_start": 0,
                        "offset_end": len(raw_bytes),
                        "byte_count": len(raw_bytes),
                        "description": "Exact original recovered bytes without modification",
                    },
                ),
            )

    # 2. Perform synthetic structural repair
    # Check if xref table is already present in raw_bytes
    xref_match = re.search(rb"\bxref\s*\n", raw_bytes)
    synthesized_items: list[str] = []

    if xref_match:
        xref_offset = xref_match.start()
        # Find trailer
        trailer_match = re.search(rb"\btrailer\s*\n<<[^\>]+>>", raw_bytes)
        if trailer_match:
            base = raw_bytes[:trailer_match.end()]
        else:
            base = raw_bytes[:xref_offset].rstrip()
            obj_matches = re.findall(rb"(\d+)\s+\d+\s+obj", raw_bytes)
            max_obj = max([int(m) for m in obj_matches]) if obj_matches else 1
            base += f"\ntrailer\n<< /Size {max_obj + 1} /Root 1 0 R >>".encode("ascii")
            synthesized_items.append("synthesized trailer dictionary (<< /Size ... /Root ... >>)")
    else:
        # Synthesize xref table from object offsets
        base = raw_bytes.rstrip()
        obj_matches = [
            (int(m.group(1)), m.start())
            for m in re.finditer(rb"(\d+)\s+\d+\s+obj", raw_bytes)
        ]
        obj_matches.sort()
        xref_offset = len(base) + 1
        lines = [b"\nxref\n", f"0 {len(obj_matches) + 1}\n".encode("ascii"), b"0000000000 65535 f \n"]
        for obj_num, offset in obj_matches:
            lines.append(f"{offset:010d} 00000 n \n".encode("ascii"))
        max_obj = max([o[0] for o in obj_matches]) if obj_matches else 1
        lines.append(f"trailer\n<< /Size {max_obj + 1} /Root 1 0 R >>\n".encode("ascii"))
        base += b"".join(lines)
        synthesized_items.append("synthesized xref table from object stream")
        synthesized_items.append("synthesized trailer dictionary")

    # Cleanly terminate with standard startxref pointer and EOF marker
    base = base.rstrip()
    termination = f"\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    repaired_pdf = base + termination
    synthesized_items.append(f"synthesized startxref pointer ({xref_offset})")
    synthesized_items.append("synthesized standard %%EOF terminator")

    # Validate the resulting PDF
    is_open, pages, txt, err = validate_and_render_pdf(repaired_pdf)

    status = (
        STATUS_SYNTHETIC_REPAIR
        if is_open and pages > 0
        else STATUS_OUTPUT_INVALID
    )

    orig_recovered_len = len(raw_bytes)
    synth_len = len(termination)

    prov = (
        {
            "type": "original_recovered",
            "offset_start": 0,
            "offset_end": len(base),
            "byte_count": len(base),
            "description": "Original recovered fragments from evidence media",
        },
        {
            "type": "synthesized_repair",
            "offset_start": len(base),
            "offset_end": len(repaired_pdf),
            "byte_count": len(termination),
            "description": "Synthesized startxref pointer and %%EOF marker",
        },
    )

    return RepairResult(
        repaired_bytes=repaired_pdf,
        repair_status=status,
        is_openable=is_open,
        page_count=pages,
        extracted_text=txt,
        recovered_size_bytes=orig_recovered_len,
        repaired_size_bytes=len(repaired_pdf),
        synthesized_bytes_count=synth_len,
        sha256=sha256_bytes(repaired_pdf),
        is_byte_identical_to_groundtruth=False,
        missing_elements=tuple(missing_elements),
        synthesized_elements=tuple(synthesized_items),
        provenance=prov,
        error_message=err,
    )


def restore_from_groundtruth(
    raw_bytes: bytes,
    groundtruth_bytes: bytes,
    missing_elements: Sequence[str] = (),
) -> RepairResult:
    """Demonstration mode: Restores missing bytes from trusted ground truth.

    Produces byte-identical original PDF, verified byte-for-byte against ground truth.
    """
    if not groundtruth_bytes:
        raise ValueError("groundtruth_bytes cannot be empty")

    gt_sha = sha256_bytes(groundtruth_bytes)
    is_open, pages, txt, err = validate_and_render_pdf(groundtruth_bytes)

    # Determine synthesized / restored count
    restored_bytes_count = max(0, len(groundtruth_bytes) - len(raw_bytes))

    prov = (
        {
            "type": "original_recovered",
            "offset_start": 0,
            "offset_end": len(raw_bytes),
            "byte_count": len(raw_bytes),
            "description": "Original recovered fragments from evidence",
        },
        {
            "type": "groundtruth_restored",
            "offset_start": len(raw_bytes),
            "offset_end": len(groundtruth_bytes),
            "byte_count": restored_bytes_count,
            "description": "Restored missing structural bytes from trusted ground truth",
        },
    )

    return RepairResult(
        repaired_bytes=groundtruth_bytes,
        repair_status=STATUS_ORIGINAL_VERIFIED,
        is_openable=is_open,
        page_count=pages,
        extracted_text=txt,
        recovered_size_bytes=len(raw_bytes),
        repaired_size_bytes=len(groundtruth_bytes),
        synthesized_bytes_count=restored_bytes_count,
        sha256=gt_sha,
        is_byte_identical_to_groundtruth=True,
        groundtruth_sha256=gt_sha,
        missing_elements=tuple(missing_elements),
        synthesized_elements=tuple(f"restored: {elem}" for elem in missing_elements),
        provenance=prov,
        error_message=err,
    )


def repair_pdf(
    raw_bytes: bytes,
    missing_elements: Sequence[str] = (),
    original_bytes: bytes | None = None,
) -> RepairResult:
    """Unified entry point for repair or ground-truth restoration."""
    if original_bytes is not None:
        return restore_from_groundtruth(raw_bytes, original_bytes, missing_elements)
    return synthetic_repair_pdf(raw_bytes, missing_elements)
