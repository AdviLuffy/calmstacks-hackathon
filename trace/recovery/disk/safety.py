"""Forensic safety enforcement: read-only image access and hardware write-blocker tracking."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import BinaryIO


class ForensicSafetyError(Exception):
    """Raised when an unsafe or non-read-only operation is attempted on evidence."""


class ReadOnlyEvidenceReader:
    """Strictly read-only wrapper ensuring zero disk or evidence modification."""

    def __init__(self, path: Path | str, write_blocked: bool = False) -> None:
        self.path = Path(path).resolve()
        self.write_blocked = write_blocked
        self._initial_sha256: str | None = None
        self._final_sha256: str | None = None
        self._handle: BinaryIO | None = None

        if not self.path.is_file():
            raise FileNotFoundError(f"Evidence file not found: {self.path}")

    def __enter__(self) -> ReadOnlyEvidenceReader:
        # Enforce read-only open mode 'rb'
        self._handle = open(self.path, "rb")
        # Compute baseline integrity hash
        self._initial_sha256 = self._compute_hash()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self._handle and not self._handle.closed:
            self._handle.close()
        # Verify integrity hash has not changed
        self._final_sha256 = self._compute_hash()
        if self._initial_sha256 != self._final_sha256:
            raise ForensicSafetyError(
                f"CRITICAL FORENSIC INTEGRITY VIOLATION: Evidence file {self.path.name} was modified! "
                f"Initial: {self._initial_sha256} -> Final: {self._final_sha256}"
            )

    def _compute_hash(self) -> str:
        h = hashlib.sha256()
        with open(self.path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()

    @property
    def sha256(self) -> str:
        if not self._initial_sha256:
            self._initial_sha256 = self._compute_hash()
        return self._initial_sha256

    def read_bytes(self) -> bytes:
        """Read entire evidence file safely."""
        with open(self.path, "rb") as f:
            return f.read()

    def read_sector(self, sector_lba: int, sector_size: int = 512) -> bytes:
        """Read a single sector by LBA without modifying the file pointer."""
        with open(self.path, "rb") as f:
            f.seek(sector_lba * sector_size)
            return f.read(sector_size)
