"""Deterministic, explainable forensic fragment feature extraction.

Computes byte-level, entropy, and structural token features from arbitrary binary fragments
without label leakage or external dependencies.
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Sequence, Union

FEATURE_NAMES: List[str] = [
    "length",
    "printable_ratio",
    "whitespace_ratio",
    "null_byte_ratio",
    "high_byte_ratio",
    "digit_ratio",
    "shannon_entropy",
    "starts_with_pdf_magic",
    "starts_with_dict_open",
    "has_dict_open",
    "has_dict_close",
    "token_count_obj",
    "token_count_endobj",
    "token_count_stream",
    "token_count_endstream",
    "token_count_xref",
    "token_count_trailer",
    "token_count_startxref",
    "token_count_eof",
    "has_type_page",
    "has_type_font",
    "has_type_catalog",
    "has_type_metadata",
    "has_subtype_image",
    "has_filter_flate",
    "has_length_key",
    "has_bt_et_text_ops",
    "token_count_bt",
    "token_count_et",
    "token_count_tj",
    "slash_name_count",
    "consecutive_printable_max",
    "is_compressed_candidate",
]

_SLASH_NAME_REGEX = re.compile(b"/[A-Za-z0-9_-]+")
_TEXT_OP_TJ_REGEX = re.compile(b"\\b(?:Tj|TJ)\\b")
_OBJ_DEF_REGEX = re.compile(b"\\b\\d+\\s+\\d+\\s+obj\\b")


class FragmentFeatureExtractor:
    """Extracts numerical features from raw binary evidence fragments."""

    def __init__(self, feature_names: Sequence[str] | None = None) -> None:
        self.feature_names = list(feature_names) if feature_names else list(FEATURE_NAMES)

    def extract_features(self, fragment: Union[bytes, bytearray, memoryview]) -> Dict[str, float]:
        """Extract deterministic feature dictionary from a fragment."""
        raw_bytes = bytes(fragment)
        length = len(raw_bytes)

        if length == 0:
            return {name: 0.0 for name in self.feature_names}

        # Byte distribution calculations
        printable_count = 0
        whitespace_count = 0
        null_count = 0
        high_count = 0
        digit_count = 0
        byte_freq = [0] * 256

        consecutive_printable = 0
        max_consecutive_printable = 0

        for b in raw_bytes:
            byte_freq[b] += 1
            if 32 <= b <= 126:
                printable_count += 1
                consecutive_printable += 1
                if consecutive_printable > max_consecutive_printable:
                    max_consecutive_printable = consecutive_printable
            elif b in (9, 10, 13):  # tab, \n, \r
                printable_count += 1
                whitespace_count += 1
                consecutive_printable += 1
                if consecutive_printable > max_consecutive_printable:
                    max_consecutive_printable = consecutive_printable
            else:
                consecutive_printable = 0

            if b == 0:
                null_count += 1
            elif b == 32:
                whitespace_count += 1

            if b > 127:
                high_count += 1

            if 48 <= b <= 57:
                digit_count += 1

        printable_ratio = printable_count / length
        whitespace_ratio = whitespace_count / length
        null_byte_ratio = null_count / length
        high_byte_ratio = high_count / length
        digit_ratio = digit_count / length

        # Shannon Entropy
        entropy = 0.0
        for count in byte_freq:
            if count > 0:
                p = count / length
                entropy -= p * math.log2(p)
        shannon_entropy = entropy

        # Structural tokens
        starts_with_pdf_magic = 1.0 if raw_bytes.startswith(b"%PDF") or b"%PDF-" in raw_bytes[:64] else 0.0
        starts_with_dict_open = 1.0 if raw_bytes.lstrip().startswith(b"<<") else 0.0
        has_dict_open = 1.0 if b"<<" in raw_bytes else 0.0
        has_dict_close = 1.0 if b">>" in raw_bytes else 0.0

        token_count_obj = float(len(_OBJ_DEF_REGEX.findall(raw_bytes)) or (1.0 if b" obj" in raw_bytes else 0.0))
        token_count_endobj = float(raw_bytes.count(b"endobj"))
        token_count_stream = float(raw_bytes.count(b"stream")) - float(raw_bytes.count(b"endstream"))
        token_count_stream = max(0.0, float(token_count_stream))
        token_count_endstream = float(raw_bytes.count(b"endstream"))

        token_count_xref = float(raw_bytes.count(b"xref"))
        token_count_trailer = float(raw_bytes.count(b"trailer"))
        token_count_startxref = float(raw_bytes.count(b"startxref"))
        token_count_eof = float(raw_bytes.count(b"%%EOF"))

        has_type_page = 1.0 if (b"/Type /Page" in raw_bytes or b"/Type/Page" in raw_bytes) else 0.0
        has_type_font = 1.0 if (b"/Type /Font" in raw_bytes or b"/Type/Font" in raw_bytes or b"/Subtype /Type1" in raw_bytes or b"/TrueType" in raw_bytes) else 0.0
        has_type_catalog = 1.0 if (b"/Type /Catalog" in raw_bytes or b"/Type/Catalog" in raw_bytes) else 0.0
        has_type_metadata = 1.0 if (b"/Type /Metadata" in raw_bytes or b"<x:xmpmeta" in raw_bytes or b"http://ns.adobe.com" in raw_bytes) else 0.0

        has_subtype_image = 1.0 if (b"/Subtype /Image" in raw_bytes or b"/Subtype/Image" in raw_bytes or b"/DCTDecode" in raw_bytes or b"/JPXDecode" in raw_bytes) else 0.0
        has_filter_flate = 1.0 if (b"/Filter /FlateDecode" in raw_bytes or b"/Filter/FlateDecode" in raw_bytes or b"FlateDecode" in raw_bytes) else 0.0
        has_length_key = 1.0 if (b"/Length " in raw_bytes or b"/Length\n" in raw_bytes) else 0.0

        token_count_bt = float(raw_bytes.count(b"BT"))
        token_count_et = float(raw_bytes.count(b"ET"))
        token_count_tj = float(len(_TEXT_OP_TJ_REGEX.findall(raw_bytes)))
        has_bt_et_text_ops = 1.0 if (token_count_bt > 0 and token_count_et > 0) or token_count_tj > 0 else 0.0

        slash_name_count = float(len(_SLASH_NAME_REGEX.findall(raw_bytes)))

        # Heuristic for compressed zlib stream (magic bytes 0x78 0x9c or 0x78 0x01 or high entropy + low printable)
        is_compressed = 0.0
        if b"\x78\x9c" in raw_bytes or b"\x78\x01" in raw_bytes or b"\x78\xda" in raw_bytes:
            is_compressed = 1.0
        elif shannon_entropy > 7.2 and printable_ratio < 0.2:
            is_compressed = 1.0

        all_features: Dict[str, float] = {
            "length": float(length),
            "printable_ratio": float(printable_ratio),
            "whitespace_ratio": float(whitespace_ratio),
            "null_byte_ratio": float(null_byte_ratio),
            "high_byte_ratio": float(high_byte_ratio),
            "digit_ratio": float(digit_ratio),
            "shannon_entropy": float(shannon_entropy),
            "starts_with_pdf_magic": float(starts_with_pdf_magic),
            "starts_with_dict_open": float(starts_with_dict_open),
            "has_dict_open": float(has_dict_open),
            "has_dict_close": float(has_dict_close),
            "token_count_obj": float(token_count_obj),
            "token_count_endobj": float(token_count_endobj),
            "token_count_stream": float(token_count_stream),
            "token_count_endstream": float(token_count_endstream),
            "token_count_xref": float(token_count_xref),
            "token_count_trailer": float(token_count_trailer),
            "token_count_startxref": float(token_count_startxref),
            "token_count_eof": float(token_count_eof),
            "has_type_page": float(has_type_page),
            "has_type_font": float(has_type_font),
            "has_type_catalog": float(has_type_catalog),
            "has_type_metadata": float(has_type_metadata),
            "has_subtype_image": float(has_subtype_image),
            "has_filter_flate": float(has_filter_flate),
            "has_length_key": float(has_length_key),
            "has_bt_et_text_ops": float(has_bt_et_text_ops),
            "token_count_bt": float(token_count_bt),
            "token_count_et": float(token_count_et),
            "token_count_tj": float(token_count_tj),
            "slash_name_count": float(slash_name_count),
            "consecutive_printable_max": float(max_consecutive_printable),
            "is_compressed_candidate": float(is_compressed),
        }

        # Return in specified feature order
        return {k: all_features.get(k, 0.0) for k in self.feature_names}

    def extract_vector(self, fragment: Union[bytes, bytearray, memoryview]) -> List[float]:
        """Extract ordered feature vector as list of floats."""
        feats = self.extract_features(fragment)
        return [feats[name] for name in self.feature_names]


def extract_fragment_features(fragment: Union[bytes, bytearray, memoryview]) -> Dict[str, float]:
    """Convenience functional extractor."""
    return FragmentFeatureExtractor().extract_features(fragment)
