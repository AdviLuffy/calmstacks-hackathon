"""Pipeline integrating deterministic recovery with the Multimodal Document Intelligence layer.

Translates raw bitstream recovery telemetry and surviving features into the normalized
hierarchical document representation, applying deterministic or model-based layout,
table, figure, equation, and reading-order engines while preserving strict provenance.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from trace.multimodal.deterministic import DeterministicDocumentIntelligence
from trace.multimodal.interfaces import (
    IDocumentClassifier,
    IDocumentLayoutDetector,
    IEquationDetector,
    IFigureDetector,
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


def build_normalized_document_from_recovery(
    surviving_features: Dict[str, Any],
    raw_evidence: Optional[bytes] = None,
    document_id: Optional[str] = None,
    layout_detector: Optional[IDocumentLayoutDetector] = None,
    reading_order_detector: Optional[IReadingOrderDetector] = None,
    table_detector: Optional[ITableDetector] = None,
    figure_detector: Optional[IFigureDetector] = None,
    equation_detector: Optional[IEquationDetector] = None,
    classifier: Optional[IDocumentClassifier] = None,
) -> NormalizedDocument:
    """Construct a NormalizedDocument from recovered forensic features and raw evidence.
    
    Guarantees:
    - Surviving text strings and recovered objects retain AUTHENTIC provenance and exact byte offsets.
    - Layout zones, tables, figures, equations, and reading order are classified via deterministic
      or model-based detectors without overwriting authentic bytes.
    - Category integrity is verified prior to returning.
    """
    doc_id = document_id or f"doc_{uuid.uuid4().hex[:8]}"
    deterministic_engine = DeterministicDocumentIntelligence()

    # Active detectors (defaulting to deterministic engine)
    layout_det = layout_detector or deterministic_engine
    reading_det = reading_order_detector or deterministic_engine
    table_det = table_detector or deterministic_engine
    figure_det = figure_detector or deterministic_engine
    equation_det = equation_detector or deterministic_engine
    clf = classifier or deterministic_engine

    # 1. Determine page geometry and page count
    page_info = surviving_features.get("page_info", {})
    page_count = max(1, page_info.get("page_count", 1))
    mediabox = page_info.get("mediabox", [0.0, 0.0, 612.0, 792.0])
    page_width = float(mediabox[2] - mediabox[0]) if len(mediabox) >= 4 else 612.0
    page_height = float(mediabox[3] - mediabox[1]) if len(mediabox) >= 4 else 792.0

    # Initialize empty DocumentPages
    pages_map: Dict[int, DocumentPage] = {}
    for p_num in range(1, page_count + 1):
        pages_map[p_num] = DocumentPage(
            page_number=p_num,
            width=page_width,
            height=page_height,
            elements=[],
            reading_order=[],
        )

    # 2. Ingest authentic surviving text strings with exact offsets
    surviving_strings = surviving_features.get("surviving_strings", [])
    for idx, s in enumerate(surviving_strings):
        if isinstance(s, dict):
            text_val = s.get("text", "")
            p_target = s.get("page", 1)
            offsets = s.get("offsets", [])
            conf = s.get("confidence", 1.0)
            bbox_raw = s.get("bbox")
        else:
            text_val = str(s)
            p_target = (idx % page_count) + 1
            offsets = []
            conf = 1.0
            bbox_raw = None

        if p_target not in pages_map:
            p_target = 1

        # Synthesize initial bounding box estimate based on page layout if not present
        if bbox_raw and len(bbox_raw) == 4:
            bbox = BoundingBox(x1=bbox_raw[0], y1=bbox_raw[1], x2=bbox_raw[2], y2=bbox_raw[3])
        else:
            # Deterministic vertical stagger based on element index within page
            current_count = len(pages_map[p_target].elements)
            y_pos = 50.0 + (current_count * 28.0)
            if y_pos > page_height - 60:
                y_pos = page_height - 60
            bbox = BoundingBox(x1=54.0, y1=y_pos, x2=page_width - 54.0, y2=y_pos + 22.0)

        pages_map[p_target].elements.append(
            DocumentElement(
                element_id=f"el_auth_str_{p_target}_{idx}",
                type=ElementType.TEXT_BLOCK,
                page_number=p_target,
                bbox=bbox,
                content=text_val,
                confidence=conf,
                provenance=ProvenanceCategory.AUTHENTIC,
                source="pdf_object_stream",
                evidence_offsets=offsets if isinstance(offsets, list) else [],
                metadata={"string_index": idx},
            )
        )

    # 3. Ingest authentic image / figure objects
    image_info = surviving_features.get("image_info", [])
    for idx, img in enumerate(image_info):
        p_target = img.get("page", 1)
        if p_target not in pages_map:
            p_target = 1

        offsets = img.get("offsets", [])
        bbox_coords = img.get("bbox", [72.0, 100.0, page_width - 72.0, 250.0])
        bbox = BoundingBox(x1=bbox_coords[0], y1=bbox_coords[1], x2=bbox_coords[2], y2=bbox_coords[3])

        pages_map[p_target].elements.append(
            DocumentElement(
                element_id=f"el_auth_img_{p_target}_{idx}",
                type=ElementType.IMAGE,
                page_number=p_target,
                bbox=bbox,
                content={"object_id": img.get("object_id", f"img_{idx}"), "format": img.get("format", "jpeg")},
                confidence=1.0,
                provenance=ProvenanceCategory.AUTHENTIC,
                source="pdf_xobject_stream",
                evidence_offsets=offsets if isinstance(offsets, list) else [],
                metadata=img,
            )
        )

    # 4. Enrich each page with specialized detectors (layout, tables, figures, equations, reading order)
    for p_num, page in pages_map.items():
        # A. Table detection
        detected_tables = table_det.detect_tables(page, raw_evidence)
        page.elements.extend(detected_tables)

        # B. Figure detection
        detected_figures = figure_det.detect_figures(page, raw_evidence)
        # Avoid duplicating existing images
        for df in detected_figures:
            if not any(e.element_id == df.element_id for e in page.elements):
                page.elements.append(df)

        # C. Equation detection
        detected_equations = equation_det.detect_equations(page, raw_evidence)
        for de in detected_equations:
            if not any(e.element_id == de.element_id for e in page.elements):
                page.elements.append(de)

        # D. Layout zone enrichment (headers, footers, column assignments)
        page.elements = layout_det.detect_layout(page, raw_evidence)

        # E. Determine reading order
        ordered_ids = reading_det.determine_reading_order(page)
        page.reading_order = ordered_ids
        for seq_idx, el_id in enumerate(ordered_ids):
            for el in page.elements:
                if el.element_id == el_id:
                    el.reading_order_index = seq_idx
                    break

    # 5. Construct NormalizedDocument
    pages_list = [pages_map[p_num] for p_num in sorted(pages_map.keys())]
    doc = NormalizedDocument(
        document_id=doc_id,
        title=surviving_features.get("metadata", {}).get("Title", ""),
        metadata=surviving_features.get("metadata", {}),
        pages=pages_list,
        evidence_references={
            "authentic_bytes_identified": surviving_features.get("authentic_bytes_identified", 0),
            "authentic_recovery_percentage": surviving_features.get("authentic_recovery_percentage", 0.0),
            "surviving_objects_count": surviving_features.get("surviving_objects_count", 0),
        },
        summary_telemetry={
            "page_count": len(pages_list),
            "total_elements": sum(len(p.elements) for p in pages_list),
        },
    )

    # 6. Document Classification
    classification_result = clf.classify_document(doc)
    doc.metadata["classification"] = classification_result

    # 7. Strictly verify forensic provenance guarantees
    audit = doc.verify_provenance_integrity()
    doc.summary_telemetry["provenance_audit"] = audit

    return doc
