"""Deterministic hashing helpers.

Every hash used by the engine comes from this module, so fragment IDs,
provenance records and integrity reports stay reproducible across runs.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

__all__ = ["sha256_bytes", "sha256_file", "content_id"]

_CHUNK_SIZE = 65536


def sha256_bytes(data: bytes) -> str:
    """Return the lowercase hex SHA-256 digest of ``data``."""
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path, chunk_size: int = _CHUNK_SIZE) -> str:
    """Return the lowercase hex SHA-256 digest of the file at ``path``.

    The file is streamed in chunks so large evidence blobs never have to be
    held in memory. It is opened read-only and is never modified.
    """
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def content_id(prefix: str, digest: str, length: int = 16) -> str:
    """Build a short, deterministic, content-addressed identifier.

    ``content_id("frag", sha256_hex)`` -> ``"frag_<16 hex chars>"``.

    No counters and no clock are involved, so the identifier is stable for
    identical content on every run and every machine.
    """
    if not prefix or not prefix.replace("_", "").isalnum():
        raise ValueError(f"invalid id prefix: {prefix!r}")
    if length < 4 or length > len(digest):
        raise ValueError(f"invalid id length: {length}")
    return f"{prefix}_{digest[:length]}"
