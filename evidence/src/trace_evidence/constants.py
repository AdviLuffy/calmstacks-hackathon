"""Shared constants for the TRACE evidence engine.

Plain string constants (rather than enums) keep the JSON artifacts readable and
the beginner-facing code simple.
"""

from __future__ import annotations

# --- Dataset shape -----------------------------------------------------------
OBJECT_COUNT = 3                    # PDF objects: Catalog, Pages, Page
EXPECTED_FRAGMENT_COUNT = 8         # header + 3 objects + xref + trailer + startxref + eof
BLOCK_SIZE = 256                    # every fragment is exactly this many bytes
DEFAULT_SEED = 1337
DATASET_FORMAT_VERSION = 1

# --- Synthetic PDF tokens ----------------------------------------------------
PDF_VERSION = "1.4"
PDF_HEADER = f"%PDF-{PDF_VERSION}\n".encode("ascii")
PDF_EOF = b"%%EOF\n"
PADDING_BYTE = b" "

# --- Fragment kinds (what a fragment looks like structurally) ----------------
KIND_HEADER = "header"
KIND_OBJECT = "object"
KIND_XREF = "xref"
KIND_TRAILER = "trailer"
KIND_STARTXREF = "startxref"
KIND_EOF = "eof"
KIND_UNKNOWN = "unknown"

# --- Relationship labels -----------------------------------------------------
# Every relationship produced by the engine is a *candidate*. "proven" is
# deliberately not defined anywhere: the engine is not allowed to emit it.
LABEL_CANDIDATE = "candidate"

# --- Integrity report statuses ----------------------------------------------
STATUS_VERIFIED = "verified"
STATUS_STRUCTURALLY_VALID = "structurally_valid"
STATUS_INCOMPLETE = "incomplete"
STATUS_FAILED = "failed"

# --- Forensic recovery states (truthful evaluation) -------------------------
RECOVERY_COMPLETE_VERIFIED = "COMPLETE AND VERIFIED"
RECOVERY_PARTIAL = "PARTIAL"
RECOVERY_CORRUPTED = "CORRUPTED"
RECOVERY_UNRECOVERABLE = "UNRECOVERABLE"

# --- Honest forensic repair & recovery statuses -----------------------------
STATUS_ORIGINAL_VERIFIED = "ORIGINAL BYTES RECOVERED AND VERIFIED"
STATUS_SYNTHETIC_REPAIR = "SYNTHETIC REPAIR — GENERATED OR REPLACED CONTENT"
STATUS_PARTIAL_UNRESTORED = "PARTIAL — MISSING CONTENT COULD NOT BE RESTORED"
STATUS_OUTPUT_INVALID = "INVALID — OUTPUT FAILED PDF VALIDATION"
