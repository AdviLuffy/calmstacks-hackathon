"""Abstract base handler for format-aware carving, reconstruction, and validation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping, Sequence

from trace.recovery.models import (
    FormatConfidence,
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
