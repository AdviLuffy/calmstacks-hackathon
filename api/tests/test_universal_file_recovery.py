"""Comprehensive test suite for Phase 12: Universal File Recovery Engine.

Validates format-aware recovery, deep container repair, signature carving,
forensic honesty (authentic vs synthesized metrics), and API integration across:
- Images: JPEG, PNG
- Office Documents: DOCX
- Archives: ZIP
- Video: MP4
"""

import hashlib
import io
import struct
import zlib
import zipfile
import pytest
from starlette.testclient import TestClient

from trace.recovery.core.carver import MultiFormatCarver
from trace.recovery.formats.jpeg.handler import JpegFormatHandler
from trace.recovery.formats.png.handler import PngFormatHandler
from trace.recovery.formats.zip.handler import ZipFormatHandler
from trace.recovery.formats.docx.handler import DocxFormatHandler
from trace.recovery.formats.mp4.handler import Mp4FormatHandler
from trace.recovery.dataset import (
    build_synthetic_jpeg,
    build_synthetic_png,
    build_synthetic_zip,
)
from app.main import app


# ==============================================================================
# Helpers for generating realistic corrupted fixtures
# ==============================================================================

def create_minimal_valid_png() -> bytes:
    """Creates a tiny 1x1 valid red PNG using standard zlib."""
    gt_png, _ = build_synthetic_png()
    return gt_png


def create_minimal_valid_jpeg() -> bytes:
    """Creates a minimal valid JPEG image."""
    gt_jpg, _ = build_synthetic_jpeg()
    return gt_jpg


def create_minimal_valid_zip() -> bytes:
    """Creates a valid zip archive containing a text file and json file."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("evidence_log.txt", "Forensic observation: subject entered perimeter at 02:14 UTC.")
        zf.writestr("metadata.json", '{"case_id": "TRACE-2026-X", "priority": "high"}')
    return buf.getvalue()


def create_minimal_valid_docx() -> bytes:
    """Creates a minimal valid ECMA-376 DOCX document."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        content_types = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
            '  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>\n'
            '  <Default Extension="xml" ContentType="application/xml"/>\n'
            '  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>\n'
            '</Types>'
        )
        zf.writestr("[Content_Types].xml", content_types)
        
        rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">\n'
            '  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>\n'
            '</Relationships>'
        )
        zf.writestr("_rels/.rels", rels)
        
        doc_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">\n'
            '  <w:body>\n'
            '    <w:p><w:r><w:t>Confidential Forensic Memorandum</w:t></w:r></w:p>\n'
            '    <w:p><w:r><w:t>The suspect drive was seized under warrant #4092-B.</w:t></w:r></w:p>\n'
            '  </w:body>\n'
            '</w:document>'
        )
        zf.writestr("word/document.xml", doc_xml)
    return buf.getvalue()


def create_minimal_valid_mp4() -> bytes:
    """Creates a minimal valid ISOBMFF MP4 file containing ftyp, moov, and mdat boxes."""
    # ftyp box
    brand = b"isom"
    minor_ver = struct.pack(">I", 512)
    compat = b"isomiso2avc1mp41"
    ftyp_payload = brand + minor_ver + compat
    ftyp_box = struct.pack(">I4s", 8 + len(ftyp_payload), b"ftyp") + ftyp_payload
    
    # moov box (mvhd + trak)
    mvhd_payload = b"\x00" * 100
    mvhd_box = struct.pack(">I4s", 8 + len(mvhd_payload), b"mvhd") + mvhd_payload
    moov_box = struct.pack(">I4s", 8 + len(mvhd_box), b"moov") + mvhd_box
    
    # mdat box containing dummy H.264 NAL units (SPS: 0x67, PPS: 0x68, IDR: 0x65)
    sps_nalu = b"\x00\x00\x00\x01\x67\x42\x00\x1f\xe9\x02\xc1\x2c\x80"
    idr_nalu = b"\x00\x00\x00\x01\x65" + b"\xff" * 200
    mdat_payload = sps_nalu + idr_nalu
    mdat_box = struct.pack(">I4s", 8 + len(mdat_payload), b"mdat") + mdat_payload
    
    return ftyp_box + moov_box + mdat_box


# ==============================================================================
# 1. JPEG Recovery Handler Tests
# ==============================================================================

class TestJpegRecoveryHandler:
    def test_intact_jpeg_repair_and_validation(self):
        handler = JpegFormatHandler()
        valid_jpg = create_minimal_valid_jpeg()
        
        result = handler.repair_or_recover(valid_jpg, "photo.jpg")
        assert result.format_name == "jpeg"
        assert result.is_recovered is True
        assert result.is_openable is True
        assert result.preview_type == "image"
        assert result.preview_data.startswith("data:image/jpeg;base64,")
        assert result.confidence_score >= 80.0
        assert result.authentic_bytes_count == len(valid_jpg)
        assert result.synthesized_bytes_count == 0
        assert "width" in result.diagnostics
        assert "height" in result.diagnostics

    def test_jpeg_preamble_garbage_stripped(self):
        handler = JpegFormatHandler()
        valid_jpg = create_minimal_valid_jpeg()
        corrupted = b"<!DOCTYPE html><html><body>Error 404</body></html>" + valid_jpg
        
        result = handler.repair_or_recover(corrupted, "corrupted.jpg")
        assert result.is_recovered is True
        assert result.is_openable is True
        assert any("stripped_preamble" in op for op in result.operations_performed)

    def test_jpeg_truncated_sealed_with_synthetic_eoi(self):
        handler = JpegFormatHandler()
        valid_jpg = create_minimal_valid_jpeg()
        assert valid_jpg.endswith(b"\xff\xd9")
        truncated = valid_jpg[:-2]
        
        result = handler.repair_or_recover(truncated, "truncated.jpg")
        assert result.is_recovered is True
        assert result.repaired_bytes.endswith(b"\xff\xd9")
        assert result.synthesized_bytes_count == 2
        assert any("synthesized_truncated_eoi_marker" in op for op in result.operations_performed)

    def test_jpeg_missing_soi_synthesized(self):
        handler = JpegFormatHandler()
        valid_jpg = create_minimal_valid_jpeg()
        assert valid_jpg.startswith(b"\xff\xd8")
        missing_soi = valid_jpg[2:]
        
        result = handler.repair_or_recover(missing_soi, "no_soi.jpg")
        assert result.is_recovered is True
        assert result.repaired_bytes.startswith(b"\xff\xd8")
        assert result.synthesized_bytes_count >= 2
        assert any("synthesized_missing_soi_header" in op for op in result.operations_performed)

    def test_jpeg_forensic_honesty_unsupported_limits(self):
        handler = JpegFormatHandler()
        valid_jpg = create_minimal_valid_jpeg()
        result = handler.repair_or_recover(valid_jpg, "test.jpg")
        assert len(result.unsupported_capabilities) > 0
        assert any("progressive" in cap.lower() for cap in result.unsupported_capabilities)


# ==============================================================================
# 2. PNG Recovery Handler Tests
# ==============================================================================

class TestPngRecoveryHandler:
    def test_intact_png_repair_and_validation(self):
        handler = PngFormatHandler()
        valid_png = create_minimal_valid_png()
        
        result = handler.repair_or_recover(valid_png, "graphic.png")
        assert result.format_name == "png"
        assert result.is_recovered is True
        assert result.is_openable is True
        assert result.preview_type == "image"
        assert result.preview_data.startswith("data:image/png;base64,")
        assert result.confidence_score >= 85.0
        assert result.diagnostics["width"] == 1
        assert result.diagnostics["height"] == 1

    def test_png_missing_magic_bytes_synthesized(self):
        handler = PngFormatHandler()
        valid_png = create_minimal_valid_png()
        stripped_png = valid_png[8:]
        
        result = handler.repair_or_recover(stripped_png, "no_magic.png")
        assert result.is_recovered is True
        assert result.repaired_bytes.startswith(b"\x89PNG\r\n\x1a\n")
        assert result.synthesized_bytes_count >= 8
        assert any("synthesized_missing_png_signature" in op for op in result.operations_performed)

    def test_png_corrupted_crc_recalculated(self):
        handler = PngFormatHandler()
        valid_png = create_minimal_valid_png()
        corrupted_crc_png = valid_png[:29] + b"\x00\x00\x00\x00" + valid_png[33:]
        
        result = handler.repair_or_recover(corrupted_crc_png, "bad_crc.png")
        assert result.is_recovered is True
        assert any("recalculated_crc" in op for op in result.operations_performed)

    def test_png_truncated_iend_synthesized(self):
        handler = PngFormatHandler()
        valid_png = create_minimal_valid_png()
        truncated_png = valid_png[:-12]
        
        result = handler.repair_or_recover(truncated_png, "no_iend.png")
        assert result.is_recovered is True
        assert result.repaired_bytes.endswith(b"IEND\xaeB`\x82")
        assert any("synthesized_missing_iend_chunk" in op for op in result.operations_performed)


# ==============================================================================
# 3. ZIP Recovery Handler Tests
# ==============================================================================

class TestZipRecoveryHandler:
    def test_intact_zip_recovery_and_extraction(self):
        handler = ZipFormatHandler()
        valid_zip = create_minimal_valid_zip()
        
        result = handler.repair_or_recover(valid_zip, "backup.zip")
        assert result.format_name == "zip"
        assert result.is_recovered is True
        assert result.is_openable is True
        assert result.preview_type == "archive"
        assert len(result.extracted_items) == 2
        assert "Forensic observation" in result.salvaged_text

    def test_zip_destroyed_central_directory_reconstructed(self):
        """Simulates catastrophic corruption where Central Directory and EOCD are completely wiped."""
        handler = ZipFormatHandler()
        valid_zip = create_minimal_valid_zip()
        
        cd_pos = valid_zip.find(b"\x50\x4b\x01\x02")
        assert cd_pos > 0
        wiped_cd_zip = valid_zip[:cd_pos]  # Only local file records remain!
        
        result = handler.repair_or_recover(wiped_cd_zip, "wiped_cd.zip")
        assert result.is_recovered is True
        assert result.is_openable is True
        assert any("reconstructed_central_directory" in op for op in result.operations_performed)
        assert len(result.extracted_items) == 2
        assert result.synthesized_bytes_count > 0

    def test_zip_slip_security_defense(self):
        """Verifies that Zip-Slip path traversal entries are quarantined."""
        handler = ZipFormatHandler()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("../../etc/shadow", "root:*:0:0:root:/root:/bin/bash")
            zf.writestr("legit.txt", "safe file")
        malicious_zip = buf.getvalue()
        
        result = handler.repair_or_recover(malicious_zip, "exploit.zip")
        assert result.is_recovered is True
        assert any("quarantined_zip_slip" in op for op in result.operations_performed)
        assert any(item["name"] == "legit.txt" for item in result.extracted_items)


# ==============================================================================
# 4. DOCX Dedicated Recovery Handler Tests
# ==============================================================================

class TestDocxRecoveryHandler:
    def test_intact_docx_recovery_and_text_extraction(self):
        handler = DocxFormatHandler()
        valid_docx = create_minimal_valid_docx()
        
        result = handler.repair_or_recover(valid_docx, "report.docx")
        assert result.format_name == "docx"
        assert result.is_recovered is True
        assert result.is_openable is True
        assert result.preview_type == "document"
        assert "Confidential Forensic Memorandum" in result.salvaged_text
        assert "suspect drive was seized" in result.salvaged_text
        assert result.diagnostics["paragraph_count"] >= 2

    def test_docx_missing_content_types_synthesized(self):
        """Tests that a DOCX with missing [Content_Types].xml is repaired with a synthetic one."""
        handler = DocxFormatHandler()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Classified notes</w:t></w:r></w:p></w:body></w:document>')
        corrupted_docx = buf.getvalue()
        
        result = handler.repair_or_recover(corrupted_docx, "no_types.docx")
        assert result.is_recovered is True
        assert result.is_openable is True
        assert any("synthesized_missing_opc_content_types" in op for op in result.operations_performed)
        assert "Classified notes" in result.salvaged_text

    def test_docx_malformed_xml_resilient_salvaging(self):
        """Tests that malformed or truncated XML in word/document.xml is salvaged via fallback scanner."""
        handler = DocxFormatHandler()
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("word/document.xml", '<w:document><w:body><w:p><w:t>Surviving sentence 1.</w:t><broken<tag><w:t>Surviving sentence 2.</w:t>')
        broken_xml_docx = buf.getvalue()
        
        result = handler.repair_or_recover(broken_xml_docx, "broken_xml.docx")
        assert result.is_recovered is True
        assert "Surviving sentence 1." in result.salvaged_text
        assert "Surviving sentence 2." in result.salvaged_text


# ==============================================================================
# 5. MP4 Dedicated Video Recovery Handler Tests
# ==============================================================================

class TestMp4RecoveryHandler:
    def test_intact_mp4_recovery_and_atom_parsing(self):
        handler = Mp4FormatHandler()
        valid_mp4 = create_minimal_valid_mp4()
        
        result = handler.repair_or_recover(valid_mp4, "surveillance.mp4")
        assert result.format_name == "mp4"
        assert result.is_recovered is True
        assert result.preview_type == "video"
        assert result.confidence_score >= 80.0
        assert "ftyp" in result.diagnostics["atoms"]
        assert "moov" in result.diagnostics["atoms"]
        assert "mdat" in result.diagnostics["atoms"]

    def test_mp4_missing_moov_index_synthesized(self):
        """Simulates a crashed recording (e.g. bodycam power loss) where moov index was never written."""
        handler = Mp4FormatHandler()
        valid_mp4 = create_minimal_valid_mp4()
        
        ftyp_end = valid_mp4.find(b"moov") - 4
        mdat_pos = valid_mp4.find(b"mdat") - 4
        crashed_mp4 = valid_mp4[:ftyp_end] + valid_mp4[mdat_pos:]
        
        result = handler.repair_or_recover(crashed_mp4, "crashed_cam.mp4")
        assert result.is_recovered is True
        assert any("synthesized_moov_index_atom" in op for op in result.operations_performed)
        assert result.synthesized_bytes_count > 0
        assert b"moov" in result.repaired_bytes

    def test_mp4_forensic_honesty_unsupported_limits(self):
        handler = Mp4FormatHandler()
        valid_mp4 = create_minimal_valid_mp4()
        result = handler.repair_or_recover(valid_mp4, "video.mp4")
        assert len(result.unsupported_capabilities) > 0
        assert any("audio" in cap.lower() for cap in result.unsupported_capabilities)


# ==============================================================================
# 6. MultiFormatCarver Integration
# ==============================================================================

class TestMultiFormatCarver:
    def test_carver_registers_all_handlers(self):
        carver = MultiFormatCarver()
        handler_names = [h.format_name for h in carver.handlers]
        assert "jpeg" in handler_names
        assert "png" in handler_names
        assert "zip" in handler_names
        assert "docx" in handler_names
        assert "mp4" in handler_names
        assert "pdf" in handler_names

    def test_carver_identifies_all_formats(self):
        carver = MultiFormatCarver()
        
        formats = {
            "jpg": (create_minimal_valid_jpeg(), "jpeg"),
            "png": (create_minimal_valid_png(), "png"),
            "zip": (create_minimal_valid_zip(), "zip"),
            "docx": (create_minimal_valid_docx(), "docx"),
            "mp4": (create_minimal_valid_mp4(), "mp4"),
        }
        for ext, (data, expected_fmt) in formats.items():
            conf = carver.identify_format(data, f"file.{ext}")
            assert conf.format_name == expected_fmt, f"Failed for {ext}: got {conf.format_name}"


# ==============================================================================
# 7. End-to-End FastAPI Ingestion, Preview & Download Tests
# ==============================================================================

@pytest.fixture
def client():
    return TestClient(app)


class TestMultiFormatApiIntegration:
    def test_e2e_jpeg_upload_and_preview(self, client):
        data = create_minimal_valid_jpeg()
        resp = client.post(
            "/api/sessions/carve",
            files={"file": ("evidence.jpg", data, "image/jpeg")},
            data={"case_id": "TEST-CASE-JPG"},
        )
        assert resp.status_code in (200, 201)
        session_id = resp.json()["session_id"]
        
        rec_resp = client.get(f"/api/sessions/{session_id}/reconstruction")
        assert rec_resp.status_code == 200
        rec_data = rec_resp.json()
        assert rec_data["detected_format"] == "jpeg"
        assert rec_data["mime_type"] == "image/jpeg"
        assert rec_data["default_extension"] == ".jpg"
        assert rec_data["preview_type"] == "image"
        assert rec_data["preview_data"].startswith("data:image/jpeg;base64,")
        assert rec_data["has_repaired_file"] is True
        
        view_resp = client.get(f"/api/sessions/{session_id}/reconstruction/view")
        assert view_resp.status_code == 200
        assert "image/jpeg" in view_resp.headers["content-type"]
        
        dl_resp = client.get(f"/api/sessions/{session_id}/reconstruction/download?mode=repaired")
        assert dl_resp.status_code == 200
        assert "attachment" in dl_resp.headers.get("content-disposition", "")
        assert ".jpg" in dl_resp.headers.get("content-disposition", "")

    def test_e2e_zip_upload_and_preview(self, client):
        data = create_minimal_valid_zip()
        resp = client.post(
            "/api/sessions/carve",
            files={"file": ("seized_archive.zip", data, "application/zip")},
            data={"case_id": "TEST-CASE-ZIP"},
        )
        assert resp.status_code in (200, 201)
        session_id = resp.json()["session_id"]
        
        rec_resp = client.get(f"/api/sessions/{session_id}/reconstruction")
        assert rec_resp.status_code == 200
        rec_data = rec_resp.json()
        assert rec_data["detected_format"] == "zip"
        assert rec_data["preview_type"] == "archive"
        assert len(rec_data["extracted_items"]) == 2
        assert "Forensic observation" in rec_data["salvaged_text"]
        
        dl_resp = client.get(f"/api/sessions/{session_id}/reconstruction/download?mode=repaired")
        assert dl_resp.status_code == 200
        assert ".zip" in dl_resp.headers.get("content-disposition", "")

    def test_e2e_docx_upload_and_preview(self, client):
        data = create_minimal_valid_docx()
        resp = client.post(
            "/api/sessions/carve",
            files={"file": ("warrant.docx", data, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
            data={"case_id": "TEST-CASE-DOCX"},
        )
        assert resp.status_code in (200, 201)
        session_id = resp.json()["session_id"]
        
        rec_resp = client.get(f"/api/sessions/{session_id}/reconstruction")
        assert rec_resp.status_code == 200
        rec_data = rec_resp.json()
        assert rec_data["detected_format"] == "docx"
        assert rec_data["preview_type"] == "document"
        assert "Confidential Forensic Memorandum" in rec_data["salvaged_text"]
        
        dl_resp = client.get(f"/api/sessions/{session_id}/reconstruction/download?mode=repaired")
        assert dl_resp.status_code == 200
        assert ".docx" in dl_resp.headers.get("content-disposition", "")

    def test_e2e_mp4_upload_and_preview(self, client):
        data = create_minimal_valid_mp4()
        resp = client.post(
            "/api/sessions/carve",
            files={"file": ("cctv_footage.mp4", data, "video/mp4")},
            data={"case_id": "TEST-CASE-MP4"},
        )
        assert resp.status_code in (200, 201)
        session_id = resp.json()["session_id"]
        
        rec_resp = client.get(f"/api/sessions/{session_id}/reconstruction")
        assert rec_resp.status_code == 200
        rec_data = rec_resp.json()
        assert rec_data["detected_format"] == "mp4"
        assert rec_data["mime_type"] == "video/mp4"
        assert rec_data["preview_type"] == "video"
        
        view_resp = client.get(f"/api/sessions/{session_id}/reconstruction/view")
        assert view_resp.status_code == 200
        assert "video/mp4" in view_resp.headers["content-type"]
