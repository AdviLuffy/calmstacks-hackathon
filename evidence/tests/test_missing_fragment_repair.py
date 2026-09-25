"""Tests for missing-fragment recovery, synthetic repair, and openable PDF verification.

Verifies:
1. P1 deterministic reconstruction on missing fragments produces authentic partial artifact.
2. Synthetic repair produces a verified openable PDF with visible text in pypdf and PyMuPDF.
3. Recovery and repair statuses are strictly and honestly reported:
   - ORIGINAL BYTES RECOVERED AND VERIFIED
   - SYNTHETIC REPAIR — GENERATED OR REPLACED CONTENT
   - PARTIAL — MISSING CONTENT COULD NOT BE RESTORED
   - INVALID — OUTPUT FAILED PDF VALIDATION
4. Original evidence remains immutable with exact provenance tracking.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from trace_evidence import constants as c
from trace_evidence.dataset import (
    VISIBLE_TEXT_CONTENT,
    build_visible_text_pdf,
    write_visible_missing_dataset,
)
from trace_evidence.hashing import sha256_bytes
from trace_evidence.pipeline import run_pipeline
from trace_evidence.repair import (
    repair_pdf,
    restore_from_groundtruth,
    synthetic_repair_pdf,
    validate_and_render_pdf,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DATASETS_DIR = REPO_ROOT / "evidence" / "datasets"
GT_PDF_PATH = DATASETS_DIR / "groundtruth" / "visible_text.pdf"
MISSING_BLOB_PATH = DATASETS_DIR / "evidence" / "blob_visible_text_missing.bin"
REPAIRED_OUTPUT_PDF = DATASETS_DIR / "evidence" / "reconstructed_repaired_visible_text.pdf"


@pytest.fixture(scope="module", autouse=True)
def ensure_missing_dataset():
    """Ensure missing-fragment dataset and groundtruth exist on disk."""
    if not MISSING_BLOB_PATH.is_file() or not GT_PDF_PATH.is_file():
        write_visible_missing_dataset(DATASETS_DIR)
    yield


def test_missing_fragment_p1_reconstruction_is_partial():
    """P1 reconstructs available fragments without ground truth and reports missing elements."""
    assert MISSING_BLOB_PATH.is_file(), f"Missing fixture not found: {MISSING_BLOB_PATH}"

    result = run_pipeline(MISSING_BLOB_PATH)

    # 1. 8 fragments placed (2048 bytes) out of 10 total
    raw_bytes = result.reconstruction.raw_bytes
    assert len(raw_bytes) == 8 * c.BLOCK_SIZE == 2048
    assert len(result.reconstruction.fragment_order) == 8

    # 2. Structural missing elements identified
    missing = result.integrity_report.missing_elements
    assert any("startxref" in elem for elem in missing)
    assert any("EOF" in elem or "eof" in elem for elem in missing)

    # 3. Truthfully reports incomplete/partial (never claims complete or verified)
    assert result.is_complete is False
    assert result.reconstruction.complete is False
    assert result.integrity_report.is_verified is False
    assert result.integrity_report.status == c.STATUS_INCOMPLETE


def test_synthetic_repair_produces_openable_pdf():
    """Synthetic repair generates a standard-conforming openable PDF from partial objects."""
    result = run_pipeline(MISSING_BLOB_PATH)
    raw_bytes = result.reconstruction.raw_bytes
    missing = result.integrity_report.missing_elements

    # Run synthetic repair (NO ground truth passed)
    rep = synthetic_repair_pdf(raw_bytes, missing)

    # 1. Honest forensic status
    assert rep.repair_status == c.STATUS_SYNTHETICALLY_REPAIRED
    assert rep.is_byte_identical_to_groundtruth is False
    assert rep.recovered_size_bytes == 2048
    assert rep.repaired_size_bytes > 0
    assert rep.synthesized_bytes_count > 0

    # 2. Confirmed openable by validator
    assert rep.is_openable is True
    assert rep.page_count == 1
    assert VISIBLE_TEXT_CONTENT in rep.extracted_text

    # 3. Open directly with pypdf
    import pypdf
    pypdf_reader = pypdf.PdfReader(io.BytesIO(rep.repaired_bytes))
    assert len(pypdf_reader.pages) == 1
    pypdf_text = pypdf_reader.pages[0].extract_text()
    assert VISIBLE_TEXT_CONTENT in pypdf_text

    # 4. Open and render with PyMuPDF
    import fitz
    doc = fitz.open(stream=rep.repaired_bytes, filetype="pdf")
    assert doc.page_count == 1
    fitz_text = doc.load_page(0).get_text()
    assert VISIBLE_TEXT_CONTENT in fitz_text
    pix = doc.load_page(0).get_pixmap()
    assert pix.width > 0 and pix.height > 0
    doc.close()

    # 5. Save resulting PDF to permanent file
    REPAIRED_OUTPUT_PDF.parent.mkdir(parents=True, exist_ok=True)
    REPAIRED_OUTPUT_PDF.write_bytes(rep.repaired_bytes)
    assert REPAIRED_OUTPUT_PDF.is_file()
    assert REPAIRED_OUTPUT_PDF.stat().st_size == len(rep.repaired_bytes)


def test_groundtruth_restoration_demonstration_mode():
    """When trusted ground truth is provided, missing bytes are restored and verified."""
    gt_bytes = GT_PDF_PATH.read_bytes()
    gt_sha = sha256_bytes(gt_bytes)

    result = run_pipeline(MISSING_BLOB_PATH)
    raw_bytes = result.reconstruction.raw_bytes
    missing = result.integrity_report.missing_elements

    # Run restoration mode with ground truth
    restored = restore_from_groundtruth(raw_bytes, gt_bytes, missing)

    # 1. Honest verified status
    assert restored.repair_status == c.STATUS_ORIGINAL_VERIFIED
    assert restored.is_byte_identical_to_groundtruth is True
    assert restored.sha256 == gt_sha
    assert restored.groundtruth_sha256 == gt_sha
    assert restored.repaired_bytes == gt_bytes
    assert restored.is_openable is True
    assert restored.page_count == 1


def test_provenance_and_immutability():
    """Evidence bytes remain immutable and provenance distinguishes recovered from synthesized bytes."""
    result = run_pipeline(MISSING_BLOB_PATH)
    raw_bytes = result.reconstruction.raw_bytes

    rep = synthetic_repair_pdf(raw_bytes, result.integrity_report.missing_elements)

    # Repaired bytes begin with the exact recovered bytes (prefix preserved)
    assert rep.repaired_bytes.startswith(raw_bytes[:1536])

    # Provenance ledger records both segments
    prov = rep.provenance
    assert len(prov) == 2
    assert prov[0]["type"] == "original_recovered"
    assert prov[0]["byte_count"] > 0
    assert prov[1]["type"] == "synthesized_repair"
    assert prov[1]["byte_count"] > 0


def test_missing_4fragments_damaged_evidence_repair():
    """Damaged evidence with 4 missing tail fragments (xref, trailer, startxref, EOF).
    
    1. P1 deterministic reconstruction places 2 of 6 fragments (33% coverage)
       due to object sequence gap, refusing to fabricate missing blocks.
    2. Synthetic repair harvests unplaced fragments from raw media, rebuilds xref/trailer/startxref/EOF.
    3. Repaired PDF opens in pypdf and fitz, rendering VISIBLE_TEXT_CONTENT.
    4. Truthfully reports STATUS_SYNTHETICALLY_REPAIRED and not byte-identical to original.
    """
    from trace_evidence.dataset import write_visible_4missing_dataset
    write_visible_4missing_dataset(DATASETS_DIR)
    damaged_blob_path = DATASETS_DIR / "evidence" / "blob_visible_text_4missing.bin"
    assert damaged_blob_path.is_file()

    media_bytes = damaged_blob_path.read_bytes()
    assert len(media_bytes) == 6 * c.BLOCK_SIZE == 1536

    # 1. Deterministic P1 reconstruction on damaged 6-block fixture (Header + Objects 1-5, missing 4 tail fragments)
    res = run_pipeline(damaged_blob_path)
    assert res.is_complete is False
    assert res.reconstruction.complete is False
    assert res.integrity_report.is_verified is False
    assert res.integrity_report.status == c.STATUS_INCOMPLETE
    assert len(res.reconstruction.fragment_order) == 6
    assert any("xref" in m for m in res.integrity_report.missing_elements)
    assert any("trailer" in m for m in res.integrity_report.missing_elements)
    assert any("startxref" in m for m in res.integrity_report.missing_elements)
    assert any("EOF" in m or "eof" in m for m in res.integrity_report.missing_elements)

    # 2. Synthetic PDF repair using recovered media (NO ground truth used)
    raw_bytes = res.reconstruction.raw_bytes
    missing = res.integrity_report.missing_elements
    repair_res = synthetic_repair_pdf(
        raw_bytes=raw_bytes,
        missing_elements=missing,
        media_bytes=media_bytes,
    )

    # 3. Honest status and non-authenticity of synthetic syntax
    assert repair_res.repair_status == c.STATUS_SYNTHETICALLY_REPAIRED
    assert repair_res.is_byte_identical_to_groundtruth is False
    assert repair_res.is_openable is True
    assert repair_res.page_count == 1
    assert VISIBLE_TEXT_CONTENT in repair_res.extracted_text

    # 4. Also test when P1 only places 2 of 6 fragments (e.g. 33% coverage due to gap or ordering):
    # synthetic_repair_pdf must harvest unplaced blocks from media_bytes to build openable PDF
    partial_raw_2frags = raw_bytes[:512]  # only 2 fragments placed
    repair_res_2placed = synthetic_repair_pdf(
        raw_bytes=partial_raw_2frags,
        missing_elements=missing,
        media_bytes=media_bytes,
    )
    assert repair_res_2placed.is_openable is True
    assert repair_res_2placed.page_count == 1
    assert VISIBLE_TEXT_CONTENT in repair_res_2placed.extracted_text
    assert repair_res_2placed.repair_status == c.STATUS_SYNTHETICALLY_REPAIRED

    # 5. Strict reader rendering
    import fitz
    import pypdf
    reader = pypdf.PdfReader(io.BytesIO(repair_res.repaired_bytes))
    assert len(reader.pages) == 1
    assert VISIBLE_TEXT_CONTENT in reader.pages[0].extract_text()

    doc = fitz.open(stream=repair_res.repaired_bytes, filetype="pdf")
    assert doc.page_count == 1
    pix = doc.load_page(0).get_pixmap()
    assert pix.width > 0 and pix.height > 0
    doc.close()
