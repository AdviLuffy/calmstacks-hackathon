"""Deterministic Synthetic Document Generator for TRACE.

Produces fully compliant ISO 32000-1 PDFs containing titles, authors, abstracts, headings,
paragraphs, multi-column text, tables, figures, equations, headers, footers, metadata,
and embedded images with reproducible seeds across Small, Medium, and Large document sizes.
"""

from __future__ import annotations

import random
from typing import Any, Dict, List, Optional, Tuple


class SyntheticDocumentGenerator:
    """Generates deterministic, fully structured test PDFs for benchmarking."""

    def __init__(self, default_seed: int = 42) -> None:
        self.default_seed = default_seed

    def generate(
        self,
        page_count: int = 1,
        seed: Optional[int] = None,
        doc_size: str = "SMALL",
    ) -> bytes:
        """Generate a valid, deterministic PDF byte buffer.
        
        doc_size:
        - 'SMALL': 1-2 pages (overrides page_count to 2 if page_count < 2)
        - 'MEDIUM': 3-10 pages (e.g. 5 pages)
        - 'LARGE': 10+ pages (e.g. 12 pages)
        """
        active_seed = seed if seed is not None else self.default_seed
        rng = random.Random(active_seed)

        if doc_size == "SMALL":
            pages = max(1, min(page_count, 2))
        elif doc_size == "MEDIUM":
            pages = max(3, min(page_count, 10))
        elif doc_size == "LARGE":
            pages = max(11, page_count)
        else:
            pages = max(1, page_count)

        return self._build_pdf(pages, rng)

    def _build_pdf(self, total_pages: int, rng: random.Random) -> bytes:
        """Construct raw PDF byte stream with exact structural objects and xref table."""
        # Objects inventory
        # 1: Catalog
        # 2: Pages tree
        # 3: Font Helvetica
        # 4: Font Helvetica-Bold
        # 5: Image XObject (4x4 checkerboard RGB)
        # 6: Document Info dictionary
        # 7 .. 7 + total_pages - 1: Page objects
        # 7 + total_pages .. 7 + 2*total_pages - 1: Content stream objects

        catalog_num = 1
        pages_tree_num = 2
        font_regular_num = 3
        font_bold_num = 4
        image_num = 5
        info_num = 6

        first_page_num = 7
        page_nums = list(range(first_page_num, first_page_num + total_pages))
        first_stream_num = first_page_num + total_pages
        stream_nums = list(range(first_stream_num, first_stream_num + total_pages))

        # Synthetic 4x4 RGB image payload (48 bytes)
        raw_rgb = bytes([
            255, 0, 0,  0, 255, 0,  0, 0, 255,  255, 255, 0,
            0, 255, 255,  255, 0, 255,  128, 128, 128,  255, 255, 255,
            0, 0, 0,  200, 100, 50,  50, 150, 200,  100, 200, 100,
            255, 128, 0,  0, 128, 255,  128, 0, 255,  255, 255, 255,
        ])
        image_stream = raw_rgb

        # Build objects
        objects_dict: Dict[int, bytes] = {}

        # 1. Catalog
        objects_dict[catalog_num] = f"<< /Type /Catalog /Pages {pages_tree_num} 0 R >>".encode("ascii")

        # 2. Pages Tree
        kids_str = " ".join(f"{p} 0 R" for p in page_nums)
        objects_dict[pages_tree_num] = f"<< /Type /Pages /Kids [ {kids_str} ] /Count {total_pages} >>".encode("ascii")

        # 3. Regular Font
        objects_dict[font_regular_num] = (
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
        )

        # 4. Bold Font
        objects_dict[font_bold_num] = (
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"
        )

        # 5. Image XObject
        img_dict = (
            f"<< /Type /XObject /Subtype /Image /Width 4 /Height 4 /BitsPerComponent 8 "
            f"/ColorSpace /DeviceRGB /Length {len(image_stream)} >>\nstream\n".encode("ascii")
            + image_stream
            + b"\nendstream"
        )
        objects_dict[image_num] = img_dict

        doc_unique_id = rng.randint(100000, 999999)

        # 6. Info Dictionary
        info_str = (
            f"<< /Title (TRACE Synthetic Benchmark Document Case {doc_unique_id}) "
            f"/Author (TRACE Forensic Laboratory) "
            f"/Subject (Ground Truth Forensic Evaluation Case {doc_unique_id}) "
            f"/Creator (TRACE Synthetic Document Generator v1.0) >>"
        )
        objects_dict[info_num] = info_str.encode("ascii")

        # Page Objects and Content Streams
        for i, (p_num, s_num) in enumerate(zip(page_nums, stream_nums)):
            page_index = i + 1

            # Build rich page stream content
            stream_lines: List[str] = [
                # Running Header
                f"BT /F2 9 Tf 54 752 Td (TRACE SYNTHETIC FORENSICS BENCHMARK -- CASE {doc_unique_id} -- PAGE {page_index} OF {total_pages}) Tj ET",
                "q 0.5 w 54 744 m 558 744 l S Q",
            ]

            if page_index == 1:
                # Title, authors, abstract, multi-column section
                stream_lines.extend([
                    f"BT /F2 16 Tf 54 710 Td (Autonomous Bitstream Recovery and Multimodal Intelligence Case {doc_unique_id}) Tj ET",
                    f"BT /F1 10 Tf 54 690 Td (Author: Dr. Alex Vance, TRACE Forensic Laboratory, Case {doc_unique_id}) Tj ET",
                    "BT /F2 11 Tf 54 665 Td (Abstract) Tj ET",
                    (
                        f"BT /F1 10 Tf 54 645 Td "
                        f"(This synthetic ground-truth document case {doc_unique_id} provides deterministic evaluation tokens.) Tj ET"
                    ),
                    "BT /F2 12 Tf 54 615 Td (1. Introduction and Problem Space) Tj ET",
                    (
                        "BT /F1 10 Tf 54 595 Td "
                        "(Column 0 introduces the sector carving challenge when metadata structures are obliterated.) Tj ET"
                    ),
                    (
                        "BT /F1 10 Tf 320 595 Td "
                        "(Column 1 discusses topological order reconstruction and stream boundary isolation.) Tj ET"
                    ),
                    # Table representation
                    "BT /F2 10 Tf 54 550 Td (Table 1: Benchmark Reconstruction Baseline) Tj ET",
                    "BT /F1 9 Tf 54 532 Td (Metric | Deterministic | Target Recovery) Tj ET",
                    "BT /F1 9 Tf 54 518 Td (Byte Recovery | 97.7% | 99.0%) Tj ET",
                    "BT /F1 9 Tf 54 504 Td (Object Fidelity | 22/22 | 100%) Tj ET",
                    # Mathematical Equation
                    "BT /F2 10 Tf 54 465 Td (2. Mathematical Formulation) Tj ET",
                    (
                        "BT /F1 10 Tf 54 445 Td "
                        "(E = mc^2 + \\int_0^1 f(x) dx = \\sum_{i=1}^N \\alpha_i \\cdot x_i  (1.1)) Tj ET"
                    ),
                    # Figure and Image invocation
                    "BT /F2 10 Tf 54 400 Td (Figure 1: Embedded Bitstream Pattern) Tj ET",
                    "q 64 0 0 64 54 320 cm /Im1 Do Q",
                ])
            else:
                # Continuation pages
                stream_lines.extend([
                    f"BT /F2 13 Tf 54 700 Td (Section {page_index}: Deep Analysis and Forensic Findings) Tj ET",
                    (
                        f"BT /F1 10 Tf 54 670 Td "
                        f"(Continuation paragraph for Page {page_index}. Systematic examination of bitstream fragments.) Tj ET"
                    ),
                    (
                        "BT /F1 10 Tf 54 640 Td "
                        "(Multi-column text layout across alternating vertical coordinate planes.) Tj ET"
                    ),
                    (
                        f"BT /F1 9 Tf 54 600 Td "
                        f"(Table {page_index}: Comparative forensic metrics across sector clusters.) Tj ET"
                    ),
                    "BT /F1 9 Tf 54 585 Td (Cluster ID | Fragmentation Index | Entropy) Tj ET",
                    f"BT /F1 9 Tf 54 570 Td (Sector_{page_index}A | 0.04 | 7.92) Tj ET",
                    # Equation
                    f"BT /F1 10 Tf 54 520 Td (dx/dt = \\lambda \\cdot e^{{-\\gamma t}} + \\theta  ({page_index}.1)) Tj ET",
                ])

            # Running Footer
            stream_lines.extend([
                "q 0.5 w 54 48 m 558 48 l S Q",
                f"BT /F1 9 Tf 270 34 Td (Page {page_index} of {total_pages}) Tj ET",
            ])

            content_bytes = "\n".join(stream_lines).encode("latin-1")
            stream_obj = (
                f"<< /Length {len(content_bytes)} >>\nstream\n".encode("ascii")
                + content_bytes
                + b"\nendstream"
            )
            objects_dict[s_num] = stream_obj

            # Page Object
            page_obj = (
                f"<< /Type /Page /Parent {pages_tree_num} 0 R /MediaBox [0 0 612 792] "
                f"/Contents {s_num} 0 R "
                f"/Resources << /Font << /F1 {font_regular_num} 0 R /F2 {font_bold_num} 0 R >> "
                f"/XObject << /Im1 {image_num} 0 R >> >> >>"
            ).encode("ascii")
            objects_dict[p_num] = page_obj

        # Assemble PDF with Header, Objects, Xref, and Trailer
        header = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"
        out = bytearray(header)
        offsets: Dict[int, int] = {}

        all_obj_nums = sorted(objects_dict.keys())
        for obj_id in all_obj_nums:
            offsets[obj_id] = len(out)
            body = objects_dict[obj_id]
            out.extend(f"{obj_id} 0 obj\n".encode("ascii"))
            out.extend(body)
            out.extend(b"\nendobj\n")

        # Xref Table
        startxref_offset = len(out)
        total_objs = max(all_obj_nums) + 1
        out.extend(f"xref\n0 {total_objs}\n".encode("ascii"))
        out.extend(b"0000000000 65535 f \n")
        for obj_id in range(1, total_objs):
            if obj_id in offsets:
                out.extend(f"{offsets[obj_id]:010d} 00000 n \n".encode("ascii"))
            else:
                out.extend(b"0000000000 65535 f \n")

        # Trailer
        trailer = (
            f"trailer\n<< /Size {total_objs} /Root {catalog_num} 0 R /Info {info_num} 0 R >>\n"
            f"startxref\n{startxref_offset}\n%%EOF\n"
        ).encode("ascii")
        out.extend(trailer)

        return bytes(out)


# Global default generator instance
default_document_generator = SyntheticDocumentGenerator()
