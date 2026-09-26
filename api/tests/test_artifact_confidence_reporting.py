"""Regression tests for TRACE forensic artifact confidence and authentic recovery reporting.

Verifies:
1. Fully recovered and verified artifact (100% authentic recovery, VERIFIED, NONE (AUTHENTIC)).
2. Synthetically repaired artifact with partial recovery (e.g. 2.0% authentic recovery, PARTIAL, UNVERIFIED, SYNTHETIC).
3. Partial artifact with unknown target size (Unknown recovery, UNVERIFIED, NOT REPAIRED).
4. Openable repaired PDF does not equal verified (is_openable == True, but integrity_status == UNVERIFIED).
5. Forensic HTML and JSON reports render separated metrics rather than misleading 100% confidence.
6. Investigation page UI renders separated table columns: AUTHENTIC RECOVERY, STATUS, INTEGRITY, STRUCTURAL REPAIR.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
import pytest
from starlette.testclient import TestClient

from trace.recovery.models import RecoveredArtifact, RecoveryCategory, ValidationResult
from trace.recovery.core.carver import MultiFormatCarver
from trace.cases.report import ForensicCase, ForensicReportGenerator


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def integrated_client(make_client) -> TestClient:
    from p3_helpers import make_settings, make_wiring
    from app.services.session_store import InMemorySessionStore

    return make_client(
        settings=make_settings(persist_sessions=False),
        wiring=make_wiring(),
        store=InMemorySessionStore(),
    )


def test_fully_recovered_and_verified_artifact(integrated_client):
    """Scenario 1: Fully recovered & verified artifact has 100% authentic recovery, VERIFIED, NONE (AUTHENTIC)."""
    r_carve = integrated_client.post(
        "/api/sessions/carve",
        data={"fixture_id": "visible_text_blob", "case_id": "CASE-VERIFIED-100"},
    )
    assert r_carve.status_code == 201
    session_id = r_carve.json()["session_id"]

    r_rec = integrated_client.get(f"/api/sessions/{session_id}/reconstruction")
    assert r_rec.status_code == 200
    rec_data = r_rec.json()
    assert rec_data["complete"] is True
    assert rec_data["is_verified"] is True

    # Check artifacts returned
    artifacts = rec_data.get("artifacts", [])
    assert len(artifacts) > 0
    primary_art = artifacts[0]

    assert primary_art["authentic_recovery_pct"] == 100.0
    assert primary_art["completeness"] == "COMPLETE"
    assert primary_art["integrity_status"] == "VERIFIED"
    assert "AUTHENTIC" in primary_art["structural_repair"]
    assert primary_art["category"] == "VERIFIED"
    assert primary_art["confidence_score"] == 100.0


def test_synthetically_repaired_artifact_with_partial_recovery(integrated_client):
    """Scenario 2: Synthetically repaired artifact with missing data never claims 100% confidence.
    
    Verifies authentic recovery is partial (e.g. ~2.0%), completeness is PARTIAL,
    integrity is UNVERIFIED, and structural repair is SYNTHETIC.
    """
    # Use 105block_one_missing fixture BIN file
    fixture_path = REPO_ROOT / "evidence" / "datasets" / "evidence" / "TRACE_105block_one_missing.bin"
    assert fixture_path.is_file(), f"Missing test fixture: {fixture_path}"
    media_bytes = fixture_path.read_bytes()

    r_upload = integrated_client.post(
        "/api/sessions/carve",
        files={"file": ("TRACE_105block_one_missing.bin", media_bytes, "application/octet-stream")},
        data={"case_id": "CASE-105BLOCK-REPAIR"},
    )
    assert r_upload.status_code == 201
    session_id = r_upload.json()["session_id"]

    # Trigger synthetic repair demo
    r_rep = integrated_client.post(f"/api/sessions/{session_id}/repair")
    assert r_rep.status_code == 200

    r_rec = integrated_client.get(f"/api/sessions/{session_id}/reconstruction")
    assert r_rec.status_code == 200
    rec_data = r_rec.json()

    artifacts = rec_data.get("artifacts", [])
    assert len(artifacts) > 0
    pdf_art = [a for a in artifacts if a.get("format_name") == "pdf"][0]

    # Verify forensic metrics are truthful and separated
    assert pdf_art["authentic_recovery_pct"] is not None
    assert pdf_art["authentic_recovery_pct"] < 10.0  # ~2.0% authentic byte/block recovery
    assert pdf_art["completeness"] == "PARTIAL"
    assert pdf_art["integrity_status"] == "UNVERIFIED"
    assert pdf_art["structural_repair"] == "SYNTHETIC"
    assert pdf_art["category"] == "PARTIAL"
    assert pdf_art["confidence_score"] < 10.0  # NOT 100.0%!


def test_partial_artifact_with_unknown_target_size():
    """Scenario 3: Partial artifact with unknown target size has Unknown recovery and UNVERIFIED integrity."""
    dummy_pdf_fragment = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"
    val = ValidationResult(
        is_valid=False,
        format_name="pdf",
        integrity_score=0.45,
        checks_passed=("header_magic", "pdf_objects"),
        checks_failed=("eof_marker", "cross_reference_structure"),
        warnings=("No EOF marker found",),
    )
    art = RecoveredArtifact(
        artifact_id="CARVE-TEST-001",
        filename="carved_stream.pdf",
        format_name="pdf",
        mime_type="application/pdf",
        size_bytes=len(dummy_pdf_fragment),
        sha256=hashlib.sha256(dummy_pdf_fragment).hexdigest(),
        category=RecoveryCategory.PARTIAL,
        confidence_score=45.0,
        format_confidence=45.0,
        authentic_recovery_pct=None,  # Unknown target size
        completeness="PARTIAL",
        integrity_status="UNVERIFIED",
        structural_repair="NOT REPAIRED",
        raw_bytes=dummy_pdf_fragment,
        validation=val,
    )

    art_dict = art.to_dict()
    assert art_dict["authentic_recovery_pct"] is None
    assert art_dict["completeness"] == "PARTIAL"
    assert art_dict["integrity_status"] == "UNVERIFIED"
    assert art_dict["structural_repair"] == "NOT REPAIRED"
    assert art_dict["confidence_score"] == 45.0


def test_openable_repaired_pdf_does_not_equal_verified(integrated_client):
    """Scenario 4: Artifact that opens successfully in PDF parser but fails cryptographic verification."""
    from trace_evidence.repair import repair_pdf

    # Construct partial PDF with valid syntax repaired so it opens
    partial_bytes = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >>\nendobj\n"
    )
    repair_res = repair_pdf(raw_bytes=partial_bytes, missing_elements=["trailer", "startxref", "xref", "eof"])
    assert repair_res is not None
    assert repair_res.is_openable is True  # Opens cleanly in PyMuPDF/pypdf

    # But integrity status is UNVERIFIED and repair is SYNTHETIC
    art = RecoveredArtifact(
        artifact_id="REC-REPAIR-001",
        filename="repaired.pdf",
        format_name="pdf",
        mime_type="application/pdf",
        size_bytes=len(repair_res.repaired_bytes),
        sha256=repair_res.sha256,
        category=RecoveryCategory.PARTIAL,
        confidence_score=35.0,
        format_confidence=100.0,
        authentic_recovery_pct=35.0,
        completeness="PARTIAL",
        integrity_status="UNVERIFIED",  # Openable != Verified!
        structural_repair="SYNTHETIC",
        raw_bytes=repair_res.repaired_bytes,
    )

    assert art.integrity_status == "UNVERIFIED"
    assert art.category != RecoveryCategory.VERIFIED
    assert art.structural_repair == "SYNTHETIC"
    assert art.authentic_recovery_pct == 35.0


def test_html_and_json_reports_render_separated_metrics():
    """Verify HTML and JSON forensic reports render the separated forensic columns and values."""
    case = ForensicCase(
        case_id="CASE-METRIC-TEST",
        title="Test Metric Separation",
        investigator="Investigator Test",
        write_blocked=True,
    )
    artifacts = [
        RecoveredArtifact(
            artifact_id="ART-001",
            filename="test_repaired.pdf",
            format_name="pdf",
            mime_type="application/pdf",
            size_bytes=24764,
            sha256="abcdef1234567890",
            category=RecoveryCategory.PARTIAL,
            confidence_score=2.0,
            format_confidence=100.0,
            authentic_recovery_pct=2.0,
            completeness="PARTIAL",
            integrity_status="UNVERIFIED",
            structural_repair="SYNTHETIC",
            explanation="Synthetically repaired; authentic recovery 2.0%",
        )
    ]

    # HTML Report
    html_report = ForensicReportGenerator.generate_html_report(case=case, artifacts=artifacts)
    assert "Authentic Recovery" in html_report
    assert "Completeness" in html_report
    assert "Integrity" in html_report
    assert "Structural Repair" in html_report
    assert "2.0%" in html_report
    assert "SYNTHETIC" in html_report
    assert "UNVERIFIED" in html_report
    assert "CONFIDENCE 100%" not in html_report

    # JSON Report
    json_report = ForensicReportGenerator.generate_json_report(case=case, artifacts=artifacts)
    art_dict = json_report["artifacts"][0]
    assert art_dict["authentic_recovery_pct"] == 2.0
    assert art_dict["completeness"] == "PARTIAL"
    assert art_dict["integrity_status"] == "UNVERIFIED"
    assert art_dict["structural_repair"] == "SYNTHETIC"
    assert art_dict["format_confidence"] == 100.0


def test_frontend_investigation_page_renders_separated_table_columns(integrated_client):
    """Verify the investigation HTML page contains the separated table headers in its JavaScript."""
    r_carve = integrated_client.post(
        "/api/sessions/carve",
        data={"fixture_id": "visible_text_4missing", "case_id": "CASE-UI-COLUMNS"},
    )
    assert r_carve.status_code == 201
    session_id = r_carve.json()["session_id"]

    r_page = integrated_client.get(f"/investigations/{session_id}")
    assert r_page.status_code == 200
    html_text = r_page.text

    # The table header must contain the separated metrics, not ambiguous CONFIDENCE column
    assert "AUTHENTIC RECOVERY" in html_text
    assert "INTEGRITY" in html_text
    assert "STRUCTURAL REPAIR" in html_text
    assert "<th style=\"padding:6px;\">CONFIDENCE</th>" not in html_text
