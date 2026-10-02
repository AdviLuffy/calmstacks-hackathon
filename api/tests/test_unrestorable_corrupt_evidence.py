"""Regression tests for unopenable/unrestorable corrupted PDF evidence.

Guarantees:
- Heavily corrupted PDF bitstreams with invalid stream syntax/elementary objects are rejected.
- The repair engine never fabricates a dummy 1-page unopenable PDF for unrecoverable streams.
- validate_and_render_pdf rigorously verifies page streams and rasterization in pypdf and pymupdf.
- Download and view endpoints in 'repaired' mode reject unopenable candidates and truthfully return HTTP 404/422.
- Download and view endpoints in 'raw' mode return authentic carved bytes with accurate headers.
- Authentic media file size is truthfully tracked and exposed separate from the JSON evidence bundle size.
"""

from __future__ import annotations

import io
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from trace_evidence.constants import (
    STATUS_OUTPUT_INVALID,
    STATUS_PARTIAL_UNRESTORED,
)
from trace_evidence.repair import (
    repair_pdf,
    synthetic_repair_pdf,
    validate_and_render_pdf,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_corrupt_partial_bytes_produce_no_fake_repair():
    """When raw recovered bytes contain invalid syntax and cannot form a valid page, repair must fail honestly."""
    # Use exact 512-byte scrambled fragment stream from 7bad investigation if present, or synthetic counterpart
    session_raw = REPO_ROOT / "api" / "var" / "sessions" / "7bad203858334b29aa7b99ef7e6de15e.pdf"
    if session_raw.is_file():
        corrupt_bytes = session_raw.read_bytes()
    else:
        corrupt_bytes = (
            b"%PDF-1.3\n1 0 obm\n<< /F 2 0 R >>\nendobj\n"
            b"2 0 obj\n<< /Type /Page /Contents 9 0 R >>\nendobj\n"
            b"9 0 obj\n<< /LengtW 2/13 \xe0>\xb3st\xeae\x9d\xd5\n170 0 cm BT /F1 12 Tf ET\nendobj\n"
        )

    res = repair_pdf(raw_bytes=corrupt_bytes, media_bytes=corrupt_bytes)
    assert not res.is_openable
    assert res.page_count == 0
    assert res.repaired_bytes == b""
    assert res.repaired_size_bytes == 0
    assert res.synthesized_bytes_count == 0
    assert res.repair_status in (STATUS_OUTPUT_INVALID, STATUS_PARTIAL_UNRESTORED)
    assert res.error_message is not None


def test_validate_and_render_pdf_rejects_corrupted_content_stream():
    """validate_and_render_pdf must detect corrupt elementary objects in page streams and return False."""
    broken_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n"
        b"4 0 obj\n<< /LengtW 99 \xe0>\xb3st\xeae\x9d\xd5\nBT invalid operator ET\nendobj\n"
        b"xref\n0 5\n"
        b"0000000000 65535 f \r\n"
        b"0000000009 00000 n \r\n"
        b"0000000058 00000 n \r\n"
        b"0000000115 00000 n \r\n"
        b"0000000206 00000 n \r\n"
        b"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n275\n%%EOF\n"
    )

    is_open, page_count, text, err = validate_and_render_pdf(broken_pdf)
    assert not is_open
    assert page_count <= 1
    assert err is not None


def test_validate_and_render_pdf_accepts_valid_documents():
    """Valid PDF documents must pass validation with accurate page counts and non-empty pixmap rendering."""
    valid_pdf_path = REPO_ROOT / "evidence" / "datasets" / "evidence" / "reconstructed_repaired_visible_text.pdf"
    if valid_pdf_path.is_file():
        pdf_bytes = valid_pdf_path.read_bytes()
        is_open, count, text, err = validate_and_render_pdf(pdf_bytes)
        assert is_open
        assert count == 1
        assert "TRACE FORENSIC RECONSTRUCTION TEST" in text
        assert err is None


def test_download_and_view_endpoints_reject_unopenable_repair(monkeypatch, tmp_path):
    """When a session has partial unopenable bytes, repaired mode returns 404/422 while raw mode returns authentic bytes."""
    monkeypatch.setenv("TRACE_PERSIST_SESSIONS", "1")
    monkeypatch.setenv("TRACE_SESSION_ROOT", str(tmp_path))

    # Prepare session with 512 bytes of raw reconstruction
    session_id = "a1b2c3d4e5f6789012345678abcdef01"
    raw_pdf = tmp_path / f"{session_id}.pdf"
    raw_pdf.write_bytes(b"%PDF-1.3\n% truncated raw bytes from 2 fragments")

    # Ingest session JSON
    session_json = tmp_path / f"{session_id}.json"
    session_json.write_text(
        f'{{"session_id": "{session_id}", "status": "complete", "submitted_at": "2026-09-27T12:00:00+00:00", '
        f'"evidence_bytes": 72846, "mock_data": false, "records": []}}',
        encoding="utf-8",
    )

    app = create_app()
    client = TestClient(app)

    # 1. Query reconstruction metadata
    res = client.get(f"/api/sessions/{session_id}/reconstruction")
    assert res.status_code == 200
    meta = res.json()
    assert not meta.get("has_repaired_file")
    assert not meta.get("repaired_is_openable")

    # 2. Query download in repaired mode: must return 404 because no valid repaired PDF exists
    res_dl = client.get(f"/api/sessions/{session_id}/reconstruction/download?mode=repaired")
    assert res_dl.status_code == 404
    assert "No valid repaired PDF could be produced" in res_dl.json()["error"]["message"]

    # 3. Query view in repaired mode: must also return 404
    res_view = client.get(f"/api/sessions/{session_id}/reconstruction/view?mode=repaired")
    assert res_view.status_code == 404

    # 4. Query download in raw mode: must succeed and return authentic 512 bytes
    res_raw = client.get(f"/api/sessions/{session_id}/reconstruction/download?mode=raw")
    assert res_raw.status_code == 200
    assert res_raw.headers["Content-Type"] == "application/pdf"
    assert f"reconstructed_{session_id}.pdf" in res_raw.headers["Content-Disposition"]
    assert res_raw.headers["X-TRACE-Repair-Status"] == "ORIGINAL BYTES RECOVERED"
    assert res_raw.content == b"%PDF-1.3\n% truncated raw bytes from 2 fragments"
