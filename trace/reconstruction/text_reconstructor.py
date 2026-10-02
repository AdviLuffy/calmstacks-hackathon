"""Text and Typography Reconstructor for TRACE Phase 9.

Recovers text streams, typography (fonts, sizes, weights), paragraphs,
multi-column reading flow, and section headings from damaged PDF evidence
with strict forensic provenance.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from trace.multimodal.representation import (
    BoundingBox,
    DocumentElement,
    ElementType,
    ProvenanceCategory,
)
from trace.reconstruction.models import TextBlockData


class TextReconstructor:
    """Extracts, parses, and reconstructs structured text blocks from PDF streams."""

    def __init__(
        self,
        default_font_size: float = 10.0,
        column_split_threshold: float = 0.5,
    ) -> None:
        self.default_font_size = default_font_size
        self.column_split_threshold = column_split_threshold

    def decode_pdf_string(self, raw_str: str) -> str:
        """Decode PDF literal string escapes and octal sequences."""
        if not raw_str:
            return ""

        # Handle hex strings <...>
        if raw_str.startswith("<") and raw_str.endswith(">"):
            hex_data = raw_str[1:-1].strip()
            try:
                if len(hex_data) % 2 != 0:
                    hex_data += "0"
                return bytes.fromhex(hex_data).decode("latin-1", errors="replace")
            except Exception:
                return hex_data

        # Literal string (...)
        if raw_str.startswith("(") and raw_str.endswith(")"):
            content = raw_str[1:-1]
        else:
            content = raw_str

        # Octal escapes \ddd
        def replace_octal(match: re.Match) -> str:
            oct_str = match.group(1)
            try:
                return chr(int(oct_str, 8))
            except Exception:
                return match.group(0)

        res = re.sub(r"\\([0-7]{1,3})", replace_octal, content)

        # Standard escapes
        res = res.replace(r"\n", "\n")
        res = res.replace(r"\r", "\r")
        res = res.replace(r"\t", "\t")
        res = res.replace(r"\b", "\b")
        res = res.replace(r"\f", "\f")
        res = res.replace(r"\(", "(")
        res = res.replace(r"\)", ")")
        res = res.replace(r"\\", "\\")
        res = re.sub(r"\\(.)", r"\1", res)

        return res

    def extract_text_from_stream(
        self,
        stream_bytes: bytes,
        page_number: int = 1,
        page_width: float = 612.0,
        page_height: float = 792.0,
        stream_offset: int = 0,
    ) -> List[TextBlockData]:
        """Parse PDF content stream text operators (BT...ET, Tf, Tm, Td, Tj, TJ)."""
        text_blocks: List[TextBlockData] = []
        if not stream_bytes:
            return text_blocks

        # Convert to string with latin-1 for byte-preserving character mapping
        stream_str = stream_bytes.decode("latin-1", errors="replace")

        # Find all BT ... ET blocks
        bt_blocks = re.findall(r"\bBT\b(.*?)\bET\b", stream_str, re.DOTALL)
        
        block_idx = 0
        current_font = "Helvetica"
        current_size = self.default_font_size

        for block_content in bt_blocks:
            current_x = 54.0
            current_y = page_height - 54.0
            current_lines: List[str] = []

            # Tokenize or scan operators inside BT...ET
            # Look for:
            # /FontName size Tf
            # x y Td or x y TD
            # a b c d x y Tm
            # (string) Tj or <hex> Tj
            # [(str) num (str)] TJ
            # T*
            op_pattern = re.compile(
                r"(?P<font>/[A-Za-z0-9_-]+\s+[\d\.]+\s+Tf)|"
                r"(?P<matrix>[-+]?[\d\.]+\s+[-+]?[\d\.]+\s+[-+]?[\d\.]+\s+[-+]?[\d\.]+\s+[-+]?[\d\.]+\s+[-+]?[\d\.]+\s+Tm)|"
                r"(?P<disp>[-+]?[\d\.]+\s+[-+]?[\d\.]+\s+T[dD])|"
                r"(?P<nextline>T\*)|"
                r"(?P<show>\((?:\\.|[^)])*\)\s*Tj|<[0-9A-Fa-f\s]+>\s*Tj)|"
                r"(?P<array>\[(?:\((?:\\.|[^)])*\)|<[0-9A-Fa-f\s]+>|[-+]?[\d\.]+|\s+)+\]\s*TJ)",
                re.DOTALL,
            )

            for match in op_pattern.finditer(block_content):
                m_dict = match.groupdict()
                if m_dict.get("font"):
                    parts = m_dict["font"].strip().split()
                    current_font = parts[0].lstrip("/")
                    try:
                        current_size = float(parts[1])
                    except (ValueError, IndexError):
                        current_size = self.default_font_size

                elif m_dict.get("matrix"):
                    parts = m_dict["matrix"].strip().split()
                    try:
                        current_x = float(parts[4])
                        current_y = float(parts[5])
                    except (ValueError, IndexError):
                        pass

                elif m_dict.get("disp"):
                    parts = m_dict["disp"].strip().split()
                    try:
                        dx = float(parts[0])
                        dy = float(parts[1])
                        current_x += dx
                        current_y += dy
                    except (ValueError, IndexError):
                        pass

                elif m_dict.get("nextline"):
                    current_y -= (current_size * 1.2)

                elif m_dict.get("show"):
                    raw_val = m_dict["show"].strip()
                    val = raw_val[:-2].strip()  # remove Tj
                    decoded = self.decode_pdf_string(val)
                    if decoded.strip():
                        current_lines.append(decoded)

                elif m_dict.get("array"):
                    raw_val = m_dict["array"].strip()
                    val = raw_val[:-2].strip()  # remove TJ
                    items = re.findall(r"\((?:\\.|[^)])*\)|<[0-9A-Fa-f\s]+>", val)
                    decoded_parts = [self.decode_pdf_string(item) for item in items]
                    joined = "".join(decoded_parts).strip()
                    if joined:
                        current_lines.append(joined)

            if current_lines:
                full_text = " ".join(current_lines).strip()
                if not full_text:
                    continue

                # Estimate bounding box
                approx_width = min(page_width - current_x - 36.0, max(60.0, len(full_text) * current_size * 0.55))
                approx_height = max(current_size * 1.2, len(current_lines) * current_size * 1.2)
                
                # Normalize PDF coordinates (bottom-left 0,0) to top-left (0,0)
                norm_y1 = max(0.0, page_height - current_y - approx_height)
                norm_y2 = min(page_height, norm_y1 + approx_height)
                norm_x1 = max(0.0, current_x)
                norm_x2 = min(page_width, norm_x1 + approx_width)

                bbox = BoundingBox(
                    x1=round(norm_x1, 1),
                    y1=round(norm_y1, 1),
                    x2=round(norm_x2, 1),
                    y2=round(norm_y2, 1),
                    coord_unit="pt",
                )

                # Determine heading status
                is_heading = False
                heading_level = 0
                if current_size >= 16.0 or (current_size >= 13.0 and len(full_text) < 120):
                    is_heading = True
                    heading_level = 1 if current_size >= 16.0 else 2
                elif full_text.isupper() and len(full_text) < 80:
                    is_heading = True
                    heading_level = 3

                # Multi-column index detection
                col_idx = 0
                mid_x = (bbox.x1 + bbox.x2) / 2.0
                if mid_x >= page_width * self.column_split_threshold and not is_heading:
                    col_idx = 1

                block_id = f"p{page_number}_tb_{block_idx}"
                block_idx += 1

                tb = TextBlockData(
                    block_id=block_id,
                    page_number=page_number,
                    text=full_text,
                    font_family=current_font,
                    font_size=current_size,
                    font_weight="bold" if is_heading else "normal",
                    bbox=bbox,
                    column_index=col_idx,
                    reading_order_index=0,  # Will be ordered later
                    is_heading=is_heading,
                    heading_level=heading_level,
                    confidence=1.0,
                    provenance=ProvenanceCategory.AUTHENTIC,
                    source_offsets=[[stream_offset, stream_offset + len(stream_bytes)]],
                )
                text_blocks.append(tb)

        # Fallback if no BT...ET blocks found, extract literal strings directly
        if not text_blocks and stream_bytes:
            raw_literals = re.findall(rb"\((?:\\.|[^)])*\)", stream_bytes)
            if raw_literals:
                combined_strs: List[str] = []
                for lit in raw_literals:
                    dec = self.decode_pdf_string(lit.decode("latin-1", errors="replace"))
                    if dec.strip() and len(dec.strip()) > 1:
                        combined_strs.append(dec.strip())
                
                if combined_strs:
                    full_text = " ".join(combined_strs)
                    bbox = BoundingBox(x1=54.0, y1=72.0, x2=page_width - 54.0, y2=page_height - 72.0)
                    tb = TextBlockData(
                        block_id=f"p{page_number}_tb_carved",
                        page_number=page_number,
                        text=full_text,
                        font_family="Helvetica",
                        font_size=self.default_font_size,
                        bbox=bbox,
                        column_index=0,
                        reading_order_index=0,
                        is_heading=False,
                        confidence=0.9,
                        provenance=ProvenanceCategory.AUTHENTIC,
                        source_offsets=[[stream_offset, stream_offset + len(stream_bytes)]],
                    )
                    text_blocks.append(tb)

        return text_blocks

    def organize_reading_order(
        self,
        blocks: List[TextBlockData],
        page_width: float = 612.0,
    ) -> List[TextBlockData]:
        """Topologically sort text blocks into natural academic reading order.
        
        Title/Abstract spanning the full width -> Left Column (col 0) top-down -> Right Column (col 1) top-down.
        """
        if not blocks:
            return []

        # Partition into:
        # 1. Spanning header/title blocks (width > 0.6 * page_width and y1 < 250)
        # 2. Left column blocks (col_idx == 0)
        # 3. Right column blocks (col_idx == 1)
        spanning: List[TextBlockData] = []
        left_col: List[TextBlockData] = []
        right_col: List[TextBlockData] = []

        for b in blocks:
            if (b.is_heading and b.heading_level == 1) or (b.bbox and b.bbox.width > page_width * 0.5 and b.bbox.y1 < 250.0):
                spanning.append(b)
            elif b.column_index == 1:
                right_col.append(b)
            else:
                left_col.append(b)

        # Sort each group vertically by y1
        spanning.sort(key=lambda x: x.bbox.y1 if x.bbox else 0.0)
        left_col.sort(key=lambda x: x.bbox.y1 if x.bbox else 0.0)
        right_col.sort(key=lambda x: x.bbox.y1 if x.bbox else 0.0)

        ordered = spanning + left_col + right_col
        for idx, item in enumerate(ordered):
            item.reading_order_index = idx

        return ordered

    def to_document_element(self, block: TextBlockData) -> DocumentElement:
        """Convert TextBlockData to standard DocumentElement."""
        return DocumentElement(
            element_id=block.block_id,
            type=ElementType.HEADER if block.is_heading else ElementType.TEXT_BLOCK,
            page_number=block.page_number,
            bbox=block.bbox,
            content=block.text,
            reading_order_index=block.reading_order_index,
            confidence=block.confidence,
            provenance=block.provenance,
            source="pdf_recovery.content_stream",
            evidence_offsets=block.source_offsets,
            metadata={
                "font_family": block.font_family,
                "font_size": block.font_size,
                "font_weight": block.font_weight,
                "column_index": block.column_index,
                "is_heading": block.is_heading,
                "heading_level": block.heading_level,
            },
        )
