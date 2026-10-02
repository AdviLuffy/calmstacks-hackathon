"""Document Layout and Geometry Engine for TRACE Phase 9.

Analyzes multi-page research paper geometry, establishes column boundaries,
detects headers and footers, and computes topological reading orders.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple

from trace.multimodal.representation import (
    BoundingBox,
    DocumentElement,
    DocumentPage,
    ElementType,
    NormalizedDocument,
    ProvenanceCategory,
)
from trace.reconstruction.models import (
    EquationElement,
    ImageElement,
    PageLayoutData,
    TableStructure,
    TextBlockData,
)


class DocumentLayoutEngine:
    """Manages page geometry, multi-column partitioning, and element placement."""

    def __init__(
        self,
        default_width: float = 612.0,
        default_height: float = 792.0,
        margin_x: float = 54.0,
        margin_y: float = 54.0,
        column_gutter: float = 18.0,
    ) -> None:
        self.default_width = default_width
        self.default_height = default_height
        self.margin_x = margin_x
        self.margin_y = margin_y
        self.column_gutter = column_gutter

    def compute_page_layout(
        self,
        page_number: int,
        width: Optional[float] = None,
        height: Optional[float] = None,
        columns_count: int = 1,
    ) -> PageLayoutData:
        """Calculate layout dimensions and column boundaries for a page."""
        w = width if width and width > 0 else self.default_width
        h = height if height and height > 0 else self.default_height

        col_boundaries: List[Tuple[float, float]] = []
        if columns_count <= 1:
            col_boundaries.append((self.margin_x, w - self.margin_x))
        else:
            # 2-column layout
            content_w = w - (2 * self.margin_x) - ((columns_count - 1) * self.column_gutter)
            col_w = content_w / columns_count
            for i in range(columns_count):
                x_start = self.margin_x + i * (col_w + self.column_gutter)
                x_end = x_start + col_w
                col_boundaries.append((round(x_start, 1), round(x_end, 1)))

        header_box = BoundingBox(
            x1=self.margin_x,
            y1=20.0,
            x2=w - self.margin_x,
            y2=self.margin_y,
            coord_unit="pt",
        )
        footer_box = BoundingBox(
            x1=self.margin_x,
            y1=h - self.margin_y,
            x2=w - self.margin_x,
            y2=h - 20.0,
            coord_unit="pt",
        )

        return PageLayoutData(
            page_number=page_number,
            width=w,
            height=h,
            columns_count=columns_count,
            column_boundaries=col_boundaries,
            margin_top=self.margin_y,
            margin_bottom=self.margin_y,
            margin_left=self.margin_x,
            margin_right=self.margin_x,
            header_box=header_box,
            footer_box=footer_box,
        )

    def assemble_document_pages(
        self,
        document_id: str,
        title: str,
        elements_by_page: Dict[int, List[DocumentElement]],
        page_dimensions: Optional[Dict[int, Tuple[float, float]]] = None,
        telemetry: Optional[Dict[str, Any]] = None,
    ) -> NormalizedDocument:
        """Assemble recovered multimodal elements into a structured NormalizedDocument."""
        pages: List[DocumentPage] = []
        dims = page_dimensions or {}

        # Ensure at least page 1 exists if there are elements or empty
        sorted_page_nums = sorted(elements_by_page.keys()) if elements_by_page else [1]

        for p_num in sorted_page_nums:
            w, h = dims.get(p_num, (self.default_width, self.default_height))
            page_els = elements_by_page.get(p_num, [])

            # Check if elements suggest 2 columns
            col1_count = 0
            for el in page_els:
                if el.metadata.get("column_index") == 1:
                    col1_count += 1
            has_two_cols = (col1_count >= 2)

            layout = self.compute_page_layout(
                page_number=p_num,
                width=w,
                height=h,
                columns_count=2 if has_two_cols else 1,
            )

            doc_page = DocumentPage(
                page_number=p_num,
                width=w,
                height=h,
                elements=[],
                page_metadata={
                    "layout": layout.to_dict(),
                    "columns_count": layout.columns_count,
                },
            )

            # Sort elements by reading order
            sorted_elements = self._sort_page_elements(page_els, w, h)
            for idx, el in enumerate(sorted_elements):
                el.reading_order_index = idx
                doc_page.add_element(el)

            pages.append(doc_page)

        return NormalizedDocument(
            document_id=document_id,
            title=title,
            pages=pages,
            summary_telemetry=telemetry or {},
        )

    def _sort_page_elements(
        self,
        elements: List[DocumentElement],
        page_width: float,
        page_height: float,
    ) -> List[DocumentElement]:
        """Establish topological reading order for all elements on a page."""
        if not elements:
            return []

        def sort_key(el: DocumentElement) -> Tuple[int, float, float]:
            col = el.metadata.get("column_index", 0)
            y = el.bbox.y1 if el.bbox else 0.0
            x = el.bbox.x1 if el.bbox else 0.0

            # Headers first
            if el.type == ElementType.HEADER:
                return (0, y, x)
            # Full width spanning elements next (e.g. title or abstract on page 1)
            if el.bbox and el.bbox.width > page_width * 0.6 and y < 250.0:
                return (1, y, x)
            # Left column
            if col == 0:
                return (2, y, x)
            # Right column
            if col == 1:
                return (3, y, x)
            # Footers last
            if el.type == ElementType.FOOTER:
                return (5, y, x)
            return (4, y, x)

        return sorted(elements, key=sort_key)
