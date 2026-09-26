"""Provenance tracking and integrity verification engine.

INTERNAL ONLY. This module builds complete byte provenance mapping reconstructed
bytes back to source fragments, and performs independent byte-for-byte verification
against a caller-supplied original.

Honesty invariants:
1. Every output byte maps back to its originating fragment and source media byte offset.
   Provenance is complete and contiguous over the reconstructed byte sequence.
2. Only an integrity report may say 'verified', and only after an independent
   byte-for-byte comparison against a known original. Without an original, status
   remains 'structurally_valid' and never claims verification.
3. Incomplete or failed reconstructions are NEVER promoted to 'verified', even if an
   original is supplied.
4. Zero oracle pollution: this module does not access the filesystem, manifests,
   or groundtruth fixtures. All original comparisons are caller-controlled.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .constants import (
    RECOVERY_COMPLETE_VERIFIED,
    RECOVERY_CORRUPTED,
    RECOVERY_PARTIAL,
    RECOVERY_UNRECOVERABLE,
    STATUS_FAILED,
    STATUS_INCOMPLETE,
    STATUS_STRUCTURALLY_VALID,
    STATUS_VERIFIED,
)
from .hashing import sha256_bytes
from .models import Fragment
from .reconstruction import ReconstructionResult, StructureValidationResult

__all__ = [
    "ByteProvenance",
    "IntegrityReport",
    "build_provenance",
    "verify_integrity",
]


@dataclass(frozen=True)
class ByteProvenance:
    """One contiguous byte range of the reconstructed file mapped to its source fragment."""

    output_range: tuple[int, int]
    fragment_id: str
    source_range: tuple[int, int]
    bytes_sha256: str
    size_bytes: int

    def __post_init__(self) -> None:
        if len(self.output_range) != 2 or len(self.source_range) != 2:
            raise ValueError("byte ranges must contain exactly two values [start, end)")
        out_start, out_end = self.output_range
        src_start, src_end = self.source_range
        if out_start < 0 or out_end <= out_start:
            raise ValueError(f"invalid output_range: {self.output_range}")
        if src_start < 0 or src_end <= src_start:
            raise ValueError(f"invalid source_range: {self.source_range}")
        if (out_end - out_start) != self.size_bytes:
            raise ValueError(
                f"output_range span {out_end - out_start} does not match size_bytes={self.size_bytes}"
            )
        if (src_end - src_start) != self.size_bytes:
            raise ValueError(
                f"source_range span {src_end - src_start} does not match size_bytes={self.size_bytes}"
            )


@dataclass(frozen=True)
class IntegrityReport:
    """Comprehensive integrity, provenance, and verification report."""

    status: str
    reconstructed_size_bytes: int
    reconstructed_sha256: str
    provenance: tuple[ByteProvenance, ...]
    structural_validation: StructureValidationResult
    verified_against_original: bool = False
    original_sha256: str | None = None
    byte_match: bool | None = None
    warnings: tuple[str, ...] = ()
    recovery_state: str = RECOVERY_UNRECOVERABLE
    missing_elements: tuple[str, ...] = ()
    corrupted_fragment_ids: tuple[str, ...] = ()

    @property
    def is_verified(self) -> bool:
        """True if and only if byte-for-byte verified against a known original."""
        return self.status == STATUS_VERIFIED and self.byte_match is True

    def to_dict(self) -> dict:
        """Human-readable dictionary representation."""
        return {
            "status": self.status,
            "recovery_state": self.recovery_state,
            "reconstructed_size_bytes": self.reconstructed_size_bytes,
            "reconstructed_sha256": self.reconstructed_sha256,
            "verified_against_original": self.verified_against_original,
            "original_sha256": self.original_sha256,
            "byte_match": self.byte_match,
            "missing_elements": list(self.missing_elements),
            "corrupted_fragment_ids": list(self.corrupted_fragment_ids),
            "provenance": [
                {
                    "output_range": list(p.output_range),
                    "fragment_id": p.fragment_id,
                    "source_range": list(p.source_range),
                    "bytes_sha256": p.bytes_sha256,
                    "size_bytes": p.size_bytes,
                }
                for p in self.provenance
            ],
            "structural_validation": {
                "is_valid": self.structural_validation.is_valid,
                "status": self.structural_validation.status,
                "startxref_offset": self.structural_validation.startxref_offset,
                "object_offsets": [list(item) for item in self.structural_validation.object_offsets],
                "errors": list(self.structural_validation.errors),
            },
            "warnings": list(self.warnings),
        }


def build_provenance(
    fragment_order: Sequence[str],
    fragments: Sequence[Fragment],
    total_output_size: int,
) -> tuple[ByteProvenance, ...]:
    """Build complete, contiguous provenance mapping output byte ranges to source fragments.

    Validates that:
    1. Fragment IDs in fragment_order are unique.
    2. Every fragment ID exists in fragments.
    3. Output byte ranges are contiguous with no gaps or overlaps.
    4. Total provenance span matches total_output_size exactly.
    """
    seen_ids: set[str] = set()
    for fid in fragment_order:
        if fid in seen_ids:
            raise ValueError(f"duplicate fragment ID in fragment_order: {fid}")
        seen_ids.add(fid)

    fragments_by_id: dict[str, Fragment] = {}
    for f in fragments:
        if f.fragment_id in fragments_by_id:
            raise ValueError(f"duplicate fragment ID in fragments sequence: {f.fragment_id}")
        fragments_by_id[f.fragment_id] = f

    records: list[ByteProvenance] = []
    current_offset = 0

    for fid in fragment_order:
        if fid not in fragments_by_id:
            raise ValueError(f"fragment ID {fid} not found in fragments sequence")
        frag = fragments_by_id[fid]
        start = current_offset
        end = current_offset + frag.size_bytes
        records.append(
            ByteProvenance(
                output_range=(start, end),
                fragment_id=frag.fragment_id,
                source_range=frag.byte_range,
                bytes_sha256=frag.bytes_sha256,
                size_bytes=frag.size_bytes,
            )
        )
        current_offset = end

    if current_offset != total_output_size:
        raise ValueError(
            f"provenance total size ({current_offset}) does not match output size ({total_output_size})"
        )

    for prev, curr in zip(records, records[1:]):
        if prev.output_range[1] != curr.output_range[0]:
            raise ValueError(
                f"gap in provenance: {prev.output_range[1]} != {curr.output_range[0]}"
            )

    return tuple(records)


def verify_integrity(
    reconstruction: ReconstructionResult,
    fragments: Sequence[Fragment],
    original_bytes: bytes | None = None,
) -> IntegrityReport:
    """Verify reconstruction integrity and provenance, and optionally verify against an original.

    Caller-controlled: original_bytes is provided only in tests/evaluation. Production
    code never reads groundtruth files.
    """
    provenance = build_provenance(
        reconstruction.fragment_order,
        fragments,
        len(reconstruction.raw_bytes),
    )

    reconstructed_sha256 = sha256_bytes(reconstruction.raw_bytes)
    status = reconstruction.status
    warnings = list(reconstruction.warnings)

    missing_elements = getattr(reconstruction, "missing_elements", ())
    corrupted_fragment_ids = getattr(reconstruction, "corrupted_fragment_ids", ())
    recovery_state = getattr(reconstruction, "recovery_state", RECOVERY_UNRECOVERABLE)

    if original_bytes is None:
        return IntegrityReport(
            status=status,
            reconstructed_size_bytes=len(reconstruction.raw_bytes),
            reconstructed_sha256=reconstructed_sha256,
            provenance=provenance,
            structural_validation=reconstruction.validation,
            verified_against_original=False,
            original_sha256=None,
            byte_match=None,
            warnings=tuple(warnings),
            recovery_state=recovery_state,
            missing_elements=missing_elements,
            corrupted_fragment_ids=corrupted_fragment_ids,
        )

    # An original was supplied for independent verification
    original_sha256 = sha256_bytes(original_bytes)
    byte_match = (reconstruction.raw_bytes == original_bytes)

    if byte_match:
        # Invariant: Never promote incomplete or failed reconstruction to verified
        if reconstruction.status == STATUS_STRUCTURALLY_VALID and reconstruction.complete:
            status = STATUS_VERIFIED
            recovery_state = RECOVERY_COMPLETE_VERIFIED
        else:
            warnings.append(
                f"byte match holds but reconstruction status is {reconstruction.status!r}; not verified"
            )
            recovery_state = (
                RECOVERY_PARTIAL
                if reconstruction.status == STATUS_INCOMPLETE and len(reconstruction.raw_bytes) > 0
                else getattr(reconstruction, "recovery_state", RECOVERY_UNRECOVERABLE)
            )
    else:
        # Check if incomplete reconstruction authentically matches prefix of original
        if (
            reconstruction.status == STATUS_INCOMPLETE
            and len(reconstruction.raw_bytes) > 0
            and len(reconstruction.raw_bytes) < len(original_bytes)
            and original_bytes[:len(reconstruction.raw_bytes)] == reconstruction.raw_bytes
        ):
            status = STATUS_INCOMPLETE
            recovery_state = RECOVERY_PARTIAL
            warnings.append(
                f"partial reconstruction matches original prefix ({len(reconstruction.raw_bytes)} of "
                f"{len(original_bytes)} bytes recovered); missing fragments prevent full file match"
            )
        else:
            status = STATUS_FAILED
            recovery_state = RECOVERY_CORRUPTED
            mismatch_offset = next(
                (
                    i
                    for i, (a, b) in enumerate(
                        zip(reconstruction.raw_bytes, original_bytes)
                    )
                    if a != b
                ),
                min(len(reconstruction.raw_bytes), len(original_bytes)),
            )
            warnings.append(
                f"byte mismatch against original at offset {mismatch_offset} "
                f"(lengths: reconstructed={len(reconstruction.raw_bytes)}, original={len(original_bytes)})"
            )

    return IntegrityReport(
        status=status,
        reconstructed_size_bytes=len(reconstruction.raw_bytes),
        reconstructed_sha256=reconstructed_sha256,
        provenance=provenance,
        structural_validation=reconstruction.validation,
        verified_against_original=True,
        original_sha256=original_sha256,
        byte_match=byte_match,
        warnings=tuple(warnings),
        recovery_state=recovery_state,
        missing_elements=missing_elements,
        corrupted_fragment_ids=corrupted_fragment_ids,
    )
