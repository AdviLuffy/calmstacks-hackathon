"""Data models for multi-format recovery, fragment graphs, and verification."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence


class RecoveryCategory(str, Enum):
    """Explicit recovery status categories per forensic standards."""

    VERIFIED = "VERIFIED"  # Byte-for-byte verified against ground truth or cryptographic anchor
    RECOVERED = "RECOVERED"  # Reconstructed and passed format-specific validation without ground truth
    PARTIAL = "PARTIAL"  # Partial reconstruction, some fragments/structures missing or damaged
    CANDIDATE = "CANDIDATE"  # Plausible reconstruction candidate that has not passed full validation
    UNRECOVERABLE = "UNRECOVERABLE"  # No valid reconstruction candidate found within supported limits


@dataclass(frozen=True)
class FragmentCandidate:
    """A carved or ingested fragment candidate."""

    fragment_id: str
    source_offset: int
    size_bytes: int
    data: bytes
    format_hint: str = "unknown"
    structural_role: str = "data"
    tokens: tuple[str, ...] = ()
    sha256: str = field(default="")
    entropy: float = 0.0
    is_header: bool = False
    is_footer: bool = False
    known_sequence_index: int | None = None

    def __post_init__(self) -> None:
        if not self.sha256:
            object.__setattr__(self, "sha256", hashlib.sha256(self.data).hexdigest())


@dataclass(frozen=True)
class FormatConfidence:
    """Format identification confidence with explainable indicators."""

    format_name: str
    mime_type: str
    confidence: float  # 0.0 to 1.0
    detected_by: str  # "magic_bytes", "structural_tokens", "entropy", "extension"
    structural_indicators: tuple[str, ...] = ()
    is_supported: bool = True
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ValidationResult:
    """Format-specific structural and integrity validation result."""

    is_valid: bool
    format_name: str
    integrity_score: float  # 0.0 to 1.0
    checks_passed: tuple[str, ...] = ()
    checks_failed: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class RecoveredArtifact:
    """A reconstructed or carved digital artifact."""

    artifact_id: str
    filename: str
    format_name: str
    mime_type: str
    size_bytes: int
    sha256: str
    category: RecoveryCategory
    confidence_score: float  # 0.0 to 100.0 explainable score
    fragments_used: list[str] = field(default_factory=list)
    fragments_unplaced: list[str] = field(default_factory=list)
    raw_bytes: bytes = b""
    validation: ValidationResult = field(
        default_factory=lambda: ValidationResult(
            is_valid=False, format_name="unknown", integrity_score=0.0
        )
    )
    explanation: str = ""
    reconstruction_method: str = "deterministic"
    ai_assisted: bool = False
    ai_provenance: Mapping[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    authentic_recovery_pct: float | None = None
    completeness: str = "UNKNOWN"
    integrity_status: str = "UNVERIFIED"
    structural_repair: str = "NONE"
    format_confidence: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "filename": self.filename,
            "format_name": self.format_name,
            "mime_type": self.mime_type,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
            "category": self.category.value,
            "confidence_score": round(self.confidence_score, 1),
            "format_confidence": round(self.format_confidence, 1) if self.format_confidence is not None else None,
            "authentic_recovery_pct": round(self.authentic_recovery_pct, 1) if self.authentic_recovery_pct is not None else None,
            "completeness": self.completeness,
            "integrity_status": self.integrity_status,
            "structural_repair": self.structural_repair,
            "fragments_used_count": len(self.fragments_used),
            "fragments_used": self.fragments_used,
            "fragments_unplaced_count": len(self.fragments_unplaced),
            "fragments_unplaced": self.fragments_unplaced,
            "is_valid": self.validation.is_valid,
            "integrity_score": self.validation.integrity_score,
            "validation_errors": list(self.validation.errors),
            "validation_warnings": list(self.validation.warnings),
            "explanation": self.explanation,
            "reconstruction_method": self.reconstruction_method,
            "ai_assisted": self.ai_assisted,
            "ai_provenance": dict(self.ai_provenance),
            "metadata": self.metadata,
        }


@dataclass
class FormatRecoveryResult:
    """Standardized result of a format-specific recovery and repair operation."""

    format_name: str
    is_recovered: bool
    is_openable: bool
    repaired_bytes: bytes
    authentic_bytes: bytes = b""
    authentic_bytes_count: int = 0
    synthesized_bytes_count: int = 0
    confidence_score: float = 0.0  # 0.0 to 100.0
    category: RecoveryCategory = RecoveryCategory.CANDIDATE
    validation: ValidationResult = field(
        default_factory=lambda: ValidationResult(is_valid=False, format_name="unknown", integrity_score=0.0)
    )
    operations_performed: list[str] = field(default_factory=list)
    unsupported_capabilities: list[str] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
    salvaged_text: str = ""
    extracted_items: list[dict[str, Any]] = field(default_factory=list)
    preview_type: str = "none"  # "image", "pdf", "text", "archive", "video"
    preview_data: str = ""  # Base64 string or display snippet
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "format_name": self.format_name,
            "is_recovered": self.is_recovered,
            "is_openable": self.is_openable,
            "repaired_size_bytes": len(self.repaired_bytes),
            "authentic_bytes_count": self.authentic_bytes_count,
            "synthesized_bytes_count": self.synthesized_bytes_count,
            "confidence_score": round(self.confidence_score, 1),
            "category": self.category.value,
            "is_valid": self.validation.is_valid,
            "integrity_score": self.validation.integrity_score,
            "validation_errors": list(self.validation.errors),
            "validation_warnings": list(self.validation.warnings),
            "operations_performed": self.operations_performed,
            "unsupported_capabilities": self.unsupported_capabilities,
            "diagnostics": self.diagnostics,
            "salvaged_text": self.salvaged_text,
            "extracted_items_count": len(self.extracted_items),
            "extracted_items": self.extracted_items,
            "preview_type": self.preview_type,
            "metadata": self.metadata,
        }

