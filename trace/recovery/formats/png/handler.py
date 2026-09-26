"""PNG format handler: chunk-level parsing, CRC-32 validation, and reconstruction."""

from __future__ import annotations

import struct
import zlib
from typing import Any, Mapping, Sequence

from trace.recovery.formats.base import BaseFormatHandler
from trace.recovery.models import FormatConfidence, FragmentCandidate, ValidationResult

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
_IEND_CRC = 0xAE426082


class PngFormatHandler(BaseFormatHandler):
    """High-assurance PNG image recovery and chunk validation engine."""

    format_name = "png"
    mime_type = "image/png"
    default_extension = ".png"

    def identify(self, data: bytes, filename: str = "") -> FormatConfidence:
        if not data:
            return FormatConfidence(self.format_name, self.mime_type, 0.0, "none", is_supported=True)

        indicators: list[str] = []
        confidence = 0.0

        if data.startswith(_PNG_MAGIC):
            indicators.append("magic_bytes:PNG")
            confidence += 0.6
        elif _PNG_MAGIC in data[:1024]:
            indicators.append("magic_bytes_embedded")
            confidence += 0.4

        if b"IHDR" in data[:128]:
            indicators.append("chunk:IHDR")
            confidence += 0.2

        if b"IDAT" in data:
            indicators.append("chunk:IDAT")
            confidence += 0.15

        if b"IEND" in data[-64:] or b"IEND" in data:
            indicators.append("chunk:IEND")
            confidence += 0.15

        if filename.lower().endswith(".png"):
            indicators.append("extension:.png")
            confidence += 0.1

        confidence = min(1.0, max(0.0, confidence))
        detected_by = "magic_bytes" if "magic_bytes:PNG" in indicators else "chunks"

        return FormatConfidence(
            format_name=self.format_name,
            mime_type=self.mime_type,
            confidence=confidence,
            detected_by=detected_by,
            structural_indicators=tuple(indicators),
            is_supported=True,
            details={"has_header": "magic_bytes:PNG" in indicators, "has_iend": "chunk:IEND" in indicators},
        )

    def carve_fragments(
        self, stream: bytes, block_size: int | None = None
    ) -> list[FragmentCandidate]:
        if not stream:
            return []

        if block_size is None:
            # Chunk-aligned parsing
            fragments: list[FragmentCandidate] = []
            offset = 0
            idx = 0
            while offset < len(stream):
                chunk_start = offset
                if stream[offset : offset + 8] == _PNG_MAGIC:
                    offset += 8

                if offset + 8 <= len(stream):
                    try:
                        (length,) = struct.unpack(">I", stream[offset : offset + 4])
                        total_chunk_len = 8 + length + 4
                        if offset + total_chunk_len <= len(stream):
                            chunk_bytes = stream[chunk_start : offset + total_chunk_len]
                            offset += total_chunk_len
                        else:
                            chunk_bytes = stream[chunk_start:]
                            offset = len(stream)
                    except struct.error:
                        chunk_bytes = stream[chunk_start:]
                        offset = len(stream)
                else:
                    chunk_bytes = stream[chunk_start:]
                    offset = len(stream)

                tokens: list[str] = []
                role = "data"
                is_header = False
                is_footer = False

                if _PNG_MAGIC in chunk_bytes or b"IHDR" in chunk_bytes:
                    tokens.extend(["PNG_HEADER", "IHDR"])
                    role = "header"
                    is_header = True
                elif b"IDAT" in chunk_bytes:
                    tokens.append("IDAT")
                    role = "idat"
                elif b"PLTE" in chunk_bytes:
                    tokens.append("PLTE")
                    role = "plte"
                elif b"IEND" in chunk_bytes:
                    tokens.append("IEND")
                    role = "footer"
                    is_footer = True

                frag = FragmentCandidate(
                    fragment_id=f"PNG-FRAG-{idx:04d}",
                    source_offset=chunk_start,
                    size_bytes=len(chunk_bytes),
                    data=chunk_bytes,
                    format_hint="png",
                    structural_role=role,
                    tokens=tuple(tokens),
                    is_header=is_header,
                    is_footer=is_footer,
                    known_sequence_index=idx,
                )
                fragments.append(frag)
                idx += 1

            if fragments:
                return fragments

        # Fixed block carving
        bs = block_size or 256
        fragments = []
        offset = 0
        idx = 0

        while offset < len(stream):
            chunk = stream[offset : offset + bs]
            tokens = []
            role = "data"
            is_header = False
            is_footer = False

            if _PNG_MAGIC in chunk or b"IHDR" in chunk:
                tokens.extend(["PNG_HEADER", "IHDR"])
                role = "header"
                is_header = True
            if b"IDAT" in chunk:
                tokens.append("IDAT")
                role = "idat"
            if b"PLTE" in chunk:
                tokens.append("PLTE")
                role = "plte"
            if b"IEND" in chunk:
                tokens.append("IEND")
                role = "footer"
                is_footer = True

            frag = FragmentCandidate(
                fragment_id=f"PNG-FRAG-{idx:04d}",
                source_offset=offset,
                size_bytes=len(chunk),
                data=chunk,
                format_hint="png",
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
        """Order PNG fragments: Header/IHDR -> Palette/Ancillary -> IDAT -> IEND."""
        if not fragments:
            return b"", [], [], {"status": "empty"}

        # Categorize
        header_frags: list[FragmentCandidate] = []
        ihdr_frags: list[FragmentCandidate] = []
        idat_frags: list[FragmentCandidate] = []
        ancillary_frags: list[FragmentCandidate] = []
        footer_frags: list[FragmentCandidate] = []
        unassigned: list[FragmentCandidate] = []

        for f in fragments:
            if f.is_header or "PNG_HEADER" in f.tokens:
                header_frags.append(f)
            elif "IHDR" in f.tokens:
                ihdr_frags.append(f)
            elif "IDAT" in f.tokens:
                idat_frags.append(f)
            elif f.is_footer or "IEND" in f.tokens:
                footer_frags.append(f)
            elif "PLTE" in f.tokens or f.structural_role in ("plte", "ancillary"):
                ancillary_frags.append(f)
            else:
                unassigned.append(f)

        # Assemble logically
        ordered: list[FragmentCandidate] = []
        ordered.extend(header_frags)
        ordered.extend(ihdr_frags)
        ordered.extend(ancillary_frags)
        ordered.extend(idat_frags)
        ordered.extend(unassigned)
        ordered.extend(footer_frags)

        placed_ids = [f.fragment_id for f in ordered]
        unplaced_ids: list[str] = []

        reconstructed_bytes = b"".join(f.data for f in ordered)
        validation = self.validate(reconstructed_bytes)

        return (
            reconstructed_bytes,
            placed_ids,
            unplaced_ids,
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

        # 1. Magic bytes
        if data.startswith(_PNG_MAGIC):
            checks_passed.append("header_magic")
        else:
            checks_failed.append("header_magic")
            errors.append("Invalid PNG magic bytes")
            return ValidationResult(
                is_valid=False,
                format_name=self.format_name,
                integrity_score=0.0,
                checks_failed=tuple(checks_failed),
                errors=tuple(errors),
            )

        # 2. Walk chunks
        offset = 8
        found_ihdr = False
        found_iend = False
        idat_count = 0
        chunk_crc_errors = 0
        chunks_parsed = 0

        while offset + 8 <= len(data):
            try:
                length, chunk_type = struct.unpack(">I4s", data[offset : offset + 8])
            except struct.error:
                errors.append(f"Malformed chunk header at offset {offset}")
                break

            offset += 8
            if offset + length + 4 > len(data):
                warnings.append(
                    f"Truncated chunk {chunk_type.decode('latin1', errors='replace')} at offset {offset}"
                )
                break

            chunk_data = data[offset : offset + length]
            offset += length
            (stored_crc,) = struct.unpack(">I", data[offset : offset + 4])
            offset += 4

            # Verify CRC32
            calc_crc = zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF
            if calc_crc != stored_crc:
                chunk_crc_errors += 1
                warnings.append(
                    f"CRC32 mismatch in chunk {chunk_type.decode('latin1', errors='replace')}: "
                    f"stored {hex(stored_crc)} != calculated {hex(calc_crc)}"
                )

            chunks_parsed += 1

            if chunk_type == b"IHDR":
                found_ihdr = True
                if len(chunk_data) >= 13:
                    w, h, depth, color, comp, filt, inter = struct.unpack(">IIBBBBB", chunk_data[:13])
                    metadata["width"] = w
                    metadata["height"] = h
                    metadata["bit_depth"] = depth
                    metadata["color_type"] = color
            elif chunk_type == b"IDAT":
                idat_count += 1
            elif chunk_type == b"IEND":
                found_iend = True
                break

        if found_ihdr:
            checks_passed.append("ihdr_chunk")
        else:
            checks_failed.append("ihdr_chunk")
            errors.append("Missing mandatory IHDR chunk")

        if idat_count > 0:
            checks_passed.append("idat_chunks")
            metadata["idat_count"] = idat_count
        else:
            checks_failed.append("idat_chunks")
            errors.append("No IDAT image data chunks found")

        if found_iend:
            checks_passed.append("iend_chunk")
        else:
            checks_failed.append("iend_chunk")
            errors.append("Missing mandatory IEND terminator chunk")

        if chunk_crc_errors == 0 and chunks_parsed > 0:
            checks_passed.append("crc32_checksums")
        elif chunk_crc_errors > 0:
            checks_failed.append("crc32_checksums")

        # Scoring
        score = 0.0
        if "header_magic" in checks_passed:
            score += 0.25
        if "ihdr_chunk" in checks_passed:
            score += 0.25
        if "idat_chunks" in checks_passed:
            score += 0.25
        if "iend_chunk" in checks_passed:
            score += 0.15
        if "crc32_checksums" in checks_passed:
            score += 0.10

        is_valid = ("header_magic" in checks_passed) and found_ihdr and (idat_count > 0) and found_iend

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
