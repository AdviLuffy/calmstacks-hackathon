"""Minimal M0 evidence bundle assembly.

Emits only contract-frozen root key names:

* ``x-canonicalization``         - frozen by A18 (``trace-cj/1.0``)
* ``engine{name,version,run_id}`` - frozen by A10 and the P2 decision on run_id
* ``media{size_bytes}``          - frozen by the P2 decision on media size
* ``fragments[]``                - EvidenceRef root, records per fragment.schema
* ``warnings[]``                 - frozen partial-failure channel

Ground truth is deliberately absent: no permutation, no original digest, no
oracle. The bundle is the only artefact P2 consumes.

Deliberately deferred to the hashing step (NOT this slice):

* ``trace-cj/1.0`` canonical serialization and ``bundle_sha256`` - no hash is
  invented here, and ``bundle_to_json`` is explicitly *not* canonical form.
* A root key naming the contract version - no such key name is frozen yet, so
  none is invented.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from . import __version__
from .scanning import ScanResult

__all__ = [
    "ENGINE_NAME",
    "BUNDLE_CANONICALIZATION",
    "new_run_id",
    "build_bundle",
    "bundle_to_json",
    "write_bundle",
]

ENGINE_NAME = "trace-evidence"
BUNDLE_CANONICALIZATION = "trace-cj/1.0"


def new_run_id() -> str:
    """Return a volatile per-run provenance identifier.

    Randomly generated and deliberately **not** derived from the machine clock,
    so the engine never manufactures a timestamp (A7 / P2 decision 9). P2
    decision 10 marks this value volatile and excludes it from deterministic
    hashing.
    """
    return uuid.uuid4().hex


def build_bundle(
    scan: ScanResult,
    run_id: str,
    engine_name: str = ENGINE_NAME,
    engine_version: str = __version__,
) -> dict:
    """Assemble the minimal evidence bundle for one scanned image."""
    if not run_id:
        raise ValueError("run_id must be a non-empty string")
    return {
        "x-canonicalization": BUNDLE_CANONICALIZATION,
        "engine": {
            "name": engine_name,
            "version": engine_version,
            "run_id": run_id,
        },
        "media": {"size_bytes": scan.media_size_bytes},
        "fragments": [fragment.to_dict() for fragment in scan.fragments],
        "warnings": list(scan.warnings),
    }


def bundle_to_json(bundle: dict) -> str:
    """Serialize a bundle for human reading.

    NOTE: this is **not** the ``trace-cj/1.0`` canonical form. Canonical
    serialization and ``bundle_sha256`` are deferred to the hashing step.
    """
    return json.dumps(bundle, indent=2, sort_keys=True, allow_nan=False) + "\n"


def write_bundle(path: str | Path, bundle: dict) -> None:
    """Write a bundle to disk as UTF-8 with LF newlines."""
    Path(path).write_text(bundle_to_json(bundle), encoding="utf-8", newline="\n")
