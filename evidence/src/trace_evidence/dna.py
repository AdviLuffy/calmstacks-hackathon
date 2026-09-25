"""Internal per-fragment structural profiling ("Evidence DNA") for PDF.

INTERNAL ONLY. This module produces in-memory value objects used to reason about
fragment order. Nothing here is serialized: no profile field is added to the
Evidence Bundle, and no profile field may be added to a fragment record (the
frozen ``fragment.schema.json`` declares exactly five fields).

Detection is deterministic and derived from fragment bytes only. The profiler
never reads the ground-truth manifest, never touches the filesystem, and never
guesses: an unrecognized block is reported as ``unknown``.

Three fixture traps this module must handle:

* ``startxref`` contains ``xref`` as a substring, so ``xref`` is matched with a
  **line anchor** - otherwise the startxref block would also classify as xref.
* The ``%%EOF`` block is left-padded, so the terminator sits at the END of the
  block; it is searched for anywhere in the block, not at offset 0.
* ``endobj`` contains ``obj``, so object headers are matched with a line-anchored
  ``<num> <gen> obj`` pattern rather than a substring search.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .constants import (
    KIND_EOF,
    KIND_HEADER,
    KIND_OBJECT,
    KIND_STARTXREF,
    KIND_TRAILER,
    KIND_UNKNOWN,
    KIND_XREF,
)
from .hashing import sha256_bytes
from .models import Fragment

__all__ = [
    "TOKEN_PDF_HEADER",
    "TOKEN_EOF",
    "TOKEN_XREF",
    "TOKEN_STARTXREF",
    "TOKEN_TRAILER",
    "TOKEN_OBJ",
    "TOKEN_ENDOBJ",
    "TOKEN_ORDER",
    "ProfileMismatchError",
    "FragmentProfile",
    "classify_block",
    "detect_tokens",
    "profile_fragment",
]

TOKEN_PDF_HEADER = "%PDF-"
TOKEN_EOF = "%%EOF"
TOKEN_XREF = "xref"
TOKEN_STARTXREF = "startxref"
TOKEN_TRAILER = "trailer"
TOKEN_OBJ = "obj"
TOKEN_ENDOBJ = "endobj"

# Fixed emission order, so two profiles are comparable directly.
TOKEN_ORDER = (
    TOKEN_PDF_HEADER,
    TOKEN_EOF,
    TOKEN_XREF,
    TOKEN_STARTXREF,
    TOKEN_TRAILER,
    TOKEN_OBJ,
    TOKEN_ENDOBJ,
)

# Line-anchored patterns. ``(?m)^`` anchors to the start of any line, which is
# what keeps ``startxref`` from being read as an ``xref`` and ``endobj`` from
# being read as an object header.
_OBJECT_RE = re.compile(rb"(?m)^(\d+)[ \t]+(\d+)[ \t]+obj\b")
_XREF_RE = re.compile(rb"(?m)^xref\b")
_STARTXREF_RE = re.compile(rb"(?m)^startxref\b")
_TRAILER_RE = re.compile(rb"(?m)^trailer\b")

# File-level terminators are searched for anywhere, because padding may put them
# at the very end of a block.
_PDF_HEADER_BYTES = b"%PDF-"
_EOF_BYTES = b"%%EOF"


class ProfileMismatchError(ValueError):
    """The supplied bytes do not belong to the supplied fragment."""


@dataclass(frozen=True)
class FragmentProfile:
    """Structural reading of one fragment.

    Internal value object: never serialized, never placed in the bundle.
    """

    fragment_id: str
    byte_range: tuple[int, int]
    kind: str
    object_number: int | None = None
    tokens: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        has_number = self.object_number is not None
        if (self.kind == KIND_OBJECT) != has_number:
            raise ValueError(
                f"object_number must be set if and only if kind is {KIND_OBJECT!r}: "
                f"kind={self.kind!r}, object_number={self.object_number!r}"
            )

    @property
    def size_bytes(self) -> int:
        return self.byte_range[1] - self.byte_range[0]

    @property
    def is_object(self) -> bool:
        return self.kind == KIND_OBJECT


def detect_tokens(block: bytes) -> tuple[str, ...]:
    """Return the structural PDF tokens present in ``block``, in a fixed order."""
    found = []
    if _PDF_HEADER_BYTES in block:
        found.append(TOKEN_PDF_HEADER)
    if _EOF_BYTES in block:
        found.append(TOKEN_EOF)
    if _XREF_RE.search(block) is not None:
        found.append(TOKEN_XREF)
    if _STARTXREF_RE.search(block) is not None:
        found.append(TOKEN_STARTXREF)
    if _TRAILER_RE.search(block) is not None:
        found.append(TOKEN_TRAILER)
    if _OBJECT_RE.search(block) is not None:
        found.append(TOKEN_OBJ)
    if b"endobj" in block:
        found.append(TOKEN_ENDOBJ)
    return tuple(token for token in TOKEN_ORDER if token in found)


def classify_block(block: bytes) -> tuple[str, int | None]:
    """Return ``(kind, object_number)`` for one fragment's bytes.

    Precedence is explicit because a coarsely-carved block can carry more than one
    marker. File-level markers are the most definitive, then the section markers,
    then object headers. Anything unrecognized is ``unknown`` - never a guess.
    """
    if _PDF_HEADER_BYTES in block:
        return KIND_HEADER, None
    if _EOF_BYTES in block:
        return KIND_EOF, None
    if _STARTXREF_RE.search(block) is not None:
        return KIND_STARTXREF, None
    if _TRAILER_RE.search(block) is not None:
        return KIND_TRAILER, None
    if _XREF_RE.search(block) is not None:
        return KIND_XREF, None

    match = _OBJECT_RE.search(block)
    if match is not None:
        return KIND_OBJECT, int(match.group(1))

    return KIND_UNKNOWN, None


def profile_fragment(fragment: Fragment, block: bytes) -> FragmentProfile:
    """Profile one fragment from its bytes.

    The bytes are checked against the fragment's identity before anything is read
    from them: the digest must equal ``fragment.bytes_sha256`` and the length must
    equal ``fragment.size_bytes``. A mismatch is an error, never a warning -
    profiling mismatched bytes would silently attribute structure to the wrong
    fragment.
    """
    digest = sha256_bytes(block)
    if digest != fragment.bytes_sha256:
        raise ProfileMismatchError(
            f"bytes do not match {fragment.fragment_id}: expected sha256 "
            f"{fragment.bytes_sha256}, got {digest}"
        )

    if len(block) != fragment.size_bytes:
        raise ProfileMismatchError(
            f"bytes do not match {fragment.fragment_id}: expected "
            f"{fragment.size_bytes} bytes, got {len(block)}"
        )

    kind, object_number = classify_block(block)

    return FragmentProfile(
        fragment_id=fragment.fragment_id,
        byte_range=fragment.byte_range,
        kind=kind,
        object_number=object_number,
        tokens=detect_tokens(block),
    )
