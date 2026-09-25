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


def test_cold_reconstruction_and_unconfigured_ai_analysis(integrated_client):
    """Verify cold reconstruction fallback and truthful AI unconfigured state."""
    from app.routers.dashboard import _RECONSTRUCTED_META

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



