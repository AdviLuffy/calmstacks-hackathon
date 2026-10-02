"""PNG format handler: chunk-level parsing, CRC-32 validation, and reconstruction."""

from __future__ import annotations

import base64
import struct
from typing import Any, Mapping, Sequence
import zlib

from trace.recovery.formats.base import BaseFormatHandler
from trace.recovery.models import (
    FormatConfidence,
    FormatRecoveryResult,
    FragmentCandidate,
    RecoveryCategory,
    ValidationResult,
)

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

    def repair_or_recover(
        self, data: bytes, filename: str = "", **kwargs: Any
    ) -> FormatRecoveryResult:
        """Deeply analyze and deterministically repair corrupted PNG image data."""
        if not data:
            val = self.validate(b"")
            return FormatRecoveryResult(
                format_name=self.format_name,
                is_recovered=False,
                is_openable=False,
                repaired_bytes=b"",
                authentic_bytes=b"",
                confidence_score=0.0,
                category=RecoveryCategory.UNRECOVERABLE,
                validation=val,
                operations_performed=[],
                unsupported_capabilities=["empty_input"],
            )

        operations: list[str] = []
        authentic_bytes = data
        repaired = bytearray(data)

        # 1. Preamble stripping / Magic bytes repair
        magic_idx = repaired.find(_PNG_MAGIC)
        if magic_idx > 0:
            repaired = repaired[magic_idx:]
            operations.append(f"stripped_preamble_garbage_{magic_idx}_bytes")
        elif magic_idx == -1:
            ihdr_idx = repaired.find(b"IHDR")
            if ihdr_idx != -1 and ihdr_idx >= 4:
                # Prepend PNG magic
                repaired = bytearray(_PNG_MAGIC) + repaired[ihdr_idx - 4:]
                operations.append("synthesized_missing_png_signature")
            elif ihdr_idx != -1:
                # IHDR is right at offset 0
                repaired = bytearray(_PNG_MAGIC + b"\x00\x00\x00\x0d") + repaired
                operations.append("synthesized_missing_png_signature_and_ihdr_len")

        # 2. Parse chunks, repair corrupted CRCs, and detect truncated chunks
        offset = 8  # Skip magic
        rebuilt_chunks = bytearray(_PNG_MAGIC)
        has_ihdr = False
        has_idat = False
        has_iend = False
        idat_count = 0

        while offset < len(repaired):
            if offset + 8 > len(repaired):
                break
            chunk_len = struct.unpack(">I", repaired[offset : offset + 4])[0]
            chunk_type = bytes(repaired[offset + 4 : offset + 8])

            # Check if chunk type is ASCII alpha
            if not all(65 <= b <= 90 or 97 <= b <= 122 for b in chunk_type):
                # Corrupted chunk marker; scan forward to next known marker
                next_marker = -1
                for known in (b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tEXt", b"sRGB", b"gAMA"):
                    pos = repaired.find(known, offset + 1)
                    if pos != -1 and (next_marker == -1 or pos < next_marker):
                        next_marker = pos
                if next_marker != -1 and next_marker >= 4:
                    offset = next_marker - 4
                    operations.append("resynchronized_corrupted_chunk_boundary")
                    continue
                else:
                    break

            if chunk_type == b"IHDR":
                has_ihdr = True
            elif chunk_type == b"IDAT":
                has_idat = True
                idat_count += 1
            elif chunk_type == b"IEND":
                has_iend = True

            data_start = offset + 8
            data_end = data_start + chunk_len
            if data_end > len(repaired):
                # Truncated chunk data: salvage surviving portion
                surviving_data = repaired[data_start:]
                calc_crc = zlib.crc32(chunk_type + surviving_data) & 0xFFFFFFFF
                rebuilt_chunks.extend(struct.pack(">I", len(surviving_data)))
                rebuilt_chunks.extend(chunk_type)
                rebuilt_chunks.extend(surviving_data)
                rebuilt_chunks.extend(struct.pack(">I", calc_crc))
                operations.append(f"salvaged_truncated_{chunk_type.decode('ascii', 'ignore')}_chunk")
                offset = len(repaired)
                break

            chunk_data = repaired[data_start:data_end]
            crc_bytes = repaired[data_end : data_end + 4] if data_end + 4 <= len(repaired) else b""
            stored_crc = struct.unpack(">I", crc_bytes)[0] if len(crc_bytes) == 4 else None
            calc_crc = zlib.crc32(chunk_type + chunk_data) & 0xFFFFFFFF

            if stored_crc is None or stored_crc != calc_crc:
                operations.append(f"recalculated_crc_{chunk_type.decode('ascii', 'ignore')}")

            rebuilt_chunks.extend(struct.pack(">I", chunk_len))
            rebuilt_chunks.extend(chunk_type)
            rebuilt_chunks.extend(chunk_data)
            rebuilt_chunks.extend(struct.pack(">I", calc_crc))

            offset = data_end + 4
            if chunk_type == b"IEND":
                break

        # 3. Synthesize missing IEND if needed
        if not has_iend:
            rebuilt_chunks.extend(b"\x00\x00\x00\x00IEND\xaeB`\x82")
            operations.append("synthesized_missing_iend_chunk")

        repaired_bytes = bytes(rebuilt_chunks)
        val = self.validate(repaired_bytes)

        # Test openability with PyMuPDF Pixmap
        is_openable = False
        width = 0
        height = 0
        channels = 0
        try:
            import pymupdf
            pix = pymupdf.Pixmap(repaired_bytes)
            if pix.width > 0 and pix.height > 0:
                is_openable = True
                width = pix.width
                height = pix.height
                channels = pix.n
        except Exception:
            is_openable = val.is_valid

        synth_count = max(0, len(repaired_bytes) - len(authentic_bytes))
        cat = (
            RecoveryCategory.RECOVERED
            if is_openable
            else (RecoveryCategory.PARTIAL if has_ihdr else RecoveryCategory.UNRECOVERABLE)
        )

        preview_data = (
            f"data:image/png;base64,{base64.b64encode(repaired_bytes).decode('ascii')}"
            if is_openable
            else ""
        )

        return FormatRecoveryResult(
            format_name=self.format_name,
            is_recovered=is_openable or val.is_valid,
            is_openable=is_openable,
            repaired_bytes=repaired_bytes,
            authentic_bytes=authentic_bytes,
            authentic_bytes_count=len(authentic_bytes),
            synthesized_bytes_count=synth_count,
            confidence_score=max(val.integrity_score * 100.0, 85.0 if is_openable else 20.0),
            category=cat,
            validation=val,
            operations_performed=operations,
            unsupported_capabilities=[
                "interlaced_adam7_missing_pass_interpolation",
                "deflate_window_corruption",
            ],
            diagnostics={
                "width": width or val.metadata.get("width", 0),
                "height": height or val.metadata.get("height", 0),
                "channels": channels,
                "has_ihdr": has_ihdr,
                "has_idat": has_idat,
                "idat_chunks_count": idat_count,
            },
            preview_type="image" if is_openable else "none",
            preview_data=preview_data,
        )

