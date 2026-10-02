"""Data models for TRACE Phase 9: Advanced Multimodal Document Reconstruction.

Extends the Normalized Document schema with rich structures for:
- Tabular data (rows, columns, headers, cells, grid lines)
- Mathematical equations (inline, display, numbered, LaTeX transcription)
- Image and figure media (XObject images, dimensions, captions, corruption flags)
- Text blocks and typography (fonts, sizes, headings, multi-column flows)
- Page geometry and layout zones (margins, columns, headers, footers)
- Forensic provenance audit telemetry and separate artifact packaging
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from trace.multimodal.representation import (
    BoundingBox,
    DocumentElement,
    DocumentPage,
    ElementType,
    NormalizedDocument,
    ProvenanceCategory,
)


class EquationType(str, Enum):
    """Classification of mathematical equations."""
    INLINE = "inline"
    DISPLAY = "display"
    NUMBERED = "numbered"


class ImageFormat(str, Enum):
    """Image data encoding format."""
    JPEG = "jpeg"
    PNG = "png"
    RAW_PIXELS = "raw_pixels"
    UNKNOWN = "unknown"


@dataclass
class TableCell:
    """A single cell in a reconstructed table."""
    row_idx: int
    col_idx: int
    text: str = ""
    bbox: Optional[BoundingBox] = None
    is_header: bool = False
    is_empty: bool = False
    row_span: int = 1
    col_span: int = 1
    confidence: float = 1.0
    provenance: ProvenanceCategory = ProvenanceCategory.AUTHENTIC

    def to_dict(self) -> Dict[str, Any]:
        return {
            "row_idx": self.row_idx,
            "col_idx": self.col_idx,
            "text": self.text,
            "bbox": self.bbox.as_list() if self.bbox else None,
            "is_header": self.is_header,
            "is_empty": self.is_empty,
            "row_span": self.row_span,
            "col_span": self.col_span,
            "confidence": round(self.confidence, 3),
            "provenance": self.provenance.value,
        }


@dataclass
class TableRow:
    """A row in a reconstructed table."""
    row_idx: int
    cells: List[TableCell] = field(default_factory=list)
    is_header: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "row_idx": self.row_idx,
            "is_header": self.is_header,
            "cells": [c.to_dict() for c in self.cells],
        }


@dataclass
class TableStructure:
    """A reconstructed table with full grid topology and forensic provenance."""
    table_id: str
    page_number: int
    rows: List[TableRow] = field(default_factory=list)
    cols_count: int = 0
    rows_count: int = 0
    bbox: Optional[BoundingBox] = None
    caption: Optional[str] = None
    confidence: float = 1.0
    provenance: ProvenanceCategory = ProvenanceCategory.DETERMINISTIC
    unrecoverable_cells_count: int = 0
    source_offsets: List[List[int]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "table_id": self.table_id,
            "page_number": self.page_number,
            "cols_count": self.cols_count,
            "rows_count": self.rows_count,
            "bbox": self.bbox.as_list() if self.bbox else None,
            "caption": self.caption,
            "confidence": round(self.confidence, 3),
            "provenance": self.provenance.value,
            "unrecoverable_cells_count": self.unrecoverable_cells_count,
            "source_offsets": self.source_offsets,
            "rows": [r.to_dict() for r in self.rows],
        }


@dataclass
class EquationElement:
    """A reconstructed mathematical formula."""
    equation_id: str
    page_number: int
    latex_content: str
    raw_tokens: List[str] = field(default_factory=list)
    equation_type: EquationType = EquationType.DISPLAY
    equation_number: Optional[str] = None
    bbox: Optional[BoundingBox] = None
    confidence: float = 1.0
    provenance: ProvenanceCategory = ProvenanceCategory.AUTHENTIC
    source_offsets: List[List[int]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "equation_id": self.equation_id,
            "page_number": self.page_number,
            "latex_content": self.latex_content,
            "raw_tokens": self.raw_tokens,
            "equation_type": self.equation_type.value,
            "equation_number": self.equation_number,
            "bbox": self.bbox.as_list() if self.bbox else None,
            "confidence": round(self.confidence, 3),
            "provenance": self.provenance.value,
            "source_offsets": self.source_offsets,
        }


@dataclass
class ImageElement:
    """A reconstructed figure or embedded image."""
    image_id: str
    page_number: int
    format: ImageFormat
    width: int
    height: int
    raw_bytes: bytes
    bbox: Optional[BoundingBox] = None
    caption: Optional[str] = None
    is_corrupted: bool = False
    color_space: str = "DeviceRGB"
    bits_per_component: int = 8
    confidence: float = 1.0
    provenance: ProvenanceCategory = ProvenanceCategory.AUTHENTIC
    source_offsets: List[List[int]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "image_id": self.image_id,
            "page_number": self.page_number,
            "format": self.format.value,
            "width": self.width,
            "height": self.height,
            "byte_size": len(self.raw_bytes),
            "bbox": self.bbox.as_list() if self.bbox else None,
            "caption": self.caption,
            "is_corrupted": self.is_corrupted,
            "color_space": self.color_space,
            "bits_per_component": self.bits_per_component,
            "confidence": round(self.confidence, 3),
            "provenance": self.provenance.value,
            "source_offsets": self.source_offsets,
        }


@dataclass
class TextBlockData:
    """A reconstructed text block or paragraph."""
    block_id: str
    page_number: int
    text: str
    font_family: str = "Helvetica"
    font_size: float = 10.0
    font_weight: str = "normal"  # normal, bold, italic
    bbox: Optional[BoundingBox] = None
    column_index: int = 0  # 0: single or left, 1: right column
    reading_order_index: int = 0
    is_heading: bool = False
    heading_level: int = 0  # 1: Title, 2: Section, 3: Subsection
    confidence: float = 1.0
    provenance: ProvenanceCategory = ProvenanceCategory.AUTHENTIC
    source_offsets: List[List[int]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "block_id": self.block_id,
            "page_number": self.page_number,
            "text": self.text,
            "font_family": self.font_family,
            "font_size": self.font_size,
            "font_weight": self.font_weight,
            "bbox": self.bbox.as_list() if self.bbox else None,
            "column_index": self.column_index,
            "reading_order_index": self.reading_order_index,
            "is_heading": self.is_heading,
            "heading_level": self.heading_level,
            "confidence": round(self.confidence, 3),
            "provenance": self.provenance.value,
            "source_offsets": self.source_offsets,
        }


@dataclass
class PageLayoutData:
    """Layout geometry and columns for a page."""
    page_number: int
    width: float = 612.0
    height: float = 792.0
    columns_count: int = 1
    column_boundaries: List[Tuple[float, float]] = field(default_factory=list)
    margin_top: float = 54.0
    margin_bottom: float = 54.0
    margin_left: float = 54.0
    margin_right: float = 54.0
    header_box: Optional[BoundingBox] = None
    footer_box: Optional[BoundingBox] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "page_number": self.page_number,
            "width": self.width,
            "height": self.height,
            "columns_count": self.columns_count,
            "column_boundaries": self.column_boundaries,
            "margins": {
                "top": self.margin_top,
                "bottom": self.margin_bottom,
                "left": self.margin_left,
                "right": self.margin_right,
            },
            "header_box": self.header_box.as_list() if self.header_box else None,
            "footer_box": self.footer_box.as_list() if self.footer_box else None,
        }


@dataclass
class ProvenanceBreakdown:
    """Audit breakdown of document elements by forensic provenance."""
    authentic_count: int = 0
    deterministic_count: int = 0
    ml_detected_count: int = 0
    ai_inferred_count: int = 0
    total_elements: int = 0

    @property
    def authentic_percentage(self) -> float:
        return (self.authentic_count / self.total_elements * 100.0) if self.total_elements > 0 else 0.0

    @property
    def deterministic_percentage(self) -> float:
        return (self.deterministic_count / self.total_elements * 100.0) if self.total_elements > 0 else 0.0

    @property
    def ml_detected_percentage(self) -> float:
        return (self.ml_detected_count / self.total_elements * 100.0) if self.total_elements > 0 else 0.0

    @property
    def ai_inferred_percentage(self) -> float:
        return (self.ai_inferred_count / self.total_elements * 100.0) if self.total_elements > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "authentic_count": self.authentic_count,
            "authentic_percentage": round(self.authentic_percentage, 2),
            "deterministic_count": self.deterministic_count,
            "deterministic_percentage": round(self.deterministic_percentage, 2),
            "ml_detected_count": self.ml_detected_count,
            "ml_detected_percentage": round(self.ml_detected_percentage, 2),
            "ai_inferred_count": self.ai_inferred_count,
            "ai_inferred_percentage": round(self.ai_inferred_percentage, 2),
            "total_elements": self.total_elements,
        }


@dataclass
class MultimodalReconstructionReport:
    """Forensic report for multimodal document reconstruction."""
    case_id: str
    document_title: str
    input_evidence_size: int
    authentic_bytes_recovered: int
    authentic_recovery_percentage: float
    total_pages_reconstructed: int
    text_blocks_count: int
    tables_count: int
    figures_count: int
    equations_count: int
    unrecoverable_regions_count: int
    provenance: ProvenanceBreakdown = field(default_factory=ProvenanceBreakdown)
    integrity_verified: bool = True
    integrity_issues: List[str] = field(default_factory=list)
    artifacts: Dict[str, str] = field(default_factory=dict)
    telemetry: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "case_id": self.case_id,
            "document_title": self.document_title,
            "input_evidence_size": self.input_evidence_size,
            "authentic_bytes_recovered": self.authentic_bytes_recovered,
            "authentic_recovery_percentage": round(self.authentic_recovery_percentage, 2),
            "total_pages_reconstructed": self.total_pages_reconstructed,
            "element_counts": {
                "text_blocks": self.text_blocks_count,
                "tables": self.tables_count,
                "figures": self.figures_count,
                "equations": self.equations_count,
                "unrecoverable_regions": self.unrecoverable_regions_count,
            },
            "provenance": self.provenance.to_dict(),
            "integrity_verified": self.integrity_verified,
            "integrity_issues": self.integrity_issues,
            "artifacts": self.artifacts,
            "telemetry": self.telemetry,
        }


@dataclass
class ReconstructionArtifacts:
    """In-memory or serialized outputs of the 5 separate forensic artifacts."""
    original_evidence: bytes
    authentic_recovered_bytes: bytes
    repaired_pdf: bytes
    multimodal_reconstructed_pdf: bytes
    report: MultimodalReconstructionReport

    def to_dict(self) -> Dict[str, Any]:
        return {
            "original_evidence_bytes": len(self.original_evidence),
            "authentic_recovered_bytes": len(self.authentic_recovered_bytes),
            "repaired_pdf_bytes": len(self.repaired_pdf),
            "multimodal_reconstructed_pdf_bytes": len(self.multimodal_reconstructed_pdf),
            "report": self.report.to_dict(),
        }
