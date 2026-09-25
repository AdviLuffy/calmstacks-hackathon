"""Comprehensive automated tests for multi-format recovery, disk analysis, and Gemini AI integration."""

import hashlib
import io
import json
import struct
import zlib
import zipfile
import pytest
from starlette.testclient import TestClient

from trace.ai.client import ResilientGeminiClient
from trace.ai.config import GeminiSettings, load_gemini_settings
from trace.ai.mock_client import MockGeminiClient
from trace.ai.schemas import AIFragmentClassification, AIRelationshipInference
from trace.ai.service import GeminiForensicService
from trace.cases.case import ForensicCase
from trace.cases.report import ForensicReportGenerator
from trace.recovery.core.carver import MultiFormatCarver
from trace.recovery.dataset import (
    build_synthetic_fat32_image,
    build_synthetic_jpeg,
    build_synthetic_png,
    build_synthetic_zip,
    run_demonstration_suite,
)
from trace.recovery.disk.disk_carver import ForensicDiskAnalyzer
from trace.recovery.disk.fat32 import Fat32Parser
from trace.recovery.disk.mbr_gpt import parse_gpt, parse_mbr
from trace.recovery.formats.jpeg.handler import JpegFormatHandler
from trace.recovery.formats.pdf.handler import PdfFormatHandler
from trace.recovery.formats.png.handler import PngFormatHandler
from trace.recovery.formats.text.handler import TextFormatHandler
from trace.recovery.formats.zip.handler import ZipFormatHandler
from trace.recovery.models import FragmentCandidate, RecoveryCategory
from trace.recovery.prioritization import RecoveryPrioritizer


# ==============================================================================
# 1. Multi-Format Format Handlers Tests
# ==============================================================================

def test_png_format_handler_recovery_and_crc_validation():
    """Verify PNG chunk parsing, CRC-32 validation, and exact reconstruction."""
    gt_png, shuf_png = build_synthetic_png()
    handler = PngFormatHandler()

    # Identify
    conf = handler.identify(gt_png, "test.png")
    assert conf.format_name == "png"
    assert conf.confidence > 0.8
    assert "magic_bytes:PNG" in conf.structural_indicators

    # Carve fragments
    frags = handler.carve_fragments(shuf_png)
    assert len(frags) >= 3

    # Reconstruct
    rec_bytes, placed, unplaced, meta = handler.order_and_reconstruct(frags)
    assert len(unplaced) == 0
    assert rec_bytes == gt_png
    assert hashlib.sha256(rec_bytes).hexdigest() == hashlib.sha256(gt_png).hexdigest()

    # Validate
    val = handler.validate(rec_bytes)
    assert val.is_valid is True
    assert "crc32_checksums" in val.checks_passed
    assert val.metadata["width"] == 1
    assert val.metadata["height"] == 1


def test_jpeg_format_handler_recovery_and_validation():
    """Verify JPEG marker parsing, segment ordering, and frame validation."""
    gt_jpg, shuf_jpg = build_synthetic_jpeg()
    handler = JpegFormatHandler()

    # Identify
    conf = handler.identify(gt_jpg, "photo.jpg")
    assert conf.format_name == "jpeg"
    assert conf.confidence > 0.7

    # Carve and reconstruct
    frags = handler.carve_fragments(shuf_jpg)
    rec_bytes, placed, unplaced, meta = handler.order_and_reconstruct(frags)
    assert rec_bytes == gt_jpg
    assert hashlib.sha256(rec_bytes).hexdigest() == hashlib.sha256(gt_jpg).hexdigest()

    val = handler.validate(rec_bytes)
    assert val.is_valid is True
    assert "marker_soi" in val.checks_passed
    assert "marker_eoi" in val.checks_passed


def test_zip_format_handler_security_and_traversal_defense():
    """Verify ZIP central directory validation, Zip-Slip defense, and text extraction."""
    gt_zip, shuf_zip = build_synthetic_zip()
    handler = ZipFormatHandler()

    conf = handler.identify(gt_zip, "archive.zip")
    assert conf.format_name == "zip"
    assert conf.confidence > 0.7

    frags = handler.carve_fragments(shuf_zip)
    rec_bytes, placed, _, _ = handler.order_and_reconstruct(frags)
    assert rec_bytes == gt_zip

    val = handler.validate(rec_bytes)
    assert val.is_valid is True
    assert "crc32_checksums" in val.checks_passed
    assert "evidence.txt" in val.metadata["entries"]

    # Test malicious zip-slip attempt
    malicious_buf = io.BytesIO()
    with zipfile.ZipFile(malicious_buf, "w") as zf:
        zf.writestr("../../etc/passwd", "root:x:0:0::/root:/bin/bash\n")
    malicious_val = handler.validate(malicious_buf.getvalue())
    assert any("path traversal" in w.lower() for w in malicious_val.warnings)


def test_text_format_handler_chronological_ordering():
    """Verify text line extraction and chronological ordering of scrambled log entries."""
    handler = TextFormatHandler()
    line1 = b"2026-09-25T10:00:00Z [INFO] Service started successfully\n"
    line2 = b"2026-09-25T10:05:00Z [WARN] Elevated disk read latency\n"
    line3 = b"2026-09-25T10:10:00Z [ERROR] Segmentation fault in worker thread\n"

    # Scramble lines
    scrambled = [
        FragmentCandidate("F2", 0, len(line2), line2, "text", "log_entry", ("TIMESTAMP",)),
        FragmentCandidate("F3", len(line2), len(line3), line3, "text", "log_entry", ("TIMESTAMP",)),
        FragmentCandidate("F1", len(line2) + len(line3), len(line1), line1, "text", "log_entry", ("TIMESTAMP",)),
    ]

    rec_bytes, placed, _, _ = handler.order_and_reconstruct(scrambled)
    assert rec_bytes == line1 + line2 + line3
    assert placed == ["F1", "F2", "F3"]


# ==============================================================================
# 2. Disk Analysis & Filesystem Tests
# ==============================================================================

def test_mbr_and_fat32_deleted_file_recovery():
    """Verify read-only MBR partition parsing and FAT32 deleted file discovery."""
    disk_bytes = build_synthetic_fat32_image()

    # 1. Parse MBR
    parts = parse_mbr(disk_bytes[:512])
    assert len(parts) == 1
    assert parts[0].scheme == "MBR"
    assert "FAT32" in parts[0].partition_type
    assert parts[0].start_lba == 1

    # 2. Parse FAT32
    vbr_offset = 512
    part_bytes = disk_bytes[vbr_offset:]
    fat_parser = Fat32Parser(part_bytes)
    assert fat_parser.bpb is not None
    assert fat_parser.bpb.bytes_per_sector == 512
    assert fat_parser.bpb.fs_type == "FAT32"

    # 3. Discover Active and Deleted files
    files = fat_parser.scan_directory()
    assert len(files) >= 2

    active_files = [f for f in files if not f.is_deleted]
    deleted_files = [f for f in files if f.is_deleted]

    assert len(active_files) == 1
    assert "EVID001" in active_files[0].name
    assert active_files[0].data == b"ACTIVE EVIDENCE NOTE 001"

    assert len(deleted_files) == 1
    assert "SECRET" in deleted_files[0].name
    assert deleted_files[0].data == b"RECOVERED DELETED EXFILTRATION RECORD"


def test_forensic_disk_analyzer_unified():
    """Verify unified disk analyzer detects partition scheme, filesystems, and carved artifacts."""
    disk_bytes = build_synthetic_fat32_image()
    analyzer = ForensicDiskAnalyzer(write_blocked=True)
    report = analyzer.analyze_bytes(disk_bytes, source_name="synthetic.img")

    assert report.partition_scheme == "MBR"
    assert len(report.partitions) == 1
    assert len(report.filesystem_files) >= 2
    assert report.write_blocked_attested is True


# ==============================================================================
# 3. Gemini AI Integration & Resilient Fallback Queue Tests
# ==============================================================================

def test_gemini_settings_and_offline_behavior():
    """Verify settings defaults and graceful operation when key is unset."""
    settings = load_gemini_settings()
    assert len(settings.model_preference) >= 3
    assert "gemini-3.8-flash" in settings.model_preference

    # With disabled settings
    disabled_settings = GeminiSettings(enabled=False, api_key="", model_preference=("gemini-3.8-flash",))
    client = ResilientGeminiClient(settings=disabled_settings)
    res = client.generate_structured("prompt", AIFragmentClassification)
    assert res.success is False
    assert res.is_disabled is True
    assert "disabled" in res.provenance.error.lower()


def test_gemini_model_fallback_queue_simulation():
    """Simulate primary model failure triggering fallback to secondary model in queue."""
    mock_client = MockGeminiClient(fail_models=["gemini-3.8-flash"])
    service = GeminiForensicService(client=mock_client)

    frag = FragmentCandidate("FRAG-01", 0, 256, b"%PDF-1.4\n", "pdf", "header", ("HEADER",))
    res = service.classify_fragment(frag)

    assert res.success is True
    assert res.data is not None
    assert res.data.likely_file_type == "pdf"
    # Provenance proves fallback occurred!
    assert res.provenance.model_used == "gemini-3.5-flash-lite"
    assert res.provenance.fallback_occurred is True
    assert res.provenance.attempts[0]["status"] == "model_not_found"
    assert res.provenance.attempts[1]["status"] == "success"


def test_gemini_auth_error_halts_immediately():
    """Verify authentication error does not loop through fallback queue endlessly."""
    mock_client = MockGeminiClient(auth_error=True)
    res = mock_client.generate_structured("prompt", AIFragmentClassification)
    assert res.success is False
    assert "authentication" in res.provenance.error.lower()
    assert len(res.provenance.attempts) == 1
    assert res.provenance.attempts[0]["status"] == "auth_error"


def test_gemini_quota_exhausted_halts_immediately():
    """Verify quota exhaustion does not loop through fallback queue endlessly."""
    mock_client = MockGeminiClient(quota_exhausted=True)
    res = mock_client.generate_structured("prompt", AIFragmentClassification)
    assert res.success is False
    assert "quota" in res.provenance.error.lower()
    assert len(res.provenance.attempts) == 1


# ==============================================================================
# 4. API Endpoints Integration Tests
# ==============================================================================

@pytest.fixture
def integrated_client(make_client) -> TestClient:
    from app.services.session_store import InMemorySessionStore
    from p3_helpers import make_settings, make_wiring
    return make_client(
        settings=make_settings(),
        wiring=make_wiring(),
        store=InMemorySessionStore(),
    )


def test_api_ai_status_endpoint(integrated_client: TestClient):
    """Verify GET /api/ai/status exposes model queue and privacy enforcement."""
    res = integrated_client.get("/api/ai/status")
    assert res.status_code == 200
    data = res.json()
    assert "model_preference_queue" in data
    assert data["data_minimization_enforced"] is True
    assert data["prompt_injection_defense"] == "untrusted_evidence_boundary"


def test_api_report_generation_endpoints(integrated_client: TestClient):
    """Verify session HTML and JSON forensic reports generate successfully."""
    # 1. Carve synthetic blob
    carve_res = integrated_client.post(
        "/api/sessions/carve",
        data={"fixture_id": "synthetic_blob", "case_id": "CASE-TEST-REP", "investigator": "Analyst"},
    )
    assert carve_res.status_code == 201
    session_id = carve_res.json()["session_id"]

    # 2. Get HTML report
    html_res = integrated_client.get(f"/api/sessions/{session_id}/report.html")
    assert html_res.status_code == 200
    assert "text/html" in html_res.headers["content-type"]
    assert "TRACE EVIDENCE INTELLIGENCE REPORT" in html_res.text
    assert "CASE-TEST-REP" in html_res.text

    # 3. Get JSON report
    json_res = integrated_client.get(f"/api/sessions/{session_id}/report.json")
    assert json_res.status_code == 200
    assert "application/json" in json_res.headers["content-type"]
    rep_data = json_res.json()
    assert rep_data["case"]["case_id"] == "CASE-TEST-REP"
    assert "summary" in rep_data

    # 4. Trigger AI analysis for session
    ai_res = integrated_client.get(f"/api/sessions/{session_id}/ai-analysis")
    assert ai_res.status_code == 200
    ai_body = ai_res.json()
    assert "explanation" in ai_body
    if not ai_body.get("configured", False):
        assert ai_body["message"] == "AI analysis unavailable — configure provider"
    else:
        assert ai_body["success"] is True


def test_full_demonstration_suite_passes():
    """Verify end-to-end multi-format demonstration suite executes with 100% pass."""
    exit_code = run_demonstration_suite()
    assert exit_code == 0
