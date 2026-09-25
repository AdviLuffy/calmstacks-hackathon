"""M0 FragmentInstanceId: the frozen fragment identifier and its frozen semantics.

Transcribed from the approved fragment-ID amendment, and nothing else.

Frozen format::

    FragmentInstanceId :=
        "FRG-" lowercase_hex{16} "-" digits{1,10} "-" digits{1,10}

Frozen semantics, as approved:

  1  fragment_id identifies a specific source byte occurrence.
  2  bytes_sha256 is the full SHA-256 digest of fragment content.
  3  byte ranges use [start, end).
  4  start >= 0.
  5  end > start.
  6  size_bytes = end - start.
  7  fragment IDs are unique within the bundle.
  8  identical bytes at different source ranges receive different IDs.
  9  every EvidenceRef must resolve to exactly one record.

How each frozen statement is enforced here:

  1  ``parse_fragment_instance_id`` decomposes the identifier, and
     ``validate_fragment_identity`` requires the identifier's range to BE the record's
     source range, so one identifier never names two occurrences.
  2  ``is_full_sha256_digest`` requires a complete 64-character SHA-256 digest. Hashing
     content is outside M0: no fragment is read, scanned or hashed here.
  3-6  The range is carried half-open as ``[start, end)``; ``end > start`` is enforced and
     ``size_bytes`` is derived and then cross-checked when a value is supplied. ``start``
     cannot be negative because the grammar admits no sign, which is asserted by a test.
  7  ``FragmentIdIndex`` refuses a repeated identifier.
  8  An identifier always carries its own range, so identical bytes at different ranges
     cannot collide; ``FragmentIdIndex`` also refuses two identifiers for one occurrence.
  9  ``FragmentIdIndex`` maps each identifier to at most one record and hands that mapping
     to ``app.contract.evidence_ref.SessionEvidenceRefResolver`` unchanged.

Two gaps in the amendment are not resolved by invention. Both are recorded in
:mod:`app.contract.registry`, and both shape the code below:

M0-AMB-07  CLOSED by the frozen Option A amendment (recorded as M0-DEC-06 in
    :mod:`app.contract.registry`). The fragments slot of the single normative EvidenceRef
    pattern now admits ``fragments[FRG-<16 lowercase hex>-<start>-<end>]`` as an alternative,
    so a frozen FragmentInstanceId IS expressible there. This module still defines no second
    EvidenceRef syntax, because a second syntax is precisely the competing definition
    M0-DEC-01 forbids, and the widening plus the exactly-one-record grounding rule are
    asserted by tests, so neither can change silently.

M0-AMB-08  The amendment freezes neither the digest's textual encoding, nor which 16 digest
    characters the identifier carries, nor a canonical spelling for ``digits{1,10}`` (which
    admits leading zeros). This module therefore accepts either hex case for the digest,
    confines the prefix derivation to ``fragment_instance_id_from_content``, never rewrites
    a supplied identifier, and refuses to register two identifiers for one occurrence.
"""
from __future__ import annotations

import re
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Final

#: The frozen collection whose instance identifiers are FragmentInstanceIds. It is one of
#: ``app.contract.evidence_ref.EVIDENCE_REF_COLLECTIONS``; a test asserts that.
FRAGMENTS_COLLECTION: Final[str] = "fragments"

#: The frozen identifier prefix.
FRAGMENT_ID_PREFIX: Final[str] = "FRG-"

#: lowercase_hex{16}
FRAGMENT_ID_DIGEST_HEX_LENGTH: Final[int] = 16

#: digits{1,10}, the bound length allowed in each numeric position.
FRAGMENT_ID_RANGE_DIGITS_MIN: Final[int] = 1
FRAGMENT_ID_RANGE_DIGITS_MAX: Final[int] = 10

#: A SHA-256 digest is 256 bits, so its full textual form is 64 hex characters.
SHA256_DIGEST_HEX_LENGTH: Final[int] = 64

#: The frozen grammar, spelled out rather than assembled, so it reads like the amendment.
#: A test pins this string and checks the constants above against its bounds.
FRAGMENT_ID_PATTERN: Final[str] = r"^FRG-[0-9a-f]{16}-\d{1,10}-\d{1,10}$"

#: The single syntactic validator for FragmentInstanceId.
FRAGMENT_ID_RE: Final[re.Pattern[str]] = re.compile(FRAGMENT_ID_PATTERN)

#: A full SHA-256 digest. M0-AMB-08: the amendment does not freeze the digest's hex case,
#: so both cases are accepted here, while the identifier's own 16 characters must be
#: lowercase, which the amendment does freeze.
SHA256_DIGEST_PATTERN: Final[str] = r"^[0-9a-fA-F]{64}$"
SHA256_DIGEST_RE: Final[re.Pattern[str]] = re.compile(SHA256_DIGEST_PATTERN)

_DIGEST_HEX_RE: Final[re.Pattern[str]] = re.compile(r"^[0-9a-f]{16}$")


class InvalidFragmentInstanceIdError(ValueError):
    """The value violates the frozen FragmentInstanceId grammar or its frozen semantics."""


class FragmentIdCollisionError(ValueError):
    """Semantics 7 and 8: two records claim the same fragment identity in one bundle."""


@dataclass(frozen=True)
class FragmentInstanceId:
    """A valid FragmentInstanceId, decomposed without rewriting the supplied string.

    ``value`` is the exact string that was validated. It is never re-serialised from the
    parsed parts, because M0-AMB-08 leaves the spelling of ``digits{1,10}`` unfrozen and
    rewriting an identifier would silently rename a fragment.
    """

    value: str
    digest_hex: str
    start: int
    end: int

    @property
    def size_bytes(self) -> int:
        """Semantics 6: size_bytes = end - start."""
        return self.end - self.start

    @property
    def byte_range(self) -> tuple[int, int]:
        """Semantics 3: the half-open source range [start, end)."""
        return (self.start, self.end)

    @property
    def occurrence(self) -> tuple[str, int, int]:
        """Semantics 1: the source byte occurrence this identifier names."""
        return (self.digest_hex, self.start, self.end)

    def __str__(self) -> str:
        return self.value


def parse_fragment_instance_id(raw: str) -> FragmentInstanceId:
    """Validate ``raw`` and decompose it, or raise InvalidFragmentInstanceIdError.

    Leading zeros in either bound are accepted exactly as the grammar states, and they are
    never normalised away. Semantics 4 (``start >= 0``) needs no runtime check because the
    grammar admits no sign; a negative bound is therefore a syntax error, not a semantic
    one, and a test locks that in.
    """
    if not isinstance(raw, str):
        raise InvalidFragmentInstanceIdError(
            "FragmentInstanceId must be a string, got %s" % type(raw).__name__
        )
    if FRAGMENT_ID_RE.fullmatch(raw) is None:
        raise InvalidFragmentInstanceIdError(
            "not a valid FragmentInstanceId under the frozen grammar "
            "(FRG-<16 lowercase hex>-<start>-<end>): %r" % (raw,)
        )

    digest_hex, start_text, end_text = raw[len(FRAGMENT_ID_PREFIX) :].split("-")
    start = int(start_text)
    end = int(end_text)
    if end <= start:  # semantics 5
        raise InvalidFragmentInstanceIdError(
            "semantics 5: end must be greater than start, got start=%d end=%d" % (start, end)
        )
    return FragmentInstanceId(value=raw, digest_hex=digest_hex, start=start, end=end)


def is_valid_fragment_instance_id(value: object) -> bool:
    """True only for a string satisfying the frozen grammar and its range semantics."""
    if not isinstance(value, str) or FRAGMENT_ID_RE.fullmatch(value) is None:
        return False
    try:
        parse_fragment_instance_id(value)
    except InvalidFragmentInstanceIdError:
        return False
    return True


def is_full_sha256_digest(value: object) -> bool:
    """Semantics 2: true only for a complete 64-character SHA-256 digest.

    Either hex case is accepted; M0-AMB-08 records that the amendment does not freeze the
    digest's textual encoding, and rejecting one case would invent a rule.
    """
    return isinstance(value, str) and SHA256_DIGEST_RE.fullmatch(value) is not None


def format_fragment_instance_id(*, digest_hex: str, start: int, end: int) -> str:
    """Build a FragmentInstanceId from a 16-hex digest prefix and a byte range.

    The arguments are exactly the three places of the frozen format, so no field name is
    invented. Every frozen semantic is enforced here as well as on parse, and the range is
    re-parsed before it is returned, so the constructor can only produce a valid identifier.
    """
    if not isinstance(digest_hex, str) or _DIGEST_HEX_RE.fullmatch(digest_hex) is None:
        raise InvalidFragmentInstanceIdError(
            "the identifier carries exactly %d lowercase hex characters, got %r"
            % (FRAGMENT_ID_DIGEST_HEX_LENGTH, digest_hex)
        )
    for name, value in (("start", start), ("end", end)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise InvalidFragmentInstanceIdError(
                "%s must be an integer, got %r" % (name, value)
            )
        if value < 0:  # semantics 4
            raise InvalidFragmentInstanceIdError(
                "semantics 4: start and end must be >= 0, got %s=%d" % (name, value)
            )
        if len(str(value)) > FRAGMENT_ID_RANGE_DIGITS_MAX:
            raise InvalidFragmentInstanceIdError(
                "the grammar allows at most %d digits per bound, got %s=%d"
                % (FRAGMENT_ID_RANGE_DIGITS_MAX, name, value)
            )
    if end <= start:  # semantics 5
        raise InvalidFragmentInstanceIdError(
            "semantics 5: end must be greater than start, got start=%d end=%d" % (start, end)
        )
    return parse_fragment_instance_id(
        "%s%s-%d-%d" % (FRAGMENT_ID_PREFIX, digest_hex, start, end)
    ).value


def digest_hex_prefix(bytes_sha256: str) -> str:
    """The 16 digest characters an identifier carries, for a full SHA-256 digest.

    This is the M0-AMB-08 derivation: the amendment does not state which 16 characters are
    used, so the choice is confined to this function and to
    ``fragment_instance_id_from_content``. Validation never requires it, so a bundle whose
    identifiers were derived differently is still valid and is never rewritten.
    """
    if not is_full_sha256_digest(bytes_sha256):
        raise InvalidFragmentInstanceIdError(
            "semantics 2: bytes_sha256 must be the full SHA-256 digest of the fragment "
            "content (%d hex characters, either case), got %r"
            % (SHA256_DIGEST_HEX_LENGTH, bytes_sha256)
        )
    return bytes_sha256[:FRAGMENT_ID_DIGEST_HEX_LENGTH].lower()


def fragment_instance_id_from_content(*, bytes_sha256: str, start: int, end: int) -> str:
    """The one constructor allowed to derive the 16 hex characters from content.

    Identical bytes at different source ranges therefore receive different identifiers
    (semantics 8): the digest prefix is equal and the range differs.
    """
    return format_fragment_instance_id(
        digest_hex=digest_hex_prefix(bytes_sha256), start=start, end=end
    )


def validate_fragment_identity(
    *,
    fragment_id: str,
    bytes_sha256: str,
    start: int,
    end: int,
    size_bytes: int | None = None,
) -> FragmentInstanceId:
    """Enforce the frozen fragment semantics for one fragment record.

    Semantics 1 ties a fragment_id to a specific source byte occurrence, so the identifier's
    own range must be the record's range: an identifier whose bounds disagree with the
    record it labels does not identify that occurrence, and accepting it would let one
    identifier name two occurrences. Semantics 6 makes ``size_bytes`` derived, so a supplied
    value is cross-checked instead of trusted, and a missing value is allowed because it is
    derivable. ``fragment_id``, ``bytes_sha256``, ``start``, ``end`` and ``size_bytes`` are
    the frozen field names from the amendment; no others are invented.
    """
    parsed = parse_fragment_instance_id(fragment_id)
    if not is_full_sha256_digest(bytes_sha256):
        raise InvalidFragmentInstanceIdError(
            "semantics 2: bytes_sha256 must be the full SHA-256 digest of the fragment "
            "content (%d hex characters, either case), got %r"
            % (SHA256_DIGEST_HEX_LENGTH, bytes_sha256)
        )
    for name, value in (("start", start), ("end", end)):
        if isinstance(value, bool) or not isinstance(value, int):
            raise InvalidFragmentInstanceIdError(
                "%s must be an integer, got %r" % (name, value)
            )
    if end <= start:  # semantics 5
        raise InvalidFragmentInstanceIdError(
            "semantics 5: end must be greater than start, got start=%d end=%d" % (start, end)
        )
    if parsed.byte_range != (start, end):
        raise InvalidFragmentInstanceIdError(
            "semantics 1: %r names the source range %s, which is not the record's range "
            "(%d, %d)" % (fragment_id, parsed.byte_range, start, end)
        )
    if size_bytes is not None:
        if isinstance(size_bytes, bool) or not isinstance(size_bytes, int):
            raise InvalidFragmentInstanceIdError(
                "size_bytes must be an integer, got %r" % (size_bytes,)
            )
        if size_bytes != parsed.size_bytes:
            raise InvalidFragmentInstanceIdError(
                "semantics 6: size_bytes must equal end - start (%d), got %r"
                % (parsed.size_bytes, size_bytes)
            )
    return parsed


class FragmentIdIndex:
    """The bundle-scoped index that keeps semantics 7, 8 and 9 true.

    One bundle owns one index.

    * Semantics 7: a repeated identifier is refused, so identifiers are unique per bundle.
    * Semantics 1: two identifiers that denote one source occurrence are refused as well,
      which also closes the leading-zero spelling gap recorded in M0-AMB-08.
    * Semantics 8: identical bytes at different source ranges are different occurrences and
      are both accepted, because an identifier always carries its own range.
    * Semantics 9: ``resolve`` returns the record registered for an identifier, so an
      EvidenceRef can resolve to exactly one record and never to a set.

    This index does NOT validate EvidenceRef strings, and ``collection_ids`` does not widen
    any pattern. A ``fragments[...]`` reference is governed by the single normative pattern
    (M0-DEC-01 as amended by the frozen Option A freeze, M0-DEC-06), whose fragments slot now
    expresses a FragmentInstanceId, and the exactly-one-record grounding of such a reference
    against a supplied bundle lives in :mod:`app.services.evidence`.
    """

    def __init__(self, fragment_ids: Iterable[str] = ()) -> None:
        self._records: dict[str, object | None] = {}
        self._occurrences: dict[tuple[str, int, int], str] = {}
        self.add_all(fragment_ids)

    def add(self, fragment_id: str, record: object | None = None) -> FragmentInstanceId:
        """Register one fragment identifier, or raise FragmentIdCollisionError.

        ``record`` is the record the identifier resolves to. Its shape is not frozen by the
        amendment, whose own record facts (``fragment_id``, ``bytes_sha256`` and the byte
        range) are checked by ``validate_fragment_identity`` before it is registered.
        """
        parsed = parse_fragment_instance_id(fragment_id)
        if parsed.value in self._records:
            raise FragmentIdCollisionError(
                "semantics 7: fragment IDs are unique within the bundle, but %r was added "
                "twice" % (fragment_id,)
            )
        claimed = self._occurrences.get(parsed.occurrence)
        if claimed is not None:
            raise FragmentIdCollisionError(
                "semantics 1: %r and %r both identify the source occurrence %s"
                % (claimed, parsed.value, parsed.occurrence)
            )
        self._records[parsed.value] = record
        self._occurrences[parsed.occurrence] = parsed.value
        return parsed

    def add_all(self, fragment_ids: Iterable[str]) -> None:
        """Register several identifiers, applying the same uniqueness rules."""
        for fragment_id in fragment_ids:
            self.add(fragment_id)

    def resolve(self, fragment_id: str) -> object | None:
        """Semantics 9: the one record this identifier resolves to, or None if unknown."""
        return self._records.get(fragment_id)

    def defines(self, fragment_id: object) -> bool:
        """True when this bundle defines the identifier, whether or not it has a record."""
        return isinstance(fragment_id, str) and fragment_id in self._records

    def __contains__(self, fragment_id: object) -> bool:
        return self.defines(fragment_id)

    def __len__(self) -> int:
        return len(self._records)

    def __iter__(self) -> Iterator[str]:
        return iter(self._records)

    @property
    def ids(self) -> tuple[str, ...]:
        """Every registered identifier, in registration order."""
        return tuple(self._records)

    def collection_ids(self) -> dict[str, frozenset[str]]:
        """The identifier set, in the shape ``SessionEvidenceRefResolver`` accepts."""
        return {FRAGMENTS_COLLECTION: frozenset(self._records)}


