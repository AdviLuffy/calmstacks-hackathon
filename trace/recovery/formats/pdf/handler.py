"""Format handler for PDF recovery, wrapping and extending the deterministic P1 engine."""

from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[4]
EVIDENCE_SRC = REPO_ROOT / "evidence" / "src"
if str(EVIDENCE_SRC) not in sys.path:
    sys.path.insert(0, str(EVIDENCE_SRC))

from trace.recovery.formats.base import BaseFormatHandler
from trace.recovery.models import FormatConfidence, FragmentCandidate, ValidationResult

try:
    from trace_evidence import constants
    from trace_evidence.pipeline import run_pipeline
    P1_AVAILABLE = True
except ImportError:
    P1_AVAILABLE = False

_PDF_HEADER_RE = re.compile(rb"^%PDF-(\d+\.\d+)")
_PDF_EOF_RE = re.compile(rb"%%EOF")
_PDF_OBJ_RE = re.compile(rb"(\d+)\s+(\d+)\s+obj")
_PDF_XREF_RE = re.compile(rb"xref\s*\r?\n")
_PDF_TRAILER_RE = re.compile(rb"trailer\s*<<")


class PdfFormatHandler(BaseFormatHandler):
    """High-assurance PDF format handler with structural checks and deterministic recovery."""

    format_name = "pdf"
    mime_type = "application/pdf"
    default_extension = ".pdf"

    def identify(self, data: bytes, filename: str = "") -> FormatConfidence:
        if not data:
            return FormatConfidence(self.format_name, self.mime_type, 0.0, "none", is_supported=True)

        indicators: list[str] = []
        confidence = 0.0

        if data[:1024].find(b"%PDF-") != -1:
            indicators.append("magic_bytes:%PDF-")
            confidence += 0.5

        if b"%%EOF" in data[-1024:]:
            indicators.append("eof_marker:%%EOF")
            confidence += 0.3
        elif b"%%EOF" in data:
            indicators.append("eof_marker_embedded")
            confidence += 0.15

        if _PDF_OBJ_RE.search(data):
            indicators.append("pdf_objects_present")
            confidence += 0.2

        if _PDF_TRAILER_RE.search(data) or b"startxref" in data:
            indicators.append("trailer_startxref_present")
            confidence += 0.1

        if filename.lower().endswith(".pdf"):
            indicators.append("extension:.pdf")
            confidence += 0.1

        confidence = min(1.0, max(0.0, confidence))
        detected_by = "magic_bytes" if "%PDF-" in str(indicators) else "tokens"

        return FormatConfidence(
            format_name=self.format_name,
            mime_type=self.mime_type,
            confidence=confidence,
            detected_by=detected_by,
            structural_indicators=tuple(indicators),
            is_supported=True,
            details={"has_header": "%PDF-" in str(indicators), "has_eof": "%%EOF" in str(indicators)},
        )

    def carve_fragments(
        self, stream: bytes, block_size: int | None = None
    ) -> list[FragmentCandidate]:
        if not stream:
            return []

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

            if chunk.startswith(b"%PDF-") or b"%PDF-" in chunk:
                tokens.append("HEADER")
                role = "header"
                is_header = True
            if b"obj" in chunk and b"endobj" in chunk:
                tokens.append("OBJECT")
                role = "object"
            if b"xref" in chunk:
                tokens.append("XREF")
                role = "xref"
            if b"trailer" in chunk:
                tokens.append("TRAILER")
                role = "trailer"
            if b"startxref" in chunk:
                tokens.append("STARTXREF")
                role = "startxref"
            if b"%%EOF" in chunk:
                tokens.append("EOF")
                role = "footer"
                is_footer = True

            frag = FragmentCandidate(
                fragment_id=f"FRAG-{idx:04d}",
                source_offset=offset,
                size_bytes=len(chunk),
                data=chunk,
                format_hint="pdf",
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
        if not fragments:
            return b"", [], [], {"status": "empty"}

        # Run authentic P1 pipeline by serializing fragments into temp media file
        if P1_AVAILABLE:
            try:
                with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as tf:
                    for f in fragments:
                        tf.write(f.data)
                    tmp_media = Path(tf.name)

                try:
                    # Detect block size
                    bs = fragments[0].size_bytes if fragments else 256
                    pipe_res = run_pipeline(tmp_media, block_size=bs)
                    recon = pipe_res.reconstruction
                    placed = list(recon.fragment_order)
                    # Map placed indices back to fragment IDs
                    frag_id_map = {f.fragment_id: f for f in fragments}
                    unplaced = [f.fragment_id for f in fragments if f.fragment_id not in placed]

                    return (
                        recon.raw_bytes,
                        placed,
                        unplaced,
                        {
                            "status": recon.status,
                            "complete": recon.complete,
                            "validation": {
                                "is_valid": recon.validation.is_valid,
                                "errors": list(recon.validation.errors),
                            },
                        },
                    )
                finally:
                    if tmp_media.is_file():
                        tmp_media.unlink()
            except Exception:
                pass

        # Fallback greedy ordering
        header_frags = [f for f in fragments if f.is_header]
        footer_frags = [f for f in fragments if f.is_footer]
        middle_frags = [f for f in fragments if not f.is_header and not f.is_footer]

        ordered = header_frags + middle_frags + footer_frags
        reconstructed_bytes = b"".join(f.data for f in ordered)
        placed_ids = [f.fragment_id for f in ordered]

        return reconstructed_bytes, placed_ids, [], {"status": "greedy_order"}

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

        # 1. Header check
        header_idx = data[:1024].find(b"%PDF-")
        if header_idx != -1:
            checks_passed.append("header_magic")
            match = _PDF_HEADER_RE.search(data[header_idx : header_idx + 20])
            version = match.group(1).decode("ascii") if match else "unknown"
        else:
            checks_failed.append("header_magic")
            errors.append("Missing %PDF- header within first 1024 bytes")
            version = "none"

        # 2. EOF check
        eof_idx = data.rfind(b"%%EOF")
        if eof_idx != -1:
            checks_passed.append("eof_marker")
            trailing_len = len(data) - (eof_idx + 5)
            if trailing_len > 1024:
                warnings.append(f"Excess trailing data after %%EOF ({trailing_len} bytes)")
        else:
            checks_failed.append("eof_marker")
            errors.append("Missing %%EOF marker in byte stream")

        # 3. Object syntax check
        obj_matches = list(_PDF_OBJ_RE.finditer(data))
        endobj_count = len(re.findall(rb"endobj", data))
        if obj_matches:
            checks_passed.append("pdf_objects")
            if abs(len(obj_matches) - endobj_count) > 2:
                warnings.append(
                    f"Mismatched object markers: {len(obj_matches)} obj vs {endobj_count} endobj"
                )
        else:
            checks_failed.append("pdf_objects")
            errors.append("No valid PDF objects found")

        # 4. Trailer / Cross-reference check
        has_xref = b"xref" in data
        has_trailer = b"trailer" in data
        has_startxref = b"startxref" in data

        if has_xref or has_trailer or has_startxref:
            checks_passed.append("cross_reference_structure")
        else:
            warnings.append("No explicit cross-reference table or trailer found (possible partial stream)")

        # Compute integrity score
        score = 0.0
        if "header_magic" in checks_passed:
            score += 0.35
        if "eof_marker" in checks_passed:
            score += 0.35
        if "pdf_objects" in checks_passed:
            score += 0.20
        if "cross_reference_structure" in checks_passed:
            score += 0.10

        is_valid = ("header_magic" in checks_passed) and ("eof_marker" in checks_passed) and ("pdf_objects" in checks_passed)

        return ValidationResult(
            is_valid=is_valid,
            format_name=self.format_name,
            integrity_score=round(score, 2),
            checks_passed=tuple(checks_passed),
            checks_failed=tuple(checks_failed),
            errors=tuple(errors),
            warnings=tuple(warnings),
            metadata={"pdf_version": version, "objects_found": len(obj_matches), "size_bytes": len(data)},
        )
