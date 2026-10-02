"""Comprehensive tests for TRACE Phase 9: Advanced Multimodal Document Reconstruction Engine.

Verifies:
- Text and typography reconstruction (content stream parsing, reading order, headings)
- Media and figure recovery (image XObjects, captions, corruption handling)
- Tabular data reconstruction (grid topology, row/column alignment, unrecoverable cells)
- Mathematical equation parsing (inline/display/numbered formulas, LaTeX transcription)
- Document layout engine (multi-column, multi-page, academic geometry)
- Multimodal PDF builder (valid PDF synthesis, provenance watermarks)
- Artifact manager (5 separate artifacts, SHA256 integrity, report export)
- End-to-end reconstruction engine (zero Gemini calls, strict provenance, no hallucinations)
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import pytest

from trace.multimodal.representation import (
    BoundingBox,
    DocumentElement,
    DocumentPage,
    ElementType,
    NormalizedDocument,
    ProvenanceCategory,
)
from trace.reconstruction.artifacts import ReconstructionArtifactManager
from trace.reconstruction.engine import (
    AdvancedMultimodalReconstructionEngine,
    ReconstructionResult,
)
from trace.reconstruction.equation_reconstructor import EquationReconstructor
from trace.reconstruction.layout_engine import DocumentLayoutEngine
from trace.reconstruction.media_reconstructor import MediaReconstructor
from trace.reconstruction.models import (
    EquationElement,
    EquationType,
    ImageElement,
    ImageFormat,
    MultimodalReconstructionReport,
    ProvenanceBreakdown,
    ReconstructionArtifacts,
    TableCell,
    TableRow,
    TableStructure,
    TextBlockData,
)
from trace.reconstruction.pdf_builder import MultimodalPdfBuilder
from trace.reconstruction.table_reconstructor import TableReconstructor
from trace.reconstruction.text_reconstructor import TextReconstructor


# Sample minimal PDF text stream
SAMPLE_CONTENT_STREAM = (
    b"BT\n"
    b"/F1 16 Tf\n"
    b"1 0 0 1 54 720 Tm\n"
    b"(Neural Forensics for Damaged Evidence) Tj\n"
    b"ET\n"
    b"BT\n"
    b"/F1 10 Tf\n"
    b"1 0 0 1 54 680 Tm\n"
    b"(Abstract: We present an advanced multimodal recovery pipeline for PDFs.) Tj\n"
    b"ET\n"
    b"BT\n"
    b"/F1 10 Tf\n"
    b"1 0 0 1 54 600 Tm\n"
    b"[(Column 1 content text line) -50 ( continuing with words)] TJ\n"
    b"ET\n"
    b"BT\n"
    b"/F1 10 Tf\n"
    b"1 0 0 1 350 600 Tm\n"
    b"(Column 2 right side text line) Tj\n"
    b"ET\n"
)


class TestTextReconstructor:
    """Tests for TextReconstructor."""

    def test_decode_pdf_string_escapes(self):
        tr = TextReconstructor()
        assert tr.decode_pdf_string(r"(Hello\ World)") == "Hello World"
        assert tr.decode_pdf_string(r"(\(Parens\))") == "(Parens)"
        assert tr.decode_pdf_string(r"(\101\102\103)") == "ABC"
        assert tr.decode_pdf_string("<48656c6c6f>") == "Hello"

    def test_extract_text_from_stream(self):
        tr = TextReconstructor()
        blocks = tr.extract_text_from_stream(
            stream_bytes=SAMPLE_CONTENT_STREAM,
            page_number=1,
            page_width=612.0,
            page_height=792.0,
        )
        assert len(blocks) >= 3

        # Heading detection
        title_block = blocks[0]
        assert "Neural Forensics" in title_block.text
        assert title_block.is_heading is True
        assert title_block.heading_level == 1
        assert title_block.provenance == ProvenanceCategory.AUTHENTIC

        # Multi-column check
        col1_blocks = [b for b in blocks if b.column_index == 1]
        assert len(col1_blocks) >= 1
        assert "Column 2" in col1_blocks[0].text

    def test_organize_reading_order(self):
        tr = TextReconstructor()
        blocks = tr.extract_text_from_stream(SAMPLE_CONTENT_STREAM, page_number=1)
        ordered = tr.organize_reading_order(blocks, page_width=612.0)
        assert len(ordered) == len(blocks)
        assert ordered[0].is_heading is True  # Title first
        # Sequential indices
        indices = [b.reading_order_index for b in ordered]
        assert indices == list(range(len(ordered)))


class TestMediaReconstructor:
    """Tests for MediaReconstructor."""

    def test_extract_jpeg_image_object(self):
        mr = MediaReconstructor()
        # Fake object representing JPEG image XObject
        fake_jpeg = b"\xff\xd8\xff\xe0" + b"\x00" * 64 + b"\xff\xd9"
        raw_obj = (
            b"5 0 obj\n"
            b"<< /Type /XObject /Subtype /Image /Width 640 /Height 480 "
            b"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode "
            + f"/Length {len(fake_jpeg)} >>\n".encode("ascii")
            + b"stream\r\n" + fake_jpeg + b"\r\nendstream\nendobj"
        )

        img = mr.extract_image_from_object(raw_obj, source_offset=1024, obj_num=5)
        assert img is not None
        assert img.width == 640
        assert img.height == 480
        assert img.format == ImageFormat.JPEG
        assert img.color_space == "DeviceRGB"
        assert img.is_corrupted is False
        assert img.provenance == ProvenanceCategory.AUTHENTIC

    def test_detect_corrupted_image(self):
        mr = MediaReconstructor()
        # Truncated invalid stream
        raw_obj = (
            b"6 0 obj\n"
            b"<< /Type /XObject /Subtype /Image /Width 100 /Height 100 /Filter /DCTDecode >>\n"
            b"stream\nnot_a_real_jpeg\nendstream\nendobj"
        )
        img = mr.extract_image_from_object(raw_obj, obj_num=6)
        assert img is not None
        assert img.is_corrupted is True
        assert img.confidence < 1.0

    def test_associate_figure_captions(self):
        mr = MediaReconstructor()
        images = [
            ImageElement(
                image_id="img_1",
                page_number=1,
                format=ImageFormat.JPEG,
                width=200,
                height=150,
                raw_bytes=b"dummy",
            )
        ]
        text_lines = [
            "Introduction section paragraph text.",
            "Fig. 1: System architecture of multimodal reconstruction pipeline.",
            "Results section paragraph text.",
        ]
        linked = mr.associate_figure_captions(images, text_lines)
        assert linked[0].caption is not None
        assert "System architecture" in linked[0].caption


class TestTableReconstructor:
    """Tests for TableReconstructor."""

    def test_detect_table_pipe_delimited(self):
        tr = TableReconstructor()
        lines = [
            "Table 1: Benchmark Reconstruction Accuracy",
            "| Model | Precision | Recall | F1 Score |",
            "| TRACE P7 | 0.98 | 0.96 | 0.97 |",
            "| Baseline | 0.81 | 0.75 | 0.78 |",
        ]
        table = tr.detect_table_from_text_lines(lines, page_number=1)
        assert table is not None
        assert table.cols_count == 4
        assert table.rows_count == 3
        assert "Benchmark" in table.caption
        assert table.rows[0].is_header is True
        assert table.rows[0].cells[0].text == "Model"
        assert table.rows[1].cells[0].text == "TRACE P7"
        assert table.unrecoverable_cells_count == 0

    def test_detect_table_multi_space_with_missing_cells(self):
        tr = TableReconstructor()
        lines = [
            "Metric      Baseline    Proposed",
            "Accuracy    88.2%       97.5%",
            "Latency                 12ms",  # Missing cell
        ]
        table = tr.detect_table_from_text_lines(lines, page_number=1)
        assert table is not None
        assert table.cols_count >= 2
        assert table.rows_count == 3
        # Third row has an empty cell
        empty_cells = [c for r in table.rows for c in r.cells if c.is_empty]
        assert len(empty_cells) >= 1
        assert empty_cells[0].confidence < 1.0


class TestEquationReconstructor:
    """Tests for EquationReconstructor."""

    def test_is_likely_equation(self):
        er = EquationReconstructor()
        assert er.is_likely_equation(r"E = mc^2  (1)") is True
        assert er.is_likely_equation(r"\sum_{i=1}^{N} x_i = y") is True
        assert er.is_likely_equation(r"∫ f(x) dx = F(x) + C") is True
        assert er.is_likely_equation("This is just regular English text.") is False

    def test_parse_numbered_equation(self):
        er = EquationReconstructor()
        raw = "E = mc^2  (1)"
        eq = er.parse_equation(raw, page_number=1, eq_idx=1)
        assert eq.equation_id == "eq_1_p1"
        assert eq.equation_type == EquationType.NUMBERED
        assert eq.equation_number == "1"
        assert eq.latex_content == "E = mc^2"
        assert eq.provenance == ProvenanceCategory.AUTHENTIC

    def test_transcribe_unicode_math_to_latex(self):
        er = EquationReconstructor()
        raw = "∑ x_i ≤ α + β"
        eq = er.parse_equation(raw, page_number=1)
        assert r"\sum" in eq.latex_content
        assert r"\le" in eq.latex_content
        assert r"\alpha" in eq.latex_content
        assert r"\beta" in eq.latex_content


class TestDocumentLayoutEngine:
    """Tests for DocumentLayoutEngine."""

    def test_compute_layout_geometry(self):
        le = DocumentLayoutEngine(default_width=612.0, default_height=792.0)
        # 1 column
        layout1 = le.compute_page_layout(page_number=1, columns_count=1)
        assert len(layout1.column_boundaries) == 1
        assert layout1.column_boundaries[0] == (54.0, 612.0 - 54.0)

        # 2 columns
        layout2 = le.compute_page_layout(page_number=1, columns_count=2)
        assert len(layout2.column_boundaries) == 2
        assert layout2.column_boundaries[0][0] == 54.0
        assert layout2.column_boundaries[1][1] == 612.0 - 54.0

    def test_assemble_document_pages(self):
        le = DocumentLayoutEngine()
        el1 = DocumentElement(
            element_id="el_1",
            type=ElementType.HEADER,
            page_number=1,
            content="Page 1 Title",
            bbox=BoundingBox(x1=54, y1=60, x2=558, y2=80),
        )
        el2 = DocumentElement(
            element_id="el_2",
            type=ElementType.TEXT_BLOCK,
            page_number=2,
            content="Page 2 Body",
            bbox=BoundingBox(x1=54, y1=100, x2=558, y2=120),
        )
        norm_doc = le.assemble_document_pages(
            document_id="DOC-TEST",
            title="Multi-Page Paper",
            elements_by_page={1: [el1], 2: [el2]},
        )
        assert norm_doc.page_count == 2
        assert norm_doc.get_page(1) is not None
        assert norm_doc.get_page(2) is not None
        assert len(norm_doc.get_page(1).elements) == 1
        assert len(norm_doc.get_page(2).elements) == 1


class TestMultimodalPdfBuilder:
    """Tests for MultimodalPdfBuilder."""

    def test_build_valid_pdf_with_elements(self):
        builder = MultimodalPdfBuilder(include_provenance_badges=True)
        # Create a NormalizedDocument with text, table, and equation
        p = DocumentPage(page_number=1, width=612, height=792)
        p.add_element(
            DocumentElement(
                element_id="hdr_1",
                type=ElementType.HEADER,
                page_number=1,
                content="Title: Advanced Evidence Reconstruction",
                bbox=BoundingBox(x1=54, y1=60, x2=558, y2=90),
            )
        )
        p.add_element(
            DocumentElement(
                element_id="tbl_1",
                type=ElementType.TABLE,
                page_number=1,
                content={
                    "caption": "Table 1: Test Results",
                    "rows": [["Method", "Score"], ["TRACE", "99.2%"]],
                },
                bbox=BoundingBox(x1=54, y1=110, x2=558, y2=160),
            )
        )
        p.add_element(
            DocumentElement(
                element_id="eq_1",
                type=ElementType.EQUATION,
                page_number=1,
                content={"latex": "f(x) = x^2 + 1", "number": "1"},
                bbox=BoundingBox(x1=54, y1=180, x2=558, y2=210),
            )
        )
        doc = NormalizedDocument(
            document_id="TEST-RECON-DOC",
            title="Test Paper",
            pages=[p],
            summary_telemetry={"authentic_recovery_percentage": 98.5},
        )

        pdf_bytes = builder.build_pdf(doc)
        assert len(pdf_bytes) > 200
        assert pdf_bytes.startswith(b"%PDF-")

        # Validate with pypdf
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(pdf_bytes))
        assert len(reader.pages) == 1
        text = reader.pages[0].extract_text()
        assert "Advanced Evidence Reconstruction" in text or "TRACE" in text


class TestArtifactManager:
    """Tests for ReconstructionArtifactManager."""

    def test_export_and_verify_all_five_artifacts(self):
        mgr = ReconstructionArtifactManager()
        report = MultimodalReconstructionReport(
            case_id="CASE-123",
            document_title="Sample Report",
            input_evidence_size=1000,
            authentic_bytes_recovered=950,
            authentic_recovery_percentage=95.0,
            total_pages_reconstructed=1,
            text_blocks_count=5,
            tables_count=1,
            figures_count=0,
            equations_count=1,
            unrecoverable_regions_count=0,
            provenance=ProvenanceBreakdown(authentic_count=6, deterministic_count=1, total_elements=7),
        )
        artifacts = ReconstructionArtifacts(
            original_evidence=b"original_corrupted_data_stream_12345",
            authentic_recovered_bytes=b"authentic_carved_bytes_verbatim",
            repaired_pdf=b"%PDF-1.4\nrepaired_pdf_bytes\n%%EOF",
            multimodal_reconstructed_pdf=b"%PDF-1.4\nmultimodal_pdf_bytes\n%%EOF",
            report=report,
        )

        with tempfile.TemporaryDirectory() as tmp_dir:
            paths = mgr.export_artifacts(artifacts, output_dir=tmp_dir, base_name="test_ev")
            assert len(paths) == 5
            assert "original_evidence" in paths
            assert "authentic_recovered_bytes" in paths
            assert "repaired_pdf" in paths
            assert "multimodal_reconstructed_pdf" in paths
            assert "report" in paths

            # Verify files exist on disk and have nonzero size
            for k, p_str in paths.items():
                p = Path(p_str)
                assert p.exists()
                assert p.stat().st_size > 0

            # Read exported JSON report
            rep_path = Path(paths["report"])
            with open(rep_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            assert data["case_id"] == "CASE-123"
            assert data["artifacts"]["original_evidence"]["bytes"] == len(artifacts.original_evidence)
            assert "sha256" in data["artifacts"]["authentic_recovered_bytes"]


class TestEndToEndMultimodalReconstructionEngine:
    """End-to-end tests for AdvancedMultimodalReconstructionEngine."""

    def _create_synthetic_damaged_evidence(self) -> bytes:
        """Create a synthetic damaged PDF containing text streams, equations, and tables."""
        # Clean basic PDF structure
        obj1 = b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        obj2 = b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        content_data = (
            b"BT /F1 14 Tf 54 720 Td (Forensic Multimodal Reconstruction Paper) Tj ET\n"
            b"BT /F1 10 Tf 54 680 Td (E = mc^2  (1)) Tj ET\n"
            b"BT /F1 10 Tf 54 650 Td (Table 1: Experimental Accuracy) Tj ET\n"
            b"BT /F1 10 Tf 54 630 Td (| Method | Accuracy |) Tj ET\n"
            b"BT /F1 10 Tf 54 610 Td (| TRACE  | 98.4%    |) Tj ET\n"
        )
        obj4 = f"4 0 obj\n<< /Length {len(content_data)} >>\nstream\n".encode("ascii") + content_data + b"\nendstream\nendobj\n"
        obj3 = b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n"

        # Corrupt header and trailer
        damaged_header = b"%PDF-1.4\nCORRUPTED_NOISE_HEADER\n"
        body = obj1 + obj2 + obj3 + obj4
        # Add damaged trailer / missing xref
        damaged_tail = b"\nTRAILER_DAMAGED_CORRUPTED_SECTOR\x00\x00\x00\x00"
        return damaged_header + body + damaged_tail

    def test_reconstruct_recovers_authentic_elements_and_builds_pdf(self):
        engine = AdvancedMultimodalReconstructionEngine()
        evidence = self._create_synthetic_damaged_evidence()

        with tempfile.TemporaryDirectory() as tmp_dir:
            result = engine.reconstruct(
                evidence_bytes=evidence,
                case_id="CASE-FORENSIC-001",
                document_title="Forensic Multimodal Reconstruction Paper",
                output_dir=tmp_dir,
            )

            assert isinstance(result, ReconstructionResult)
            # Reconstructed PDF is generated and openable
            assert len(result.reconstructed_pdf_bytes) > 200
            assert result.reconstructed_pdf_bytes.startswith(b"%PDF-")

            # Report telemetry is populated
            report = result.report
            assert report.case_id == "CASE-FORENSIC-001"
            assert report.input_evidence_size == len(evidence)
            assert report.authentic_bytes_recovered > 0
            assert report.authentic_recovery_percentage > 0.0

            # Elements were extracted
            assert report.text_blocks_count + report.equations_count >= 1

            # Provenance integrity verified (no mixed categories)
            assert report.integrity_verified is True
            assert len(report.integrity_issues) == 0

            # 5 separate artifacts were exported
            assert len(result.artifact_paths) == 5
            for art_name, p_str in result.artifact_paths.items():
                p = Path(p_str)
                assert p.exists()
                assert p.stat().st_size > 0

    def test_zero_gemini_dependency_local_only(self):
        """Verify engine executes entirely locally without contacting external AI APIs."""
        engine = AdvancedMultimodalReconstructionEngine()
        evidence = self._create_synthetic_damaged_evidence()

        result = engine.reconstruct(evidence_bytes=evidence)
        # Provenance must have ZERO AI_INFERRED items when running locally
        assert result.report.provenance.ai_inferred_count == 0
        assert result.report.provenance.ai_inferred_percentage == 0.0


class TestMultimodalApiEndpoints:
    """Tests for dashboard API endpoints exposing multimodal reconstruction."""

    def test_multimodal_reconstruction_lifecycle(self, monkeypatch, tmp_path):
        from fastapi.testclient import TestClient
        from app.main import create_app

        monkeypatch.setenv("TRACE_SESSION_ROOT", str(tmp_path))
        monkeypatch.setenv("TRACE_PERSIST_SESSIONS", "true")
        session_id = "f0e1d2c3b4a5678912345678abcdef99"

        # Evidence bytes (minimal PDF with text)
        obj1 = b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        obj2 = b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        content = b"BT /F1 12 Tf 54 700 Td (Multimodal Endpoint Test) Tj ET\n"
        obj4 = f"4 0 obj\n<< /Length {len(content)} >>\nstream\n".encode("ascii") + content + b"\nendstream\nendobj\n"
        obj3 = b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n"
        raw_evidence = b"%PDF-1.4\n" + obj1 + obj2 + obj3 + obj4 + b"%%EOF\n"

        # Save session file and media
        raw_file = tmp_path / f"{session_id}.pdf"
        raw_file.write_bytes(raw_evidence)
        session_json = tmp_path / f"{session_id}.json"
        session_json.write_text(
            f'{{"session_id": "{session_id}", "status": "complete", "submitted_at": "2026-10-01T12:00:00+00:00", '
            f'"evidence_bytes": {len(raw_evidence)}, "case_id": "MM-001", "mock_data": false, "records": []}}',
            encoding="utf-8",
        )

        app = create_app()
        client = TestClient(app)

        # 1. Before execution, GET status returns not_generated
        res_pre = client.get(f"/api/sessions/{session_id}/multimodal-reconstruction")
        assert res_pre.status_code == 200
        assert res_pre.json()["has_multimodal_file"] is False

        # 2. Trigger POST reconstruction
        res_post = client.post(f"/api/sessions/{session_id}/multimodal-reconstruction")
        assert res_post.status_code == 200
        data = res_post.json()
        assert data["status"] == "completed"
        assert data["pdf_size_bytes"] > 0
        assert "report" in data

        # 3. GET status now returns true
        res_status = client.get(f"/api/sessions/{session_id}/multimodal-reconstruction")
        assert res_status.status_code == 200
        assert res_status.json()["has_multimodal_file"] is True

        # 4. Download artifact
        res_dl = client.get(f"/api/sessions/{session_id}/multimodal-reconstruction/download")
        assert res_dl.status_code == 200
        assert res_dl.headers["Content-Type"] == "application/pdf"
        assert "MULTIMODAL RECONSTRUCTED" in res_dl.headers["X-TRACE-Repair-Status"]

        # 5. View artifact inline
        res_view = client.get(f"/api/sessions/{session_id}/multimodal-reconstruction/view")
        assert res_view.status_code == 200
        assert "inline;" in res_view.headers["Content-Disposition"]

