"""Ground-truth label generator for document fragments.

Maps byte ranges of clean/original documents and corruption manifestations
to exact or heuristic FragmentLabel categories without data leakage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from trace.datasets.schemas.ground_truth import FragmentLabel


@dataclass
class DocumentByteRegion:
    """Designated byte interval corresponding to a known structural entity."""
    start: int
    end: int
    label: FragmentLabel
    entity_id: str
    is_exact: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DocumentStructuralMap:
    """Spatial map of all known structural components in a PDF document."""
    doc_id: str
    total_bytes: int
    regions: List[DocumentByteRegion] = field(default_factory=list)

    def get_dominant_label_for_range(self, start: int, end: int) -> Tuple[FragmentLabel, bool, str]:
        """Find the entity that has the maximum byte overlap with [start, end)."""
        if end <= start:
            return FragmentLabel.UNKNOWN, True, "empty_range"

        range_len = end - start
        best_overlap = 0
        best_region: Optional[DocumentByteRegion] = None

        # Priority 1: If range contains or overlaps the PDF header signature at start
        for reg in self.regions:
            if reg.label == FragmentLabel.PDF_HEADER and max(start, reg.start) < min(end, reg.end):
                return FragmentLabel.PDF_HEADER, True, reg.entity_id

        for reg in self.regions:
            overlap = max(0, min(end, reg.end) - max(start, reg.start))
            if overlap > best_overlap:
                best_overlap = overlap
                best_region = reg

        # If overlap is significant (at least 25% of the fragment or >= 32 bytes)
        if best_region and (best_overlap >= range_len * 0.25 or best_overlap >= 32):
            return best_region.label, best_region.is_exact, best_region.entity_id

        return FragmentLabel.UNKNOWN, False, "no_overlap"


class FragmentLabelBuilder:
    """Constructs structural maps and labels from PDF byte streams."""

    _OBJ_HEADER_RE = re.compile(rb"(\d+)\s+(\d+)\s+obj")
    _ENDOBJ_RE = re.compile(rb"endobj")
    _STREAM_START_RE = re.compile(rb"stream[\r\n]+")
    _ENDSTREAM_RE = re.compile(rb"endstream")
    _XREF_RE = re.compile(rb"\bxref\b")
    _TRAILER_RE = re.compile(rb"\btrailer\b")
    _STARTXREF_RE = re.compile(rb"\bstartxref\b")

    def build_structural_map(self, pdf_bytes: bytes, doc_id: str = "doc") -> DocumentStructuralMap:
        """Parse raw PDF bytes into a spatial layout of structural regions."""
        smap = DocumentStructuralMap(doc_id=doc_id, total_bytes=len(pdf_bytes))
        total_len = len(pdf_bytes)
        if total_len == 0:
            return smap

        # 1. Header region
        if pdf_bytes.startswith(b"%PDF"):
            hdr_end = pdf_bytes.find(b"\n")
            if hdr_end == -1:
                hdr_end = min(32, total_len)
            else:
                hdr_end = min(hdr_end + 1, total_len)
            smap.regions.append(DocumentByteRegion(
                start=0,
                end=hdr_end,
                label=FragmentLabel.PDF_HEADER,
                entity_id="header_0",
                is_exact=True,
            ))

        # 2. Xref tables and trailers
        for m in self._XREF_RE.finditer(pdf_bytes):
            start = m.start()
            # Xref extends until trailer or next token
            end = min(total_len, start + 256)
            trail = self._TRAILER_RE.search(pdf_bytes, start)
            if trail and trail.start() - start < 1024:
                end = trail.start()
            smap.regions.append(DocumentByteRegion(
                start=start,
                end=end,
                label=FragmentLabel.XREF,
                entity_id=f"xref_{start}",
                is_exact=True,
            ))

        for m in self._TRAILER_RE.finditer(pdf_bytes):
            start = m.start()
            end = min(total_len, start + 256)
            eof = pdf_bytes.find(b"%%EOF", start)
            if eof != -1 and eof - start < 512:
                end = eof + 5
            smap.regions.append(DocumentByteRegion(
                start=start,
                end=end,
                label=FragmentLabel.TRAILER,
                entity_id=f"trailer_{start}",
                is_exact=True,
            ))

        for m in self._STARTXREF_RE.finditer(pdf_bytes):
            start = m.start()
            eof = pdf_bytes.find(b"%%EOF", start)
            end = (eof + 5) if eof != -1 else min(total_len, start + 64)
            smap.regions.append(DocumentByteRegion(
                start=start,
                end=end,
                label=FragmentLabel.TRAILER,
                entity_id=f"startxref_{start}",
                is_exact=True,
            ))

        # 3. Indirect Objects & Streams
        for m in self._OBJ_HEADER_RE.finditer(pdf_bytes):
            obj_num = int(m.group(1))
            gen_num = int(m.group(2))
            obj_start = m.start()

            # Find matching endobj
            endobj_m = self._ENDOBJ_RE.search(pdf_bytes, m.end())
            if endobj_m:
                obj_end = endobj_m.end()
            else:
                obj_end = min(total_len, obj_start + 4096)

            obj_chunk = pdf_bytes[obj_start:obj_end]
            entity_id = f"obj_{obj_num}_{gen_num}"

            # Check if this object contains a stream
            stream_start_m = self._STREAM_START_RE.search(obj_chunk)
            stream_region: Optional[DocumentByteRegion] = None

            if stream_start_m:
                stream_content_start = obj_start + stream_start_m.end()
                stream_end_m = self._ENDSTREAM_RE.search(pdf_bytes, stream_content_start)
                if stream_end_m:
                    stream_content_end = stream_end_m.start()
                else:
                    stream_content_end = obj_end

                stream_bytes = pdf_bytes[stream_content_start:stream_content_end]

                # Classify stream subtype
                is_image = (
                    b"/Subtype /Image" in obj_chunk
                    or b"/Subtype/Image" in obj_chunk
                    or b"/DCTDecode" in obj_chunk
                    or b"/JPXDecode" in obj_chunk
                )
                is_text = (
                    b"BT" in stream_bytes and b"ET" in stream_bytes
                ) or (
                    b"/Type /Page" in obj_chunk and b"/Contents" in obj_chunk
                )
                is_font = (
                    b"/FontFile" in obj_chunk
                    or b"/FontFile2" in obj_chunk
                    or b"/FontFile3" in obj_chunk
                )

                if is_image:
                    stream_label = FragmentLabel.IMAGE_STREAM
                elif is_text:
                    stream_label = FragmentLabel.TEXT_STREAM
                elif is_font:
                    stream_label = FragmentLabel.FONT_OBJECT
                else:
                    stream_label = FragmentLabel.PDF_STREAM

                stream_region = DocumentByteRegion(
                    start=stream_content_start,
                    end=stream_content_end,
                    label=stream_label,
                    entity_id=f"{entity_id}_stream",
                    is_exact=True,
                )

            # Classify object dictionary container
            is_page = b"/Type /Page" in obj_chunk or b"/Type/Page" in obj_chunk
            is_font = b"/Type /Font" in obj_chunk or b"/Type/Font" in obj_chunk
            is_meta = b"/Type /Metadata" in obj_chunk or b"/Type/Metadata" in obj_chunk

            if is_meta:
                obj_label = FragmentLabel.METADATA
            elif is_page:
                obj_label = FragmentLabel.PAGE_OBJECT
            elif is_font:
                obj_label = FragmentLabel.FONT_OBJECT
            else:
                obj_label = FragmentLabel.PDF_OBJECT

            # If there is a stream, the object has non-stream header/footer and stream body
            if stream_region:
                # Add dictionary header region
                if stream_region.start > obj_start:
                    smap.regions.append(DocumentByteRegion(
                        start=obj_start,
                        end=stream_region.start,
                        label=obj_label,
                        entity_id=f"{entity_id}_dict",
                        is_exact=True,
                    ))
                # Add stream region
                smap.regions.append(stream_region)
                # Add endstream / endobj footer region
                if obj_end > stream_region.end:
                    smap.regions.append(DocumentByteRegion(
                        start=stream_region.end,
                        end=obj_end,
                        label=obj_label,
                        entity_id=f"{entity_id}_footer",
                        is_exact=True,
                    ))
            else:
                smap.regions.append(DocumentByteRegion(
                    start=obj_start,
                    end=obj_end,
                    label=obj_label,
                    entity_id=entity_id,
                    is_exact=True,
                ))

        return smap


def build_labeled_fragments_from_document(
    pdf_bytes: bytes,
    doc_id: str,
    block_sizes: Sequence[int] = (256, 512),
    stride: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Slice a document into labeled fragment items using exact structural boundaries."""
    builder = FragmentLabelBuilder()
    smap = builder.build_structural_map(pdf_bytes, doc_id=doc_id)
    results: List[Dict[str, Any]] = []

    total_len = len(pdf_bytes)
    if total_len == 0:
        return results

    for bs in block_sizes:
        step = stride if stride is not None else bs
        for offset in range(0, total_len, step):
            end_offset = min(total_len, offset + bs)
            frag_bytes = pdf_bytes[offset:end_offset]
            label, is_exact, entity_id = smap.get_dominant_label_for_range(offset, end_offset)

            results.append({
                "fragment_id": f"{doc_id}_sz{bs}_off{offset:06d}",
                "doc_id": doc_id,
                "offset": offset,
                "length": len(frag_bytes),
                "bytes": frag_bytes,
                "label": label.value,
                "is_exact": is_exact,
                "entity_id": entity_id,
            })

    return results
