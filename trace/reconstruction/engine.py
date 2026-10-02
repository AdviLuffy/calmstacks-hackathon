"""Advanced Multimodal Document Reconstruction Engine for TRACE Phase 9.

Orchestrates full multimodal reconstruction of damaged research papers and PDFs:
- Phase 1 deterministic recovery engine (byte harvesting, syntax repair)
- Phase 7 ML fragment classification (CPU-friendly balanced ensemble)
- Phase 8 fragment relationship graph & scoring
- Text & typography parsing (fonts, multi-column flows, reading order)
- Media & image recovery (XObject images, dimensions, captions, corruption flags)
- Table detection and grid reconstruction (rows, columns, headers, empty cells)
- Mathematical formula detection and LaTeX formatting (inline, display, numbered)
- Document layout geometry (margins, columns, header/footer zones)
- High-fidelity PDF document generation
- Separate forensic artifact packaging and provenance audit
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from trace_evidence.pdf_recovery import (
    CorruptionDiagnostic,
    GeneralizedPdfRecoveryEngine,
    RecoveredObject,
    diagnose_pdf_corruption,
)
from trace.ml.inference.fragment_predictor import FragmentPredictor
from trace.ml.relationships.features import FragmentInput
from trace.ml.relationships.graph import ReconstructionGraph
from trace.ml.relationships.scorer import ForensicRelationshipScorer
from trace.multimodal.representation import (
    BoundingBox,
    DocumentElement,
    DocumentPage,
    ElementType,
    NormalizedDocument,
    ProvenanceCategory,
)
from trace.reconstruction.artifacts import ReconstructionArtifactManager
from trace.reconstruction.equation_reconstructor import EquationReconstructor
from trace.reconstruction.layout_engine import DocumentLayoutEngine
from trace.reconstruction.media_reconstructor import MediaReconstructor
from trace.reconstruction.models import (
    EquationElement,
    ImageElement,
    MultimodalReconstructionReport,
    PageLayoutData,
    ProvenanceBreakdown,
    ReconstructionArtifacts,
    TableStructure,
    TextBlockData,
)
from trace.reconstruction.pdf_builder import MultimodalPdfBuilder
from trace.reconstruction.table_reconstructor import TableReconstructor
from trace.reconstruction.text_reconstructor import TextReconstructor

logger = logging.getLogger(__name__)


@dataclass
class ReconstructionResult:
    """Result returned by AdvancedMultimodalReconstructionEngine."""
    normalized_document: NormalizedDocument
    artifacts: ReconstructionArtifacts
    report: MultimodalReconstructionReport
    reconstructed_pdf_bytes: bytes
    repaired_pdf_bytes: bytes
    authentic_recovered_bytes: bytes
    artifact_paths: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "document_id": self.normalized_document.document_id,
            "title": self.normalized_document.title,
            "page_count": self.normalized_document.page_count,
            "total_elements": self.normalized_document.total_elements,
            "report": self.report.to_dict(),
            "artifact_paths": self.artifact_paths,
        }


class AdvancedMultimodalReconstructionEngine:
    """End-to-end multimodal document reconstruction engine with forensic provenance."""

    def __init__(
        self,
        predictor: Optional[FragmentPredictor] = None,
        relationship_scorer: Optional[ForensicRelationshipScorer] = None,
        include_provenance_badges: bool = True,
    ) -> None:
        self.predictor = predictor or FragmentPredictor()
        self.relationship_scorer = relationship_scorer or ForensicRelationshipScorer()
        self.text_reconstructor = TextReconstructor()
        self.media_reconstructor = MediaReconstructor()
        self.table_reconstructor = TableReconstructor()
        self.equation_reconstructor = EquationReconstructor()
        self.layout_engine = DocumentLayoutEngine()
        self.pdf_builder = MultimodalPdfBuilder(include_provenance_badges=include_provenance_badges)
        self.artifact_manager = ReconstructionArtifactManager()

    def reconstruct(
        self,
        evidence_bytes: bytes,
        case_id: str = "CASE-TRACE-RECON",
        document_title: str = "Reconstructed Forensic Document",
        output_dir: Optional[Union[str, Path]] = None,
        base_name: str = "evidence",
    ) -> ReconstructionResult:
        """Execute full multimodal reconstruction on raw corrupted evidence bytes."""
        if not evidence_bytes:
            raise ValueError("evidence_bytes cannot be empty")

        recovery_engine = GeneralizedPdfRecoveryEngine(raw_bytes=evidence_bytes)
        rebuilt_pdf, synth_items, recovery_meta = recovery_engine.recover()
        diagnostic = recovery_engine.diagnostic

        recovered_objs: List[RecoveredObject] = getattr(recovery_engine, "recovered_objects", [])
        authentic_carved_bytes: bytes = recovery_meta.get("authentic_recovered_bytes") or getattr(
            recovery_engine, "authentic_carved_bytes", b""
        )
        surviving_texts: List[str] = list(recovery_meta.get("surviving_text", []))
        telemetry = recovery_meta.get("telemetry", {})

        from trace.ml.relationships.graph import GraphNode

        recon_graph = ReconstructionGraph(name=f"graph_{case_id}")
        for obj in recovered_objs:
            pred = self.predictor.predict_fragment(obj.raw_bytes[:512])
            recon_graph.add_node(
                GraphNode(
                    fragment_id=f"obj_{obj.object_number}",
                    length=len(obj.raw_bytes),
                    offset=obj.source_offset_start,
                    source_id=case_id,
                    predicted_label=pred.predicted_label,
                    label_confidence=pred.confidence,
                    provenance="CARVED_FRAGMENT",
                    metadata={"object_number": obj.object_number, "object_type": obj.object_type},
                )
            )

        # ------------------------------------------------------------------
        # Stage 3: Multimodal Element Extraction
        # ------------------------------------------------------------------
        elements_by_page: Dict[int, List[DocumentElement]] = {}
        all_images: List[ImageElement] = []
        all_tables: List[TableStructure] = []
        all_equations: List[EquationElement] = []
        all_text_blocks: List[TextBlockData] = []

        # Determine page count
        discovered_pages_count = max(1, telemetry.get("pages_discovered", 1))

        # 3A. Images & Figures
        for obj in recovered_objs:
            img = self.media_reconstructor.extract_image_from_object(
                raw_obj_bytes=obj.raw_bytes,
                decompressed_stream=obj.decompressed_stream,
                page_number=1,
                source_offset=obj.source_offset_start,
                obj_num=obj.object_number,
            )
            if img:
                all_images.append(img)

        # Associate captions
        if all_images and surviving_texts:
            all_images = self.media_reconstructor.associate_figure_captions(all_images, surviving_texts)

        # 3B. Text Streams
        content_stream_count = 0
        for obj in recovered_objs:
            stm = obj.decompressed_stream or (obj.raw_bytes if b"BT" in obj.raw_bytes else None)
            if stm:
                content_stream_count += 1
                page_target = min(content_stream_count, discovered_pages_count)
                blocks = self.text_reconstructor.extract_text_from_stream(
                    stream_bytes=stm,
                    page_number=page_target,
                    stream_offset=obj.source_offset_start,
                )
                all_text_blocks.extend(blocks)

        # Fallback if no text blocks from content streams, use surviving texts
        if not all_text_blocks and surviving_texts:
            page_target = 1
            for idx, txt in enumerate(surviving_texts):
                if len(txt.strip()) < 2:
                    continue
                tb = TextBlockData(
                    block_id=f"p1_surviving_{idx}",
                    page_number=1,
                    text=txt.strip(),
                    font_family="Helvetica",
                    font_size=10.0,
                    bbox=BoundingBox(x1=54.0, y1=80.0 + (idx * 24.0), x2=558.0, y2=100.0 + (idx * 24.0)),
                    column_index=0,
                    reading_order_index=idx,
                    confidence=1.0,
                    provenance=ProvenanceCategory.AUTHENTIC,
                )
                all_text_blocks.append(tb)

        # 3C. Equations & Formulas
        # Check text lines for equations
        non_equation_blocks: List[TextBlockData] = []
        eq_counter = 1
        for tb in all_text_blocks:
            if self.equation_reconstructor.is_likely_equation(tb.text):
                eq_el = self.equation_reconstructor.parse_equation(
                    text=tb.text,
                    page_number=tb.page_number,
                    source_offset=tb.source_offsets[0][0] if tb.source_offsets else 0,
                    eq_idx=eq_counter,
                )
                eq_counter += 1
                all_equations.append(eq_el)
            else:
                non_equation_blocks.append(tb)
        all_text_blocks = non_equation_blocks

        # 3D. Tables
        # Check surviving text lines for tables
        if surviving_texts:
            detected_table = self.table_reconstructor.detect_table_from_text_lines(
                text_lines=surviving_texts,
                page_number=1,
                source_offset=0,
                table_idx=1,
            )
            if detected_table:
                all_tables.append(detected_table)

        # ------------------------------------------------------------------
        # Stage 4: Layout & Multi-Page Assembly
        # ------------------------------------------------------------------
        # Convert all to DocumentElement and group by page
        for tb in all_text_blocks:
            el = self.text_reconstructor.to_document_element(tb)
            elements_by_page.setdefault(tb.page_number, []).append(el)

        for img in all_images:
            el = self.media_reconstructor.to_document_element(img)
            elements_by_page.setdefault(img.page_number, []).append(el)

        for tbl in all_tables:
            el = self.table_reconstructor.to_document_element(tbl)
            elements_by_page.setdefault(tbl.page_number, []).append(el)

        for eq in all_equations:
            el = self.equation_reconstructor.to_document_element(eq)
            elements_by_page.setdefault(eq.page_number, []).append(el)

        norm_doc = self.layout_engine.assemble_document_pages(
            document_id=case_id,
            title=document_title,
            elements_by_page=elements_by_page,
            telemetry=telemetry,
        )

        # ------------------------------------------------------------------
        # Stage 5: High-Fidelity Reconstructed PDF Generation
        # ------------------------------------------------------------------
        reconstructed_pdf = self.pdf_builder.build_pdf(norm_doc)

        # ------------------------------------------------------------------
        # Stage 6: Provenance Verification & Audit Telemetry
        # ------------------------------------------------------------------
        prov_audit = norm_doc.verify_provenance_integrity()

        counts = prov_audit.get("counts", {})
        provenance_breakdown = ProvenanceBreakdown(
            authentic_count=counts.get(ProvenanceCategory.AUTHENTIC.value, 0),
            deterministic_count=counts.get(ProvenanceCategory.DETERMINISTIC.value, 0),
            ml_detected_count=counts.get(ProvenanceCategory.ML_DETECTED.value, 0),
            ai_inferred_count=counts.get(ProvenanceCategory.AI_INFERRED.value, 0),
            total_elements=norm_doc.total_elements,
        )

        auth_recovered_bytes_count = len(authentic_carved_bytes)
        auth_pct = (auth_recovered_bytes_count / len(evidence_bytes) * 100.0) if evidence_bytes else 0.0

        report = MultimodalReconstructionReport(
            case_id=case_id,
            document_title=document_title,
            input_evidence_size=len(evidence_bytes),
            authentic_bytes_recovered=auth_recovered_bytes_count,
            authentic_recovery_percentage=auth_pct,
            total_pages_reconstructed=norm_doc.page_count,
            text_blocks_count=len(all_text_blocks),
            tables_count=len(all_tables),
            figures_count=len(all_images),
            equations_count=len(all_equations),
            unrecoverable_regions_count=sum(t.unrecoverable_cells_count for t in all_tables)
            + sum(1 for i in all_images if i.is_corrupted),
            provenance=provenance_breakdown,
            integrity_verified=prov_audit.get("valid", True),
            integrity_issues=prov_audit.get("issues", []),
            telemetry={
                "corruption_diagnostic": diagnostic.to_dict(),
                "recovery_telemetry": telemetry,
                "graph_nodes_count": len(recon_graph.nodes),
            },
        )

        artifacts = ReconstructionArtifacts(
            original_evidence=evidence_bytes,
            authentic_recovered_bytes=authentic_carved_bytes,
            repaired_pdf=rebuilt_pdf,
            multimodal_reconstructed_pdf=reconstructed_pdf,
            report=report,
        )

        artifact_paths: Dict[str, str] = {}
        if output_dir:
            artifact_paths = self.artifact_manager.export_artifacts(
                artifacts=artifacts,
                output_dir=output_dir,
                base_name=base_name,
            )

        return ReconstructionResult(
            normalized_document=norm_doc,
            artifacts=artifacts,
            report=report,
            reconstructed_pdf_bytes=reconstructed_pdf,
            repaired_pdf_bytes=rebuilt_pdf,
            authentic_recovered_bytes=authentic_carved_bytes,
            artifact_paths=artifact_paths,
        )

    def reconstruct_from_file(
        self,
        input_path: Union[str, Path],
        output_dir: Optional[Union[str, Path]] = None,
        case_id: Optional[str] = None,
        document_title: Optional[str] = None,
    ) -> ReconstructionResult:
        """Reconstruct from an evidence file on disk."""
        in_p = Path(input_path)
        if not in_p.exists():
            raise FileNotFoundError(f"Input evidence file not found: {input_path}")

        raw_bytes = in_p.read_bytes()
        cid = case_id or f"CASE-{in_p.stem.upper()}"
        title = document_title or in_p.stem.replace("_", " ").title()
        return self.reconstruct(
            evidence_bytes=raw_bytes,
            case_id=cid,
            document_title=title,
            output_dir=output_dir,
            base_name=in_p.stem,
        )
