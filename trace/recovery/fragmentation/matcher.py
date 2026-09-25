"""Advanced fragment alignment: deduplication, variable-length handling, and boundary continuity."""

from __future__ import annotations

import hashlib
from typing import Sequence

from trace.recovery.models import FragmentCandidate


class FragmentMatcher:
    """Manages fragment deduplication, variable block alignment, and boundary stitching."""

    @staticmethod
    def deduplicate(
        fragments: Sequence[FragmentCandidate],
    ) -> tuple[list[FragmentCandidate], list[dict[str, str]]]:
        """Identify identical fragments by SHA-256 and preserve unique instances with provenance."""
        seen_hashes: dict[str, str] = {}
        unique_fragments: list[FragmentCandidate] = []
        duplicate_records: list[dict[str, str]] = []

        for f in fragments:
            if f.sha256 in seen_hashes:
                duplicate_records.append(
                    {
                        "duplicate_id": f.fragment_id,
                        "retained_id": seen_hashes[f.sha256],
                        "sha256": f.sha256,
                        "offset": str(f.source_offset),
                    }
                )
            else:
                seen_hashes[f.sha256] = f.fragment_id
                unique_fragments.append(f)

        return unique_fragments, duplicate_records

    @staticmethod
    def compute_boundary_continuity(frag_a: bytes, frag_b: bytes) -> float:
        """Measure syntactic continuity across fragment boundary [frag_a | frag_b].

        Returns:
            Affinity score 0.0 to 1.0 based on line syntax, token splits, and whitespace.
        """
        if not frag_a or not frag_b:
            return 0.0

        tail = frag_a[-16:]
        head = frag_b[:16]

        score = 0.5  # Base neutral affinity

        # Check line endings
        if tail.endswith((b"\r\n", b"\n")):
            # Clean statement boundary
            score += 0.2

        # Check for unclosed keywords across boundary
        if tail.endswith(b"ob") and head.startswith(b"j "):
            score += 0.4
        elif tail.endswith(b"stream") and head.startswith((b"\r\n", b"\n")):
            score += 0.4
        elif tail.endswith(b"end") and head.startswith(b"obj"):
            score += 0.4

        # Disincentivize null-padding to active byte transition unless block boundary
        if tail.endswith(b"\x00\x00") and not head.startswith(b"\x00"):
            score -= 0.2

        return min(1.0, max(0.0, score))
