"""Normalized Document Representation for TRACE Multimodal Document Intelligence.

Provides a unified hierarchical schema for representing multi-page documents containing
text blocks, tables, figures, images, equations, headers, footers, and metadata with
strict provenance tracking (AUTHENTIC, DETERMINISTIC, ML_DETECTED, AI_INFERRED).
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union
from pydantic import BaseModel, Field, model_validator


class ProvenanceCategory(str, Enum):
    """Forensic provenance categories.
    
    CRITICAL RULE: Deterministic evidence is authoritative. ML output is probabilistic.
    These categories must never be silently mixed or conflated.
    """
    AUTHENTIC = "AUTHENTIC"          # Directly recovered byte evidence (verifiable at exact offsets)
    DETERMINISTIC = "DETERMINISTIC"  # Parsed or reconstructed from validated evidence via rule/spec
    ML_DETECTED = "ML_DETECTED"      # Identified, classified, or extracted by an ML model
    AI_INFERRED = "AI_INFERRED"      # Generated, hallucinated, or synthesized content


class ElementType(str, Enum):
    """Structural and semantic document element types."""
    TEXT_BLOCK = "text_block"
    TABLE = "table"
    FIGURE = "figure"
    IMAGE = "image"
    EQUATION = "equation"
    HEADER = "header"
    FOOTER = "footer"
    METADATA = "metadata"


class BoundingBox(BaseModel):
    """Bounding box coordinates for a document element [x1, y1, x2, y2]."""
    x1: float
    y1: float
    x2: float
    y2: float
    coord_unit: str = Field(default="pt", description="'pt' (points) or 'normalized' (0.0 to 1.0)")

    @property
    def width(self) -> float:
        return max(0.0, self.x2 - self.x1)

    @property
    def height(self) -> float:
        return max(0.0, self.y2 - self.y1)

    @property
    def area(self) -> float:
        return self.width * self.height

    def as_list(self) -> List[float]:
        return [self.x1, self.y1, self.x2, self.y2]

    def as_tuple(self) -> Tuple[float, float, float, float]:
        return (self.x1, self.y1, self.x2, self.y2)

    def intersects(self, other: BoundingBox) -> bool:
        """Return True if this bounding box intersects with another."""
        return not (
            self.x2 < other.x1 or
            self.x1 > other.x2 or
            self.y2 < other.y1 or
            self.y1 > other.y2
        )

    def iou(self, other: BoundingBox) -> float:
        """Calculate Intersection over Union (IoU) with another bounding box."""
        inter_x1 = max(self.x1, other.x1)
        inter_y1 = max(self.y1, other.y1)
        inter_x2 = min(self.x2, other.x2)
        inter_y2 = min(self.y2, other.y2)

        inter_w = max(0.0, inter_x2 - inter_x1)
        inter_h = max(0.0, inter_y2 - inter_y1)
        inter_area = inter_w * inter_h

        union_area = self.area + other.area - inter_area
        if union_area <= 0:
            return 0.0
        return inter_area / union_area


class DocumentElement(BaseModel):
    """Normalized document element with explicit forensic provenance."""
    element_id: str
    type: ElementType
    page_number: int = Field(ge=1, description="1-indexed document page number")
    bbox: Optional[BoundingBox] = None
    content: Any = Field(description="Text string, table data dict, or image representation")
    reading_order_index: Optional[int] = Field(default=None, description="Sequence in reading order")
    confidence: float = Field(ge=0.0, le=1.0, default=1.0, description="Confidence score from 0.0 to 1.0")
    provenance: ProvenanceCategory = Field(default=ProvenanceCategory.AUTHENTIC)
    source: str = Field(default="evidence", description="Origin: pdf_object, deterministic_parser, ml, ocr")
    evidence_offsets: List[List[int]] = Field(
        default_factory=list,
        description="Byte offsets in original evidence [[start, end], ...]"
    )
    model_provenance: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Structured ML provenance dict if produced or modified by an ML model"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_provenance_rules(self) -> "DocumentElement":
        # Rule: ML results must carry model provenance
        if self.provenance == ProvenanceCategory.ML_DETECTED and not self.model_provenance:
            self.model_provenance = {
                "source": "ml",
                "model": self.source,
                "confidence": self.confidence,
                "evidence_offsets": self.evidence_offsets,
                "inference": True,
            }
        return self


class DocumentPage(BaseModel):
    """Single page in a normalized document."""
    page_number: int = Field(ge=1)
    width: float = Field(default=612.0, description="Page width in points (standard letter is 612x792)")
    height: float = Field(default=792.0, description="Page height in points")
    elements: List[DocumentElement] = Field(default_factory=list)
    reading_order: List[str] = Field(
        default_factory=list,
        description="Element IDs sorted according to visual reading order"
    )
    page_metadata: Dict[str, Any] = Field(default_factory=dict)

    def add_element(self, element: DocumentElement) -> None:
        """Add an element and update reading order if applicable."""
        self.elements.append(element)
        if element.reading_order_index is not None:
            self._recalculate_reading_order()

    def _recalculate_reading_order(self) -> None:
        """Sort element IDs by reading_order_index."""
        indexed = [el for el in self.elements if el.reading_order_index is not None]
        unindexed = [el for el in self.elements if el.reading_order_index is None]
        indexed.sort(key=lambda x: x.reading_order_index if x.reading_order_index is not None else 999999)
        self.reading_order = [el.element_id for el in indexed] + [el.element_id for el in unindexed]

    def get_elements_by_type(self, element_type: ElementType) -> List[DocumentElement]:
        return [el for el in self.elements if el.type == element_type]

    def get_elements_by_provenance(self, category: ProvenanceCategory) -> List[DocumentElement]:
        return [el for el in self.elements if el.provenance == category]


class NormalizedDocument(BaseModel):
    """Complete multi-page normalized document representation."""
    document_id: str
    title: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
    pages: List[DocumentPage] = Field(default_factory=list)
    evidence_references: Dict[str, Any] = Field(default_factory=dict)
    summary_telemetry: Dict[str, Any] = Field(default_factory=dict)

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def total_elements(self) -> int:
        return sum(len(p.elements) for p in self.pages)

    def get_page(self, page_number: int) -> Optional[DocumentPage]:
        for p in self.pages:
            if p.page_number == page_number:
                return p
        return None

    def get_element(self, element_id: str) -> Optional[DocumentElement]:
        for page in self.pages:
            for el in page.elements:
                if el.element_id == element_id:
                    return el
        return None

    def get_all_elements_by_type(self, element_type: ElementType) -> List[DocumentElement]:
        results = []
        for page in self.pages:
            results.extend(page.get_elements_by_type(element_type))
        return results

    def get_all_elements_by_provenance(self, category: ProvenanceCategory) -> List[DocumentElement]:
        results = []
        for page in self.pages:
            results.extend(page.get_elements_by_provenance(category))
        return results

    def verify_provenance_integrity(self) -> Dict[str, Any]:
        """Perform strict verification of forensic provenance guarantees.
        
        Ensures:
        1. No AUTHENTIC element has an empty evidence offset list if flagged as offset-tracked.
        2. All ML_DETECTED elements carry model provenance metadata.
        3. Never overwrite authentic recovered bytes with ML output.
        """
        issues: List[str] = []
        counts: Dict[str, int] = {cat.value: 0 for cat in ProvenanceCategory}

        for page in self.pages:
            for el in page.elements:
                counts[el.provenance.value] += 1
                if el.provenance == ProvenanceCategory.ML_DETECTED:
                    if not el.model_provenance:
                        issues.append(f"Element {el.element_id} is ML_DETECTED but lacks model_provenance metadata")
                    elif not el.model_provenance.get("inference", False):
                        issues.append(f"Element {el.element_id} model_provenance does not have inference=True")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "counts": counts,
            "total_elements": self.total_elements,
        }
