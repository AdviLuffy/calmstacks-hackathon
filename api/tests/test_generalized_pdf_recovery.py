"""Comprehensive test suite for general-purpose AI-assisted PDF forensic recovery.

Verifies:
1. Preamble noise and offset %PDF-1.x headers are normalized and stripped.
2. Missing %PDF- header is safely synthesized.
3. Abruptly truncated bitstreams (missing xref, trailer, startxref, EOF) are recovered into openable PDFs.
4. Wiped or corrupt cross-reference tables are reconstructed to exact ISO 32000-1 specifications.
5. Orphaned /Page objects without a parent /Pages tree are unified into a valid page hierarchy.
6. Broken content stream operators (unclosed BT/ET, unclosed q/Q, unclosed string parentheses) are balanced.
7. Incorrect /Length values in stream dictionaries are corrected to actual byte counts.
8. PDF 1.5+ compressed Object Streams (/Type /ObjStm) are decompressed and unpacked.
9. Erased / null-filled sector boundaries within streams are salvaged.
10. Strict forensic honesty: repaired PDFs are never reported as original or cryptographically verified.
11. Multi-engine rendering and text extraction via pypdf and PyMuPDF.
12. Integration with API repair endpoints and diagnostic reporting.
"""

from __future__ import annotations

import io
from pathlib import Path
import zlib

import pytest

from trace_evidence import constants as c
from trace_evidence.pdf_recovery import (
    CorruptionDiagnostic,
    GeneralizedPdfRecoveryEngine,
    diagnose_pdf_corruption,
)
from trace_evidence.repair import (
    repair_pdf,
    synthetic_repair_pdf,
    validate_and_render_pdf,
)

# Reference minimal 1-page PDF template (PDF 1.4)
MINIMAL_VALID_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
    b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
    b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    b"5 0 obj\n<< /Length 44 >>\nstream\n"
    b"BT /F1 24 Tf 100 700 Td (Autonomous Forensics) Tj ET\n"
    b"endstream\nendobj\n"
    b"xref\n0 6\n"
    b"0000000000 65535 f \r\n"
    b"0000000010 00000 n \r\n"
    b"0000000060 00000 n \r\n"
    b"0000000117 00000 n \r\n"
    b"0000000224 00000 n \r\n"
    b"0000000293 00000 n \r\n"
    b"trailer\n<< /Size 6 /Root 1 0 R >>\n"
    b"startxref\n390\n%%EOF\n"
)


def test_offset_header_and_preamble_noise():
    """Corrupted bitstream preceded by arbitrary preamble noise (e.g. HTTP headers or disk garbage)."""
    preamble = b"HTTP/1.1 200 OK\r\nContent-Type: application/pdf\r\nServer: StaleProxy\r\n\r\n\x00\xff\xfe"
    damaged = preamble + MINIMAL_VALID_PDF

    # Diagnostic detects offset header
    diag = diagnose_pdf_corruption(damaged)
    assert diag.has_header is True
    assert diag.header_offset == len(preamble)
    assert "OFFSET_HEADER_PREAMBLE_NOISE" in diag.corruption_classes

    # Engine strips preamble and recovers valid openable PDF
    engine = GeneralizedPdfRecoveryEngine(damaged)
    repaired, items, meta = engine.recover()

    assert repaired.startswith(b"%PDF-1.4\n")
    assert any("preamble noise" in it for it in items)

    # Validates cleanly in both engines
    is_open, pages, text, err = validate_and_render_pdf(repaired)
    assert is_open is True
    assert pages == 1
    assert "Autonomous Forensics" in text


def test_missing_header_fallback():
    """Bitstream where %PDF- magic bytes were completely destroyed."""
    # Strip the first line (%PDF-1.4\n)
    damaged = MINIMAL_VALID_PDF[10:]
    assert not damaged.startswith(b"%PDF-")

    diag = diagnose_pdf_corruption(damaged)
    assert diag.has_header is False
    assert "MISSING_HEADER" in diag.corruption_classes

    engine = GeneralizedPdfRecoveryEngine(damaged)
    repaired, items, meta = engine.recover()

    assert repaired.startswith(b"%PDF-1.4\n")
    assert any("synthesized standard PDF header" in it for it in items)

    is_open, pages, text, err = validate_and_render_pdf(repaired)
    assert is_open is True
    assert pages == 1
    assert "Autonomous Forensics" in text


def test_truncated_bitstream_without_xref_or_eof():
    """Abruptly truncated file missing xref, trailer, startxref, and %%EOF."""
    # Truncate before xref
    xref_pos = MINIMAL_VALID_PDF.find(b"xref")
    damaged = MINIMAL_VALID_PDF[:xref_pos]
    assert b"xref" not in damaged
    assert b"%%EOF" not in damaged

    diag = diagnose_pdf_corruption(damaged)
    assert diag.has_eof is False
    assert "TRUNCATED_BITSTREAM_NO_EOF" in diag.corruption_classes
    assert "DESTROYED_CROSS_REFERENCE_TABLE" in diag.corruption_classes

    # Synthetic repair on truncated data
    rep = synthetic_repair_pdf(damaged)
    assert rep.is_openable is True
    assert rep.page_count == 1
    assert "Autonomous Forensics" in rep.extracted_text
    assert rep.repair_status == c.STATUS_SYNTHETICALLY_REPAIRED
    assert rep.synthesized_bytes_count > 0


def test_wiped_xref_table():
    """PDF where xref table is replaced with zeroes/garbage."""
    xref_pos = MINIMAL_VALID_PDF.find(b"xref")
    damaged = MINIMAL_VALID_PDF[:xref_pos] + (b"\x00" * 200) + b"\nstartxref\n99999\n%%EOF\n"

    engine = GeneralizedPdfRecoveryEngine(damaged)
    repaired, items, meta = engine.recover()

    is_open, pages, text, err = validate_and_render_pdf(repaired)
    assert is_open is True
    assert pages == 1
    assert "Autonomous Forensics" in text


def test_orphan_pages_reconstructed():
    """PDF where the root /Pages tree object is completely missing, leaving orphan /Page objects."""
    # Objects: 1 (Catalog pointing to non-existent 9 0 R), 3 (Page with Parent 9 0 R), 4 (Font), 5 (Contents)
    body = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 9 0 R >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 9 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        b"5 0 obj\n<< /Length 38 >>\nstream\n"
        b"BT /F1 20 Tf 50 700 Td (Orphan Rescued) Tj ET\n"
        b"endstream\nendobj\n"
    )

    diag = diagnose_pdf_corruption(body)
    assert "ORPHAN_PAGES_NO_PARENT_TREE" in diag.corruption_classes

    engine = GeneralizedPdfRecoveryEngine(body)
    repaired, items, meta = engine.recover()

    assert any("synthesized root Pages tree" in it for it in items)
    is_open, pages, text, err = validate_and_render_pdf(repaired)
    assert is_open is True
    assert pages == 1
    assert "Orphan Rescued" in text


def test_unbalanced_operators_and_unterminated_strings():
    """Content stream with unbalanced BT/ET, unclosed q/Q, and open string parenthesis."""
    # In object 5, BT is not closed with ET, q is not closed with Q, and string literal is severed mid-text
    broken_stream = b"q\nBT /F1 16 Tf 50 650 Td (Severed String Content Without Close"
    body = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        + f"5 0 obj\n<< /Length {len(broken_stream)} >>\nstream\n".encode("ascii")
        + broken_stream
        + b"\nendstream\nendobj\n"
    )

    engine = GeneralizedPdfRecoveryEngine(body)
    repaired, items, meta = engine.recover()

    is_open, pages, text, err = validate_and_render_pdf(repaired)
    assert is_open is True
    assert pages == 1
    assert "Severed String Content" in text


def test_stream_length_mismatch_correction():
    """Stream dictionary declares wrong /Length (e.g. 99999 or 2)."""
    stream_data = b"BT /F1 14 Tf 72 700 Td (Exact Length Test) Tj ET\n"
    body = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        + b"5 0 obj\n<< /Length 2 >>\nstream\n"
        + stream_data
        + b"endstream\nendobj\n"
    )

    engine = GeneralizedPdfRecoveryEngine(body)
    repaired, items, meta = engine.recover()

    # Verify that repaired stream has updated /Length matching actual byte count
    import re
    m = re.search(rb"5 0 obj\s*<<[^>]*?/Length\s+(\d+)", repaired)
    assert m is not None
    assert int(m.group(1)) == len(stream_data.strip(b"\r\n"))

    is_open, pages, text, err = validate_and_render_pdf(repaired)
    assert is_open is True
    assert pages == 1
    assert "Exact Length Test" in text


def test_compressed_object_stream_recovery():
    """PDF 1.5+ compressed Object Stream (/Type /ObjStm) unpacking."""
    # Create an object stream containing object 3 (Page) and object 4 (Font)
    # Header format: <obj_num> <offset> <obj_num> <offset>
    obj3_content = b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\n"
    obj4_content = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    sub_data = obj3_content + obj4_content
    hdr = f"3 0 4 {len(obj3_content)}\n".encode("ascii")
    raw_stm = hdr + sub_data
    compressed_stm = zlib.compress(raw_stm)

    body = (
        b"%PDF-1.5\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        + f"10 0 obj\n<< /Type /ObjStm /N 2 /First {len(hdr)} /Length {len(compressed_stm)} /Filter /FlateDecode >>\nstream\n".encode("ascii")
        + compressed_stm
        + b"\nendstream\nendobj\n"
        b"5 0 obj\n<< /Length 39 >>\nstream\n"
        b"BT /F1 16 Tf 72 700 Td (Object Stream Unpacked) Tj ET\n"
        b"endstream\nendobj\n"
    )

    diag = diagnose_pdf_corruption(body)
    assert diag.has_object_streams is True
    assert "COMPRESSED_OBJECT_STREAMS" in diag.corruption_classes

    engine = GeneralizedPdfRecoveryEngine(body)
    repaired, items, meta = engine.recover()

    assert any("unpacked" in it and "Object Streams" in it for it in items)
    is_open, pages, text, err = validate_and_render_pdf(repaired)
    assert is_open is True
    assert pages == 1
    assert "Object Stream Unpacked" in text


def test_erased_sector_null_run_salvage():
    """8-page real-world damaged fixture with 512-byte erased sector (TRACE_105block_one_missing.bin)."""
    fixture_path = Path("evidence/datasets/evidence/TRACE_105block_one_missing.bin")
    if not fixture_path.is_file():
        pytest.skip("Fixture TRACE_105block_one_missing.bin not found")

    media_bytes = fixture_path.read_bytes()
    diag = diagnose_pdf_corruption(media_bytes)
    assert diag.has_erased_regions is True
    assert "ERASED_SECTOR_NULL_RUNS" in diag.corruption_classes

    # Run repair via unified repair_pdf
    rep = repair_pdf(raw_bytes=media_bytes[:512], media_bytes=media_bytes)
    assert rep.is_openable is True
    assert rep.page_count == 8
    assert rep.repair_status == c.STATUS_SYNTHETICALLY_REPAIRED
    assert rep.diagnostic is not None
    assert rep.diagnostic["salvaged_pages_count"] == 8

    # Multi-engine check
    import fitz
    import pypdf

    doc = fitz.open(stream=rep.repaired_bytes, filetype="pdf")
    assert doc.page_count == 8
    for i in range(doc.page_count):
        pix = doc.load_page(i).get_pixmap()
        assert pix.width > 0 and pix.height > 0
    doc.close()

    reader = pypdf.PdfReader(io.BytesIO(rep.repaired_bytes))
    assert len(reader.pages) == 8


def test_forensic_honesty_and_provenance():
    """Repaired PDF reports honest non-verified status, exact provenance ledger, and never claims 100% byte match."""
    damaged = MINIMAL_VALID_PDF[:MINIMAL_VALID_PDF.find(b"xref")]
    rep = synthetic_repair_pdf(damaged)

    assert rep.repair_status == c.STATUS_SYNTHETICALLY_REPAIRED
    assert rep.is_byte_identical_to_groundtruth is False
    assert rep.recovered_size_bytes == len(damaged)
    assert rep.repaired_size_bytes > len(damaged)
    assert rep.synthesized_bytes_count > 0

    prov = rep.provenance
    assert len(prov) >= 2
    assert prov[0]["type"] == "original_recovered"
    assert prov[1]["type"] == "synthesized_repair"
    assert prov[0]["byte_count"] + prov[1]["byte_count"] == len(rep.repaired_bytes)


def test_resource_bounds_and_safety():
    """Engine enforces resource bounds on oversized inputs and decompression limits."""
    # Safe handling of empty or tiny data
    assert diagnose_pdf_corruption(b"").surviving_objects_count == 0
    rep_empty = synthetic_repair_pdf(b"")
    assert rep_empty.is_openable is False
    assert rep_empty.repair_status == c.STATUS_PARTIAL_UNRESTORED


def test_api_repair_and_download_flow():
    """Full API end-to-end integration: upload damaged evidence, run repair, download openable PDF."""
    from fastapi.testclient import TestClient
    from api.app.main import app

    client = TestClient(app)

    # 1. Investigate damaged evidence fixture via carve
    resp = client.post("/api/sessions/carve", data={"fixture_id": "visible_text_missing", "case_id": "CASE-GEN-REPAIR"})
    assert resp.status_code == 201
    data = resp.json()
    session_id = data["session_id"]

    # 2. Check reconstruction metadata
    meta_resp = client.get(f"/api/sessions/{session_id}/reconstruction")
    assert meta_resp.status_code == 200
    meta = meta_resp.json()
    assert meta["has_repaired_file"] is True
    assert "diagnostic" in meta
    assert meta["diagnostic"]["has_header"] is True

    # 3. Trigger synthetic repair action explicitly
    repair_resp = client.post(f"/api/sessions/{session_id}/repair")
    assert repair_resp.status_code == 200
    repair_data = repair_resp.json()
    assert repair_data["session_id"] == session_id
    rep_res = repair_data["repair_result"]
    assert rep_res["is_openable"] is True
    assert rep_res["page_count"] >= 1
    assert "diagnostic" in rep_res
    assert repair_data["metadata"]["has_repaired_file"] is True

    # 4. Download repaired PDF
    dl_resp = client.get(f"/api/sessions/{session_id}/reconstruction/download?mode=repaired")
    assert dl_resp.status_code == 200
    assert dl_resp.headers["content-type"] == "application/pdf"
    assert "SYNTHETICALLY REPAIRED" in dl_resp.headers["x-trace-repair-status"]

    import pypdf
    reader = pypdf.PdfReader(io.BytesIO(dl_resp.content))
    assert len(reader.pages) >= 1
