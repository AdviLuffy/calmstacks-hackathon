"""Schemas for real-world PDF dataset integration and benchmarking (TRACE Phase 10).

Defines schemas for:
- Real-world document registry records (arXiv, PDF Association SafeDocs, Public Domain)
- Content characteristics, licensing, and safety warnings
- Controlled corruption records derived from real-world ground truth
- Genuinely damaged evaluation samples (without fabricated ground truth)
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class LicenseType(str, Enum):
    """Permitted open and research licenses."""
    CC_BY_4_0 = "CC-BY-4.0"
    CC_BY_SA_4_0 = "CC-BY-SA-4.0"
    CC0_1_0 = "CC0-1.0"
    PUBLIC_DOMAIN = "PUBLIC_DOMAIN"
    OPEN_ACCESS = "OPEN_ACCESS"
    SAFEDOCS_RESEARCH = "SAFEDOCS_RESEARCH"
    RESTRICTED = "RESTRICTED"


class ContentCharacteristic(str, Enum):
    """Structural and semantic content tags of documents."""
    SINGLE_COLUMN = "single_column"
    TWO_COLUMN = "two_column"
    MULTI_PAGE = "multi_page"
    TEXT_HEAVY = "text_heavy"
    TABLES = "tables"
    FIGURES = "figures"
    EQUATIONS = "equations"
    EMBEDDED_FONTS = "embedded_fonts"
    VECTOR_GRAPHICS = "vector_graphics"


class DocumentCategory(str, Enum):
    """High-level document genre."""
    RESEARCH_PAPER = "research_paper"
    TECHNICAL_SPECIFICATION = "technical_specification"
    GOVERNMENT_REPORT = "government_report"
    SYNTHETIC_CANONICAL = "synthetic_canonical"
    CORPUS_TEST_CASE = "corpus_test_case"


class RealWorldDocumentRecord(BaseModel):
    """Forensic metadata record for an individual real-world document in the registry."""
    dataset_id: str = Field(description="Unique dataset identifier, e.g. 'arxiv-ml-open', 'safedocs-corpus'")
    document_id: str = Field(description="Unique document identifier, e.g. 'arxiv_1706_03762', 'safedocs_440'")
    title: str = Field(description="Document title")
    authors: List[str] = Field(default_factory=list, description="Authors or originating body")
    source_name: str = Field(description="Originating repository, e.g. 'arXiv', 'PDF Association SafeDocs', 'W3C'")
    source_url: str = Field(description="Web page URL describing the source document")
    download_url: Optional[str] = Field(default=None, description="Direct download URL if permitted")
    license_type: LicenseType = Field(description="Verified license identifier")
    license_url: str = Field(description="URL to full license terms")
    acquisition_date: str = Field(description="ISO-8601 acquisition timestamp")
    original_sha256: str = Field(description="Cryptographic SHA-256 hash of original file")
    file_size_bytes: int = Field(ge=0, description="Exact byte size of original file")
    category: DocumentCategory = Field(description="Document genre")
    characteristics: List[ContentCharacteristic] = Field(
        default_factory=list,
        description="Features present: multi-column, equations, tables, figures, etc."
    )
    page_count: int = Field(ge=1, description="Number of pages in intact document")
    is_intact: bool = Field(default=True, description="True if document is a valid intact PDF")
    has_verified_ground_truth: bool = Field(
        default=True,
        description="True if original intact bytes provide authoritative ground truth"
    )
    safety_warnings: List[str] = Field(
        default_factory=list,
        description="Safe-handling notes (e.g. malformed syntax, untrusted source)"
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ControlledCorruptionRecord(BaseModel):
    """Specification and provenance of a controlled corruption applied to a real-world document."""
    corruption_sample_id: str = Field(description="Unique sample ID, e.g. 'rw_arxiv_1706_03762_c01'")
    source_document_id: str = Field(description="Reference to parent RealWorldDocumentRecord")
    source_sha256: str = Field(description="Original document SHA-256 hash")
    corrupted_sha256: str = Field(description="Corrupted output SHA-256 hash")
    operation_type: str = Field(description="Corruption operation name (from ForensicCorruptionEngine)")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="Parameters passed to corruption operator")
    seed: int = Field(description="Deterministic random seed used")
    original_size_bytes: int = Field(ge=0)
    corrupted_size_bytes: int = Field(ge=0)
    preserves_content: bool = Field(
        description="True if some content is recoverable; False if destructive"
    )
    split: str = Field(
        default="test",
        description="Dataset split assignment (must be isolated at document level: train/val/test)"
    )
    ground_truth_reference: str = Field(
        description="Path or URI to verified ground truth metadata"
    )
    created_at: str = Field(description="ISO-8601 timestamp")


class GenuinelyDamagedRecord(BaseModel):
    """Forensic record for a genuinely damaged real-world PDF where no original may exist."""
    sample_id: str = Field(description="Unique ID in the genuinely damaged corpus")
    source_name: str = Field(description="Corpus source (e.g. 'SafeDocs Issue Corpus', 'Forensic Ingestion')")
    source_url: Optional[str] = Field(default=None)
    license_type: LicenseType = Field(default=LicenseType.SAFEDOCS_RESEARCH)
    license_url: str = Field(default="")
    sha256: str = Field(description="Cryptographic SHA-256 of the damaged bitstream")
    file_size_bytes: int = Field(ge=0)
    has_verified_ground_truth: bool = Field(
        default=False,
        description="CRITICAL RULE: Genuinely damaged files must NOT claim unverified ground truth"
    )
    associated_original_sha256: Optional[str] = Field(
        default=None,
        description="SHA-256 of verified clean version if known, else None"
    )
    observed_damage_classes: List[str] = Field(
        default_factory=list,
        description="Heuristic corruption classes observed (e.g. MISSING_EOF, TRUNCATED_STREAM)"
    )
    safety_warnings: List[str] = Field(
        default_factory=lambda: ["Untrusted evidence bitstream — do not execute active PDF content"],
        description="Handling precautions"
    )
    notes: str = Field(default="")


class RealWorldCorpusRegistry(BaseModel):
    """Collection registry managing real-world candidate documents and corpora."""
    registry_version: str = "1.0.0"
    created_at: str = Field(description="ISO-8601 registry creation timestamp")
    documents: List[RealWorldDocumentRecord] = Field(default_factory=list)
    controlled_corruptions: List[ControlledCorruptionRecord] = Field(default_factory=list)
    genuinely_damaged_samples: List[GenuinelyDamagedRecord] = Field(default_factory=list)

    def get_document(self, document_id: str) -> Optional[RealWorldDocumentRecord]:
        for doc in self.documents:
            if doc.document_id == document_id:
                return doc
        return None

    def filter_by_license(self, license_type: LicenseType) -> List[RealWorldDocumentRecord]:
        return [doc for doc in self.documents if doc.license_type == license_type]

    def filter_by_characteristic(self, char: ContentCharacteristic) -> List[RealWorldDocumentRecord]:
        return [doc for doc in self.documents if char in doc.characteristics]
