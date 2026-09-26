"""Fragment identity and record model.

Frozen fragment ID contract (M0 amendment, approved by P2 and P3):

    FRG-<16 lowercase hex>-<start>-<end>

* ``bytes_sha256`` is authoritative for content.
* Byte ranges use [start, end) semantics.
* ``start >= 0``, ``end > start``, and ``size_bytes = end - start``.
* IDs are unique within the bundle.
* Identical bytes at different source ranges receive different fragment IDs.
* Every EvidenceRef must resolve to exactly one record.

Only contract-frozen field names are emitted: ``fragment_id``, ``byte_range``,
``size_bytes``, ``bytes_sha256`` and ``warnings``. Those names come from the
frozen EvidenceRef example ``fragments[FRG-...].byte_range``, the frozen ID
amendment (``bytes_sha256``, ``size_bytes``) and the frozen partial-failure rule
(``warnings[]``). No label, confidence, engine, path or timestamp field belongs
on a fragment record.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "FRAGMENT_ID_PREFIX",
    "FRAGMENT_ID_HEX_LENGTH",
    "FRAGMENT_ID_PATTERN",
    "DIGEST_HEX_LENGTH",
    "FragmentRangeError",
    "validate_range",
    "make_fragment_id",
    "parse_fragment_id",
    "Fragment",
    "validate_fragment_collection",
]

FRAGMENT_ID_PREFIX = "FRG"
FRAGMENT_ID_HEX_LENGTH = 16
DIGEST_HEX_LENGTH = 64
FRAGMENT_ID_PATTERN = (
    rf"^{FRAGMENT_ID_PREFIX}-[0-9a-f]{{{FRAGMENT_ID_HEX_LENGTH}}}-[0-9]+-[0-9]+$"
)

_LOWER_HEX = frozenset("0123456789abcdef")


class FragmentRangeError(ValueError):
    """A byte range violated the frozen [start, end) contract."""


def validate_range(start: int, end: int) -> None:
    """Enforce the frozen range contract: ``start >= 0`` and ``end > start``."""
    if (
        isinstance(start, bool)
        or isinstance(end, bool)
        or not isinstance(start, int)
        or not isinstance(end, int)
    ):
        raise FragmentRangeError("start and end must be integers")
    if start < 0:
        raise FragmentRangeError(f"start must be >= 0, got {start}")
    if end <= start:
        raise FragmentRangeError(f"end must be > start, got start={start}, end={end}")


def make_fragment_id(bytes_sha256: str, start: int, end: int) -> str:
    """Return ``FRG-<16 lowercase hex>-<start>-<end>``.

    The digest is truncated to 16 hex characters for readability; the full
    ``bytes_sha256`` stays authoritative for content and is carried on the
    record. The source range is part of the ID, so identical bytes at different
    source ranges receive different IDs.
    """
    validate_range(start, end)
    if (
        not isinstance(bytes_sha256, str)
        or len(bytes_sha256) != DIGEST_HEX_LENGTH
        or not set(bytes_sha256) <= _LOWER_HEX
    ):
        raise ValueError("bytes_sha256 must be a 64-character lowercase hex digest")
    return f"{FRAGMENT_ID_PREFIX}-{bytes_sha256[:FRAGMENT_ID_HEX_LENGTH]}-{start}-{end}"


def parse_fragment_id(fragment_id: str) -> tuple[str, int, int]:
    """Return ``(digest_prefix, start, end)`` parsed from a fragment ID.

    Decimal fields must be canonical (ASCII digits only, no leading zeros), so a
    given source range has exactly one ID and the frozen uniqueness rule holds.
    """
    if not isinstance(fragment_id, str):
        raise ValueError("fragment_id must be a string")

    parts = fragment_id.split("-")
    if len(parts) != 4:
        raise ValueError(f"malformed fragment id: {fragment_id!r}")

    prefix, digest, start_text, end_text = parts
    if prefix != FRAGMENT_ID_PREFIX:
        raise ValueError(f"unexpected fragment id prefix: {prefix!r}")
    if len(digest) != FRAGMENT_ID_HEX_LENGTH or not set(digest) <= _LOWER_HEX:
        raise ValueError(f"malformed digest segment: {digest!r}")
    for text in (start_text, end_text):
        if not (text.isascii() and text.isdigit()):
            raise ValueError(f"non-canonical decimal field: {text!r}")
        if len(text) > 1 and text.startswith("0"):
            raise ValueError(f"non-canonical decimal field: {text!r}")

    start, end = int(start_text), int(end_text)
    validate_range(start, end)
    return digest, start, end


@dataclass(frozen=True)
class Fragment:
    """One contiguous byte range of the source media.

    Construction is self-checking: ``fragment_id`` must equal the ID derived from
    the digest and range, so a record can never disagree with its own identity
    (frozen: every EvidenceRef resolves to exactly one record).
    """

    fragment_id: str
    byte_range: tuple[int, int]
    bytes_sha256: str
    warnings: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if len(self.byte_range) != 2:
            raise FragmentRangeError("byte_range must contain exactly two values")
        start, end = self.byte_range
        validate_range(start, end)
        expected = make_fragment_id(self.bytes_sha256, start, end)
        if self.fragment_id != expected:
            raise ValueError(
                f"fragment_id {self.fragment_id!r} does not match content and range: "
                f"expected {expected!r}"
            )

    @property
    def start(self) -> int:
        return self.byte_range[0]

    @property
    def end(self) -> int:
        return self.byte_range[1]

    @property
    def size_bytes(self) -> int:
        """Frozen: ``size_bytes = end - start``."""
        return self.end - self.start

    @property
    def digest_prefix(self) -> str:
        """First 16 hex characters of ``bytes_sha256``, as embedded in the ID."""
        return self.bytes_sha256[:FRAGMENT_ID_HEX_LENGTH]

    def to_dict(self) -> dict:
        """JSON-compatible record using only contract-frozen field names."""
        return {
            "fragment_id": self.fragment_id,
            "byte_range": [self.start, self.end],
            "size_bytes": self.size_bytes,
            "bytes_sha256": self.bytes_sha256,
            "warnings": list(self.warnings),
        }


def validate_fragment_collection(fragments: Sequence[Fragment]) -> tuple[str, ...]:
    """Inspect a collection of carved fragments for integrity anomalies.

    Detects:
    - Empty collection (no fragments).
    - Duplicate fragment IDs.
    - Overlapping byte ranges in source media.
    - Zero-sized or malformed fragment spans.
    """
    anomalies: list[str] = []
    if not fragments:
        return ("fragment collection is empty: zero fragments available",)

    seen_ids: set[str] = set()
    for f in fragments:
        if f.fragment_id in seen_ids:
            anomalies.append(f"duplicate fragment ID detected in collection: {f.fragment_id}")
        seen_ids.add(f.fragment_id)
        if f.size_bytes <= 0:
            anomalies.append(f"zero or negative size for fragment {f.fragment_id}")

    # Check for overlapping ranges in source media
    sorted_frags = sorted(fragments, key=lambda f: (f.start, f.end))
    for prev, curr in zip(sorted_frags, sorted_frags[1:]):
        if prev.end > curr.start:
            anomalies.append(
                f"overlapping fragment ranges: {prev.fragment_id} [{prev.start}, {prev.end}) "
                f"overlaps with {curr.fragment_id} [{curr.start}, {curr.end})"
            )

    return tuple(anomalies)
