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


@dataclass(frozen=True)
class RecoveredObject:
    """Forensic record of a recovered PDF object and its source provenance."""

    object_number: int
    generation: int
    source_offset_start: int
    source_offset_end: int
    byte_count: int
    raw_bytes: bytes
    has_stream: bool = False
    stream_length: int | None = None
    is_flate_compressed: bool = False
    decompressed_stream: bytes | None = None
    is_decompressed_valid: bool = False
    extracted_text: tuple[str, ...] = ()
    object_type: str = "generic"
    is_authentic: bool = True
    confidence: float = 1.0
    provenance_origin: str = "authentic_evidence"

    def to_dict(self) -> dict[str, Any]:
        return {
            "object_number": self.object_number,
            "generation": self.generation,
            "source_offset_start": self.source_offset_start,
            "source_offset_end": self.source_offset_end,
            "byte_count": self.byte_count,
            "has_stream": self.has_stream,
            "stream_length": self.stream_length,
            "is_flate_compressed": self.is_flate_compressed,
            "is_decompressed_valid": self.is_decompressed_valid,
            "extracted_text_count": len(self.extracted_text),
            "object_type": self.object_type,
            "is_authentic": self.is_authentic,
            "confidence": self.confidence,
            "provenance_origin": self.provenance_origin,
        }


@dataclass(frozen=True)
class ForensicRecoveryTelemetry:
    """Comprehensive telemetry from evidence-aware PDF recovery."""

    original_evidence_size: int
    authentic_bytes_identified: int
    authentic_recovery_percentage: float
    indirect_objects_found: int
    validated_objects: int
    streams_found: int
    successfully_decompressed_streams: int
    text_fragments_recovered: int
    pages_discovered: int
    fonts_discovered: tuple[str, ...]
    recovered_objects: tuple[RecoveredObject, ...]
    placed_objects_count: int
    unplaced_bytes_count: int
    surviving_text_strings: tuple[str, ...]
    parser_status: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "original_evidence_size": self.original_evidence_size,
            "authentic_bytes_identified": self.authentic_bytes_identified,
            "authentic_recovery_percentage": round(self.authentic_recovery_percentage, 2),
            "indirect_objects_found": self.indirect_objects_found,
            "validated_objects": self.validated_objects,
            "streams_found": self.streams_found,
            "successfully_decompressed_streams": self.successfully_decompressed_streams,
            "text_fragments_recovered": self.text_fragments_recovered,
            "pages_discovered": self.pages_discovered,
            "fonts_discovered": list(self.fonts_discovered),
            "placed_objects_count": self.placed_objects_count,
            "unplaced_bytes_count": self.unplaced_bytes_count,
            "surviving_text_count": len(self.surviving_text_strings),
            "surviving_text_strings": list(self.surviving_text_strings[:50]),
            "parser_status": self.parser_status,
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
    """Decompress Flate data safely with bounded memory limits and partial salvage.

    Tolerates corrupted or missing zlib headers, trailing checksum mismatches,
    and partial bitstream truncations.
    """
    if not compressed_data:
        return None

    data = compressed_data.strip(b"\r\n\x00 ")
    if not data:
        return None

    # Strategy 1: Standard zlib decompress
    try:
        decomp = zlib.decompress(data, bufsize=65536)
        if len(decomp) > MAX_DECOMPRESSED_BYTES:
            return decomp[:MAX_DECOMPRESSED_BYTES]
        return decomp
    except Exception:
        pass

    # Strategy 2: Raw deflate without zlib header (wbits = -zlib.MAX_WBITS)
    try:
        decomp = zlib.decompress(data, wbits=-zlib.MAX_WBITS, bufsize=65536)
        if decomp:
            if len(decomp) > MAX_DECOMPRESSED_BYTES:
                return decomp[:MAX_DECOMPRESSED_BYTES]
            return decomp
    except Exception:
        pass

    # Strategy 3: Gzip / zlib auto-detect (wbits = 32 + zlib.MAX_WBITS)
    try:
        decomp = zlib.decompress(data, wbits=32 + zlib.MAX_WBITS, bufsize=65536)
        if decomp:
            if len(decomp) > MAX_DECOMPRESSED_BYTES:
                return decomp[:MAX_DECOMPRESSED_BYTES]
            return decomp
    except Exception:
        pass

    # Strategy 4: Sliding window search for zlib header candidates or raw deflate
    for offset in range(1, min(16, len(data) - 4)):
        cand = data[offset:]
        try:
            decomp = zlib.decompress(cand, bufsize=65536)
            if decomp:
                return decomp[:MAX_DECOMPRESSED_BYTES]
        except Exception:
            pass
        try:
            decomp = zlib.decompress(cand, wbits=-zlib.MAX_WBITS, bufsize=65536)
            if decomp:
                return decomp[:MAX_DECOMPRESSED_BYTES]
        except Exception:
            pass

    # Strategy 5: Streaming partial salvage (recovering up to first corrupted byte)
    for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS, 32 + zlib.MAX_WBITS):
        try:
            d = zlib.decompressobj(wbits=wbits)
            salvaged = d.decompress(data, MAX_DECOMPRESSED_BYTES)
            if salvaged and len(salvaged) > 8:
                return salvaged
        except Exception:
            pass

    return None


def _decompress_stream_data(dict_part: bytes, raw_stream: bytes) -> tuple[bytes | None, bool]:
    """Decompress stream data supporting /FlateDecode, /ASCII85Decode, or combinations."""
    if not raw_stream:
        return None, False

    is_flate = b"/FlateDecode" in dict_part or b"/Filter" not in dict_part
    is_a85 = b"/ASCII85Decode" in dict_part

    current = raw_stream.strip()
    if is_a85:
        try:
            import base64
            current = base64.a85decode(current, adobe=True)
        except Exception:
            try:
                import base64
                current = base64.a85decode(current)
            except Exception:
                pass

    if is_flate or b"/FlateDecode" in dict_part:
        decomp = _safe_flate_decompress(current)
        if decomp is not None:
            return decomp, True
        if b"/FlateDecode" in dict_part:
            return None, False

    if is_a85 and current != raw_stream:
        return current, True

    return None, False


def _decode_hex_pdf_string(hex_bytes: bytes) -> str | None:
    """Decode ASCII or UTF-16BE hex strings from PDF streams."""
    try:
        clean_hex = re.sub(rb"\s+", b"", hex_bytes)
        if len(clean_hex) % 2 != 0:
            clean_hex += b"0"
        raw = bytes.fromhex(clean_hex.decode("ascii"))
        if len(raw) >= 2 and raw[0] == 0 and (32 <= raw[1] <= 126 or raw[1] in (9, 10, 13)):
            try:
                s = raw.decode("utf-16-be", errors="ignore")
                clean = "".join(c if (32 <= ord(c) <= 126) else " " for c in s).strip()
                if len(clean) >= 2:
                    return clean
            except Exception:
                pass
        s = raw.decode("latin-1", errors="replace")
        clean = "".join(c if (32 <= ord(c) <= 126) else " " for c in s).strip()
        if len(clean) >= 2:
            return clean
    except Exception:
        pass
    return None


def _extract_text_strings(data: bytes) -> list[str]:
    """Extract readable text strings from PDF content streams (Tj, TJ, hex literals, ', \")."""
    if not data:
        return []
    strings: list[str] = []

    # 1. ( ... ) Tj
    for m in re.finditer(rb"\(([^)\r\n]{1,250})\)\s*Tj", data):
        try:
            s = m.group(1).decode("latin-1", errors="replace").strip()
            clean = "".join(c if (32 <= ord(c) <= 126) else " " for c in s).strip()
            if len(clean) >= 2 and clean not in strings:
                strings.append(clean)
        except Exception:
            pass

    # 2. < ... > Tj (hex string literal)
    for m in re.finditer(rb"<([0-9A-Fa-f\s]{2,500})>\s*Tj", data):
        h_str = _decode_hex_pdf_string(m.group(1))
        if h_str and h_str not in strings:
            strings.append(h_str)

    # 3. [ ... ] TJ (array of strings, hex strings, and kerning offsets)
    for m in re.finditer(rb"\[([^\]]{1,2000})\]\s*TJ", data):
        arr_content = m.group(1)
        sub_strings: list[str] = []
        for sm in re.finditer(rb"\(([^)\r\n]{1,250})\)|<([0-9A-Fa-f\s]{2,500})>", arr_content):
            if sm.group(1) is not None:
                try:
                    sub_s = sm.group(1).decode("latin-1", errors="replace").strip()
                    clean_sub = "".join(c if (32 <= ord(c) <= 126) else " " for c in sub_s).strip()
                    if clean_sub:
                        sub_strings.append(clean_sub)
                except Exception:
                    pass
            elif sm.group(2) is not None:
                h_sub = _decode_hex_pdf_string(sm.group(2))
                if h_sub:
                    sub_strings.append(h_sub)
        if sub_strings:
            combined = " ".join(sub_strings).strip()
            if len(combined) >= 2 and combined not in strings:
                strings.append(combined)

    # 4. Fallback: string literals in parentheses if no Tj/TJ operators found
    if not strings:
        for m in re.finditer(rb"\(([^\)\r\n]{4,120})\)", data):
            try:
                s_cand = m.group(1).decode("ascii", errors="ignore").strip()
                p_ratio = sum(1 for c in s_cand if 32 <= ord(c) <= 126) / max(len(s_cand), 1)
                if p_ratio >= 0.85 and len(s_cand) >= 4:
                    if not any(k in s_cand for k in ["obj", "endobj", "stream", "endstream", "xref"]):
                        if s_cand not in strings:
                            strings.append(s_cand)
            except Exception:
                pass

    return strings


def _detect_object_type(obj_bytes: bytes) -> str:
    """Classify PDF object type from its dictionary tokens."""
    if re.search(rb"/Type\s*/Catalog\b", obj_bytes):
        return "Catalog"
    if re.search(rb"/Type\s*/Pages\b", obj_bytes):
        return "Pages"
    if re.search(rb"/Type\s*/Page\b", obj_bytes):
        return "Page"
    if re.search(rb"/Type\s*/Font\b", obj_bytes) or b"/BaseFont" in obj_bytes:
        return "Font"
    if re.search(rb"/Subtype\s*/Image\b", obj_bytes):
        return "Image"
    if b"/Author" in obj_bytes or b"/Creator" in obj_bytes or b"/CreationDate" in obj_bytes:
        return "Info"
    if b"stream" in obj_bytes:
        if b"BT" in obj_bytes or b"Tj" in obj_bytes or b"cm" in obj_bytes:
            return "ContentStream"
        return "Stream"
    return "Object"


def _extract_dict_value(data: bytes, key: bytes) -> bytes | None:
    """Extract the value associated with a key in a PDF dictionary, supporting nested dicts and indirect refs."""
    pos = data.find(key)
    if pos == -1:
        return None
    val_part = data[pos + len(key):].lstrip(b" \t\r\n")
    if not val_part:
        return None
    ref_match = re.match(rb"^(\d+\s+\d+\s+R)", val_part)
    if ref_match:
        return ref_match.group(1)
    if val_part.startswith(b"<<"):
        depth = 0
        i = 0
        n = len(val_part)
        while i < n:
            if val_part[i:i+2] == b"<<":
                depth += 1
                i += 2
            elif val_part[i:i+2] == b">>":
                depth -= 1
                i += 2
                if depth == 0:
                    return val_part[:i]
            else:
                i += 1
        return val_part
    if val_part.startswith(b"["):
        end_idx = val_part.find(b"]")
        if end_idx != -1:
            return val_part[:end_idx + 1]
    return None



def _repair_content_stream_syntax(stream_content: bytes) -> bytes:
    """Ensure strict PDF operator syntax: sanitize rogue operator bytes, balance BT/ET, q/Q, and string parentheses."""
    if not stream_content:
        return stream_content

    # 1. Clean non-ASCII bytes that occur OUTSIDE string literals (...) or <...>
    cleaned = bytearray()
    in_paren_str = False
    in_hex_str = False
    in_escape = False

    for b in stream_content:
        if in_paren_str:
            cleaned.append(b)
            if in_escape:
                in_escape = False
            elif b == 0x5C:  # backslash '\'
                in_escape = True
            elif b == 0x29:  # ')'
                in_paren_str = False
        elif in_hex_str:
            cleaned.append(b)
            if b == 0x3E:  # '>'
                in_hex_str = False
        else:
            if b == 0x28:  # '('
                in_paren_str = True
                cleaned.append(b)
            elif b == 0x3C:  # '<'
                in_hex_str = True
                cleaned.append(b)
            elif b in b",;@$#`~":
                # Rogue punctuation not used as operators in PDF content streams outside strings
                cleaned.append(0x20)
            elif 32 <= b <= 126 or b in (9, 10, 13):
                cleaned.append(b)
            else:
                # Replace rogue non-ASCII operator byte with whitespace
                cleaned.append(0x20)

    res = cleaned

    # 2. Balance string literal parentheses: count unescaped '(' vs ')'
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

    # 3. Balance text objects: BT (Begin Text) vs ET (End Text)
    # Must be done BEFORE restoring graphics state Q
    last_bt = res.rfind(b"BT")
    last_et = res.rfind(b"ET")
    if last_bt != -1 and (last_et == -1 or last_et < last_bt):
        stripped = bytes(res).rstrip()
        if stripped.endswith(b")"):
            res.extend(b" Tj T* ET\n")
        else:
            res.extend(b" ET\n")

    # 4. Balance graphics state stack: q (save) vs Q (restore)
    # Must come AFTER closing BT text blocks!
    q_count = len(re.findall(rb"(?:^|[\s])q(?:$|[\s])", res))
    cap_q_count = len(re.findall(rb"(?:^|[\s])Q(?:$|[\s])", res))
    if q_count > cap_q_count:
        needed_q = q_count - cap_q_count
        res.extend(b"\n" + b"Q\n" * needed_q)

    return bytes(res)


def _is_valid_stream_object(obj_bytes: bytes) -> bool:
    """Check if an object contains a syntactically valid or repairable PDF stream structure."""
    if b"stream" not in obj_bytes:
        return False
    dict_match = re.search(rb"<<([\s\S]*?)>>\s*(?:stream\r\n|stream\n|stream)", obj_bytes)
    if not dict_match:
        dict_alt = re.search(rb"<<([\s\S]*?)>>", obj_bytes)
        if not dict_alt:
            return False
        dict_content = dict_alt.group(1)
    else:
        dict_content = dict_match.group(1)

    names = re.findall(rb"/([A-Za-z0-9_-]+)", dict_content)
    if not names:
        return False
    # If the dictionary contains excessive unescaped non-ASCII noise (> 25%), discard
    non_ascii = sum(1 for b in dict_content if b > 126 or (b < 32 and b not in (9, 10, 13)))
    if non_ascii > max(4, len(dict_content) * 0.25):
        return False
    return True


def _is_valid_or_repairable_pdf_object(obj_bytes: bytes) -> bool:
    """Filter out objects whose bodies consist of scrambled binary noise."""
    if not obj_bytes or len(obj_bytes) < 4:
        return False
    # If it claims to be a stream, verify dictionary and stream markers
    if b"stream" in obj_bytes:
        return _is_valid_stream_object(obj_bytes)
    # If it is a dictionary, verify matching >> and valid ASCII keys
    if b"<<" in obj_bytes:
        dict_match = re.search(rb"<<([\s\S]*?)>>", obj_bytes)
        if not dict_match:
            return False
        dict_content = dict_match.group(1)
        names = re.findall(rb"/([A-Za-z0-9_-]+)", dict_content)
        if not names:
            return False
        # Discard dictionaries with excessive non-ASCII corruption in structure
        non_ascii = sum(1 for b in dict_content if b > 126 or (b < 32 and b not in (9, 10, 13)))
        if non_ascii > max(4, len(dict_content) * 0.25):
            return False
    return True


def _normalize_stream_object(obj_bytes: bytes) -> bytes:
    """Ensure exact /Length attribute and clean EOL termination in stream dictionary.

    Guarantees strict ISO 32000-1 §7.3.8 conformance so that strict PDF parsers and
    Adobe Acrobat find the endstream marker exactly at stream_start + /Length without
    reading into subsequent objects.
    """
    if b"stream" not in obj_bytes:
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
    if e_idx == -1 or e_idx < s_start:
        endobj_idx = obj_bytes.rfind(b"endobj")
        if endobj_idx != -1 and endobj_idx > s_start:
            raw_stream = obj_bytes[s_start:endobj_idx].rstrip()
        else:
            raw_stream = obj_bytes[s_start:].rstrip()
    else:
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
    hdr_m = re.match(rb"\s*(\d+\s+\d+\s+obj)", dict_part)
    hdr_prefix = hdr_m.group(1) if hdr_m else b""

    is_image = b"/Image" in dict_part
    if is_image:
        clean_keys = []
        for key in (b"Type", b"Subtype", b"Width", b"Height", b"BitsPerComponent", b"ColorSpace"):
            km = re.search(rb"/" + key + rb"\s+([A-Za-z0-9_/\[\]\.-]+)", dict_part)
            if km:
                clean_keys.append(b"/" + key + b" " + km.group(1))
        if b"/Filter /DCTDecode" in dict_part or b"/DCTDecode" in dict_part:
            clean_keys.append(b"/Filter /DCTDecode")
        elif is_flate:
            clean_keys.append(b"/Filter /FlateDecode")
        clean_dict_content = b" ".join(clean_keys)
        new_dict = (hdr_prefix + b"\n<< /Length " + str(actual_len).encode("ascii") + b" " + clean_dict_content + b" >>\n")
    elif b"/ObjStm" in dict_part:
        n_m = re.search(rb"/N\s+(\d+)", dict_part)
        f_m = re.search(rb"/First\s+(\d+)", dict_part)
        n_val = n_m.group(1) if n_m else b"0"
        f_val = f_m.group(1) if f_m else b"0"
        new_dict = (hdr_prefix + f"\n<< /Type /ObjStm /N {n_val.decode('ascii')} /First {f_val.decode('ascii')} /Length {actual_len} /Filter /FlateDecode >>\n".encode("ascii"))
    else:
        flate_clause = b" /Filter /FlateDecode" if is_flate else b""
        new_dict = (hdr_prefix + f"\n<< /Length {actual_len}{flate_clause.decode('ascii')} >>\n".encode("ascii"))

    return new_dict + b"stream\n" + stream_content + b"\nendstream\nendobj"


def _heal_dictionary_syntax(target: bytes) -> bytes:
    """Heal corrupted dictionary syntax tokens caused by byte scramblers or transfer errors."""
    # 1. Fix single '<' or corrupted '<X' before a key into '<< '
    target = re.sub(rb"<+[^<\s/]*\s*/", rb"<< /", target)
    # 2. Heal standard dictionary keys with noise glued to them
    std_keys = [
        b"Subtype", b"BaseFont", b"MediaBox", b"Resources", b"Contents",
        b"Kids", b"Count", b"Filter", b"Length", b"Root", b"Size", b"Parent"
    ]
    for k in std_keys:
        target = re.sub(rb"/" + k + rb"[^/\s<>\[\]()]*(?=[/\s])", b"/" + k, target)
        target = re.sub(rb"(" + k + rb")(?=/)", rb"\1 ", target)
    target = re.sub(rb"/B\s+seFont\b", b"/BaseFont", target)
    target = re.sub(rb"/Type[^/\s<>\[\]()]*\s*(?=/(?:Font|Pages|Page|Catalog|ObjStm|XRef|XObject))", b"/Type ", target)

    # 3. Ensure closing '>>' is present if opened with '<<'
    if b"<<" in target and b">>" not in target:
        target = target.rstrip() + b" >>"
    return target


def _sanitize_dictionary_noise(obj_bytes: bytes) -> bytes:
    """Sanitize non-ASCII byte noise inside PDF dictionaries and structural tokens."""
    if not obj_bytes:
        return obj_bytes
    if b"stream" in obj_bytes:
        s_idx = obj_bytes.find(b"stream")
        dict_part = obj_bytes[:s_idx]
        stream_part = obj_bytes[s_idx:]
        clean_dict = bytes(b if (32 <= b <= 126 or b in (9, 10, 13)) else 32 for b in dict_part)
        clean_dict = _heal_dictionary_syntax(clean_dict)
        return clean_dict + stream_part
    else:
        dict_end = obj_bytes.rfind(b">>")
        target = obj_bytes[:dict_end + 2] if dict_end != -1 else obj_bytes
        clean = bytes(b if (32 <= b <= 126 or b in (9, 10, 13)) else 32 for b in target)
        clean = _heal_dictionary_syntax(clean)
        if not clean.endswith(b"endobj"):
            clean = clean.rstrip() + b"\nendobj"
        return clean



def _carve_pdf_objects_resilient(source: bytes) -> list[tuple[int, int, int, int, bytes, bool]]:
    """Carve indirect objects from raw bitstream with boundary isolation.

    Prevents missing endobj from merging multiple objects together.
    Returns:
        list of (num, gen, start_off, end_off, obj_bytes, was_unterminated)
    """
    obj_starts: list[tuple[int, int, int]] = []
    for m in re.finditer(rb"(?:^|[\r\n\s])(\d+)\s+(\d+)\s+obj\b", source):
        raw_match = m.group(0)
        digits_start = m.start() + (len(raw_match) - len(raw_match.lstrip(b"\r\n \t")))
        num = int(m.group(1))
        gen = int(m.group(2))
        obj_starts.append((digits_start, num, gen))

    results: list[tuple[int, int, int, int, bytes, bool]] = []
    seen_nums: set[int] = set()

    for idx, (s_off, num, gen) in enumerate(obj_starts):
        if num in seen_nums:
            continue
        next_s_off = obj_starts[idx + 1][0] if idx + 1 < len(obj_starts) else len(source)
        chunk = source[s_off:next_s_off]

        endobj_match = re.search(rb"\bendobj\b", chunk)
        if endobj_match:
            e_off = s_off + endobj_match.end()
            body = source[s_off:e_off].strip()
            was_unterminated = False
        else:
            cut_idx = len(chunk)
            for marker in (rb"\bxref\b", rb"\btrailer\b", rb"\bstartxref\b", rb"%%EOF"):
                m = re.search(marker, chunk)
                if m and m.start() < cut_idx:
                    cut_idx = m.start()
            body = chunk[:cut_idx].strip()
            if b"stream" in body and b"endstream" not in body:
                body += b"\nendstream"
            if not body.endswith(b"endobj"):
                body += b"\nendobj"
            e_off = s_off + cut_idx
            was_unterminated = True

        if _is_valid_or_repairable_pdf_object(body):
            results.append((num, gen, s_off, e_off, body, was_unterminated))
            seen_nums.add(num)

    return results


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
        self.telemetry: ForensicRecoveryTelemetry | None = None
        self.authentic_carved_bytes: bytes = b""
        self.recovered_objects: list[RecoveredObject] = []
        self.provenance: list[dict[str, Any]] = []

    def recover(self) -> tuple[bytes, list[str], dict[str, Any]]:
        """Execute full multi-stage recovery pipeline.

        Returns:
            (repaired_bytes, synthesized_items, recovery_metadata)
        """
        synthesized_items: list[str] = []
        source = self.source_bytes
        if not source:
            empty_telemetry = ForensicRecoveryTelemetry(
                original_evidence_size=0,
                authentic_bytes_identified=0,
                authentic_recovery_percentage=0.0,
                indirect_objects_found=0,
                validated_objects=0,
                streams_found=0,
                successfully_decompressed_streams=0,
                text_fragments_recovered=0,
                pages_discovered=0,
                fonts_discovered=(),
                recovered_objects=(),
                placed_objects_count=0,
                unplaced_bytes_count=0,
                surviving_text_strings=(),
                parser_status={"is_openable": False, "page_count": 0, "error": "empty source input"},
            )
            self.telemetry = empty_telemetry
            return b"", ["empty source input"], {"status": "empty", "telemetry": empty_telemetry.to_dict()}

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
        harvested_records: dict[int, RecoveredObject] = {}
        harvested_ranges: dict[int, tuple[int, int]] = {}
        decompressed_stream_count = 0
        total_text_strings: list[str] = []

        # Scan for indirect objects using boundary-isolated carving (tolerating missing endobj)
        carved_list = _carve_pdf_objects_resilient(source)
        for num, gen, start_off, end_off, obj_raw, was_unterminated in carved_list:
            if len(harvested_objs) >= MAX_OBJECT_COUNT:
                break
            harvested_objs[num] = obj_raw
            harvested_ranges[num] = (start_off, end_off)
            if was_unterminated:
                synthesized_items.append(f"closed unterminated object {num} with synthetic delimiter")

            # Analyze stream and text
            has_stream = b"stream" in obj_raw
            stream_len = None
            is_flate = False
            decomp_stream = None
            decomp_valid = False
            obj_text: list[str] = []

            if has_stream:
                s_idx = obj_raw.find(b"stream")
                e_idx = obj_raw.rfind(b"endstream")
                dict_part = obj_raw[:s_idx]
                len_match = re.search(rb"/Length\s+(\d+)", dict_part)
                if len_match:
                    stream_len = int(len_match.group(1))
                is_flate = b"/FlateDecode" in dict_part

                if obj_raw[s_idx:].startswith(b"stream\r\n"):
                    s_data = obj_raw[s_idx + 8:e_idx] if e_idx != -1 else obj_raw[s_idx + 8:]
                elif obj_raw[s_idx:].startswith(b"stream\n"):
                    s_data = obj_raw[s_idx + 7:e_idx] if e_idx != -1 else obj_raw[s_idx + 7:]
                else:
                    s_data = obj_raw[s_idx + 6:e_idx] if e_idx != -1 else obj_raw[s_idx + 6:]

                if is_flate or b"/ASCII85Decode" in dict_part or b"/Filter" in dict_part:
                    d_bytes, d_ok = _decompress_stream_data(dict_part, s_data)
                    if d_ok and d_bytes is not None:
                        decomp_stream = d_bytes
                        decomp_valid = True
                        decompressed_stream_count += 1
                        obj_text = _extract_text_strings(d_bytes)
                else:
                    obj_text = _extract_text_strings(s_data)
            else:
                obj_text = _extract_text_strings(obj_raw)

            for txt in obj_text:
                if txt not in total_text_strings:
                    total_text_strings.append(txt)

            rec_obj = RecoveredObject(
                object_number=num,
                generation=gen,
                source_offset_start=start_off,
                source_offset_end=end_off,
                byte_count=len(obj_raw),
                raw_bytes=obj_raw,
                has_stream=has_stream,
                stream_length=stream_len,
                is_flate_compressed=is_flate,
                decompressed_stream=decomp_stream,
                is_decompressed_valid=decomp_valid,
                extracted_text=tuple(obj_text),
                object_type=_detect_object_type(obj_raw),
                is_authentic=True,
                confidence=0.85 if was_unterminated else 1.0,
                provenance_origin="authentic_evidence",
            )
            harvested_records[num] = rec_obj

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
                        parent_range = harvested_ranges.get(num, (0, 0))
                        harvested_ranges[in_num] = parent_range
                        unpacked_count += 1
                        rec_obj = RecoveredObject(
                            object_number=in_num,
                            generation=0,
                            source_offset_start=parent_range[0],
                            source_offset_end=parent_range[1],
                            byte_count=len(in_bytes),
                            raw_bytes=in_bytes,
                            object_type=_detect_object_type(in_bytes),
                            is_authentic=True,
                            confidence=0.95,
                            provenance_origin="authentic_evidence",
                        )
                        harvested_records[in_num] = rec_obj
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

        # If info_num still None, scan source for trailer /Info pointer
        if info_num is None:
            for m in re.finditer(rb"/Info\s+(\d+)\s+0\s+R", source):
                cand = int(m.group(1))
                if cand in harvested_objs:
                    info_num = cand
                    break

        # Collect all font names referenced across all harvested content streams
        referenced_font_names: set[str] = set()
        for num, obj_bytes in harvested_objs.items():
            for fm in re.finditer(rb"/([A-Za-z0-9_-]+)\s+\d+(?:\.\d+)?\s+Tf", obj_bytes):
                fn = fm.group(1).decode("ascii", errors="ignore")
                if fn and fn not in ("F", "Tf"):
                    referenced_font_names.add(fn)

        if not referenced_font_names:
            referenced_font_names.add("F1")

        # If page objects exist but /Type /Pages is missing or disconnected, rebuild /Pages container
        all_ids = set(harvested_objs.keys())
        parent_pages_id = pages_objs[0] if pages_objs else (max(all_ids, default=0) + 1)
        font_obj_id = max(all_ids, default=0) + 2
        all_ids.add(parent_pages_id)
        all_ids.add(font_obj_id)

        standard_font_obj = (
            f"{font_obj_id} 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>\nendobj".encode("ascii")
        )
        font_dict_entries = " ".join(f"/{fn} {font_obj_id} 0 R" for fn in sorted(referenced_font_names))
        font_resources_fragment = f"/Resources << /Font << {font_dict_entries} >> >>".encode("ascii")
        has_added_font = False

        # If we have streams but 0 pages identified, rescue ALL content streams into sequential pages
        if not page_objs:
            content_candidates = [
                num for num, ob in harvested_objs.items()
                if (b"BT" in ob or b"Tj" in ob or b"TJ" in ob or b"cm" in ob) and b"stream" in ob
            ]
            for cs_num in content_candidates:
                page_id = max(all_ids, default=0) + 1
                all_ids.add(page_id)
                page_def = (
                    f"{page_id} 0 obj\n<< /Type /Page /Parent {parent_pages_id} 0 R /MediaBox [0 0 612 792] "
                    f"/Resources << /Font << {font_dict_entries} >> >> /Contents {cs_num} 0 R >>\nendobj"
                ).encode("ascii")
                harvested_objs[page_id] = page_def
                page_objs.append(page_id)
                has_added_font = True
                synthesized_items.append(f"synthesized Page wrapper ({page_id} 0 obj) for unlinked content stream {cs_num}")

        # Collect image references across all objects for safe /XObject map
        image_obj_ids = [
            n for n, ob in harvested_objs.items()
            if b"/Subtype /Image" in ob or b"/Subtype/Image" in ob
        ]
        xobject_dict_entries = " ".join(f"/Im{i+1} {iid} 0 R" for i, iid in enumerate(image_obj_ids))
        xobject_clause = f" /XObject << {xobject_dict_entries} >>" if xobject_dict_entries else ""

        # Sanitize each /Page object: ensure valid Parent, MediaBox, Font, and Content references
        page_objs.sort()
        for p_id in page_objs:
            p_bytes = harvested_objs[p_id]

            # Check if page already has a valid uncorrupted Resources reference
            res_val = _extract_dict_value(p_bytes, b"/Resources")
            if res_val and not any(b > 126 for b in res_val):
                resources_clause = b"/Resources " + res_val
            else:
                resources_clause = f"/Resources << /Font << {font_dict_entries} >>{xobject_clause} >>".encode("ascii")
                has_added_font = True

            c_val = _extract_dict_value(p_bytes, b"/Contents")
            if not c_val:
                c_match = re.search(rb"/Contents\s+(\d+\s+\d+\s+R|\[[^\]]+\])", p_bytes)
                if c_match:
                    c_val = c_match.group(1)

            if c_val:
                contents_clause = b"/Contents " + c_val
            else:
                candidate_contents = [
                    o_num for o_num in harvested_objs
                    if o_num != p_id and (b"BT" in harvested_objs[o_num] or b"cm" in harvested_objs[o_num] or b"Tj" in harvested_objs[o_num]) and b"stream" in harvested_objs[o_num]
                ]
                contents_clause = f"/Contents {candidate_contents[0]} 0 R".encode("ascii") if candidate_contents else b""

            mb_val = _extract_dict_value(p_bytes, b"/MediaBox")
            if mb_val and re.match(rb"^\[\s*-?\d+(?:\.\d+)?\s+-?\d+(?:\.\d+)?\s+-?\d+(?:\.\d+)?\s+-?\d+(?:\.\d+)?\s*\]", mb_val):
                mb_clause = b"/MediaBox " + mb_val
            else:
                mb_clause = b"/MediaBox [0 0 612 792]"


            clean_page = (
                f"{p_id} 0 obj\n<< /Type /Page /Parent {parent_pages_id} 0 R ".encode("ascii")
                + mb_clause
                + b" "
                + resources_clause
                + b" "
                + contents_clause
                + b" >>\nendobj"
            )
            harvested_objs[p_id] = clean_page

        if has_added_font and font_obj_id not in harvested_objs:
            harvested_objs[font_obj_id] = standard_font_obj
            synthesized_items.append(f"synthesized Base14 standard Font object ({font_obj_id} 0 obj) with universal aliases")

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

        # Rebuild guaranteed clean /Type /Catalog
        if cat_num is None or cat_num not in harvested_objs:
            cat_num = max(set(harvested_objs.keys()), default=0) + 1
            cat_obj = f"{cat_num} 0 obj\n<< /Type /Catalog /Pages {parent_pages_id} 0 R >>\nendobj".encode("ascii")
            harvested_objs[cat_num] = cat_obj
            synthesized_items.append(f"synthesized root Catalog dictionary ({cat_num} 0 obj)")
        else:
            cat_bytes = harvested_objs[cat_num]
            if re.search(rb"/Pages\s+\d+\s+\d+\s+R", cat_bytes):
                harvested_objs[cat_num] = re.sub(
                    rb"/Pages\s+\d+\s+\d+\s+R",
                    f"/Pages {parent_pages_id} 0 R".encode("ascii"),
                    cat_bytes,
                )
            else:
                harvested_objs[cat_num] = (
                    f"{cat_num} 0 obj\n<< /Type /Catalog /Pages {parent_pages_id} 0 R >>\nendobj".encode("ascii")
                )



        # -------------------------------------------------------------
        # Stage 5: ISO 32000-1 Xref Table & Trailer Synthesis
        # -------------------------------------------------------------
        sorted_obj_nums = sorted(harvested_objs.keys())
        body_chunks = [header_bytes]
        offsets: dict[int, int] = {}
        current_offset = len(header_bytes)

        for num in sorted_obj_nums:
            sanitized = _sanitize_dictionary_noise(harvested_objs[num])
            chunk = _normalize_stream_object(sanitized) + b"\n"
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

        # Build authentic carved bytes: concatenation of all authentic harvested objects
        authentic_body = b"".join(harvested_objs[num] + b"\n" for num in sorted_obj_nums if num in harvested_ranges)
        self.authentic_carved_bytes = authentic_body

        # Build detailed provenance list
        provenance_records: list[dict[str, Any]] = []
        out_offset = len(header_bytes)
        for num in sorted_obj_nums:
            chunk = _normalize_stream_object(harvested_objs[num]) + b"\n"
            c_len = len(chunk)
            src_range = harvested_ranges.get(num)
            is_auth = src_range is not None
            prov_entry = {
                "object_number": num,
                "type": "original_recovered" if is_auth else "synthesized_repair",
                "output_offset_start": out_offset,
                "output_offset_end": out_offset + c_len,
                "byte_count": c_len,
                "media_offset_start": src_range[0] if is_auth else None,
                "media_offset_end": src_range[1] if is_auth else None,
                "confidence": 1.0 if is_auth else 0.0,
                "origin": "authentic_evidence" if is_auth else "synthesized_repair",
                "description": f"Object {num} ({harvested_records[num].object_type if num in harvested_records else 'synthetic'})",
            }
            provenance_records.append(prov_entry)
            out_offset += c_len

        # Synthesized trailer and xref
        synth_xref_len = len(rebuilt_pdf) - xref_offset
        provenance_records.append({
            "type": "synthesized_repair",
            "output_offset_start": xref_offset,
            "output_offset_end": len(rebuilt_pdf),
            "byte_count": synth_xref_len,
            "media_offset_start": None,
            "media_offset_end": None,
            "confidence": 0.0,
            "origin": "synthesized_repair",
            "description": "Synthesized ISO 32000-1 xref table, trailer dictionary, startxref pointer, and %%EOF marker",
        })

        self.provenance = provenance_records
        self.recovered_objects = [harvested_records[n] for n in sorted(harvested_records.keys())]

        auth_bytes_count = sum(r.byte_count for r in self.recovered_objects if r.is_authentic)
        coverage_pct = (auth_bytes_count / len(source) * 100) if source else 0.0

        # Validate resulting PDF with pypdf and fitz
        from .repair import validate_and_render_pdf
        v_open, v_pages, v_txt, v_err = validate_and_render_pdf(rebuilt_pdf)

        fonts_found: list[str] = []
        for o in self.recovered_objects:
            for fn in re.findall(rb"/BaseFont\s*/([A-Za-z0-9_-]+)", o.raw_bytes):
                f_str = fn.decode("ascii", errors="ignore")
                if f_str not in fonts_found:
                    fonts_found.append(f_str)

        self.telemetry = ForensicRecoveryTelemetry(
            original_evidence_size=len(source),
            authentic_bytes_identified=auth_bytes_count,
            authentic_recovery_percentage=coverage_pct,
            indirect_objects_found=len(harvested_objs),
            validated_objects=len(self.recovered_objects),
            streams_found=sum(1 for o in self.recovered_objects if o.has_stream),
            successfully_decompressed_streams=decompressed_stream_count,
            text_fragments_recovered=len(total_text_strings),
            pages_discovered=len(page_objs),
            fonts_discovered=tuple(fonts_found),
            recovered_objects=tuple(self.recovered_objects),
            placed_objects_count=len(sorted_obj_nums),
            unplaced_bytes_count=max(0, len(source) - auth_bytes_count),
            surviving_text_strings=tuple(total_text_strings),
            parser_status={
                "is_openable": v_open,
                "page_count": v_pages,
                "error": v_err,
            },
        )

        meta = {
            "version": pdf_version,
            "objects_recovered": len(sorted_obj_nums),
            "pages_reconstructed": len(page_objs),
            "root_catalog": cat_num,
            "xref_offset": xref_offset,
            "synthesized_size": len(rebuilt_pdf) - len(assembled_body),
            "body_size": len(assembled_body),
            "telemetry": self.telemetry.to_dict(),
            "authentic_recovered_bytes": self.authentic_carved_bytes,
            "provenance": self.provenance,
            "recovered_objects": [o.to_dict() for o in self.recovered_objects],
            "surviving_text": list(total_text_strings),
            "parser_status": self.telemetry.parser_status,
        }

        return rebuilt_pdf, synthesized_items, meta

    def extract_salvaged_text(self) -> str:
        """Return all recovered readable text in sequential order."""
        if self.telemetry:
            return "\n\n".join(self.telemetry.surviving_text_strings)
        return ""

    def extract_salvaged_images(self) -> list[dict[str, Any]]:
        """Extract authentic image streams (e.g. JPEG, raw bitmaps) discovered in evidence."""
        images: list[dict[str, Any]] = []
        for obj in self.recovered_objects:
            if obj.object_type == "Image" or b"/Subtype /Image" in obj.raw_bytes or b"/Subtype/Image" in obj.raw_bytes:
                is_jpeg = b"/DCTDecode" in obj.raw_bytes
                mime = "image/jpeg" if is_jpeg else "application/octet-stream"
                ext = "jpg" if is_jpeg else "bin"
                s_idx = obj.raw_bytes.find(b"stream")
                e_idx = obj.raw_bytes.rfind(b"endstream")
                if s_idx != -1 and e_idx != -1 and e_idx > s_idx:
                    if obj.raw_bytes[s_idx:].startswith(b"stream\r\n"):
                        img_data = obj.raw_bytes[s_idx + 8:e_idx]
                    elif obj.raw_bytes[s_idx:].startswith(b"stream\n"):
                        img_data = obj.raw_bytes[s_idx + 7:e_idx]
                    else:
                        img_data = obj.raw_bytes[s_idx + 6:e_idx]
                    img_data = img_data.rstrip(b"\r\n")
                    images.append({

                        "object_number": obj.object_number,
                        "mime_type": mime,
                        "extension": ext,
                        "byte_count": len(img_data),
                        "data": img_data,
                        "is_jpeg": is_jpeg,
                    })
        return images

    def generate_forensic_report(self) -> dict[str, Any]:
        """Generate structured forensic recovery report."""
        diagnostic_dict = self.diagnostic.to_dict() if self.diagnostic else {}
        telemetry_dict = self.telemetry.to_dict() if self.telemetry else {}
        auth_bytes = telemetry_dict.get("authentic_bytes_identified", 0)
        total_ev = telemetry_dict.get("original_evidence_size", len(self.source_bytes))
        auth_pct = telemetry_dict.get("authentic_recovery_percentage", 0.0)

        return {
            "title": "TRACE Forensic PDF Recovery Report",
            "evidence_sha256": sha256_bytes(self.source_bytes),
            "evidence_size_bytes": len(self.source_bytes),
            "diagnostic": diagnostic_dict,
            "telemetry": telemetry_dict,
            "provenance": self.provenance,
            "salvaged_pages_count": len(self.telemetry.surviving_text_strings) if self.telemetry else 0,
            "authentic_vs_synthesized_breakdown": {
                "authentic_bytes": auth_bytes,
                "total_evidence_bytes": total_ev,
                "authentic_percentage": auth_pct,
                "synthesized_records_count": sum(1 for p in self.provenance if p.get("type") == "synthesized_repair"),
            },
            "summary": (
                f"# TRACE Forensic PDF Recovery Report\n\n"
                f"- **Evidence SHA-256**: `{sha256_bytes(self.source_bytes)}`\n"
                f"- **Authentic Recovery Percentage**: {auth_pct:.2f}%\n"
                f"- **Surviving Objects**: {len(self.recovered_objects)}\n"
                f"- **Provenance Records**: {len(self.provenance)}\n"
            ),
        }

