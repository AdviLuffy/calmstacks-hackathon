"""High-Fidelity PDF Document Builder for TRACE Phase 9.

Synthesizes clean, standards-compliant multi-page PDF documents from
reconstructed NormalizedDocument representations, rendering authentic text,
tables, figures, and equations with clear forensic provenance indicators.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Tuple

from trace.multimodal.representation import (
    BoundingBox,
    DocumentElement,
    DocumentPage,
    ElementType,
    NormalizedDocument,
    ProvenanceCategory,
)

logger = logging.getLogger(__name__)


class MultimodalPdfBuilder:
    """Builds multi-page PDFs from NormalizedDocument using PyMuPDF (with fallback)."""

    def __init__(self, include_provenance_badges: bool = True) -> None:
        self.include_provenance_badges = include_provenance_badges

    def build_pdf(self, document: NormalizedDocument) -> bytes:
        """Render a NormalizedDocument into standard PDF byte stream."""
        try:
            return self._build_with_pymupdf(document)
        except Exception as e:
            logger.warning("PyMuPDF build failed (%s); using pure-python fallback", e)
            return self._build_pure_fallback(document)

    def _build_with_pymupdf(self, document: NormalizedDocument) -> bytes:
        """Render document using PyMuPDF."""
        import pymupdf

        pdf_doc = pymupdf.open()

        for page in document.pages:
            p_width = page.width if page.width > 0 else 612.0
            p_height = page.height if page.height > 0 else 792.0
            pdf_page = pdf_doc.new_page(width=p_width, height=p_height)

            # Draw forensic provenance banner / watermark at top
            if self.include_provenance_badges:
                pdf_page.draw_rect(
                    pymupdf.Rect(54, 18, p_width - 54, 34),
                    color=(0.85, 0.88, 0.92),
                    fill=(0.95, 0.96, 0.98),
                    width=0.5,
                )
                auth_pct = document.summary_telemetry.get("authentic_recovery_percentage", 100.0)
                banner_text = (
                    f"TRACE FORENSIC RECONSTRUCTION  |  Authenticity: {auth_pct:.1f}%  |  "
                    f"Doc ID: {document.document_id[:16]}  |  Page {page.page_number}/{len(document.pages)}"
                )
                pdf_page.insert_text(
                    (60, 29),
                    banner_text,
                    fontsize=7,
                    color=(0.2, 0.3, 0.4),
                )

            # Track vertical pen position for elements without strict bounding box
            current_y = 54.0

            # Render elements in reading order
            sorted_elements = page.elements
            if page.reading_order:
                # Map elements by ID
                el_map = {el.element_id: el for el in page.elements}
                sorted_elements = [el_map[eid] for eid in page.reading_order if eid in el_map]
                # Add any unindexed elements
                for el in page.elements:
                    if el.element_id not in page.reading_order:
                        sorted_elements.append(el)

            for el in sorted_elements:
                if el.type in (ElementType.HEADER, ElementType.TEXT_BLOCK):
                    current_y = self._render_text_block(pdf_page, el, current_y, p_width, p_height)
                elif el.type == ElementType.TABLE:
                    current_y = self._render_table(pdf_page, el, current_y, p_width, p_height)
                elif el.type in (ElementType.IMAGE, ElementType.FIGURE):
                    current_y = self._render_image(pdf_page, el, current_y, p_width, p_height)
                elif el.type == ElementType.EQUATION:
                    current_y = self._render_equation(pdf_page, el, current_y, p_width, p_height)
                elif el.type == ElementType.FOOTER:
                    self._render_footer(pdf_page, el, p_width, p_height)

            # Footer on bottom
            pdf_page.insert_text(
                (p_width / 2.0 - 20.0, p_height - 24.0),
                f"- {page.page_number} -",
                fontsize=9,
                color=(0.4, 0.4, 0.4),
            )

        pdf_bytes = pdf_doc.tobytes()
        pdf_doc.close()
        return pdf_bytes

    def _render_text_block(
        self,
        page: Any,
        el: DocumentElement,
        current_y: float,
        page_width: float,
        page_height: float,
    ) -> float:
        """Render text block with appropriate typography and layout."""
        import pymupdf

        text = str(el.content).strip()
        if not text:
            return current_y

        is_heading = el.type == ElementType.HEADER or el.metadata.get("is_heading", False)
        heading_level = el.metadata.get("heading_level", 0)
        font_size = 14.0 if is_heading and heading_level == 1 else (12.0 if is_heading else 9.5)
        col_idx = el.metadata.get("column_index", 0)

        # Calculate bounding rect
        if el.bbox and el.bbox.width > 20 and el.bbox.height > 10:
            target_rect = pymupdf.Rect(el.bbox.x1, el.bbox.y1, el.bbox.x2, el.bbox.y2)
        else:
            # Fallback column flow
            if col_idx == 1:
                x1 = (page_width / 2.0) + 10.0
                x2 = page_width - 54.0
            else:
                x1 = 54.0
                x2 = (page_width / 2.0) - 10.0 if not is_heading else (page_width - 54.0)

            approx_lines = max(1, len(text) // 60 + 1)
            h = approx_lines * font_size * 1.3 + 6.0
            y1 = max(current_y, 45.0)
            target_rect = pymupdf.Rect(x1, y1, x2, min(page_height - 40.0, y1 + h))

        # Insert textbox
        color = (0.0, 0.0, 0.0) if not is_heading else (0.1, 0.2, 0.35)
        page.insert_textbox(
            target_rect,
            text,
            fontsize=font_size,
            color=color,
        )

        return target_rect.y1 + target_rect.height + 4.0

    def _render_table(
        self,
        page: Any,
        el: DocumentElement,
        current_y: float,
        page_width: float,
        page_height: float,
    ) -> float:
        """Render structured table with grid lines, header shading, and cell text."""
        import pymupdf

        content = el.content if isinstance(el.content, dict) else {}
        rows = content.get("rows", [])
        caption = content.get("caption") or el.metadata.get("caption")

        y_start = max(current_y + 8.0, 50.0)

        # Draw caption if present
        if caption:
            cap_rect = pymupdf.Rect(54, y_start, page_width - 54, y_start + 16)
            page.insert_textbox(cap_rect, caption, fontsize=9, color=(0.1, 0.1, 0.1))
            y_start += 18.0

        if not rows:
            return y_start + 10.0

        col_count = max(len(r) for r in rows)
        if col_count == 0:
            return y_start

        table_width = page_width - 108.0
        col_w = table_width / col_count
        row_h = 18.0

        for r_idx, row in enumerate(rows):
            r_y = y_start + (r_idx * row_h)
            if r_y + row_h > page_height - 40.0:
                break

            for c_idx, cell_text in enumerate(row):
                c_x = 54.0 + (c_idx * col_w)
                cell_rect = pymupdf.Rect(c_x, r_y, c_x + col_w, r_y + row_h)

                # Shading for header row
                if r_idx == 0:
                    page.draw_rect(cell_rect, color=(0.7, 0.7, 0.7), fill=(0.92, 0.94, 0.96), width=0.5)
                else:
                    page.draw_rect(cell_rect, color=(0.75, 0.75, 0.75), width=0.5)

                txt_str = str(cell_text).strip()
                if txt_str:
                    inner_rect = pymupdf.Rect(c_x + 3, r_y + 2, c_x + col_w - 3, r_y + row_h - 2)
                    page.insert_textbox(
                        inner_rect,
                        txt_str,
                        fontsize=8,
                        color=(0.1, 0.1, 0.1),
                    )

        total_table_height = (len(rows) * row_h)
        return y_start + total_table_height + 12.0

    def _render_image(
        self,
        page: Any,
        el: DocumentElement,
        current_y: float,
        page_width: float,
        page_height: float,
    ) -> float:
        """Render image XObject or placeholder if corrupted, with caption."""
        import pymupdf

        content = el.content if isinstance(el.content, dict) else {}
        raw_bytes = content.get("raw_bytes") or el.metadata.get("raw_bytes")
        caption = content.get("caption") or el.metadata.get("caption")
        is_corrupted = content.get("is_corrupted", False) or el.metadata.get("is_corrupted", False)

        y_start = max(current_y + 10.0, 50.0)
        img_w = min(page_width - 108.0, 320.0)
        img_h = 160.0
        x_start = (page_width - img_w) / 2.0

        img_rect = pymupdf.Rect(x_start, y_start, x_start + img_w, y_start + img_h)

        inserted = False
        if raw_bytes and not is_corrupted:
            try:
                page.insert_image(img_rect, stream=raw_bytes)
                inserted = True
            except Exception as e:
                logger.debug("Failed to render raw image bytes directly: %s", e)

        if not inserted:
            # Draw placeholder box indicating recovered image object
            page.draw_rect(img_rect, color=(0.4, 0.5, 0.6), fill=(0.95, 0.95, 0.97), width=1)
            status_text = "[Corrupted Image Evidence - Raw Stream Recovered]" if is_corrupted else f"[Figure: {el.element_id}]"
            page.insert_textbox(
                img_rect,
                status_text,
                fontsize=9,
                color=(0.3, 0.3, 0.4),
            )

        # Draw caption underneath
        y_caption = y_start + img_h + 4.0
        if caption:
            cap_rect = pymupdf.Rect(x_start, y_caption, x_start + img_w, y_caption + 16)
            page.insert_textbox(cap_rect, caption, fontsize=8.5, color=(0.2, 0.2, 0.2))
            y_caption += 18.0

        return y_caption + 8.0

    def _render_equation(
        self,
        page: Any,
        el: DocumentElement,
        current_y: float,
        page_width: float,
        page_height: float,
    ) -> float:
        """Render mathematical formula with centered formula and right-aligned numbering."""
        import pymupdf

        content = el.content if isinstance(el.content, dict) else {}
        latex = content.get("latex") or el.metadata.get("latex") or str(el.content)
        eq_num = content.get("number") or el.metadata.get("equation_number")

        y_start = max(current_y + 6.0, 50.0)
        eq_h = 24.0

        # Draw subtle equation background
        box_rect = pymupdf.Rect(54, y_start, page_width - 54, y_start + eq_h)
        page.draw_rect(box_rect, color=(0.9, 0.9, 0.9), fill=(0.98, 0.98, 0.99), width=0.5)

        # Formula text
        formula_rect = pymupdf.Rect(72, y_start + 3, page_width - 120, y_start + eq_h - 3)
        page.insert_textbox(
            formula_rect,
            latex,
            fontsize=9.5,
            color=(0.05, 0.05, 0.15),
        )

        # Equation number on far right
        if eq_num:
            num_rect = pymupdf.Rect(page_width - 110, y_start + 3, page_width - 60, y_start + eq_h - 3)
            page.insert_textbox(
                num_rect,
                f"({eq_num})",
                fontsize=9.5,
                color=(0.2, 0.2, 0.2),
            )

        return y_start + eq_h + 8.0

    def _render_footer(
        self,
        page: Any,
        el: DocumentElement,
        page_width: float,
        page_height: float,
    ) -> None:
        """Render page footer."""
        import pymupdf

        text = str(el.content).strip()
        if text:
            rect = pymupdf.Rect(54, page_height - 35.0, page_width - 54, page_height - 20.0)
            page.insert_textbox(rect, text, fontsize=8, color=(0.4, 0.4, 0.4))

    def _build_pure_fallback(self, document: NormalizedDocument) -> bytes:
        """Pure-Python fallback minimal PDF synthesizer when PyMuPDF is unavailable."""
        # Simple valid ISO 32000-1 PDF
        lines: List[bytes] = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
        offsets: List[int] = []

        def add_obj(obj_bytes: bytes) -> int:
            offsets.append(sum(len(l) for l in lines))
            lines.append(obj_bytes)
            return len(offsets)

        # Font object
        font_obj = b"1 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        add_obj(font_obj)

        page_refs: List[str] = []
        page_obj_ids: List[int] = []

        for p_idx, page in enumerate(document.pages, start=1):
            stream_lines: List[str] = ["BT", "/F1 10 Tf", "54 738 Td"]
            for el in page.elements:
                txt = str(el.content)[:120].replace("(", "\\(").replace(")", "\\)")
                stream_lines.append(f"({txt}) Tj")
                stream_lines.append("0 -14 Td")
            stream_lines.append("ET")
            stream_content = "\n".join(stream_lines).encode("latin-1", errors="replace")

            # Content stream object
            stm_id = len(offsets) + 1
            stm_obj = f"{stm_id} 0 obj\n<< /Length {len(stream_content)} >>\nstream\n".encode("ascii") + stream_content + b"\nendstream\nendobj\n"
            add_obj(stm_obj)

            # Page object
            pg_id = len(offsets) + 1
            pg_obj = (
                f"{pg_id} 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 1 0 R >> >> /Contents {stm_id} 0 R >>\nendobj\n"
            ).encode("ascii")
            add_obj(pg_obj)
            page_obj_ids.append(pg_id)
            page_refs.append(f"{pg_id} 0 R")

        # Pages tree object (id 2)
        kids_str = " ".join(page_refs)
        pages_obj = f"2 0 obj\n<< /Type /Pages /Kids [{kids_str}] /Count {len(page_refs)} >>\nendobj\n".encode("ascii")
        # Put pages_obj as object 2: insert into lines and recalculate offsets
        catalog_id = len(offsets) + 1
        cat_obj = f"{catalog_id} 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n".encode("ascii")
        add_obj(cat_obj)

        # Assemble with xref
        full_body = b"".join(lines)
        xref_offset = len(full_body)
        total_objs = len(offsets) + 1
        xref = f"xref\n0 {total_objs}\n0000000000 65535 f \n"
        for off in offsets:
            xref += f"{off:010d} 00000 n \n"
        trailer = f"trailer\n<< /Size {total_objs} /Root {catalog_id} 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n"
        return full_body + xref.encode("ascii") + trailer.encode("ascii")
