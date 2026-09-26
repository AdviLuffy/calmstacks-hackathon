"""Tests for intact PDF passthrough, incomplete P1 carving, and forensic hash verification."""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pytest
from app.main import create_app
from fastapi.testclient import TestClient
from p3_helpers import make_settings, make_wiring
from trace.intel.bundle_loader import BundleLoader

from app.services.session_store import InMemorySessionStore
from p3_helpers import make_settings, make_wiring

REPO_ROOT = Path(__file__).resolve().parents[2]
GROUND_TRUTH_DIR = REPO_ROOT / "evidence" / "datasets" / "groundtruth"
EVIDENCE_DIR = REPO_ROOT / "evidence" / "datasets" / "evidence"


@pytest.fixture
def integrated_client(make_client) -> TestClient:
    return make_client(
        settings=make_settings(),
        wiring=make_wiring(),
        store=InMemorySessionStore(),
    )


def _make_sample_intact_pdf() -> bytes:
    """Generate a minimal valid intact PDF conforming to ISO 32000-1."""
    pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n"
        b"4 0 obj\n<< /Length 55 >>\nstream\n"
        b"BT\n/F1 16 Tf\n50 350 Td\n(TRACE FORENSIC INTACT PDF TEST) Tj\nET\n"
        b"endstream\nendobj\n"
        b"xref\n"
        b"0 5\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000206 00000 n \n"
        b"trailer\n<< /Size 5 /Root 1 0 R >>\n"
        b"startxref\n312\n%%EOF\n"
    )
    return pdf


# ---------------------------------------------------------------------------
# Test 1: Intact PDF Upload Passthrough
# ---------------------------------------------------------------------------

def test_intact_pdf_upload_preserves_exact_bytes_and_validates_schema(integrated_client: TestClient, tmp_path: Path):
    """Uploading an intact valid PDF must preserve exact bytes and pass P2 schema without claiming fragmented recovery."""
    input_pdf = _make_sample_intact_pdf()
    input_sha256 = hashlib.sha256(input_pdf).hexdigest()

    response = integrated_client.post(
        "/api/sessions/carve",
        data={
            "case_id": "CASE-INTACT-01",
            "case_title": "Intact PDF Passthrough Verification",
            "investigator": "Forensic Examiner #1",
            "write_blocked": "true",
            "acquisition_method": "file_copy",
        },
        files={"file": ("sample_document.pdf", io.BytesIO(input_pdf), "application/pdf")},
    )
    assert response.status_code == 201, response.text
    session = response.json()
    session_id = session["session_id"]

    # 1. Check reconstruction metadata endpoint
    recon_res = integrated_client.get(f"/api/sessions/{session_id}/reconstruction")
    assert recon_res.status_code == 200
    recon = recon_res.json()

    assert recon["is_intact_passthrough"] is True
    assert recon["status"] == "intact_verified"
    assert recon["complete"] is True
    assert recon["is_verified"] is True
    assert recon["reconstructed_sha256"] == input_sha256
    assert recon["pdf_size_bytes"] == len(input_pdf)
    assert recon["fragments_carved"] == 0
    assert recon["fragments_placed"] == 0
    assert recon["unplaced_fragments_count"] == 0

    # 2. Check download endpoint returns exact original bytes byte-for-byte
    dl_res = integrated_client.get(f"/api/sessions/{session_id}/reconstruction/download")
    assert dl_res.status_code == 200
    assert dl_res.headers["content-type"] == "application/pdf"
    assert dl_res.content == input_pdf
    assert hashlib.sha256(dl_res.content).hexdigest() == input_sha256

    # 3. Check Evidence Bundle Root projection and fragments endpoint
    ev_res = integrated_client.get(f"/api/sessions/{session_id}/evidence")
    assert ev_res.status_code == 200
    root_data = ev_res.json()
    assert root_data["schema_version"] == "trace.evidence_bundle/1.0"
    assert root_data["array_counts"]["fragments"] == 0
    assert root_data["array_counts"]["reconstruction_groups"] == 0

    frags_res = integrated_client.get(f"/api/sessions/{session_id}/evidence/fragments")
    assert frags_res.status_code == 200
    assert frags_res.json()["total"] == 0

    # Validate the generated intact evidence bundle against frozen schema using BundleLoader
    from app.services.pdf_validator import build_intact_evidence_bundle
    intact_bundle = build_intact_evidence_bundle(
        media_bytes=input_pdf,
        media_name="sample_document.pdf",
        case_id="CASE-INTACT-01",
        title="Intact PDF Passthrough Verification",
        write_blocked=True,
    )
    assert intact_bundle["fragments"] == []
    assert intact_bundle["reconstruction_groups"] == []
    assert intact_bundle["acquisition"]["media"][0]["write_blocked"] is True

    bundle_file = tmp_path / "intact_bundle.json"
    bundle_file.write_text(json.dumps(intact_bundle), encoding="utf-8")
    loader = BundleLoader(bundle_file)
    assert loader.bundle["bundle_id"] == intact_bundle["bundle_id"]

    # 4. Check Intelligence Report with Person 2 TraceIntelligenceEngine
    from trace.intel.engine import TraceIntelligenceEngine
    req = type("StageReq", (), {
        "evidence": intact_bundle,
        "case_id": "CASE-INTACT-01",
        "bundle_sha256": hashlib.sha256(json.dumps(intact_bundle).encode("utf-8")).hexdigest(),
        "module_version": "1.0.0",
    })()
    report = TraceIntelligenceEngine().analyse(req)
    assert report["validation"]["bundle_conforms"] is True
    assert report["brief"]["key_findings"][0] == "Analyzed 0 evidence fragments"
    assert report["brief"]["key_findings"][1] == "Processed 0 structural reconstruction group(s)"
    assert report["brief"]["key_findings"][2] == "Bundle schema conformance: PASSED"

    # Ensure no false CLM-0002 claiming fragment reconstruction was made
    claim_texts = [c["text"] for c in report["explainability"]["claims_index"]]
    assert not any("assembled" in t and "fragments" in t for t in claim_texts)
    assert any("0 carved fragments across 0 reconstruction group(s)" in t for t in claim_texts)


# ---------------------------------------------------------------------------
# Test 2: Existing Shuffled Synthetic Fixtures Byte-for-Byte Verification
# ---------------------------------------------------------------------------

def test_shuffled_synthetic_fixture_carve_recovers_exact_ground_truth(integrated_client: TestClient):
    """Synthetic blob (blob_1337.bin) with 8 shuffled fragments must reconstruct 100% exact ground truth."""
    gt_path = GROUND_TRUTH_DIR / "synthetic.pdf"
    gt_bytes = gt_path.read_bytes()
    expected_sha256 = hashlib.sha256(gt_bytes).hexdigest()

    response = integrated_client.post(
        "/api/sessions/carve",
        data={
            "fixture_id": "synthetic_blob",
            "case_id": "CASE-SYNTH-01",
            "case_title": "Synthetic Fixture Shuffled Carve",
            "write_blocked": "true",
        },
    )
    assert response.status_code == 201, response.text
    session = response.json()
    session_id = session["session_id"]

    recon_res = integrated_client.get(f"/api/sessions/{session_id}/reconstruction")
    assert recon_res.status_code == 200
    recon = recon_res.json()

    assert recon["is_intact_passthrough"] is False
    assert recon["status"] == "structurally_valid"
    assert recon["complete"] is True
    assert recon["fragments_carved"] == 8
    assert recon["fragments_placed"] == 8
    assert recon["unplaced_fragments_count"] == 0
    assert recon["reconstructed_sha256"] == expected_sha256

    dl_res = integrated_client.get(f"/api/sessions/{session_id}/reconstruction/download")
    assert dl_res.status_code == 200
    assert dl_res.content == gt_bytes
    assert hashlib.sha256(dl_res.content).hexdigest() == expected_sha256


def test_visible_text_fixture_carve_recovers_visible_text_content(integrated_client: TestClient):
    """Visible text fixture (blob_visible_text.bin) with 10 shuffled fragments must reconstruct 100% exact text."""
    gt_path = GROUND_TRUTH_DIR / "visible_text.pdf"
    gt_bytes = gt_path.read_bytes()
    expected_sha256 = hashlib.sha256(gt_bytes).hexdigest()

    response = integrated_client.post(
        "/api/sessions/carve",
        data={
            "fixture_id": "visible_text_blob",
            "case_id": "CASE-VIS-01",
            "case_title": "Visible Text Fixture Carve",
            "write_blocked": "true",
        },
    )
    assert response.status_code == 201, response.text
    session = response.json()
    session_id = session["session_id"]

    recon_res = integrated_client.get(f"/api/sessions/{session_id}/reconstruction")
    assert recon_res.status_code == 200
    recon = recon_res.json()

    assert recon["is_intact_passthrough"] is False
    assert recon["status"] == "structurally_valid"
    assert recon["complete"] is True
    assert recon["fragments_carved"] == 10
    assert recon["fragments_placed"] == 10
    assert recon["unplaced_fragments_count"] == 0
    assert recon["reconstructed_sha256"] == expected_sha256

    dl_res = integrated_client.get(f"/api/sessions/{session_id}/reconstruction/download")
    assert dl_res.status_code == 200
    assert dl_res.content == gt_bytes
    assert b"TRACE FORENSIC RECONSTRUCTION TEST" in dl_res.content
    assert hashlib.sha256(dl_res.content).hexdigest() == expected_sha256


# ---------------------------------------------------------------------------
# Test 3: Incomplete Carve Handling & Non-Fabrication Invariants
# ---------------------------------------------------------------------------

def test_unaligned_raw_media_reports_incomplete_and_never_claims_verified(integrated_client: TestClient):
    """Unaligned raw media that breaks P1 structural chains must report INCOMPLETE with unplaced count."""
    # Synthetic raw unaligned binary: Header in block 0, broken non-ascending object in block 1, padding
    raw_unaligned = (
        b"%PDF-1.4\n% unaligned raw bytes\n" + b"A" * 230 +
        b"\n999 0 obj\n<< /Type /Unknown >>\nendobj\n" + b"B" * 215 +
        b"\n%%EOF\n" + b"C" * 248
    )
    assert len(raw_unaligned) >= 512

    response = integrated_client.post(
        "/api/sessions/carve",
        data={
            "case_id": "CASE-INCOMPLETE-01",
            "case_title": "Incomplete Carving Test",
            "write_blocked": "false",
        },
        files={"file": ("unaligned_disk.bin", io.BytesIO(raw_unaligned), "application/octet-stream")},
    )
    assert response.status_code == 201, response.text
    session = response.json()
    session_id = session["session_id"]

    recon_res = integrated_client.get(f"/api/sessions/{session_id}/reconstruction")
    assert recon_res.status_code == 200
    recon = recon_res.json()

    # Critical forensic invariants:
    assert recon["is_intact_passthrough"] is False
    assert recon["status"] == "incomplete"
    assert recon["complete"] is False
    assert recon["is_verified"] is False
    assert recon["unplaced_fragments_count"] > 0
    assert "incomplete" in recon["forensic_notice"].lower()
    assert recon["reconstructed_sha256"] is None


# ---------------------------------------------------------------------------
# Test 4: Structure-Aligned Scrambled Evidence Upload End-to-End
# ---------------------------------------------------------------------------

def test_scrambled_evidence_upload_reconstruction_end_to_end(integrated_client: TestClient):
    """Uploading TRACE_Scrambled_Evidence.bin reconstructs 100% byte-for-byte and validates against ground truth."""
    scrambled_path = EVIDENCE_DIR / "TRACE_Scrambled_Evidence.bin"
    gt_path = GROUND_TRUTH_DIR / "TRACE_Scramble_Test_GroundTruth.pdf"
    if not scrambled_path.is_file() or not gt_path.is_file():
        pytest.skip("Scrambled evidence fixture not found on disk")

    scrambled_bytes = scrambled_path.read_bytes()
    gt_bytes = gt_path.read_bytes()
    expected_sha256 = hashlib.sha256(gt_bytes).hexdigest()

    response = integrated_client.post(
        "/api/sessions/carve",
        data={
            "case_id": "CASE-SCRAMBLED-01",
            "case_title": "Scrambled PDF Evidence Examination",
            "investigator": "Examiner-Scramble",
            "write_blocked": "true",
            "acquisition_method": "file_copy",
        },
        files={"file": ("TRACE_Scrambled_Evidence.bin", io.BytesIO(scrambled_bytes), "application/octet-stream")},
    )
    assert response.status_code == 201, response.text
    session_id = response.json()["session_id"]

    recon_res = integrated_client.get(f"/api/sessions/{session_id}/reconstruction")
    assert recon_res.status_code == 200
    recon = recon_res.json()

    assert recon["is_intact_passthrough"] is False
    assert recon["complete"] is True
    # Per P1 Honesty Invariant #2, is_verified is False without test-only ground truth oracle
    assert recon["is_verified"] is False
    assert recon["fragments_carved"] == 7
    assert recon["fragments_placed"] == 7
    assert recon["unplaced_fragments_count"] == 0
    assert recon["reconstructed_sha256"] == expected_sha256
    assert recon["byte_coverage"] == "100%"

    dl_res = integrated_client.get(f"/api/sessions/{session_id}/reconstruction/download")
    assert dl_res.status_code == 200
    assert dl_res.content == gt_bytes
    assert hashlib.sha256(dl_res.content).hexdigest() == expected_sha256
    assert b"TRACE SCRAMBLED TEST FILE" in dl_res.content


# ---------------------------------------------------------------------------
# Test 5: Arbitrary Non-PDF Binary Upload
# ---------------------------------------------------------------------------

def test_arbitrary_binary_upload_yields_incomplete_with_zero_placed(integrated_client: TestClient):
    """Uploading arbitrary non-PDF bytes must report incomplete, 0 placed fragments, and never return fake files."""
    arbitrary_bytes = b"\x00\x01\x02\x03\x04\x05" * 256  # 1536 bytes of non-PDF data

    response = integrated_client.post(
        "/api/sessions/carve",
        data={
            "case_id": "CASE-RANDOM-01",
            "case_title": "Arbitrary Non-PDF Data",
            "write_blocked": "false",
        },
        files={"file": ("random_stream.bin", io.BytesIO(arbitrary_bytes), "application/octet-stream")},
    )
    assert response.status_code == 201, response.text
    session_id = response.json()["session_id"]

    recon_res = integrated_client.get(f"/api/sessions/{session_id}/reconstruction")
    assert recon_res.status_code == 200
    recon = recon_res.json()

    assert recon["is_intact_passthrough"] is False
    assert recon["complete"] is False
    assert recon["status"] == "incomplete"
    assert recon["is_verified"] is False
    assert recon["fragments_placed"] == 0
    assert recon["unplaced_fragments_count"] > 0
    assert recon["reconstructed_sha256"] is None

    # Downloading an incomplete reconstruction with 0 placed fragments returns 404 (not a fake file)
    dl_res = integrated_client.get(f"/api/sessions/{session_id}/reconstruction/download")
    assert dl_res.status_code == 404
