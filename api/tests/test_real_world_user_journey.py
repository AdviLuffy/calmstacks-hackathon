"""End-to-End User Journey Tests for Real-World Corrupted PDF Recovery (Phase 11).

Verifies the entire lifecycle of damaged PDF files:
1. User uploads a corrupted PDF file to /api/sessions/carve.
2. System auto-diagnoses the damage and executes deterministic recovery.
3. Extracted readable text and structural metrics are immediately available.
4. Embedded visual document preview (/reconstruction/view?mode=auto) renders openable PDF.
5. Clean downloads (/reconstruction/download?mode=repaired and ?mode=authentic) function without (Demo) labels.
6. Forensic reports (/investigations/{id}, /report.html, /report.json) maintain strict evidentiary integrity.
"""

from __future__ import annotations

import io
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
CORPUS_DIR = REPO_ROOT / "trace" / "datasets" / "real_world" / "corpus" / "damaged"


@pytest.fixture
def test_client(make_client) -> TestClient:
    return make_client()


def test_user_journey_mangled_header_corruption(test_client: TestClient):
    """Corrupted PDF with HTML preamble and damaged %PDF- header is uploaded and recovered."""
    target_pdf = CORPUS_DIR / "CORPUS_01_mangled_header.pdf"
    assert target_pdf.is_file(), f"Missing corpus file: {target_pdf}"
    damaged_bytes = target_pdf.read_bytes()

    # 1. User uploads corrupted PDF to carve endpoint
    resp = test_client.post(
        "/api/sessions/carve",
        files={"file": ("corrupted_header.pdf", io.BytesIO(damaged_bytes), "application/pdf")},
        data={"case_id": "CASE-RW-HEADER-01"},
    )
    assert resp.status_code == 201, f"Carve failed: {resp.text}"
    session_id = resp.json()["session_id"]
    assert session_id

    # 2. Check reconstruction metadata
    recon_resp = test_client.get(f"/api/sessions/{session_id}/reconstruction")
    assert recon_resp.status_code == 200
    meta = recon_resp.json()

    assert meta.get("has_repaired_file") is True
    assert meta.get("repaired_is_openable") is True
    assert meta.get("repaired_page_count", 0) >= 1

    # Verify readable text was salvaged
    salvaged = meta.get("salvaged_text", "")
    assert len(salvaged) > 0
    assert any(w in salvaged for w in ("Autonomous Bitstream", "TRACE", "Attention", "Forensic"))

    # Diagnostic audit check
    diag = meta.get("diagnostic", {})
    corruption_classes = diag.get("corruption_classes", [])
    assert any("HEADER" in c or "PREAMBLE" in c for c in corruption_classes)

    # 3. Verify embedded visual preview endpoint
    view_resp = test_client.get(f"/api/sessions/{session_id}/reconstruction/view?mode=auto")
    assert view_resp.status_code == 200
    assert "application/pdf" in view_resp.headers.get("content-type", "")
    pdf_bytes = view_resp.content
    assert pdf_bytes.startswith(b"%PDF-")
    assert b"%%EOF" in pdf_bytes[-1024:]

    # 4. Verify download endpoint
    dl_resp = test_client.get(f"/api/sessions/{session_id}/reconstruction/download?mode=repaired")
    assert dl_resp.status_code == 200
    assert "application/pdf" in dl_resp.headers.get("content-type", "")
    assert "attachment" in dl_resp.headers.get("content-disposition", "")
    assert dl_resp.content == pdf_bytes

    # 5. Verify UI investigation page renders preview panel and has no (Demo) labels
    ui_resp = test_client.get(f"/investigations/{session_id}")
    assert ui_resp.status_code == 200
    html = ui_resp.text
    assert "realworld-pdf-recovery-panel" in html
    assert "rw-pdf-iframe" in html
    assert "rw-salvaged-text" in html
    assert "(Demo)" not in html


def test_user_journey_destroyed_xref_corruption(test_client: TestClient):
    """Corrupted PDF with zeroed/destroyed xref table and missing trailer is recovered."""
    target_pdf = CORPUS_DIR / "CORPUS_02_destroyed_xref_trailer.pdf"
    assert target_pdf.is_file(), f"Missing corpus file: {target_pdf}"
    damaged_bytes = target_pdf.read_bytes()

    resp = test_client.post(
        "/api/sessions/carve",
        files={"file": ("damaged_xref.pdf", io.BytesIO(damaged_bytes), "application/pdf")},
        data={"case_id": "CASE-RW-XREF-02"},
    )
    assert resp.status_code == 201
    session_id = resp.json()["session_id"]

    recon_resp = test_client.get(f"/api/sessions/{session_id}/reconstruction")
    assert recon_resp.status_code == 200
    meta = recon_resp.json()

    assert meta.get("has_repaired_file") is True
    assert meta.get("repaired_is_openable") is True
    assert meta.get("repaired_page_count", 0) >= 1
    assert len(meta.get("salvaged_text", "")) > 0

    corruption_classes = meta.get("diagnostic", {}).get("corruption_classes", [])
    assert any("XREF" in c or "CROSS_REFERENCE" in c or "TRAILER" in c for c in corruption_classes)

    # View & Download
    view_resp = test_client.get(f"/api/sessions/{session_id}/reconstruction/view?mode=auto")
    assert view_resp.status_code == 200
    assert view_resp.content.startswith(b"%PDF-")


def test_user_journey_online_scramble_corruption(test_client: TestClient):
    """Corrupted PDF simulating online corruption tool byte scrambling is recovered."""
    target_pdf = CORPUS_DIR / "CORPUS_08_online_scramble.pdf"
    assert target_pdf.is_file(), f"Missing corpus file: {target_pdf}"
    damaged_bytes = target_pdf.read_bytes()

    resp = test_client.post(
        "/api/sessions/carve",
        files={"file": ("online_scramble.pdf", io.BytesIO(damaged_bytes), "application/pdf")},
        data={"case_id": "CASE-RW-SCRAMBLE-08"},
    )
    assert resp.status_code == 201
    session_id = resp.json()["session_id"]

    recon_resp = test_client.get(f"/api/sessions/{session_id}/reconstruction")
    assert recon_resp.status_code == 200
    meta = recon_resp.json()

    assert meta.get("has_repaired_file") is True
    assert meta.get("repaired_is_openable") is True
    assert len(meta.get("salvaged_text", "")) > 0


def test_user_journey_safedocs_corruption(test_client: TestClient):
    """DARPA SafeDocs genuine corrupted sample is ingested and recovered."""
    target_pdf = CORPUS_DIR / "CORPUS_10_safedocs_xref_corruption.pdf"
    assert target_pdf.is_file(), f"Missing corpus file: {target_pdf}"
    damaged_bytes = target_pdf.read_bytes()

    resp = test_client.post(
        "/api/sessions/carve",
        files={"file": ("safedocs_corrupt.pdf", io.BytesIO(damaged_bytes), "application/pdf")},
        data={"case_id": "CASE-RW-SAFEDOCS-10"},
    )
    assert resp.status_code == 201
    session_id = resp.json()["session_id"]

    recon_resp = test_client.get(f"/api/sessions/{session_id}/reconstruction")
    assert recon_resp.status_code == 200
    meta = recon_resp.json()

    assert meta.get("has_repaired_file") is True
    assert meta.get("repaired_is_openable") is True

    # Audit reports
    rep_html = test_client.get(f"/api/sessions/{session_id}/report.html")
    assert rep_html.status_code == 200
    assert "TRACE" in rep_html.text

    rep_json = test_client.get(f"/api/sessions/{session_id}/report.json")
    assert rep_json.status_code == 200
    assert rep_json.json()["case"]["case_id"] == "CASE-RW-SAFEDOCS-10"
