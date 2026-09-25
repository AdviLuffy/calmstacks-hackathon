"""Blind fragment scanning of an evidence image.

The evidence file is opened read-only and never modified. Nothing is inferred
about content: fragments are carved at fixed block boundaries and hashed. No
label, path, timestamp or classification is assigned to a fragment.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .constants import BLOCK_SIZE
from .hashing import sha256_bytes, sha256_file
from .models import Fragment, make_fragment_id

__all__ = ["ScanResult", "scan_media"]


@dataclass(frozen=True)
class ScanResult:
    """Outcome of scanning one evidence image."""

    media_size_bytes: int
    media_sha256: str
    fragments: tuple[Fragment, ...]
    warnings: tuple[str, ...]

    def to_dict(self) -> dict:
        return {
            "media_size_bytes": self.media_size_bytes,
            "media_sha256": self.media_sha256,
            "fragments": [fragment.to_dict() for fragment in self.fragments],
            "warnings": list(self.warnings),
        }


def scan_media(media_path: str | Path, block_size: int = BLOCK_SIZE) -> ScanResult:
    """Carve an evidence image into fixed-size fragments.

    The image is streamed so a large image is never fully resident in memory, and
    it is opened ``"rb"`` only so the evidence is preserved byte-for-byte.
    """
    if block_size <= 0:
        raise ValueError("block_size must be > 0")

    path = Path(media_path)
    fragments: list[Fragment] = []
    warnings: list[str] = []
    offset = 0

    with open(path, "rb") as handle:
        while True:
            block = handle.read(block_size)
            if not block:
                break

            start = offset
            end = offset + len(block)
            offset = end

            block_warnings: tuple[str, ...] = ()
            if len(block) < block_size:
                message = (
                    f"partial trailing block at byte_range [{start}, {end}): "
                    f"{len(block)} of {block_size} bytes"
                )
                block_warnings = (message,)
                warnings.append(message)

            digest = sha256_bytes(block)
            fragments.append(
                Fragment(
                    fragment_id=make_fragment_id(digest, start, end),
                    byte_range=(start, end),
                    bytes_sha256=digest,
                    warnings=block_warnings,
                )
            )

    if offset == 0:
        warnings.append("media is empty: no fragments carved")

    return ScanResult(
        media_size_bytes=offset,
        media_sha256=sha256_file(path),
        fragments=tuple(fragments),
        warnings=tuple(warnings),
    )
