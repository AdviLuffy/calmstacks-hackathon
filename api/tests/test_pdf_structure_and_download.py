"""Regression and validation tests for reconstructed PDF structure, download endpoints, and ISO 32000-1 content validation."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
GROUNDTRUTH_PDF = REPO_ROOT / "evidence" / "datasets" / "groundtruth" / "synthetic.pdf"
BLOB_1337 = REPO_ROOT / "evidence" / "datasets" / "evidence" / "blob_1337.bin"

EXPECTED_GROUNDTRUTH_SHA256 = "1ba5d499d667001095a9fefa4d57551538f742824bb2e2de1feae5e224d64caf"
EXPECTED_BLOB_SHA256 = "2ef92ac2f6546f4036fe0223cf55e9ddad03371e30e451837cac03bc7d83ead6"

VISIBLE_GROUNDTRUTH_PDF = REPO_ROOT / "evidence" / "datasets" / "groundtruth" / "visible_text.pdf"
BLOB_VISIBLE_TEXT = REPO_ROOT / "evidence" / "datasets" / "evidence" / "blob_visible_text.bin"
EXPECTED_VISIBLE_PDF_SHA256 = "9decf803a2cc4688356ebe1f6788ab577c637ec0f54cfd9dd52fae3b236435f2"
EXPECTED_VISIBLE_BLOB_SHA256 = "58e7de08b02f1808492632ad09275ee141bab20d994651ef10e2bded8ecaf032"


@pytest.fixture
def integrated_client(make_client) -> TestClient:
    from p3_helpers import make_settings, make_wiring
    from app.services.session_store import InMemorySessionStore

    return make_client(
        settings=make_settings(),
        wiring=make_wiring(),
        store=InMemorySessionStore(),
    )


def test_blob_1337_reconstruction_fidelity_and_hashes(integrated_client):
    """Verify that carving blob_1337.bin reconstructs byte-for-byte identical output to synthetic.pdf."""
    # 1. Verify fixture integrity
    assert BLOB_1337.is_file(), f"missing fixture: {BLOB_1337}"
    blob_bytes = BLOB_1337.read_bytes()
    assert len(blob_bytes) == 2048
    assert hashlib.sha256(blob_bytes).hexdigest() == EXPECTED_BLOB_SHA256

    assert GROUNDTRUTH_PDF.is_file(), f"missing ground truth: {GROUNDTRUTH_PDF}"
    gt_bytes = GROUNDTRUTH_PDF.read_bytes()
    assert len(gt_bytes) == 2048
    assert hashlib.sha256(gt_bytes).hexdigest() == EXPECTED_GROUNDTRUTH_SHA256

    # 2. Carve via API
    r_carve = integrated_client.post(
        "/api/sessions/carve",
        data={"fixture_id": "synthetic_blob", "case_id": "CASE-PDF-REGRESSION"},
    )
    assert r_carve.status_code == 201
    session_id = r_carve.json()["session_id"]

    # 3. Download reconstructed PDF
    r_dl = integrated_client.get(f"/api/sessions/{session_id}/reconstruction/download")
    assert r_dl.status_code == 200
    assert r_dl.headers["content-type"] == "application/pdf"
    assert f'filename="reconstructed_{session_id}.pdf"' in r_dl.headers["content-disposition"]
    assert "attachment" in r_dl.headers["content-disposition"]

    downloaded_bytes = r_dl.content
    assert len(downloaded_bytes) == 2048, "Downloaded PDF must be exactly 2048 bytes"
    assert hashlib.sha256(downloaded_bytes).hexdigest() == EXPECTED_GROUNDTRUTH_SHA256
    assert downloaded_bytes == gt_bytes, "Downloaded bytes must be 100% identical to ground truth"


def test_reconstruction_inline_view_endpoint(integrated_client):
    """Verify that GET /sessions/{id}/reconstruction/view serves the file inline for browser rendering."""
    r_carve = integrated_client.post(
        "/api/sessions/carve",
        data={"fixture_id": "synthetic_blob", "case_id": "CASE-PDF-VIEW"},
    )
    session_id = r_carve.json()["session_id"]

    r_view = integrated_client.get(f"/api/sessions/{session_id}/reconstruction/view")
    assert r_view.status_code == 200
    assert r_view.headers["content-type"] == "application/pdf"
    assert f'filename="reconstructed_{session_id}.pdf"' in r_view.headers["content-disposition"]
    assert "inline" in r_view.headers["content-disposition"]
    assert len(r_view.content) == 2048
    assert hashlib.sha256(r_view.content).hexdigest() == EXPECTED_GROUNDTRUTH_SHA256


def test_reconstruction_metadata_and_structural_introspection(integrated_client):
    """Verify that GET /sessions/{id}/reconstruction returns accurate structural introspection."""
    r_carve = integrated_client.post(
        "/api/sessions/carve",
        data={"fixture_id": "synthetic_blob", "case_id": "CASE-PDF-META"},
    )
    session_id = r_carve.json()["session_id"]

    r_meta = integrated_client.get(f"/api/sessions/{session_id}/reconstruction")
    assert r_meta.status_code == 200
    data = r_meta.json()

    assert data["session_id"] == session_id
    assert data["status"] == "structurally_valid"
    assert data["complete"] is True
    # Per P1 Honesty Invariant #2, is_verified is False without test-only ground truth oracle
    assert data["is_verified"] is False
    assert data["reconstructed_sha256"] == EXPECTED_GROUNDTRUTH_SHA256
    assert data["pdf_size_bytes"] == 2048
    assert data["fragments_placed"] == 8

    # PDF Structural Telemetry
    ps = data.get("pdf_structure")
    assert ps is not None
    assert ps["version"] == "1.4"
    assert ps["is_valid_structure"] is True
    assert ps["page_count"] == 1
    assert ps["mediabox"] == [0, 0, 200, 200]
    assert ps["object_count"] == 3
    assert ps["object_ids"] == [1, 2, 3]
    assert ps["has_contents_stream"] is False
    assert ps["stream_count"] == 0
    assert ps["has_text_operators"] is False
    assert "ISO 32000-1 §7.7.3.3" in ps["specification_status"]
    assert ps["rendered_appearance"] == "blank_canvas_200x200"


def test_pdf_structural_validation_iso_32000_rules():
    """Verify groundtruth and reconstructed PDF adhere strictly to ISO 32000-1 rules.
    
    Under ISO 32000-1 Section 7.7.3.3 (Page Objects):
      '/Contents (Optional) A content stream that describes the contents of this page.
       If this entry is absent, the page is empty.'
    
    This confirms with mathematical certainty why PDF viewers render a blank 200x200 page:
    Object 3 has no /Contents stream, meaning the canvas is empty by design in the fixture.
    """
    pdf_bytes = GROUNDTRUTH_PDF.read_bytes()

    # 1. Valid PDF header
    assert pdf_bytes.startswith(b"%PDF-1.4\n")

    # 2. Valid PDF EOF marker
    assert pdf_bytes.rstrip().endswith(b"%%EOF")

    # 3. Object 1: Catalog
    assert b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj" in pdf_bytes

    # 4. Object 2: Pages tree
    assert b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj" in pdf_bytes

    # 5. Object 3: Page descriptor
    assert b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>\nendobj" in pdf_bytes

    # 6. Absence of /Contents and stream operators
    assert b"/Contents" not in pdf_bytes
    assert b"stream" not in pdf_bytes
    assert b"endstream" not in pdf_bytes
    assert b"BT" not in pdf_bytes  # Begin Text operator
    assert b"ET" not in pdf_bytes  # End Text operator

    # 7. Valid cross-reference table and trailer
    assert b"xref\n0 4\n0000000000 65535 f \n" in pdf_bytes
    assert b"trailer\n<< /Size 4 /Root 1 0 R >>\n" in pdf_bytes
    assert b"startxref\n1024\n" in pdf_bytes


def test_independent_pdf_content_validator_with_synthetic_text():
    """Verify that an independent validator correctly detects visible text streams when present."""
    from app.routers.dashboard import inspect_pdf_structure

    # 1. Blank synthetic PDF (blob_1337)
    blank_result = inspect_pdf_structure(GROUNDTRUTH_PDF.read_bytes())
    assert blank_result["has_contents_stream"] is False
    assert blank_result["has_text_operators"] is False
    assert blank_result["stream_count"] == 0
    assert blank_result["rendered_appearance"] == "blank_canvas_200x200"

    # 2. Test PDF with an injected visible text stream
    pdf_with_text = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents 4 0 R >> endobj\n"
        b"4 0 obj << /Length 44 >>\n"
        b"stream\n"
        b"BT /F1 12 Tf 50 150 Td (TRACE FORENSIC EVIDENCE) Tj ET\n"
        b"endstream\n"
        b"endobj\n"
        b"xref\n0 5\n0000000000 65535 f \n"
        b"trailer << /Size 5 /Root 1 0 R >>\nstartxref\n250\n%%EOF"
    )

    text_result = inspect_pdf_structure(pdf_with_text)
    assert text_result["is_valid_structure"] is True
    assert text_result["has_contents_stream"] is True
    assert text_result["stream_count"] == 1
    assert text_result["has_text_operators"] is True
    assert text_result["rendered_appearance"] == "rendered_content"


def test_visible_text_blob_carve_reconstruction_and_content(integrated_client):
    """Verify that carving blob_visible_text.bin reconstructs the exact visible-text PDF with text content."""
    # 1. Verify fixture files and hashes
    assert BLOB_VISIBLE_TEXT.is_file(), f"missing fixture: {BLOB_VISIBLE_TEXT}"
    blob_bytes = BLOB_VISIBLE_TEXT.read_bytes()
    assert len(blob_bytes) == 2560
    assert hashlib.sha256(blob_bytes).hexdigest() == EXPECTED_VISIBLE_BLOB_SHA256

    assert VISIBLE_GROUNDTRUTH_PDF.is_file(), f"missing ground truth: {VISIBLE_GROUNDTRUTH_PDF}"
    gt_bytes = VISIBLE_GROUNDTRUTH_PDF.read_bytes()
    assert len(gt_bytes) == 2560
    assert hashlib.sha256(gt_bytes).hexdigest() == EXPECTED_VISIBLE_PDF_SHA256
    assert b"TRACE FORENSIC RECONSTRUCTION TEST" in gt_bytes

    # 2. Carve via API
    r_carve = integrated_client.post(
        "/api/sessions/carve",
        data={"fixture_id": "visible_text_blob", "case_id": "CASE-VISIBLE-TEXT"},
    )
    assert r_carve.status_code == 201
    session_id = r_carve.json()["session_id"]

    # 3. Retrieve reconstruction metadata
    r_meta = integrated_client.get(f"/api/sessions/{session_id}/reconstruction")
    assert r_meta.status_code == 200
    meta = r_meta.json()
    assert meta["session_id"] == session_id
    assert meta["status"] == "structurally_valid"
    assert meta["complete"] is True
    assert meta["pdf_size_bytes"] == 2560
    assert meta["reconstructed_sha256"] == EXPECTED_VISIBLE_PDF_SHA256
    assert meta["fragments_placed"] == 10

    # Verify structural introspection for visible content
    ps = meta.get("pdf_structure")
    assert ps is not None
    assert ps["version"] == "1.4"
    assert ps["is_valid_structure"] is True
    assert ps["page_count"] == 1
    assert ps["mediabox"] == [0, 0, 400, 400]
    assert ps["object_count"] == 5
    assert ps["has_contents_stream"] is True
    assert ps["stream_count"] == 1
    assert ps["has_text_operators"] is True
    assert ps["rendered_appearance"] == "rendered_content"
    assert "active content streams" in ps["specification_status"].lower()

    # 4. Download reconstructed PDF bytes
    r_dl = integrated_client.get(f"/api/sessions/{session_id}/reconstruction/download")
    assert r_dl.status_code == 200
    assert r_dl.headers["content-type"] == "application/pdf"
    assert f'filename="reconstructed_{session_id}.pdf"' in r_dl.headers["content-disposition"]
    assert "attachment" in r_dl.headers["content-disposition"]

    dl_bytes = r_dl.content
    assert len(dl_bytes) == 2560
    assert hashlib.sha256(dl_bytes).hexdigest() == EXPECTED_VISIBLE_PDF_SHA256
    assert dl_bytes == gt_bytes, "Downloaded bytes must be 100% identical to ground truth visible_text.pdf"
    assert b"TRACE FORENSIC RECONSTRUCTION TEST" in dl_bytes

    # 5. Inline view endpoint
    r_view = integrated_client.get(f"/api/sessions/{session_id}/reconstruction/view")
    assert r_view.status_code == 200
    assert r_view.headers["content-type"] == "application/pdf"
    assert f'filename="reconstructed_{session_id}.pdf"' in r_view.headers["content-disposition"]
    assert r_view.content == gt_bytes


def test_missing_fragments_and_synthetic_repair_download(integrated_client):
    """Verify carving visible_text_missing yields partial recovery with openable synthetic repair."""
    import io
    import pypdf

    # 1. Carve missing fragments fixture
    r_carve = integrated_client.post(
        "/api/sessions/carve",
        data={"fixture_id": "visible_text_missing", "case_id": "CASE-MISSING-REPAIR"},
    )
    assert r_carve.status_code == 201
    session_id = r_carve.json()["session_id"]

    # 2. Retrieve reconstruction metadata
    r_meta = integrated_client.get(f"/api/sessions/{session_id}/reconstruction")
    assert r_meta.status_code == 200
    meta = r_meta.json()
    assert meta["session_id"] == session_id
    assert meta["complete"] is False
    assert meta["is_verified"] is False
    assert meta["recovery_state"] == "SYNTHETICALLY REPAIRED — NOT BYTE-IDENTICAL TO ORIGINAL"
    assert meta["has_repaired_file"] is True
    assert meta["repaired_is_openable"] is True
    assert meta["repaired_page_count"] == 1
    assert "TRACE FORENSIC RECONSTRUCTION TEST" in meta["repaired_extracted_text"]

    # 3. Download repaired openable PDF (mode=repaired)
    r_dl_rep = integrated_client.get(f"/api/sessions/{session_id}/reconstruction/download?mode=repaired")
    assert r_dl_rep.status_code == 200
    assert r_dl_rep.headers["content-type"] == "application/pdf"
    assert "repaired" in r_dl_rep.headers["content-disposition"]
    assert "SYNTHETIC" in r_dl_rep.headers["X-TRACE-Repair-Status"]

    rep_bytes = r_dl_rep.content
    assert len(rep_bytes) > 0
    # Must parse cleanly with pypdf
    reader = pypdf.PdfReader(io.BytesIO(rep_bytes))
    assert len(reader.pages) == 1
    assert "TRACE FORENSIC RECONSTRUCTION TEST" in reader.pages[0].extract_text()

    # 4. Download raw partial bytes (mode=raw)
    r_dl_raw = integrated_client.get(f"/api/sessions/{session_id}/reconstruction/download?mode=raw")
    assert r_dl_raw.status_code == 200
    assert len(r_dl_raw.content) == 2048


def test_4missing_fixture_and_repair_action(integrated_client):
    """Verify carving visible_text_4missing and executing POST /repair endpoint."""
    import io
    import pypdf

    # 1. Carve 4-missing damaged fixture
    r_carve = integrated_client.post(
        "/api/sessions/carve",
        data={"fixture_id": "visible_text_4missing", "case_id": "CASE-4MISSING"},
    )
    assert r_carve.status_code == 201
    session_id = r_carve.json()["session_id"]

    # 2. Check metadata: not marked as complete or verified
    r_meta = integrated_client.get(f"/api/sessions/{session_id}/reconstruction")
    assert r_meta.status_code == 200
    meta = r_meta.json()
    assert meta["complete"] is False
    assert meta["is_verified"] is False
    assert "SYNTHETIC" in meta["recovery_state"]
    assert meta["has_repaired_file"] is True
    assert meta["repaired_is_openable"] is True
    assert meta["repaired_page_count"] == 1
    assert "TRACE FORENSIC RECONSTRUCTION TEST" in meta["repaired_extracted_text"]

    # 3. Explicitly execute the Synthetic Repair (Demo) action endpoint
    r_repair = integrated_client.post(f"/api/sessions/{session_id}/repair")
    assert r_repair.status_code == 200
    repair_data = r_repair.json()
    assert repair_data["session_id"] == session_id
    res = repair_data["repair_result"]
    assert res["is_openable"] is True
    assert res["page_count"] == 1
    assert "TRACE FORENSIC RECONSTRUCTION TEST" in res["extracted_text"]
    assert res["repair_status"] == "SYNTHETICALLY REPAIRED — NOT BYTE-IDENTICAL TO ORIGINAL"
    assert res["is_byte_identical_to_groundtruth"] is False

    # 4. Download repaired PDF and check header
    r_dl = integrated_client.get(f"/api/sessions/{session_id}/reconstruction/download?mode=repaired")
    assert r_dl.status_code == 200
    assert "SYNTHETICALLY REPAIRED" in r_dl.headers["X-TRACE-Repair-Status"]
    assert "NOT BYTE-IDENTICAL TO ORIGINAL" in r_dl.headers["X-TRACE-Repair-Status"]
    rep_pdf = r_dl.content
    reader = pypdf.PdfReader(io.BytesIO(rep_pdf))
    assert len(reader.pages) == 1
    assert "TRACE FORENSIC RECONSTRUCTION TEST" in reader.pages[0].extract_text()

    # 5. Check investigation overview HTML does not show misleading COMPLETE badge
    r_page = integrated_client.get(f"/investigations/{session_id}")
    assert r_page.status_code == 200
    page_html = r_page.text
    assert "SYNTHETIC REPAIR (DEMO)" in page_html
    # Case badges separate PIPELINE from RECOVERY
    assert "PIPELINE: PROCESSED" in page_html


def test_cold_reconstruction_and_unconfigured_ai_analysis(integrated_client, monkeypatch):
    """Verify cold reconstruction fallback and truthful AI unconfigured state."""
    from app.routers.dashboard import _RECONSTRUCTED_META

    monkeypatch.setenv("TRACE_SKIP_DOTENV", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("TRACE_GEMINI_API_KEY", "")

    # 1. Carve a session
    r_carve = integrated_client.post(
        "/api/sessions/carve",
        data={"fixture_id": "visible_text_4missing", "case_id": "CASE-COLD-TEST"},
    )
    assert r_carve.status_code == 201
    session_id = r_carve.json()["session_id"]

    # 2. Simulate cold restart by clearing in-memory meta cache
    if session_id in _RECONSTRUCTED_META:
        del _RECONSTRUCTED_META[session_id]

    # 3. GET /reconstruction must gracefully succeed from bundle/disk without NoneType AttributeError
    r_rec = integrated_client.get(f"/api/sessions/{session_id}/reconstruction")
    assert r_rec.status_code == 200
    rec_data = r_rec.json()
    assert rec_data["session_id"] == session_id
    assert "status" in rec_data
    assert "reconstructed_sha256" in rec_data
    assert "pdf_structure" in rec_data

    # 4. GET /ai-analysis must return unconfigured message when GEMINI_API_KEY is not configured
    r_ai = integrated_client.get(f"/api/sessions/{session_id}/ai-analysis")
    assert r_ai.status_code == 200
    ai_data = r_ai.json()
    assert ai_data["configured"] is False
    assert ai_data["status"] == "unavailable"
    assert ai_data["message"] == "AI analysis unavailable — configure provider"
    assert ai_data["explanation"] is None

    # 5. Verify investigation page HTML contains robust JS loaders and timeouts
    r_html = integrated_client.get(f"/investigations/{session_id}")
    assert r_html.status_code == 200
    html_text = r_html.text
    assert "fetchWithTimeout" in html_text
    assert "loadSessionDetail" in html_text
    assert "loadEvidenceBundle" in html_text
    assert "loadReconstructionMetadata" in html_text
    assert "loadIntelligenceReport" in html_text
    assert "loadAiAnalysis" in html_text
    assert "AI analysis unavailable — configure provider" in html_text
    assert "triggerSyntheticRepair" in html_text


def test_105block_erased_recovery_and_synthetic_repair(integrated_client):
    """Verify carving TRACE_105block_one_missing.bin:
    1. Detects erased/zero-filled regions (slot 53 at [13312, 13568) and trailing blocks).
    2. Carves only valid non-zero fragments (98 fragments).
    3. Truthfully reports authentic recovery as PARTIAL without guessing missing data.
    4. Performs synthetic repair producing an 8-page valid PDF openable in pypdf and PyMuPDF.
    5. Verifies download comparison against reference_complete.pdf strictly for evaluation.
    """
    import io
    import pypdf
    import fitz

    fixture_bin = REPO_ROOT / "evidence" / "datasets" / "evidence" / "TRACE_105block_one_missing.bin"
    assert fixture_bin.is_file(), f"Missing fixture: {fixture_bin}"
    raw_bin_bytes = fixture_bin.read_bytes()
    assert len(raw_bin_bytes) == 26880

    ref_gt_pdf = REPO_ROOT / "evidence" / "datasets" / "groundtruth" / "reference_complete.pdf"
    assert ref_gt_pdf.is_file(), f"Missing evaluation reference: {ref_gt_pdf}"
    ref_gt_bytes = ref_gt_pdf.read_bytes()

    # 1. Carve via fixture_id="105block_one_missing"
    r_carve = integrated_client.post(
        "/api/sessions/carve",
        data={"fixture_id": "105block_one_missing", "case_id": "CASE-105BLOCK-TEST"},
    )
    assert r_carve.status_code == 201
    session_id = r_carve.json()["session_id"]

    # 2. Check reconstruction metadata and missing-region detection
    r_meta = integrated_client.get(f"/api/sessions/{session_id}/reconstruction")
    assert r_meta.status_code == 200
    meta = r_meta.json()

    assert meta["fragments_carved"] == 98, f"Expected 98 valid non-zero fragments, got {meta['fragments_carved']}"
    assert meta["status"] in ("incomplete", "partial"), f"Expected incomplete/partial, got {meta['status']}"

    # Verify missing-region detection in reconstruction metadata and scan warnings
    assert [13312, 13568] in meta["erased_regions"], f"Erased slot 53 [13312, 13568) must be detected, got {meta['erased_regions']}"
    assert any("13312" in w and "13568" in w for w in meta["scan_warnings"]), "Scan warnings must record erased slot 53 region [13312, 13568)"

    # 3. Test authentic download (raw authentic reconstruction without synthetic fabrication)
    r_dl_raw = integrated_client.get(f"/api/sessions/{session_id}/reconstruction/download")
    assert r_dl_raw.status_code == 200
    assert r_dl_raw.headers["content-type"] == "application/pdf"

    # 4. Test synthetic repair download (?mode=repaired)
    r_dl_rep = integrated_client.get(f"/api/sessions/{session_id}/reconstruction/download?mode=repaired")
    assert r_dl_rep.status_code == 200
    assert r_dl_rep.headers["content-type"] == "application/pdf"
    repaired_bytes = r_dl_rep.content
    assert len(repaired_bytes) > 20000

    # 5. Validate repaired PDF opens cleanly in pypdf
    pypdf_reader = pypdf.PdfReader(io.BytesIO(repaired_bytes))
    assert len(pypdf_reader.pages) == 8, f"Expected 8 pages in repaired PDF, got {len(pypdf_reader.pages)}"

    p1_text = pypdf_reader.pages[0].extract_text()
    assert "TRACE Fragment Reconstruction Test" in p1_text
    assert "page 1 of 8" in p1_text

    p5_text = pypdf_reader.pages[4].extract_text()
    assert "page 5 of 8" in p5_text or "Page 5" in p5_text

    # 6. Validate repaired PDF renders cleanly in PyMuPDF
    doc = fitz.open(stream=repaired_bytes, filetype="pdf")
    assert doc.page_count == 8, f"Expected 8 pages in fitz, got {doc.page_count}"
    pix = doc.load_page(0).get_pixmap()
    assert pix.width > 0 and pix.height > 0
    doc.close()

    # 7. Also test upload via multipart file upload directly (.bin extension)
    r_upload = integrated_client.post(
        "/api/sessions/carve",
        files={"file": ("TRACE_105block_one_missing.bin", raw_bin_bytes, "application/octet-stream")},
        data={"case_id": "CASE-105BLOCK-UPLOAD"},
    )
    assert r_upload.status_code == 201
    upload_session_id = r_upload.json()["session_id"]

    # Verify upload metadata matches fixture metadata exactly
    r_up_meta = integrated_client.get(f"/api/sessions/{upload_session_id}/reconstruction")
    assert r_up_meta.status_code == 200
    meta_up = r_up_meta.json()

    assert meta_up["fragments_carved"] == 98, f"Expected 98 carved fragments in upload, got {meta_up['fragments_carved']}"
    assert meta_up["fragments_placed"] == 2, f"Expected 2 placed fragments in upload, got {meta_up['fragments_placed']}"
    assert meta_up["unplaced_fragments_count"] == 96
    assert meta_up["status"] in ("incomplete", "partial")
    assert meta_up["is_intact_passthrough"] is False
    assert meta_up["has_repaired_file"] is True
    assert meta_up["repaired_page_count"] == 8
    assert meta_up["repaired_is_openable"] is True
    assert [13312, 13568] in meta_up["erased_regions"], f"Erased slot 53 [13312, 13568) must be detected in upload, got {meta_up['erased_regions']}"
    assert any("13312" in w and "13568" in w for w in meta_up["scan_warnings"])

    # Test auto download for uploaded file (defaults to openable repaired PDF)
    r_upload_auto = integrated_client.get(f"/api/sessions/{upload_session_id}/reconstruction/download")
    assert r_upload_auto.status_code == 200
    upload_auto_reader = pypdf.PdfReader(io.BytesIO(r_upload_auto.content))
    assert len(upload_auto_reader.pages) == 8

    # Test raw download for uploaded file (preserves authentic 512 bytes)
    r_upload_raw = integrated_client.get(f"/api/sessions/{upload_session_id}/reconstruction/download?mode=raw")
    assert r_upload_raw.status_code == 200
    assert len(r_upload_raw.content) == 512

    # Test explicit repaired mode download for uploaded file
    r_upload_rep = integrated_client.get(f"/api/sessions/{upload_session_id}/reconstruction/download?mode=repaired")
    assert r_upload_rep.status_code == 200
    upload_rep_bytes = r_upload_rep.content

    # Strict ISO 32000-1 & Adobe Acrobat compatibility verification
    import warnings
    with warnings.catch_warnings(record=True) as captured_warnings:
        warnings.simplefilter("always")
        strict_reader = pypdf.PdfReader(io.BytesIO(upload_rep_bytes), strict=True)
        assert len(strict_reader.pages) == 8, f"Expected 8 pages, got {len(strict_reader.pages)}"
        for p_idx, page in enumerate(strict_reader.pages):
            page_text = page.extract_text()
            assert len(page_text) > 0, f"Page {p_idx + 1} extracted empty text"
            assert "TRACE Fragment Reconstruction Test" in page_text or f"page {p_idx + 1}" in page_text.lower()
        # Zero warnings from strict PDF parsing confirms clean stream lengths and markers
        assert len(captured_warnings) == 0, f"Unexpected strict warnings: {[str(w.message) for w in captured_warnings]}"

    # Verify every stream object has an exact matching /Length attribute
    stream_objs = list(re.finditer(rb"(\d+)\s+0\s+obj[\s\S]*?stream[\r\n]+([\s\S]*?)[\r\n]+endstream", upload_rep_bytes))
    assert len(stream_objs) >= 8, f"Expected at least 8 stream objects, found {len(stream_objs)}"
    for sm in stream_objs:
        obj_hdr = sm.group(0)
        obj_body = sm.group(2)
        len_match = re.search(rb"/Length\s+(\d+)", obj_hdr)
        assert len_match is not None, f"Object {sm.group(1)} is missing /Length attribute"
        declared_len = int(len_match.group(1))
        actual_len = len(obj_body)
        assert declared_len == actual_len, f"Object {sm.group(1)} /Length mismatch: declared={declared_len}, actual={actual_len}"

        # Verify BT/ET and q/Q operator balance
        bt_count = len(re.findall(rb"\bBT\b", obj_body))
        et_count = len(re.findall(rb"\bET\b", obj_body))
        assert bt_count == et_count, f"Object {sm.group(1)} has unbalanced text blocks: BT={bt_count}, ET={et_count}"
        q_count = len(re.findall(rb"\bq\b", obj_body))
        big_q_count = len(re.findall(rb"\bQ\b", obj_body))
        assert q_count == big_q_count, f"Object {sm.group(1)} has unbalanced graphics states: q={q_count}, Q={big_q_count}"

    # Verify PyMuPDF renders all 8 pages without error
    doc_up = fitz.open(stream=upload_rep_bytes, filetype="pdf")
    assert doc_up.page_count == 8
    for page_idx in range(8):
        pm = doc_up.load_page(page_idx).get_pixmap()
        assert pm.width == 612 and pm.height == 792
    doc_up.close()

    # 8. Evaluation comparison against ground truth strictly in test harness
    assert len(ref_gt_bytes) == 26778
    # Truth check: repaired PDF is synthesized and NOT byte-identical to original ground truth
    assert repaired_bytes != ref_gt_bytes



