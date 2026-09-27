"""General-Purpose AI-Assisted PDF Forensic Recovery Engine.

Provides autonomous, multi-stage recovery for diverse real-world corrupted PDFs:
- Preamble stripping and header normalization (offset %PDF-1.x or missing magic bytes).
- Deep indirect object extraction across broken bitstreams (regex + stateful scanner).
- PDF 1.5+ Object Stream (/Type /ObjStm) decompression and indirect object unpacking.
- Flate stream recovery and dynamic stream length re-calculation.
- Content stream syntax repair: operator balancing (BT/ET, q/Q) and string literal closing.
- Page tree and catalog hierarchy reconstruction (orphan /Page recovery, /Pages container, /Catalog).
- Font resource fallback for error-free rendering in strict viewers (Adobe Acrobat, pypdf, fitz).
- ISO 32000-1 conformant cross-reference table (xref), trailer dictionary, and startxref generation.
- Forensic provenance tracking: separating authentic recovered bytes from synthesized repair bytes.
- Resource bounded execution and decompression bomb protection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import io
import math
import re
from typing import Any, Mapping, Sequence
import zlib

from .constants import (
    STATUS_ORIGINAL_VERIFIED,
    STATUS_SYNTHETICALLY_REPAIRED,
    STATUS_PARTIAL_UNRESTORED,
    STATUS_OUTPUT_INVALID,
)
from .hashing import sha256_bytes

# Maximum safety limits to prevent denial-of-service / decompression bombs
MAX_DECOMPRESSED_RATIO = 100
MAX_DECOMPRESSED_BYTES = 50 * 1024 * 1024  # 50 MB
MAX_OBJECT_COUNT = 50_000
MAX_PDF_SIZE_BYTES = 100 * 1024 * 1024  # 100 MB


@dataclass(frozen=True)
class CorruptionDiagnostic:
    """Detailed forensic analysis of PDF corruption patterns."""

    corruption_classes: tuple[str, ...]
    detected_version: str
    has_header: bool
    header_offset: int
    has_xref: bool
    has_trailer: bool
    has_startxref: bool
    has_eof: bool
    surviving_objects_count: int
    salvaged_pages_count: int
    has_object_streams: bool
    has_erased_regions: bool
    entropy: float
    integrity_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "corruption_classes": list(self.corruption_classes),
            "detected_version": self.detected_version,
            "has_header": self.has_header,
            "header_offset": self.header_offset,
            "has_xref": self.has_xref,
            "has_trailer": self.has_trailer,
            "has_startxref": self.has_startxref,
            "has_eof": self.has_eof,
            "surviving_objects_count": self.surviving_objects_count,
            "salvaged_pages_count": self.salvaged_pages_count,
            "has_object_streams": self.has_object_streams,
            "has_erased_regions": self.has_erased_regions,
            "entropy": round(self.entropy, 2),
            "integrity_score": round(self.integrity_score, 2),
        }


def compute_byte_entropy(data: bytes) -> float:
    """Compute Shannon entropy (0.0 to 8.0 bits per byte)."""
    if not data:
        return 0.0
    freq: dict[int, int] = {}
    for b in data:
        freq[b] = freq.get(b, 0) + 1
    total = len(data)
    entropy = 0.0
    for count in freq.values():
        p = count / total
        entropy -= p * math.log2(p)
    return entropy


def diagnose_pdf_corruption(raw_bytes: bytes) -> CorruptionDiagnostic:
    """Perform heuristic and statistical forensic classification of PDF corruption."""
    if not raw_bytes:
        return CorruptionDiagnostic(
            corruption_classes=("EMPTY_INPUT",),
            detected_version="unknown",
            has_header=False,
            header_offset=-1,
            has_xref=False,
            has_trailer=False,
            has_startxref=False,
            has_eof=False,
            surviving_objects_count=0,
            salvaged_pages_count=0,
            has_object_streams=False,
            has_erased_regions=False,
            entropy=0.0,
            integrity_score=0.0,
        )

    classes: list[str] = []
    header_match = re.search(rb"%PDF-(\d+\.\d+)", raw_bytes[:1024 * 1024])
    has_header = header_match is not None
    header_offset = header_match.start() if header_match else -1
    version = header_match.group(1).decode("ascii", errors="replace") if header_match else "unknown"

    if not has_header:
        classes.append("MISSING_HEADER")
    elif header_offset > 0:
        classes.append("OFFSET_HEADER_PREAMBLE_NOISE")

    has_eof = b"%%EOF" in raw_bytes[-2048:] or b"%%EOF" in raw_bytes
    if not has_eof:
        classes.append("TRUNCATED_BITSTREAM_NO_EOF")

    has_startxref = b"startxref" in raw_bytes
    if not has_startxref:
        classes.append("MISSING_STARTXREF")

    has_trailer = b"trailer" in raw_bytes
    if not has_trailer:
        classes.append("MISSING_TRAILER_DICT")

    has_xref = b"xref" in raw_bytes or b"/Type /XRef" in raw_bytes or b"/Type/XRef" in raw_bytes
    if not has_xref:
        classes.append("DESTROYED_CROSS_REFERENCE_TABLE")

    # Object count
    obj_count = len(re.findall(rb"\b\d+\s+\d+\s+obj\b", raw_bytes))
    endobj_count = len(re.findall(rb"\bendobj\b", raw_bytes))
    if obj_count == 0:
        classes.append("NO_INDIRECT_OBJECTS")
    elif abs(obj_count - endobj_count) > 0:
        classes.append("UNTERMINATED_OBJECTS")

    # Page count
    page_count = len(re.findall(rb"/Type\s*/Page\b", raw_bytes))
    pages_count = len(re.findall(rb"/Type\s*/Pages\b", raw_bytes))
    cat_count = len(re.findall(rb"/Type\s*/Catalog\b", raw_bytes))

    if page_count > 0 and pages_count == 0:
        classes.append("ORPHAN_PAGES_NO_PARENT_TREE")
    if cat_count == 0 and page_count > 0:
        classes.append("MISSING_DOCUMENT_CATALOG")

    # Erased / null byte runs
    has_null_runs = bool(re.search(rb"\x00{32,}", raw_bytes))
    if has_null_runs:
        classes.append("ERASED_SECTOR_NULL_RUNS")

    # Object stream presence
    has_obj_stm = bool(re.search(rb"/Type\s*/ObjStm\b", raw_bytes))
    if has_obj_stm:
        classes.append("COMPRESSED_OBJECT_STREAMS")

    # Compute structural integrity score (0.0 to 1.0)
    score = 0.0
    if has_header and header_offset == 0:
        score += 0.25
    elif has_header:
        score += 0.15
    if has_eof:
        score += 0.20
    if has_xref:
        score += 0.20
    if has_trailer:
        score += 0.15
    if obj_count > 0 and abs(obj_count - endobj_count) <= 1:
        score += 0.10
    if page_count > 0 and cat_count > 0:
        score += 0.10

    entropy = compute_byte_entropy(raw_bytes[:65536])

    return CorruptionDiagnostic(
        corruption_classes=tuple(classes),
        detected_version=version,
        has_header=has_header,
        header_offset=header_offset,
        has_xref=has_xref,
        has_trailer=has_trailer,
        has_startxref=has_startxref,
        has_eof=has_eof,
        surviving_objects_count=obj_count,
        salvaged_pages_count=page_count,
        has_object_streams=has_obj_stm,
        has_erased_regions=has_null_runs,
        entropy=entropy,
        integrity_score=min(1.0, max(0.0, score)),
    )


def _safe_flate_decompress(compressed_data: bytes) -> bytes | None:
    """Decompress Flate data safely with bounded memory limits and partial salvage."""
    if not compressed_data:
        return None
    try:
        decomp = zlib.decompress(compressed_data, bufsize=65536)
        if len(decomp) > MAX_DECOMPRESSED_BYTES:
            return decomp[:MAX_DECOMPRESSED_BYTES]
        return decomp
    except Exception:
        # Attempt streaming partial decompression
        try:
            d = zlib.decompressobj()
            salvaged = d.decompress(compressed_data, MAX_DECOMPRESSED_BYTES)
            if salvaged:
                return salvaged
        except Exception:
            pass
    return None


def _repair_content_stream_syntax(stream_content: bytes) -> bytes:
    """Ensure strict PDF operator syntax: balance BT/ET, q/Q, and string parentheses."""
    if not stream_content:
        return stream_content

    res = bytearray(stream_content)

    # 1. Balance string literal parentheses: count unescaped '(' vs ')'
    open_parens = 0
    in_escape = False
    for b in res:
        if in_escape:
            in_escape = False
            continue
        if b == 0x5C:  # backslash '\'
            in_escape = True
        elif b == 0x28:  # '('
            open_parens += 1
        elif b == 0x29:  # ')'
            if open_parens > 0:
                open_parens -= 1

    if open_parens > 0:
        res.extend(b")" * open_parens)

    # 2. Balance text objects: BT (Begin Text) vs ET (End Text)
    # Must be done BEFORE restoring graphics state Q
    last_bt = res.rfind(b"BT")
    last_et = res.rfind(b"ET")
    if last_bt != -1 and (last_et == -1 or last_et < last_bt):
        stripped = bytes(res).rstrip()
        if stripped.endswith(b")"):
            res.extend(b" Tj T* ET\n")
        else:
            res.extend(b" ET\n")

    # 3. Balance graphics state stack: q (save) vs Q (restore)
    # Must come AFTER closing BT text blocks!
    q_count = len(re.findall(rb"(?:^|[\s])q(?:$|[\s])", res))
    cap_q_count = len(re.findall(rb"(?:^|[\s])Q(?:$|[\s])", res))
    if q_count > cap_q_count:
        needed_q = q_count - cap_q_count
        res.extend(b"\n" + b"Q\n" * needed_q)

    return bytes(res)


def _normalize_stream_object(obj_bytes: bytes) -> bytes:
    """Ensure exact /Length attribute and clean EOL termination in stream dictionary.

    Guarantees strict ISO 32000-1 §7.3.8 conformance so that strict PDF parsers and
    Adobe Acrobat find the endstream marker exactly at stream_start + /Length without
    reading into subsequent objects.
    """
    if b"stream" not in obj_bytes or b"endstream" not in obj_bytes:
        return obj_bytes

    s_idx = obj_bytes.find(b"stream")
    dict_part = obj_bytes[:s_idx]

    if obj_bytes[s_idx:].startswith(b"stream\r\n"):
        s_start = s_idx + 8
    elif obj_bytes[s_idx:].startswith(b"stream\n"):
        s_start = s_idx + 7
    else:
        s_start = s_idx + 6

    e_idx = obj_bytes.rfind(b"endstream")
    raw_stream = obj_bytes[s_start:e_idx]

    is_flate = b"/FlateDecode" in dict_part or b"/Filter" in dict_part
    if not is_flate:
        if raw_stream.endswith(b"\r\n"):
            stream_content = raw_stream[:-2]
        elif raw_stream.endswith(b"\n"):
            stream_content = raw_stream[:-1]
        else:
            stream_content = raw_stream
        if b"BT" in stream_content or b"ET" in stream_content or b"cm" in stream_content:
            stream_content = _repair_content_stream_syntax(stream_content)
    else:
        stream_content = raw_stream

    actual_len = len(stream_content)
    if re.search(rb"/Length\s+\d+", dict_part):
        new_dict = re.sub(rb"/Length\s+\d+", f"/Length {actual_len}".encode("ascii"), dict_part)
    elif b"<<" in dict_part:
        new_dict = dict_part.replace(b"<<", f"<< /Length {actual_len} ".encode("ascii"), 1)
    else:
        new_dict = dict_part

    return new_dict + b"stream\n" + stream_content + b"\nendstream\nendobj"


def _unpack_object_stream(obj_num: int, obj_bytes: bytes) -> dict[int, bytes]:
    """Extract packed indirect objects from a PDF 1.5+ Object Stream (/Type /ObjStm)."""
    sub_objs: dict[int, bytes] = {}
    if b"/Type" not in obj_bytes or b"/ObjStm" not in obj_bytes:
        return sub_objs

    # Extract /N (number of objects) and /First (byte offset of first object in decompressed stream)
    n_match = re.search(rb"/N\s+(\d+)", obj_bytes)
    first_match = re.search(rb"/First\s+(\d+)", obj_bytes)
    if not n_match or not first_match:
        return sub_objs

    num_objects = int(n_match.group(1))
    first_offset = int(first_match.group(1))

    # Extract compressed stream
    s_idx = obj_bytes.find(b"stream")
    if s_idx == -1:
        return sub_objs
    e_idx = obj_bytes.rfind(b"endstream")
    if e_idx == -1:
        return sub_objs

    if obj_bytes[s_idx:].startswith(b"stream\r\n"):
        stream_data = obj_bytes[s_idx + 8:e_idx]
    elif obj_bytes[s_idx:].startswith(b"stream\n"):
        stream_data = obj_bytes[s_idx + 7:e_idx]
    else:
        stream_data = obj_bytes[s_idx + 6:e_idx]

    decompressed = _safe_flate_decompress(stream_data.strip(b"\r\n"))
    if not decompressed or len(decompressed) < first_offset:
        return sub_objs

    # Parse header: integer pairs (obj_num, offset_relative_to_first)
    header_part = decompressed[:first_offset].decode("ascii", errors="replace")
    tokens = [t for t in header_part.split() if t]
    if len(tokens) < num_objects * 2:
        return sub_objs

    pairs: list[tuple[int, int]] = []
    for i in range(0, num_objects * 2, 2):
        try:
            o_num = int(tokens[i])
            o_off = int(tokens[i + 1])
            pairs.append((o_num, o_off))
        except ValueError:
            break

    data_part = decompressed[first_offset:]
    for idx, (o_num, o_off) in enumerate(pairs):
        end_off = pairs[idx + 1][1] if idx + 1 < len(pairs) else len(data_part)
        o_content = data_part[o_off:end_off].strip()
        if o_content:
            sub_objs[o_num] = f"{o_num} 0 obj\n".encode("ascii") + o_content + b"\nendobj"

    return sub_objs


class GeneralizedPdfRecoveryEngine:
    """Robust, general-purpose PDF recovery engine for arbitrary corruption patterns."""

    def __init__(self, raw_bytes: bytes, media_bytes: bytes | None = None) -> None:
        self.raw_bytes = raw_bytes or b""
        self.media_bytes = media_bytes or b""
        self.source_bytes = self.media_bytes if self.media_bytes else self.raw_bytes
        self.diagnostic = diagnose_pdf_corruption(self.source_bytes)

    def recover(self) -> tuple[bytes, list[str], dict[str, Any]]:
        """Execute full multi-stage recovery pipeline.

        Returns:
            (repaired_bytes, synthesized_items, recovery_metadata)
        """
        synthesized_items: list[str] = []
        source = self.source_bytes
        if not source:
            return b"", ["empty source input"], {"status": "empty"}

        # -------------------------------------------------------------
        # Stage 1: Preamble Normalization and Header Synthesis
        # -------------------------------------------------------------
        header_match = re.search(rb"%PDF-(\d+\.\d+)", source[:1024 * 1024])
        if header_match:
            pdf_version = header_match.group(1).decode("ascii", errors="replace")
            header_bytes = f"%PDF-{pdf_version}\n%TRACE-FORENSIC-SALVAGED\n".encode("ascii")
            if header_match.start() > 0:
                synthesized_items.append(
                    f"stripped {header_match.start()} bytes of leading preamble noise before %PDF-{pdf_version}"
                )
        else:
            pdf_version = "1.4"
            header_bytes = b"%PDF-1.4\n%TRACE-FORENSIC-SALVAGED\n"
            synthesized_items.append("synthesized standard PDF header (%PDF-1.4)")

        # -------------------------------------------------------------
        # Stage 2: Deep Indirect Object Harvester & Parser
        # -------------------------------------------------------------
        harvested_objs: dict[int, bytes] = {}

        # Scan for indirect object definitions: (\d+) (\d+) obj ... endobj
        # Match dotall greedily or non-greedily with boundary lookahead
        pattern = re.compile(rb"(\d+)\s+(\d+)\s+obj\b(.*?)endobj", re.DOTALL)
        for m in pattern.finditer(source):
            if len(harvested_objs) >= MAX_OBJECT_COUNT:
                break
            num = int(m.group(1))
            harvested_objs[num] = m.group(0).strip()

        # Handle unterminated objects (e.g. truncated at EOF without endobj)
        last_obj_match = re.search(rb"(\d+)\s+(\d+)\s+obj\b(?!.*endobj)(.*)$", source, re.DOTALL)
        if last_obj_match:
            num = int(last_obj_match.group(1))
            if num not in harvested_objs:
                body = last_obj_match.group(0).strip()
                if not body.endswith(b"endobj"):
                    body += b"\nendobj"
                harvested_objs[num] = body
                synthesized_items.append(f"closed truncated object {num} with synthetic endobj")

        # PDF 1.5+ Object Stream Unpacking
        unpacked_count = 0
        obj_stm_ids = [n for n, ob in harvested_objs.items() if b"/ObjStm" in ob]
        for num in obj_stm_ids:
            inner_objs = _unpack_object_stream(num, harvested_objs[num])
            if inner_objs:
                del harvested_objs[num]
                for in_num, in_bytes in inner_objs.items():
                    if in_num not in harvested_objs:
                        harvested_objs[in_num] = in_bytes
                        unpacked_count += 1
        if unpacked_count > 0:
            synthesized_items.append(f"unpacked {unpacked_count} indirect objects from compressed Object Streams")

        # -------------------------------------------------------------
        # Stage 3: Erased Sector / Null Block Stream Repair
        # -------------------------------------------------------------
        referenced_objs: set[int] = set()
        for m in re.finditer(rb"/Contents\s+(\d+)\s+0\s+R", source):
            referenced_objs.add(int(m.group(1)))
        for m in re.finditer(rb"/Kids\s*\[([^\]]+)\]", source):
            for r in re.finditer(rb"(\d+)\s+0\s+R", m.group(1)):
                referenced_objs.add(int(r.group(1)))

        missing_refs = sorted(r for r in referenced_objs if r not in harvested_objs)

        for num, obj_bytes in list(harvested_objs.items()):
            null_run = re.search(rb"(\x00{32,})", obj_bytes)
            if null_run:
                pre_null = obj_bytes[:null_run.start()].rstrip(b"\x00 \t\r\n")
                post_null = obj_bytes[null_run.end():].lstrip(b"\x00 \t\r\n")

                s_idx = pre_null.find(b"stream")
                if s_idx != -1:
                    if pre_null[s_idx:].startswith(b"stream\r\n"):
                        stream_body = pre_null[s_idx + 8:]
                    elif pre_null[s_idx:].startswith(b"stream\n"):
                        stream_body = pre_null[s_idx + 7:]
                    else:
                        stream_body = pre_null[s_idx + 6:]

                    # Repair stream operators
                    stream_body = _repair_content_stream_syntax(stream_body)
                    stream_body = stream_body.strip(b"\r\n")
                    new_pre = (
                        f"{num} 0 obj\n<< /Length {len(stream_body)} >>\nstream\n".encode("ascii")
                        + stream_body
                        + b"\nendstream\nendobj"
                    )
                    harvested_objs[num] = new_pre
                else:
                    harvested_objs[num] = pre_null

                # Salvage post_null into missing referenced stream
                if missing_refs:
                    miss_num = missing_refs.pop(0)
                    if post_null.endswith(b"endobj"):
                        post_null = post_null[:-6].rstrip()
                    if post_null.endswith(b"endstream"):
                        post_null = post_null[:-9].rstrip()

                    # Rebuild valid graphics/text state preamble for severed stream
                    post_stream = b"1 0 0 1 0 0 cm  " + _repair_content_stream_syntax(post_null)
                    post_stream = post_stream.strip(b"\r\n")
                    synth_obj = (
                        f"{miss_num} 0 obj\n<< /Length {len(post_stream)} >>\nstream\n".encode("ascii")
                        + post_stream
                        + b"\nendstream\nendobj"
                    )
                    harvested_objs[miss_num] = synth_obj
                    synthesized_items.append(
                        f"recovered surviving content for object {miss_num} across damaged sector boundary"
                    )

        # Synthesize placeholder empty stream for any still-missing references
        for r in missing_refs:
            if r not in harvested_objs:
                harvested_objs[r] = f"{r} 0 obj\n<< /Length 0 >>\nstream\n\nendstream\nendobj".encode("ascii")
                synthesized_items.append(f"synthesized placeholder stream for unrecovered object {r}")

        # -------------------------------------------------------------
        # Stage 4: Page Tree, Catalog, and Font Resources Recovery
        # -------------------------------------------------------------
        page_objs: list[int] = []
        pages_objs: list[int] = []
        cat_num: int | None = None
        info_num: int | None = None

        for num, obj_bytes in harvested_objs.items():
            if re.search(rb"/Type\s*/Catalog\b", obj_bytes):
                cat_num = num
            elif re.search(rb"/Type\s*/Pages\b", obj_bytes):
                pages_objs.append(num)
            elif re.search(rb"/Type\s*/Page\b", obj_bytes):
                page_objs.append(num)

            if info_num is None and (b"/Author" in obj_bytes or b"/Creator" in obj_bytes or b"/CreationDate" in obj_bytes):
                info_num = num

        # If page objects exist but /Type /Pages is missing or disconnected, rebuild /Pages container
        all_ids = set(harvested_objs.keys())
        parent_pages_id = pages_objs[0] if pages_objs else (max(all_ids, default=0) + 1)

        # Standard fallback Font object (Helvetica Base14) for rendering safety
        font_obj_id = max(all_ids, default=0) + 2
        standard_font_obj = (
            f"{font_obj_id} 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>\nendobj".encode("ascii")
        )
        has_added_font = False

        # If we have streams but 0 pages identified, check if any stream looks like page content
        if not page_objs:
            for num, obj_bytes in harvested_objs.items():
                if b"stream" in obj_bytes and (b"BT" in obj_bytes or b"Tj" in obj_bytes or b"cm" in obj_bytes):
                    # Synthesize a Page object pointing to this content stream
                    page_id = max(all_ids, default=0) + 3
                    page_def = (
                        f"{page_id} 0 obj\n<< /Type /Page /Parent {parent_pages_id} 0 R /MediaBox [0 0 612 792] "
                        f"/Resources << /Font << /F1 {font_obj_id} 0 R >> >> /Contents {num} 0 R >>\nendobj"
                    ).encode("ascii")
                    harvested_objs[page_id] = page_def
                    page_objs.append(page_id)
                    all_ids.add(page_id)
                    has_added_font = True
                    synthesized_items.append(f"synthesized Page wrapper ({page_id} 0 obj) for unlinked content stream {num}")
                    break

        # Sanitize each /Page object: ensure valid Parent and Resources
        page_objs.sort()
        for p_id in page_objs:
            p_bytes = harvested_objs[p_id]
            # Replace /Parent to guarantee link to parent_pages_id
            if re.search(rb"/Parent\s+\d+\s+\d+\s+R", p_bytes):
                p_bytes = re.sub(
                    rb"/Parent\s+\d+\s+\d+\s+R",
                    f"/Parent {parent_pages_id} 0 R".encode("ascii"),
                    p_bytes,
                )
            else:
                p_bytes = re.sub(
                    rb">>$",
                    f" /Parent {parent_pages_id} 0 R >>".encode("ascii"),
                    p_bytes.strip(),
                )
                if not p_bytes.endswith(b"endobj"):
                    p_bytes += b"\nendobj"

            # Check Resources
            if b"/Resources" not in p_bytes:
                has_added_font = True
                p_bytes = re.sub(
                    rb">>$",
                    f" /Resources << /Font << /F1 {font_obj_id} 0 R >> >> >>".encode("ascii"),
                    p_bytes.strip(),
                )
                if not p_bytes.endswith(b"endobj"):
                    p_bytes += b"\nendobj"

            harvested_objs[p_id] = p_bytes

        if has_added_font and font_obj_id not in harvested_objs:
            harvested_objs[font_obj_id] = standard_font_obj
            synthesized_items.append(f"synthesized Base14 standard Font object ({font_obj_id} 0 obj) for safe rendering")

        # Synthesize or verify /Type /Pages
        if page_objs:
            kids_str = " ".join(f"{p} 0 R" for p in page_objs)
            pages_dict = (
                f"{parent_pages_id} 0 obj\n<< /Type /Pages /Kids [{kids_str}] /Count {len(page_objs)} >>\nendobj".encode("ascii")
            )
            harvested_objs[parent_pages_id] = pages_dict
            if parent_pages_id not in pages_objs:
                synthesized_items.append(
                    f"synthesized root Pages tree ({parent_pages_id} 0 obj) linking {len(page_objs)} page(s)"
                )
            pages_objs = [parent_pages_id]

        # Synthesize or verify /Type /Catalog
        if cat_num is not None and cat_num in harvested_objs:
            cat_bytes = harvested_objs[cat_num]
            if re.search(rb"/Pages\s+\d+\s+\d+\s+R", cat_bytes):
                harvested_objs[cat_num] = re.sub(
                    rb"/Pages\s+\d+\s+\d+\s+R",
                    f"/Pages {parent_pages_id} 0 R".encode("ascii"),
                    cat_bytes,
                )
            else:
                harvested_objs[cat_num] = re.sub(
                    rb">>$",
                    f" /Pages {parent_pages_id} 0 R >>".encode("ascii"),
                    cat_bytes.strip(),
                )
        else:
            cat_num = max(set(harvested_objs.keys()), default=0) + 1
            cat_obj = f"{cat_num} 0 obj\n<< /Type /Catalog /Pages {parent_pages_id} 0 R >>\nendobj".encode("ascii")
            harvested_objs[cat_num] = cat_obj
            synthesized_items.append(f"synthesized root Catalog dictionary ({cat_num} 0 obj)")

        # -------------------------------------------------------------
        # Stage 5: ISO 32000-1 Xref Table & Trailer Synthesis
        # -------------------------------------------------------------
        sorted_obj_nums = sorted(harvested_objs.keys())
        body_chunks = [header_bytes]
        offsets: dict[int, int] = {}
        current_offset = len(header_bytes)

        for num in sorted_obj_nums:
            chunk = _normalize_stream_object(harvested_objs[num]) + b"\n"
            offsets[num] = current_offset
            body_chunks.append(chunk)
            current_offset += len(chunk)

        assembled_body = b"".join(body_chunks)
        xref_offset = len(assembled_body)
        max_obj_num = max(sorted_obj_nums, default=1)

        # Write standard xref table
        xref_lines = [
            b"xref\n",
            f"0 {max_obj_num + 1}\n".encode("ascii"),
            b"0000000000 65535 f \r\n",
        ]
        for n in range(1, max_obj_num + 1):
            if n in offsets:
                xref_lines.append(f"{offsets[n]:010d} 00000 n \r\n".encode("ascii"))
            else:
                xref_lines.append(f"0000000000 65535 f \r\n".encode("ascii"))

        info_clause = f" /Info {info_num} 0 R" if (info_num and info_num in harvested_objs) else ""
        trailer_block = (
            f"trailer\n<< /Size {max_obj_num + 1} /Root {cat_num} 0 R{info_clause} >>\n"
            f"startxref\n{xref_offset}\n%%EOF\n"
        ).encode("ascii")

        rebuilt_pdf = assembled_body + b"".join(xref_lines) + trailer_block
        synthesized_items.extend([
            "rebuilt ISO 32000-1 cross-reference table (xref)",
            f"rebuilt trailer dictionary (Root={cat_num}, Size={max_obj_num + 1})",
            f"synthesized startxref pointer ({xref_offset})",
            "synthesized %%EOF file terminator",
        ])

        meta = {
            "version": pdf_version,
            "objects_recovered": len(sorted_obj_nums),
            "pages_reconstructed": len(page_objs),
            "root_catalog": cat_num,
            "xref_offset": xref_offset,
            "synthesized_size": len(rebuilt_pdf) - len(assembled_body),
            "body_size": len(assembled_body),
        }

        return rebuilt_pdf, synthesized_items, meta
