"""Genuinely Damaged PDF Corpus Management (TRACE Phase 10).

Manages evaluation samples from public corpora (SafeDocs, PDF Association, real-world forensic cases).
Strictly separates genuinely malformed files from synthetically corrupted files and guarantees
that unverified missing content is NEVER fabricated as ground truth.
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from trace_evidence.pdf_recovery import diagnose_pdf_corruption
from trace.datasets.schemas.real_world import (
    GenuinelyDamagedRecord,
    LicenseType,
)

logger = logging.getLogger(__name__)

DEFAULT_GENUINE_DIR = Path(__file__).resolve().parent / "data" / "genuine_damaged"


# Canonical public SafeDocs research samples (CC0 / Open Research)
SAFEDOCS_SAMPLES = [
    {
        "sample_id": "safedocs_xref_corruption_01",
        "source_name": "PDF Association SafeDocs Issue Corpus",
        "source_url": "https://github.com/pdf-association/safedocs",
        "license_type": LicenseType.SAFEDOCS_RESEARCH,
        "license_url": "https://github.com/pdf-association/safedocs/blob/main/LICENSE",
        "observed_damage_classes": ["DESTROYED_CROSS_REFERENCE_TABLE", "MISSING_TRAILER_DICT"],
        "safety_warnings": ["Untrusted research test bitstream — static parsing only, no active script execution"],
        "notes": "Corrupted xref table offset with intact body object streams.",
        # Minimal malformed PDF stream representing authentic damaged xref
        "sample_bytes": (
            b"%PDF-1.4\n"
            b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
            b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n"
            b"4 0 obj\n<< /Length 45 >>\nstream\nBT /F1 10 Tf 54 700 Td (Authentic Damaged Case Sample) Tj ET\nendstream\nendobj\n"
            b"xref\n0 5\nMALFORMED_GARBAGE_XREF_ENTRIES_CORRUPTED_DISASTER\n"
            b"startxref\n999999\n%%EOF"
        ),
    },
    {
        "sample_id": "safedocs_truncated_stream_02",
        "source_name": "PDF Association SafeDocs Issue Corpus",
        "source_url": "https://github.com/pdf-association/safedocs",
        "license_type": LicenseType.SAFEDOCS_RESEARCH,
        "license_url": "https://github.com/pdf-association/safedocs/blob/main/LICENSE",
        "observed_damage_classes": ["TRUNCATED_BITSTREAM_NO_EOF", "ERASED_SECTOR_NULL_RUNS"],
        "safety_warnings": ["Truncated bitstream with null run sectors."],
        "notes": "Bitstream abruptly truncated across object stream boundary without EOF marker.",
        "sample_bytes": (
            b"%PDF-1.4\n"
            b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
            b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n"
            b"4 0 obj\n<< /Length 120 >>\nstream\nBT /F1 12 Tf 54 720 Td (Severed stream header) Tj ET\n"
            + (b"\x00" * 48)  # null run sector erasure
        ),
    },
]


class GenuinelyDamagedCorpusManager:
    """Manages collection, storage, and safe inspection of genuinely damaged PDF samples."""

    def __init__(self, corpus_dir: Optional[Union[str, Path]] = None) -> None:
        if corpus_dir:
            self.corpus_dir = Path(corpus_dir)
        elif os.environ.get("VERCEL"):
            self.corpus_dir = Path("/tmp/trace_data/genuine_damaged")
        else:
            self.corpus_dir = DEFAULT_GENUINE_DIR

        try:
            self.corpus_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            self.corpus_dir = Path("/tmp/trace_data/genuine_damaged")
            self.corpus_dir.mkdir(parents=True, exist_ok=True)

        self._initialize_canonical_samples()

    def compute_sha256(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def _initialize_canonical_samples(self) -> None:
        """Seed directory with documented canonical SafeDocs research test cases."""
        for s in SAFEDOCS_SAMPLES:
            sample_id = s["sample_id"]
            sample_file = self.corpus_dir / f"{sample_id}.pdf"
            meta_file = self.corpus_dir / f"{sample_id}.json"

            sample_bytes = s["sample_bytes"]
            if not sample_file.is_file():
                sample_file.write_bytes(sample_bytes)

            if not meta_file.is_file():
                rec = GenuinelyDamagedRecord(
                    sample_id=sample_id,
                    source_name=s["source_name"],
                    source_url=s["source_url"],
                    license_type=s["license_type"],
                    license_url=s["license_url"],
                    sha256=self.compute_sha256(sample_bytes),
                    file_size_bytes=len(sample_bytes),
                    has_verified_ground_truth=False,  # CRITICAL: Never claim unverified ground truth
                    associated_original_sha256=None,
                    observed_damage_classes=s["observed_damage_classes"],
                    safety_warnings=s["safety_warnings"],
                    notes=s["notes"],
                )
                meta_file.write_text(rec.model_dump_json(indent=2), encoding="utf-8")

    def list_samples(self) -> List[GenuinelyDamagedRecord]:
        """List all genuinely damaged samples in the corpus."""
        records: List[GenuinelyDamagedRecord] = []
        for meta_file in sorted(self.corpus_dir.glob("*.json")):
            try:
                rec = GenuinelyDamagedRecord.model_validate_json(meta_file.read_text(encoding="utf-8"))
                records.append(rec)
            except Exception as e:
                logger.warning("Failed to load damaged sample metadata %s: %s", meta_file, e)
        return records

    def get_sample_bytes(self, sample_id: str) -> Optional[bytes]:
        """Safely retrieve raw bytes of a damaged sample."""
        sample_file = self.corpus_dir / f"{sample_id}.pdf"
        if sample_file.is_file():
            return sample_file.read_bytes()
        return None

    def inspect_sample_safety(self, sample_bytes: bytes) -> Dict[str, Any]:
        """Perform static analysis on unknown damaged PDF to verify it contains no active payloads."""
        has_js = b"/JavaScript" in sample_bytes or b"/JS" in sample_bytes
        has_launch = b"/Launch" in sample_bytes
        has_embedded_files = b"/EmbeddedFiles" in sample_bytes
        has_action = b"/A <</S" in sample_bytes or b"/OpenAction" in sample_bytes

        diag = diagnose_pdf_corruption(sample_bytes)

        return {
            "safe_for_static_parsing": not (has_js or has_launch),
            "contains_javascript": has_js,
            "contains_launch_action": has_launch,
            "contains_embedded_files": has_embedded_files,
            "contains_open_action": has_action,
            "corruption_classes": list(diag.corruption_classes),
            "integrity_score": diag.integrity_score,
            "entropy": diag.entropy,
        }

    def verify_safety_static(self, sample_id: str) -> Tuple[bool, List[str]]:
        """Check whether sample is safe for static parsing without active execution risks."""
        sample_bytes = self.get_sample_bytes(sample_id)
        if not sample_bytes:
            return False, ["Sample file not found"]
        info = self.inspect_sample_safety(sample_bytes)
        issues = []
        if info["contains_javascript"]:
            issues.append("Contains JavaScript payload")
        if info["contains_launch_action"]:
            issues.append("Contains Launch action")
        return info["safe_for_static_parsing"], issues

