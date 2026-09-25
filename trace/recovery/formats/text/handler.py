"""Plain text and structured log format handler: encoding validation, timestamp extraction, and chronological reordering."""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

from trace.recovery.formats.base import BaseFormatHandler
from trace.recovery.models import FormatConfidence, FragmentCandidate, ValidationResult

_ISO_TS_RE = re.compile(rb"(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?)")
_SYSLOG_TS_RE = re.compile(rb"([A-Z][a-z]{2}\s+\d+\s+\d{2}:\d{2}:\d{2})")
_CLF_TS_RE = re.compile(rb"\[(\d{2}/[A-Z][a-z]{2}/\d{4}:\d{2}:\d{2}:\d{2})")


class TextFormatHandler(BaseFormatHandler):
    """High-assurance plain text and chronological log file recovery engine."""

    format_name = "text"
    mime_type = "text/plain"
    default_extension = ".txt"

    def identify(self, data: bytes, filename: str = "") -> FormatConfidence:
        if not data:
            return FormatConfidence(self.format_name, self.mime_type, 0.0, "none", is_supported=True)

        # Check printable character ratio
        printable_count = sum(1 for b in data if 32 <= b <= 126 or b in (9, 10, 13))
        ratio = printable_count / len(data)

        indicators: list[str] = []
        confidence = 0.0
        is_log = False

        if ratio > 0.95:
            indicators.append(f"printable_ratio:{ratio:.2f}")
            confidence += 0.5
        elif ratio > 0.80:
            indicators.append(f"printable_ratio:{ratio:.2f}")
            confidence += 0.3

        # Check for log timestamps
        if _ISO_TS_RE.search(data):
            indicators.append("timestamp:ISO8601")
            is_log = True
            confidence += 0.3
        elif _SYSLOG_TS_RE.search(data):
            indicators.append("timestamp:Syslog")
            is_log = True
            confidence += 0.3
        elif _CLF_TS_RE.search(data):
            indicators.append("timestamp:CommonLogFormat")
            is_log = True
            confidence += 0.3

        if filename.lower().endswith(".log"):
            indicators.append("extension:.log")
            is_log = True
            confidence += 0.1
        elif filename.lower().endswith((".txt", ".json", ".csv", ".xml")):
            indicators.append("extension:text")
            confidence += 0.1

        confidence = min(1.0, max(0.0, confidence))
        fmt = "log" if is_log else "text"
        return FormatConfidence(
            format_name=fmt,
            mime_type="text/plain",
            confidence=confidence,
            detected_by="timestamps" if is_log else "printable_characters",
            structural_indicators=tuple(indicators),
            is_supported=True,
            details={"is_log": is_log, "printable_ratio": round(ratio, 2)},
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
            role = "text_line"

            ts_match = _ISO_TS_RE.search(chunk) or _SYSLOG_TS_RE.search(chunk)
            if ts_match:
                tokens.append("TIMESTAMP")
                role = "log_entry"

            frag = FragmentCandidate(
                fragment_id=f"TXT-FRAG-{idx:04d}",
                source_offset=offset,
                size_bytes=len(chunk),
                data=chunk,
                format_hint="text",
                structural_role=role,
                tokens=tuple(tokens),
                known_sequence_index=idx,
            )
            fragments.append(frag)
            offset += bs
            idx += 1

        return fragments

    def order_and_reconstruct(
        self, fragments: Sequence[FragmentCandidate]
    ) -> tuple[bytes, list[str], list[str], dict[str, Any]]:
        """Order text/log fragments. For logs, sorts by earliest extracted timestamp in each fragment."""
        if not fragments:
            return b"", [], [], {"status": "empty"}

        # Extract timestamps for each fragment to evaluate chronological sort
        ts_keyed: list[tuple[bytes | None, FragmentCandidate]] = []
        for f in fragments:
            m = _ISO_TS_RE.search(f.data) or _SYSLOG_TS_RE.search(f.data) or _CLF_TS_RE.search(f.data)
            ts_val = m.group(1) if m else None
            ts_keyed.append((ts_val, f))

        has_timestamps = any(t[0] is not None for t in ts_keyed)
        if has_timestamps:
            # Sort by timestamp when available, preserving relative order for non-timestamped
            ordered_frags = sorted(
                ts_keyed,
                key=lambda x: (x[0] is None, x[0] or b"", x[1].source_offset),
            )
            ordered = [t[1] for t in ordered_frags]
        else:
            ordered = list(fragments)

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

        # 1. Encoding check
        try:
            decoded = data.decode("utf-8")
            checks_passed.append("utf8_decodable")
        except UnicodeDecodeError:
            try:
                decoded = data.decode("latin-1")
                checks_passed.append("latin1_fallback")
                warnings.append("Data required Latin-1 fallback decoding")
            except Exception as e:
                checks_failed.append("text_encoding")
                errors.append(f"Text decoding failed: {e}")
                return ValidationResult(
                    is_valid=False,
                    format_name=self.format_name,
                    integrity_score=0.0,
                    checks_failed=tuple(checks_failed),
                    errors=tuple(errors),
                )

        # 2. Line integrity
        lines = decoded.splitlines()
        checks_passed.append("line_structure")

        score = 0.5
        if "utf8_decodable" in checks_passed:
            score += 0.3
        if len(lines) > 0:
            score += 0.2

        return ValidationResult(
            is_valid=True,
            format_name=self.format_name,
            integrity_score=round(score, 2),
            checks_passed=tuple(checks_passed),
            checks_failed=tuple(checks_failed),
            errors=tuple(errors),
            warnings=tuple(warnings),
            metadata={"lines_count": len(lines), "size_bytes": len(data)},
        )
