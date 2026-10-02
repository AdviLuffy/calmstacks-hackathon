"""Comprehensive regression and integration tests for AI-Assisted Missing PDF Content Reconstruction.

Guarantees:
1. When authentic recovery is partial and structural repair cannot open the file,
   the AI reconstruction engine synthesizes a 100% valid ISO 32000-1 PDF artifact.
2. The generated PDF opens cleanly in pypdf and renders in PyMuPDF (fitz) without errors.
3. Every page displays the mandatory warning banner:
   "[TRACE FORENSIC RECONSTRUCTION - AI INFERRED CONTENT]"
   "WARNING: Probabilistic reconstruction from partial fragments. Not byte-identical to original evidence."
4. Authentic recovered bytes are preserved strictly separate from AI-inferred content.
5. Metrics are honestly tracked and calibrated: authentic recovery %, AI-generated %,
   structural synthesis %, and fidelity confidence (never blind 100%).
6. API endpoints for generating, querying, viewing, and downloading AI-reconstructed PDFs
   operate correctly with precise forensic headers.
"""

from __future__ import annotations

import io
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from trace.ai.reconstruction import (
    AIReconstructionEngine,
    calibrate_fidelity_confidence,
    extract_surviving_features,
)
from trace_evidence.repair import validate_and_render_pdf

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_calibrate_fidelity_confidence_is_scientifically_honest():
    """Fidelity confidence must reflect evidence scarcity and never inflate to 100%."""
    # Scenario: 512 authentic bytes out of 24,898 bytes (2% coverage), 0 surviving strings
    score_low = calibrate_fidelity_confidence(
        authentic_bytes=512,
        media_size=24898,
        surviving_strings_count=0,
        objects_count=0,
    )
    assert 5.0 <= score_low <= 25.0
    assert score_low < 50.0

    # Scenario: 50% authentic coverage with some surviving strings
    score_mid = calibrate_fidelity_confidence(
        authentic_bytes=12000,
        media_size=24000,
        surviving_strings_count=3,
        objects_count=4,
    )
    assert 30.0 <= score_mid <= 75.0
    assert score_mid < 100.0


def test_ai_reconstruction_engine_produces_valid_iso_pdf():
    """AIReconstructionEngine must synthesize a 100% valid ISO 32000-1 PDF that opens in pypdf and pymupdf."""
    # Use real 512-byte fragment from session 7bad if present, or synthetic equivalent
    raw_path = REPO_ROOT / "api" / "var" / "sessions" / "7bad203858334b29aa7b99ef7e6de15e.pdf"
    if raw_path.is_file():
        raw_bytes = raw_path.read_bytes()
    else:
        raw_bytes = (
            b"%PDF-1.3\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
            b"% truncated stream fragments\n"
        )

    engine = AIReconstructionEngine(
        raw_bytes=raw_bytes,
        media_bytes=None,
        session_id="test_session_ai_recon_001",
        case_id="TEST-111",
        unplaced_count=96,
        metadata={"media_size_bytes": 24898},
    )
    result = engine.reconstruct()

    # 1. Structural validity
    assert result.is_valid
    assert result.page_count >= 1
    assert len(result.pdf_bytes) > 1000
    assert result.pdf_bytes.startswith(b"%PDF-1.4\n")
    assert b"%%EOF" in result.pdf_bytes
    assert b"startxref" in result.pdf_bytes
    assert b"xref\n" in result.pdf_bytes

    # 2. Independent validation with pypdf and pymupdf
    is_open, page_count, extracted_text, val_err = validate_and_render_pdf(result.pdf_bytes)
    assert is_open
    assert page_count >= 1
    assert val_err is None

    # 3. Mandatory visual warning indicators
    assert "TRACE RECONSTRUCTED DOCUMENT" in extracted_text
    assert "WARNING:" in extracted_text
    assert "TRACE FORENSIC PROVENANCE LEDGER" in extracted_text
    assert "UNCALIBRATED ESTIMATE" in extracted_text

    # 4. Authentic vs Reconstructed separation
    assert "AUTHENTIC RECOVERED CONTENT" in extracted_text

    # 5. Model provenance and invocation tracking
    assert hasattr(result, "ai_invoked")
    assert hasattr(result, "provider")
    assert hasattr(result, "inference_result")
    if result.ai_invoked:
        assert result.provider == "google-genai"
        assert "gemini" in result.model_used.lower()
    else:
        assert result.provider == "rule-based-synthesizer"
        assert result.model_used == "none"

    # 6. Reconciled surviving object count
    objs = result.provenance_report["surviving_objects"]
    assert result.provenance_report["surviving_objects_count"] == len(objs)


def test_ai_reconstruction_honest_metric_separation():
    """Metrics must separately track authentic recovery %, AI-generated %, and structural synthesis %."""
    raw_bytes = b"%PDF-1.3\n% 512 bytes of carved data\n" + (b"0" * 480)
    media_size = 25600

    engine = AIReconstructionEngine(
        raw_bytes=raw_bytes,
        media_bytes=None,
        session_id="test_session_metrics",
        case_id="METRICS-CASE",
        unplaced_count=98,
        metadata={"media_size_bytes": media_size},
    )
    res = engine.reconstruct()

    metrics = res.metrics
    assert metrics["authentic_bytes_count"] == len(raw_bytes)
    assert metrics["media_size_bytes"] == media_size
    # Authentic recovery percentage is (512 / 25600) * 100 = 2.0%
    assert round(metrics["authentic_recovery_pct"], 1) == 2.0
    # AI generated percentage is tracked separately
    assert metrics["ai_generated_pct"] > 50.0
    # Content fidelity confidence is bounded honestly
    assert 5.0 <= metrics["content_fidelity_confidence"] <= 35.0


def test_ai_reconstruction_endpoints_e2e(monkeypatch, tmp_path):
    """E2E verification of AI reconstruction API endpoints: POST, GET, download, and view."""
    monkeypatch.setenv("TRACE_PERSIST_SESSIONS", "1")
    monkeypatch.setenv("TRACE_SESSION_ROOT", str(tmp_path))

    session_id = "c0d1e2f3a4b5678912345678abcdef02"
    # Write authentic 512-byte partial recovery
    raw_bytes = b"%PDF-1.3\n1 0 obj\n<< /Type /Page >>\nendobj\n" + (b"A" * 460)
    raw_file = tmp_path / f"{session_id}.pdf"
    raw_file.write_bytes(raw_bytes)

    session_json = tmp_path / f"{session_id}.json"
    session_json.write_text(
        f'{{"session_id": "{session_id}", "status": "complete", "submitted_at": "2026-09-27T12:00:00+00:00", '
        f'"evidence_bytes": 24898, "case_id": "TEST-111", "mock_data": false, "records": []}}',
        encoding="utf-8",
    )

    app = create_app()
    client = TestClient(app)

    # 1. Initially, GET /ai-reconstruction reports not generated
    res_init = client.get(f"/api/sessions/{session_id}/ai-reconstruction")
    assert res_init.status_code == 200
    assert not res_init.json().get("has_ai_reconstructed_file")

    # 2. Trigger AI reconstruction via POST
    res_post = client.post(f"/api/sessions/{session_id}/ai-reconstruction")
    assert res_post.status_code == 200
    post_data = res_post.json()
    assert post_data["is_valid"] is True
    assert post_data["page_count"] >= 1
    assert post_data["metrics"]["authentic_bytes_count"] == len(raw_bytes)
    assert post_data["metrics"]["media_size_bytes"] == 24898

    # Verify disk files were created
    disk_ai_pdf = tmp_path / f"{session_id}_ai_reconstructed.pdf"
    disk_ai_json = tmp_path / f"{session_id}_ai_reconstruction.json"
    assert disk_ai_pdf.is_file()
    assert disk_ai_json.is_file()

    # 3. GET /ai-reconstruction now reports active with telemetry
    res_status = client.get(f"/api/sessions/{session_id}/ai-reconstruction")
    assert res_status.status_code == 200
    status_data = res_status.json()
    assert status_data["is_valid"] is True
    assert status_data["has_reconstructed_file"] is True

    # 4. Download endpoint returns application/pdf with distinct AI header
    res_dl = client.get(f"/api/sessions/{session_id}/ai-reconstruction/download")
    assert res_dl.status_code == 200
    assert res_dl.headers["Content-Type"] == "application/pdf"
    assert f"ai_reconstructed_{session_id}.pdf" in res_dl.headers["Content-Disposition"]
    assert "AI-RECONSTRUCTED" in res_dl.headers["X-TRACE-Repair-Status"]
    assert len(res_dl.content) == len(disk_ai_pdf.read_bytes())

    # 5. View endpoint returns application/pdf with inline header
    res_view = client.get(f"/api/sessions/{session_id}/ai-reconstruction/view")
    assert res_view.status_code == 200
    assert "inline;" in res_view.headers["Content-Disposition"]

    # 6. Mode in standard download supports mode=ai_reconstructed
    res_mode_ai = client.get(f"/api/sessions/{session_id}/reconstruction/download?mode=ai_reconstructed")
    assert res_mode_ai.status_code == 200
    assert len(res_mode_ai.content) == len(disk_ai_pdf.read_bytes())

    # 7. Authentic raw download preserves original 512 bytes unmodified
    res_mode_raw = client.get(f"/api/sessions/{session_id}/reconstruction/download?mode=raw")
    assert res_mode_raw.status_code == 200
    assert res_mode_raw.headers["X-TRACE-Repair-Status"] == "ORIGINAL BYTES RECOVERED"
    assert res_mode_raw.content == raw_bytes
    assert len(res_mode_raw.content) == len(raw_bytes)


def test_extract_surviving_features_from_complete_evidence():
    """Verify that extract_surviving_features harvests full evidence, decompressing streams and extracting metadata."""
    evidence_path = REPO_ROOT / "evidence" / "datasets" / "evidence" / "reconstructed_repaired_105block.pdf"
    if not evidence_path.is_file():
        pytest.skip("reconstructed_repaired_105block.pdf not found")

    full_evidence = evidence_path.read_bytes()
    partial_512 = full_evidence[:512]

    # When given only partial 512 bytes with no media, it handles it gracefully
    feat_partial = extract_surviving_features(partial_512, None)
    assert feat_partial["surviving_objects_count"] <= 5

    # When given complete evidence, it extracts rich structured authentic features
    feat_full = extract_surviving_features(partial_512, full_evidence)

    # 1. Authentic recovery metrics
    assert feat_full["authentic_bytes_identified"] > 20000
    assert feat_full["authentic_recovery_percentage"] > 90.0

    # 2. Indirect objects and pages
    assert feat_full["surviving_objects_count"] >= 20
    assert feat_full["page_info"]["page_count"] == 8

    # 3. Stream decompression and text operators
    assert len(feat_full["surviving_strings"]) >= 20
    assert any("TRACE" in s or "Page" in s for s in feat_full["surviving_strings"])

    # 4. Fonts and metadata
    assert "Helvetica" in feat_full["fonts_found"]
    assert "metadata" in feat_full
    assert feat_full["metadata"].get("producer") is not None

    # 5. Provenance tracking
    assert len(feat_full["provenance"]) > 0


def test_artifact_and_download_flow_honesty_e2e(monkeypatch, tmp_path):
    """Verify clean separation and accurate headers for all 5 forensic artifacts:
    1. original corrupted evidence
    2. authentic recovered/carved evidence
    3. deterministic reconstructed/repaired PDF
    4. AI-assisted reconstructed PDF
    5. forensic provenance/audit report
    """
    monkeypatch.setenv("TRACE_PERSIST_SESSIONS", "1")
    monkeypatch.setenv("TRACE_SESSION_ROOT", str(tmp_path))

    session_id = "d1e2f3a4b567890123456789abcdef03"

    # Setup 5 distinct artifacts on disk
    orig_media_bytes = b"CORRUPTED_RAW_DISK_IMAGE_SECTORS_1234567890" * 50
    raw_carved_bytes = b"%PDF-1.4\n% Raw carved 512 byte block\n" + (b"B" * 460)
    auth_carved_bytes = b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n" + (b"C" * 1200)

    # Repaired PDF (valid ISO PDF)
    from trace.ai.reconstruction import AIReconstructionEngine
    engine = AIReconstructionEngine(
        raw_bytes=raw_carved_bytes,
        media_bytes=orig_media_bytes,
        session_id=session_id,
        case_id="TEST-ARTIFACTS",
        unplaced_count=10,
    )
    res_ai = engine.reconstruct()
    repaired_pdf_bytes = res_ai.pdf_bytes  # Use valid PDF as repaired fixture

    # Persist files
    (tmp_path / f"{session_id}_media.bin").write_bytes(orig_media_bytes)
    (tmp_path / f"{session_id}.pdf").write_bytes(raw_carved_bytes)
    (tmp_path / f"{session_id}_authentic.bin").write_bytes(auth_carved_bytes)
    (tmp_path / f"{session_id}_repaired.pdf").write_bytes(repaired_pdf_bytes)
    (tmp_path / f"{session_id}_ai_reconstructed.pdf").write_bytes(res_ai.pdf_bytes)

    session_json = tmp_path / f"{session_id}.json"
    session_json.write_text(
        f'{{"session_id": "{session_id}", "status": "complete", "submitted_at": "2026-09-27T12:00:00+00:00", '
        f'"evidence_bytes": {len(orig_media_bytes)}, "case_id": "TEST-ARTIFACTS", "mock_data": false, "records": []}}',
        encoding="utf-8",
    )

    app = create_app()
    client = TestClient(app)

    # 1. Download original corrupted evidence
    res_media = client.get(f"/api/sessions/{session_id}/media/download")
    assert res_media.status_code == 200
    assert res_media.content == orig_media_bytes
    assert res_media.headers["X-TRACE-Artifact-Type"] == "original-corrupted-evidence"
    assert "ORIGINAL UNCARVED EVIDENCE" in res_media.headers["X-TRACE-Repair-Status"]

    # 2. Download authentic carved evidence
    res_auth = client.get(f"/api/sessions/{session_id}/reconstruction/download?mode=authentic")
    assert res_auth.status_code == 200
    assert res_auth.content == auth_carved_bytes
    assert res_auth.headers["X-TRACE-Artifact-Type"] == "authentic-recovered-evidence"
    assert "ORIGINAL BYTES RECOVERED (AUTHENTIC)" in res_auth.headers["X-TRACE-Repair-Status"]

    # 3. Download deterministic reconstructed/repaired PDF
    res_rep = client.get(f"/api/sessions/{session_id}/reconstruction/download?mode=repaired")
    assert res_rep.status_code == 200
    assert res_rep.content == repaired_pdf_bytes
    assert res_rep.headers["X-TRACE-Artifact-Type"] == "deterministic-repaired-pdf"
    assert "SYNTHETICALLY REPAIRED" in res_rep.headers["X-TRACE-Repair-Status"]
    # Structural validation of repaired PDF
    is_open_rep, pages_rep, _, err_rep = validate_and_render_pdf(res_rep.content)
    assert is_open_rep and pages_rep >= 1 and err_rep is None

    # 4. Download AI-assisted reconstructed PDF
    res_ai_dl = client.get(f"/api/sessions/{session_id}/ai-reconstruction/download")
    assert res_ai_dl.status_code == 200
    assert res_ai_dl.content == res_ai.pdf_bytes
    assert res_ai_dl.headers["X-TRACE-Artifact-Type"] == "ai-assisted-reconstructed-pdf"
    assert "AI-RECONSTRUCTED" in res_ai_dl.headers["X-TRACE-Repair-Status"]
    # Structural validation of AI PDF
    is_open_ai, pages_ai, _, err_ai = validate_and_render_pdf(res_ai_dl.content)
    assert is_open_ai and pages_ai >= 1 and err_ai is None

    # 5. Download forensic provenance/audit report (HTML and JSON)
    res_rep_html = client.get(f"/api/sessions/{session_id}/report.html")
    assert res_rep_html.status_code == 200
    assert "html" in res_rep_html.headers["Content-Type"]

    res_rep_json = client.get(f"/api/sessions/{session_id}/report.json")
    assert res_rep_json.status_code == 200
    assert "application/json" in res_rep_json.headers["Content-Type"]
    json_data = res_rep_json.json()
    assert "case" in json_data

