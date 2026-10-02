"""Deterministic Fallback Implementation for TRACE Document Intelligence.

Provides zero-dependency, CPU-only implementations of layout detection, reading-order
topological sorting, table detection, figure discovery, equation identification, and
document classification based on structural heuristics and geometric properties.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

from trace.multimodal.interfaces import (
    IDocumentClassifier,
    IDocumentLayoutDetector,
    IEquationDetector,
    IFigureDetector,
    IFragmentRelationshipScorer,
    IReadingOrderDetector,
    ITableDetector,
)
from trace.multimodal.representation import (
    BoundingBox,
    DocumentElement,
    DocumentPage,
    ElementType,
    NormalizedDocument,
    ProvenanceCategory,
)


class DeterministicDocumentIntelligence(
    IDocumentLayoutDetector,
    IReadingOrderDetector,
    ITableDetector,
    IFigureDetector,
    IEquationDetector,
    IDocumentClassifier,
    IFragmentRelationshipScorer,
):
    """Deterministic structural and geometric document intelligence engine."""

    def __init__(self, column_split_threshold: float = 0.5) -> None:
        self.column_split_threshold = column_split_threshold

    # --- IDocumentLayoutDetector ---
    def detect_layout(
        self,
        page: DocumentPage,
        raw_evidence: Optional[bytes] = None,
    ) -> List[DocumentElement]:
        """Classify elements into headers, footers, and text blocks with multi-column tags."""
        enriched: List[DocumentElement] = []
        page_height = page.height if page.height > 0 else 792.0
        page_width = page.width if page.width > 0 else 612.0

        for el in page.elements:
            # If already a specialized element (table, figure, equation), preserve
            if el.type in (ElementType.TABLE, ElementType.FIGURE, ElementType.IMAGE, ElementType.EQUATION):
                enriched.append(el)
                continue

            content_str = str(el.content).strip()
            bbox = el.bbox

            # Header detection heuristic: Top 12% of page or explicit Title/Header
            if bbox and bbox.y1 <= page_height * 0.12 and bbox.y2 <= page_height * 0.18:
                el_copy = el.model_copy(update={
                    "type": ElementType.HEADER,
                    "provenance": el.provenance,
                    "metadata": {**el.metadata, "zone": "header", "rule": "top_margin"},
                })
                enriched.append(el_copy)
                continue

            # Footer detection heuristic: Bottom 10% of page or page numbers
            if bbox and bbox.y2 >= page_height * 0.90:
                is_page_num = bool(re.search(r"^(?:page\s+)?\d+(?:\s*(?:of|/)\s*\d+)?$", content_str, re.IGNORECASE))
                el_copy = el.model_copy(update={
                    "type": ElementType.FOOTER,
                    "provenance": el.provenance,
                    "metadata": {**el.metadata, "zone": "footer", "is_page_number": is_page_num},
                })
                enriched.append(el_copy)
                continue

            # Multi-column tagging
            column_idx = 0
            if bbox:
                mid_x = (bbox.x1 + bbox.x2) / 2.0
                if mid_x >= page_width * self.column_split_threshold:
                    column_idx = 1

            el_copy = el.model_copy(update={
                "type": ElementType.TEXT_BLOCK,
                "metadata": {**el.metadata, "column_index": column_idx},
            })
            enriched.append(el_copy)

        return enriched

    # --- IReadingOrderDetector ---
    def determine_reading_order(
        self,
        page: DocumentPage,
    ) -> List[str]:
        """Order elements according to multi-column reading flow.
        
        Order:
        1. Full-width headers (y-ascending)
        2. Column 0 elements (y-ascending)
        3. Column 1 elements (y-ascending)
        4. Footers (y-ascending)
        """
        page_width = page.width if page.width > 0 else 612.0
        page_height = page.height if page.height > 0 else 792.0

        headers: List[DocumentElement] = []
        col0: List[DocumentElement] = []
        col1: List[DocumentElement] = []
        footers: List[DocumentElement] = []
        others: List[DocumentElement] = []

        for el in page.elements:
            bbox = el.bbox
            if el.type == ElementType.HEADER or (bbox and bbox.y1 <= page_height * 0.12):
                headers.append(el)
            elif el.type == ElementType.FOOTER or (bbox and bbox.y2 >= page_height * 0.90):
                footers.append(el)
            elif bbox:
                mid_x = (bbox.x1 + bbox.x2) / 2.0
                # If element spans across more than 75% of page width, treat as spanning/full-width
                if bbox.width > page_width * 0.75:
                    headers.append(el)
                elif mid_x < page_width * self.column_split_threshold:
                    col0.append(el)
                else:
                    col1.append(el)
            else:
                others.append(el)

        # Sort each band by y1 ascending, then x1 ascending
        key_fn = lambda x: (x.bbox.y1 if x.bbox else 999999.0, x.bbox.x1 if x.bbox else 999999.0)
        headers.sort(key=key_fn)
        col0.sort(key=key_fn)
        col1.sort(key=key_fn)
        footers.sort(key=key_fn)

        sorted_elements = headers + col0 + col1 + others + footers
        return [el.element_id for el in sorted_elements]

    # --- ITableDetector ---
    def detect_tables(
        self,
        page: DocumentPage,
        raw_evidence: Optional[bytes] = None,
    ) -> List[DocumentElement]:
        """Identify tabular structures via pipe '|', tab markers, or multi-element row alignment."""
        tables: List[DocumentElement] = []

        # Check existing elements for tabular text representation
        for idx, el in enumerate(page.elements):
            content_str = str(el.content)
            lines = [line.strip() for line in content_str.split("\n") if line.strip()]
            
            # Heuristic 1: Markdown-style pipes or delimiter lines
            has_pipe_delims = any("|" in line for line in lines) and len(lines) >= 2
            
            # Heuristic 2: Tab-separated or repeated column spacing
            has_tsv = any("\t" in line for line in lines) and len(lines) >= 2

            if has_pipe_delims or has_tsv:
                table_rows = []
                for line in lines:
                    if "|" in line:
                        cells = [c.strip() for c in line.split("|") if c.strip()]
                    else:
                        cells = [c.strip() for c in line.split("\t") if c.strip()]
                    if cells:
                        table_rows.append(cells)

                if table_rows:
                    tables.append(
                        DocumentElement(
                            element_id=f"{el.element_id}_table",
                            type=ElementType.TABLE,
                            page_number=page.page_number,
                            bbox=el.bbox,
                            content={"rows": table_rows, "row_count": len(table_rows)},
                            confidence=0.88,
                            provenance=ProvenanceCategory.DETERMINISTIC,
                            source="deterministic_table_detector",
                            evidence_offsets=el.evidence_offsets,
                            metadata={"parsed_rows": len(table_rows), "has_header": True},
                        )
                    )

        return tables

    # --- IFigureDetector ---
    def detect_figures(
        self,
        page: DocumentPage,
        raw_evidence: Optional[bytes] = None,
    ) -> List[DocumentElement]:
        """Detect figure captions or embedded visual blocks."""
        figures: List[DocumentElement] = []
        fig_caption_pattern = re.compile(r"^(?:Figure|Fig\.?|Chart|Diagram)\s+(\d+[:.]?.*)$", re.IGNORECASE)

        for el in page.elements:
            if el.type in (ElementType.FIGURE, ElementType.IMAGE):
                figures.append(el)
                continue

            content_str = str(el.content).strip()
            match = fig_caption_pattern.match(content_str)
            if match:
                fig_element = DocumentElement(
                    element_id=f"{el.element_id}_figure",
                    type=ElementType.FIGURE,
                    page_number=page.page_number,
                    bbox=el.bbox,
                    content={"caption": content_str, "label": match.group(0)},
                    confidence=0.92,
                    provenance=ProvenanceCategory.DETERMINISTIC,
                    source="deterministic_figure_detector",
                    evidence_offsets=el.evidence_offsets,
                    metadata={"caption": content_str},
                )
                figures.append(fig_element)

        return figures

    # --- IEquationDetector ---
    def detect_equations(
        self,
        page: DocumentPage,
        raw_evidence: Optional[bytes] = None,
    ) -> List[DocumentElement]:
        """Detect mathematical expressions and numbered equations."""
        equations: List[DocumentElement] = []
        # Matches patterns like "(1)", "(2.3)", or common math symbols
        eq_numbered = re.compile(r".*?\(\s*\d+(?:\.\d+)?\s*\)\s*$")
        math_symbols = {"\\sum", "\\int", "\\alpha", "\\beta", "\\gamma", "\\theta", "\\lambda", "dx/dt", "±", "≠", "≤", "≥", "∑", "∫"}

        for el in page.elements:
            if el.type == ElementType.EQUATION:
                equations.append(el)
                continue

            content_str = str(el.content).strip()
            has_symbols = any(sym in content_str for sym in math_symbols)
            is_numbered_eq = bool(eq_numbered.match(content_str)) and any(c in content_str for c in "=+-*/^")

            if has_symbols or is_numbered_eq:
                equations.append(
                    DocumentElement(
                        element_id=f"{el.element_id}_equation",
                        type=ElementType.EQUATION,
                        page_number=page.page_number,
                        bbox=el.bbox,
                        content=content_str,
                        confidence=0.85,
                        provenance=ProvenanceCategory.DETERMINISTIC,
                        source="deterministic_equation_detector",
                        evidence_offsets=el.evidence_offsets,
                        metadata={"is_numbered": is_numbered_eq},
                    )
                )

        return equations

    # --- IDocumentClassifier ---
    def classify_document(
        self,
        document: NormalizedDocument,
    ) -> Dict[str, Any]:
        """Deterministic fingerprint classifier based on document structural features."""
        all_text = " ".join(
            str(el.content)
            for page in document.pages
            for el in page.elements
            if isinstance(el.content, str)
        ).lower()

        scores: Dict[str, int] = {
            "research_paper": 0,
            "invoice": 0,
            "legal_contract": 0,
            "financial_report": 0,
            "technical_specification": 0,
        }

        # Signatures
        keywords = {
            "research_paper": ["abstract", "introduction", "methodology", "references", "results", "discussion", "et al."],
            "invoice": ["invoice", "bill to", "due date", "balance due", "subtotal", "tax", "payment terms"],
            "legal_contract": ["agreement", "terms and conditions", "governing law", "hereby", "parties", "indemnification", "jurisdiction"],
            "financial_report": ["balance sheet", "income statement", "cash flows", "fiscal year", "ebitda", "assets", "liabilities"],
            "technical_specification": ["specification", "requirements", "rfc", "protocol", "architecture", "payload", "interface"],
        }

        for category, terms in keywords.items():
            for term in terms:
                if term in all_text:
                    scores[category] += 1

        best_category = max(scores, key=lambda k: scores[k])
        max_score = scores[best_category]

        if max_score == 0:
            best_category = "general_document"
            confidence = 0.50
        else:
            confidence = min(0.95, 0.60 + (max_score * 0.05))

        return {
            "primary_category": best_category,
            "confidence": round(confidence, 2),
            "feature_counts": scores,
            "provenance": ProvenanceCategory.DETERMINISTIC.value,
            "source": "deterministic_fingerprint_classifier",
        }

    # --- IFragmentRelationshipScorer ---
    def score_relationship(
        self,
        fragment_a_id: str,
        fragment_a_data: bytes,
        fragment_b_id: str,
        fragment_b_data: bytes,
    ) -> Dict[str, Any]:
        """Calculate continuity or affinity score between fragment A and fragment B."""
        from trace.ml.relationships.features import FragmentInput
        from trace.ml.relationships.scorer import ForensicRelationshipScorer

        scorer = ForensicRelationshipScorer()
        frag_a = FragmentInput(fragment_id=fragment_a_id, data=fragment_a_data)
        frag_b = FragmentInput(fragment_id=fragment_b_id, data=fragment_b_data)

        cand = scorer.score_pair(frag_a, frag_b)
        return {
            "source_fragment_id": fragment_a_id,
            "target_fragment_id": fragment_b_id,
            "affinity_score": cand.affinity_score,
            "relationship_type": cand.relationship_type.value,
            "confidence_tier": cand.confidence_tier.value,
            "can_precede": cand.affinity_score >= 0.50 and cand.relationship_type.value != "DISJOINT",
            "component_scores": cand.component_scores,
            "evidence_observed": cand.evidence_observed,
            "inferred_compatibility": cand.inferred_compatibility,
            "negative_signals": cand.negative_signals,
            "uncertainty_limitations": cand.uncertainty_limitations,
            "provenance": ProvenanceCategory.DETERMINISTIC.value,
            "source": "deterministic_relationship_scorer",
        }

