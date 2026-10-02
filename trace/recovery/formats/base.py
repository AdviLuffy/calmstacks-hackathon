"""Abstract base handler for format-aware carving, reconstruction, and validation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping, Sequence

from trace.recovery.models import (
    FormatConfidence,
    FormatRecoveryResult,
    FragmentCandidate,
    RecoveryCategory,
    ValidationResult,
)


class BaseFormatHandler(ABC):
    """Abstract interface implemented by all format-specific recovery modules."""

    format_name: str = "generic"
    mime_type: str = "application/octet-stream"
    default_extension: str = ".bin"

    @abstractmethod
    def identify(self, data: bytes, filename: str = "") -> FormatConfidence:
        """Analyze data header, tokens, or markers to assess format match confidence."""
        raise NotImplementedError

    @abstractmethod
    def carve_fragments(
        self, stream: bytes, block_size: int | None = None
    ) -> list[FragmentCandidate]:
        """Carve candidate fragments or recognizable structural blocks from raw stream."""
        raise NotImplementedError

    @abstractmethod
    def order_and_reconstruct(
        self, fragments: Sequence[FragmentCandidate]
    ) -> tuple[bytes, list[str], list[str], dict[str, Any]]:
        """Order fragments using format structural constraints.

        Returns:
            (reconstructed_bytes, placed_fragment_ids, unplaced_fragment_ids, metadata)
        """
        raise NotImplementedError

    @abstractmethod
    def validate(self, data: bytes) -> ValidationResult:
        """Deeply inspect byte sequence to verify format conformance and structural validity."""
        raise NotImplementedError

    def repair_or_recover(
        self, data: bytes, filename: str = "", **kwargs: Any
    ) -> FormatRecoveryResult:
        """Analyze, repair structural container/markers, and recover format content."""
        val = self.validate(data)
        return FormatRecoveryResult(
            format_name=self.format_name,
            is_recovered=val.is_valid,
            is_openable=val.is_valid,
            repaired_bytes=data,
            authentic_bytes=data,
            authentic_bytes_count=len(data),
            synthesized_bytes_count=0,
            confidence_score=val.integrity_score * 100.0,
            category=RecoveryCategory.RECOVERED if val.is_valid else RecoveryCategory.PARTIAL,
            validation=val,
            operations_performed=[],
            unsupported_capabilities=[],
            diagnostics={
                "checks_passed": list(val.checks_passed),
                "checks_failed": list(val.checks_failed),
            },
        )

