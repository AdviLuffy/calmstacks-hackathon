"""JPEG format handler: marker parsing, frame analysis, and reconstruction."""

from __future__ import annotations

import struct
from typing import Any, Mapping, Sequence

from trace.recovery.formats.base import BaseFormatHandler
from trace.recovery.models import FormatConfidence, FragmentCandidate, ValidationResult

_SOI = b"\xff\xd8"
_EOI = b"\xff\xd9"
_SOS = b"\xff\xda"
_SOF0 = b"\xff\xc0"
_SOF2 = b"\xff\xc2"
_DQT = b"\xff\xdb"
_DHT = b"\xff\xc4"


class JpegFormatHandler(BaseFormatHandler):
    """High-assurance JPEG image recovery and marker validation engine."""

    format_name = "jpeg"
    mime_type = "image/jpeg"
    default_extension = ".jpg"

    def identify(self, data: bytes, filename: str = "") -> FormatConfidence:
        if not data:
            return FormatConfidence(self.format_name, self.mime_type, 0.0, "none", is_supported=True)

        indicators: list[str] = []
        confidence = 0.0

        if data.startswith(_SOI):
            indicators.append("marker:SOI")
            confidence += 0.5
        elif _SOI in data[:1024]:
            indicators.append("marker:SOI_embedded")
            confidence += 0.3

        if data.endswith(_EOI) or _EOI in data[-128:]:
            indicators.append("marker:EOI")
            confidence += 0.3
        elif _EOI in data:
            indicators.append("marker:EOI_embedded")
            confidence += 0.15

        if _SOF0 in data or _SOF2 in data:
            indicators.append("marker:SOF")
            confidence += 0.2

        if _DQT in data:
            indicators.append("marker:DQT")
            confidence += 0.1

        if filename.lower() in (".jpg", ".jpeg"):
            indicators.append("extension:jpeg")
            confidence += 0.1

        confidence = min(1.0, max(0.0, confidence))
        detected_by = "magic_bytes" if "marker:SOI" in indicators else "markers"

        return FormatConfidence(
            format_name=self.format_name,
            mime_type=self.mime_type,
            confidence=confidence,
            detected_by=detected_by,
            structural_indicators=tuple(indicators),
            is_supported=True,
            details={"has_soi": "marker:SOI" in indicators, "has_eoi": "marker:EOI" in indicators},
        )

    def carve_fragments(
        self, stream: bytes, block_size: int | None = None
    ) -> list[FragmentCandidate]:
        if block_size is None:
            fragments = []
            offset = 0
            idx = 0
            while offset < len(stream):
                seg_start = offset
                if stream[offset : offset + 2] == _SOI:
                    offset += 2
                    if offset + 4 <= len(stream) and stream[offset] == 0xFF and (0xE0 <= stream[offset + 1] <= 0xEF):
                        seg_len = struct.unpack(">H", stream[offset + 2 : offset + 4])[0]
                        offset += 2 + seg_len
                    seg_bytes = stream[seg_start:offset]
                    role = "header"
                    is_header = True
                    is_footer = False
                    tokens = ["SOI"]
                elif stream[offset : offset + 2] == _EOI:
                    seg_bytes = stream[offset : offset + 2]
                    offset += 2
                    role = "footer"
                    is_header = False
                    is_footer = True
                    tokens = ["EOI"]
                elif stream[offset] == 0xFF and offset + 2 <= len(stream):
                    marker = stream[offset : offset + 2]
                    offset += 2
                    if offset + 2 <= len(stream) and marker not in (_SOI, _EOI, b"\xff\x00") and not (0xFFD0 <= marker[1] <= 0xFFD7):
                        seg_len = struct.unpack(">H", stream[offset : offset + 2])[0]
                        offset += seg_len
                    seg_bytes = stream[seg_start:offset]
                    role = "metadata"
                    is_header = False
                    is_footer = False
                    tokens = []
                    if _SOF0 in seg_bytes or _SOF2 in seg_bytes:
                        tokens.append("SOF")
                    if _DQT in seg_bytes:
                        tokens.append("DQT")
                    if _DHT in seg_bytes:
                        tokens.append("DHT")
                    if _SOS in seg_bytes:
                        tokens.append("SOS")
                        role = "scan_start"
                else:
                    next_ff = stream.find(b"\xff", offset)
                    if next_ff != -1:
                        seg_bytes = stream[seg_start:next_ff]
                        offset = next_ff
                    else:
                        seg_bytes = stream[seg_start:]
                        offset = len(stream)
                    role = "scan_data"
                    is_header = False
                    is_footer = False
                    tokens = ["SCAN_DATA"]

                if seg_bytes:
                    fragments.append(
                        FragmentCandidate(
                            fragment_id=f"JPG-FRAG-{idx:04d}",
                            source_offset=seg_start,
                            size_bytes=len(seg_bytes),
                            data=seg_bytes,
                            format_hint="jpeg",
                            structural_role=role,
                            tokens=tuple(tokens),
                            is_header=is_header,
                            is_footer=is_footer,
                            known_sequence_index=idx,
                        )
                    )
                    idx += 1
            if fragments:
                return fragments

        # Fixed block carving
        bs = block_size or 256
        fragments: list[FragmentCandidate] = []
        offset = 0
        idx = 0

        while offset < len(stream):
            chunk = stream[offset : offset + bs]
            tokens: list[str] = []
            role = "data"
            is_header = False
            is_footer = False

            if _SOI in chunk:
                tokens.append("SOI")
                role = "header"
                is_header = True
            if _SOF0 in chunk or _SOF2 in chunk:
                tokens.append("SOF")
                role = "frame"
            if _DQT in chunk:
                tokens.append("DQT")
            if _DHT in chunk:
                tokens.append("DHT")
            if _SOS in chunk:
                tokens.append("SOS")
                role = "scan_start"
            if _EOI in chunk:
                tokens.append("EOI")
                role = "footer"
                is_footer = True

            frag = FragmentCandidate(
                fragment_id=f"JPG-FRAG-{idx:04d}",
                source_offset=offset,
                size_bytes=len(chunk),
                data=chunk,
                format_hint="jpeg",
                structural_role=role,
                tokens=tuple(tokens),
                is_header=is_header,
                is_footer=is_footer,
                known_sequence_index=idx,
            )
            fragments.append(frag)
            offset += bs
            idx += 1

        return fragments

    def order_and_reconstruct(
        self, fragments: Sequence[FragmentCandidate]
    ) -> tuple[bytes, list[str], list[str], dict[str, Any]]:
        """Order JPEG fragments: SOI/Header -> Table/Frame chunks -> Scan/Data -> Footer."""
        if not fragments:
            return b"", [], [], {"status": "empty"}

        header_frags: list[FragmentCandidate] = []
        metadata_frags: list[FragmentCandidate] = []
        scan_frags: list[FragmentCandidate] = []
        footer_frags: list[FragmentCandidate] = []

        for f in fragments:
            if f.is_header or "SOI" in f.tokens:
                header_frags.append(f)
            elif f.is_footer or "EOI" in f.tokens:
                footer_frags.append(f)
            elif "DQT" in f.tokens or "DHT" in f.tokens or "SOF" in f.tokens:
                metadata_frags.append(f)
            else:
                scan_frags.append(f)

        ordered = header_frags + metadata_frags + scan_frags + footer_frags
        reconstructed_bytes = b"".join(f.data for f in ordered)
        placed_ids = [f.fragment_id for f in ordered]

        validation = self.validate(reconstructed_bytes)
        return (
            reconstructed_bytes,
            placed_ids,
            [],
            {
                "status": "structurally_valid" if validation.is_valid else "incomplete",
                "validation": {
                    "is_valid": validation.is_valid,
                    "errors": list(validation.errors),
                },
            },
        )

    def validate(self, data: bytes) -> ValidationResult:
        if not data:
            return ValidationResult(
                is_valid=False,
                format_name=self.format_name,
                integrity_score=0.0,
                checks_failed=("non_empty",),
                errors=("Byte stream is empty",),
            )

        checks_passed: list[str] = []
        checks_failed: list[str] = []
        errors: list[str] = []
        warnings: list[str] = []
        metadata: dict[str, Any] = {"size_bytes": len(data)}

        # 1. SOI check
        if data.startswith(_SOI):
            checks_passed.append("marker_soi")
        else:
            checks_failed.append("marker_soi")
            errors.append("Missing SOI (0xFFD8) start marker")
            return ValidationResult(
                is_valid=False,
                format_name=self.format_name,
                integrity_score=0.0,
                checks_failed=tuple(checks_failed),
                errors=tuple(errors),
            )

        # 2. EOI check
        eoi_idx = data.rfind(_EOI)
        if eoi_idx != -1:
            checks_passed.append("marker_eoi")
        else:
            checks_failed.append("marker_eoi")
            errors.append("Missing EOI (0xFFD9) end marker")

        # 3. Parse segments
        offset = 2
        found_sof = False
        found_sos = False
        found_dqt = False

        while offset < len(data) - 1:
            if data[offset] != 0xFF:
                # In scan data or entropy stream, scan until next marker
                offset += 1
                continue

            marker = data[offset : offset + 2]
            if marker == _EOI:
                break
            if marker in (_SOF0, _SOF2):
                found_sof = True
                if offset + 8 < len(data):
                    try:
                        precision, h, w = struct.unpack(">BHH", data[offset + 4 : offset + 9])
                        metadata["width"] = w
                        metadata["height"] = h
                        metadata["precision"] = precision
                    except struct.error:
                        pass
            elif marker == _DQT:
                found_dqt = True
            elif marker == _SOS:
                found_sos = True

            # If marker has length field
            if marker not in (_SOI, _EOI, b"\xff\x00") and not (0xFFD0 <= marker[1] <= 0xFFD7):
                if offset + 4 <= len(data):
                    seg_len = struct.unpack(">H", data[offset + 2 : offset + 4])[0]
                    offset += 2 + seg_len
                    continue

            offset += 2

        if found_sof:
            checks_passed.append("frame_header_sof")
        else:
            checks_failed.append("frame_header_sof")
            errors.append("No SOF frame header marker found")

        if found_sos:
            checks_passed.append("scan_header_sos")
        else:
            warnings.append("No explicit SOS scan marker identified before EOF")

        score = 0.0
        if "marker_soi" in checks_passed:
            score += 0.35
        if "marker_eoi" in checks_passed:
            score += 0.35
        if "frame_header_sof" in checks_passed:
            score += 0.20
        if "scan_header_sos" in checks_passed:
            score += 0.10

        is_valid = ("marker_soi" in checks_passed) and ("marker_eoi" in checks_passed) and found_sof

        return ValidationResult(
            is_valid=is_valid,
            format_name=self.format_name,
            integrity_score=round(score, 2),
            checks_passed=tuple(checks_passed),
            checks_failed=tuple(checks_failed),
            errors=tuple(errors),
            warnings=tuple(warnings),
            metadata=metadata,
        )
