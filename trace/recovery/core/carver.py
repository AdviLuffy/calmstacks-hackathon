"""Core multi-format file carver: signature-driven extraction and boundary analysis."""

from __future__ import annotations

import hashlib
import re
from typing import Sequence

from trace.recovery.formats.base import BaseFormatHandler
from trace.recovery.formats.jpeg.handler import JpegFormatHandler
from trace.recovery.formats.pdf.handler import PdfFormatHandler
from trace.recovery.formats.png.handler import PngFormatHandler
from trace.recovery.formats.text.handler import TextFormatHandler
from trace.recovery.formats.zip.handler import ZipFormatHandler
from trace.recovery.models import (
    FormatConfidence,
    FragmentCandidate,
    RecoveredArtifact,
    RecoveryCategory,
)


class MultiFormatCarver:
    """High-assurance multi-format file carver for raw disks and fragmented evidence."""

    def __init__(self, handlers: Sequence[BaseFormatHandler] | None = None) -> None:
        self.handlers: list[BaseFormatHandler] = list(
            handlers
            or [
                PdfFormatHandler(),
                PngFormatHandler(),
                JpegFormatHandler(),
                ZipFormatHandler(),
                TextFormatHandler(),
            ]
        )

    def identify_format(self, data: bytes, filename: str = "") -> FormatConfidence:
        """Evaluate format handlers to find the best match."""
        best: FormatConfidence = FormatConfidence(
            format_name="binary",
            mime_type="application/octet-stream",
            confidence=0.0,
            detected_by="default",
            is_supported=False,
        )

        for handler in self.handlers:
            conf = handler.identify(data, filename)
            if conf.confidence > best.confidence:
                best = conf

        return best

    def carve_raw_stream(
        self, stream: bytes, max_artifacts: int = 50
    ) -> list[RecoveredArtifact]:
        """Carve recognizable file artifacts from an unformatted raw byte stream or disk image."""
        if not stream:
            return []

        artifacts: list[RecoveredArtifact] = []

        # 1. Carve PDFs: %PDF- ... %%EOF
        for m in re.finditer(rb"%PDF-(\d+\.\d+)", stream):
            if len(artifacts) >= max_artifacts:
                break
            start = m.start()
            eof_match = re.search(rb"%%EOF", stream[start:])
            if eof_match:
                end = start + eof_match.end()
                # allow trailing newline if present
                if end < len(stream) and stream[end : end + 2] in (b"\r\n", b"\n\r"):
                    end += 2
                elif end < len(stream) and stream[end : end + 1] in (b"\n", b"\r"):
                    end += 1

                candidate_bytes = stream[start:end]
                pdf_handler = PdfFormatHandler()
                val = pdf_handler.validate(candidate_bytes)
                cat = RecoveryCategory.RECOVERED if val.is_valid else RecoveryCategory.PARTIAL
                artifacts.append(
                    RecoveredArtifact(
                        artifact_id=f"CARVE-PDF-{len(artifacts) + 1:03d}",
                        filename=f"carved_{start:08x}.pdf",
                        format_name="pdf",
                        mime_type="application/pdf",
                        size_bytes=len(candidate_bytes),
                        sha256=hashlib.sha256(candidate_bytes).hexdigest(),
                        category=cat,
                        confidence_score=val.integrity_score * 100.0,
                        format_confidence=val.integrity_score * 100.0,
                        authentic_recovery_pct=None,
                        completeness="COMPLETE" if val.is_valid else "PARTIAL",
                        integrity_status="UNVERIFIED",
                        structural_repair="NONE",
                        raw_bytes=candidate_bytes,
                        validation=val,
                        reconstruction_method="signature_carve",
                        explanation=f"Carved PDF from byte offset {start} to {end}",
                        metadata={"source_offset_start": start, "source_offset_end": end},
                    )
                )

        # 2. Carve PNGs: \x89PNG\r\n\x1a\n ... IEND
        png_sig = b"\x89PNG\r\n\x1a\n"
        offset = 0
        while len(artifacts) < max_artifacts:
            start = stream.find(png_sig, offset)
            if start == -1:
                break
            iend_idx = stream.find(b"IEND", start)
            if iend_idx != -1 and iend_idx + 8 <= len(stream):
                end = iend_idx + 8  # 4 bytes type + 4 bytes CRC
                candidate_bytes = stream[start:end]
                png_handler = PngFormatHandler()
                val = png_handler.validate(candidate_bytes)
                cat = RecoveryCategory.RECOVERED if val.is_valid else RecoveryCategory.PARTIAL
                artifacts.append(
                    RecoveredArtifact(
                        artifact_id=f"CARVE-PNG-{len(artifacts) + 1:03d}",
                        filename=f"carved_{start:08x}.png",
                        format_name="png",
                        mime_type="image/png",
                        size_bytes=len(candidate_bytes),
                        sha256=hashlib.sha256(candidate_bytes).hexdigest(),
                        category=cat,
                        confidence_score=val.integrity_score * 100.0,
                        format_confidence=val.integrity_score * 100.0,
                        authentic_recovery_pct=None,
                        completeness="COMPLETE" if val.is_valid else "PARTIAL",
                        integrity_status="UNVERIFIED",
                        structural_repair="NONE",
                        raw_bytes=candidate_bytes,
                        validation=val,
                        reconstruction_method="signature_carve",
                        explanation=f"Carved PNG from byte offset {start} to {end}",
                        metadata={"source_offset_start": start, "source_offset_end": end},
                    )
                )
                offset = end
            else:
                offset = start + 8

        # 3. Carve JPEGs: \xFF\xD8 ... \xFF\xD9
        jpeg_sig = b"\xff\xd8"
        offset = 0
        while len(artifacts) < max_artifacts:
            start = stream.find(jpeg_sig, offset)
            if start == -1:
                break
            # Find next EOI \xff\xd9 after SOI
            eoi_idx = stream.find(b"\xff\xd9", start + 2)
            if eoi_idx != -1:
                end = eoi_idx + 2
                candidate_bytes = stream[start:end]
                jpeg_handler = JpegFormatHandler()
                val = jpeg_handler.validate(candidate_bytes)
                if val.is_valid or val.integrity_score >= 0.5:
                    cat = RecoveryCategory.RECOVERED if val.is_valid else RecoveryCategory.PARTIAL
                    artifacts.append(
                        RecoveredArtifact(
                            artifact_id=f"CARVE-JPG-{len(artifacts) + 1:03d}",
                            filename=f"carved_{start:08x}.jpg",
                            format_name="jpeg",
                            mime_type="image/jpeg",
                            size_bytes=len(candidate_bytes),
                            sha256=hashlib.sha256(candidate_bytes).hexdigest(),
                            category=cat,
                            confidence_score=val.integrity_score * 100.0,
                            format_confidence=val.integrity_score * 100.0,
                            authentic_recovery_pct=None,
                            completeness="COMPLETE" if val.is_valid else "PARTIAL",
                            integrity_status="UNVERIFIED",
                            structural_repair="NONE",
                            raw_bytes=candidate_bytes,
                            validation=val,
                            reconstruction_method="signature_carve",
                            explanation=f"Carved JPEG from byte offset {start} to {end}",
                            metadata={"source_offset_start": start, "source_offset_end": end},
                        )
                    )
                offset = end
            else:
                offset = start + 2

        # 4. Carve ZIP / DOCX: PK\x03\x04 ... PK\x05\x06 + 22 bytes
        zip_sig = b"PK\x03\x04"
        offset = 0
        while len(artifacts) < max_artifacts:
            start = stream.find(zip_sig, offset)
            if start == -1:
                break
            eocd_idx = stream.find(b"PK\x05\x06", start + 4)
            if eocd_idx != -1 and eocd_idx + 22 <= len(stream):
                end = eocd_idx + 22
                candidate_bytes = stream[start:end]
                zip_handler = ZipFormatHandler()
                val = zip_handler.validate(candidate_bytes)
                if val.is_valid:
                    ext = ".docx" if val.format_name == "docx" else ".zip"
                    mime = (
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                        if val.format_name == "docx"
                        else "application/zip"
                    )
                    artifacts.append(
                        RecoveredArtifact(
                            artifact_id=f"CARVE-ZIP-{len(artifacts) + 1:03d}",
                            filename=f"carved_{start:08x}{ext}",
                            format_name=val.format_name,
                            mime_type=mime,
                            size_bytes=len(candidate_bytes),
                            sha256="",
                            category=RecoveryCategory.RECOVERED,
                            confidence_score=val.integrity_score * 100.0,
                            raw_bytes=candidate_bytes,
                            validation=val,
                            reconstruction_method="signature_carve",
                            explanation=f"Carved {val.format_name.upper()} archive from byte offset {start} to {end}",
                            metadata={"source_offset_start": start, "source_offset_end": end},
                        )
                    )
                    offset = end
                    continue
            offset = start + 4

        # Compute SHA256 for all carved artifacts
        for art in artifacts:
            if not art.sha256 and art.raw_bytes:
                art.sha256 = hashlib.sha256(art.raw_bytes).hexdigest()

        return artifacts
