"""Pydantic schemas for forensic corruption operations and manifests."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CorruptionSeverity(int, Enum):
    """Reproducible corruption severity levels."""
    LEVEL_0 = 0  # No corruption
    LEVEL_1 = 1  # Light (isolated byte/object glitches)
    LEVEL_2 = 2  # Moderate (structural or single stream corruption)
    LEVEL_3 = 3  # Heavy (xref, stream, or multi-object damage)
    LEVEL_4 = 4  # Severe (multi-region destruction, truncation)


class Recoverability(str, Enum):
    """Theoretical and forensic recoverability expectations."""
    FULL = "full"
    PARTIAL = "partial"
    NONE = "none"
    RECOVERABLE_FROM_SURVIVING_EVIDENCE = "recoverable_from_surviving_evidence"
    UNRECOVERABLE_WITHOUT_EXTERNAL_REDUNDANCY = "unrecoverable_without_external_redundancy"


class CorruptionType(str, Enum):
    """Granular catalog of corruption operators."""
    # Byte-level
    DELETE_BYTES = "delete_bytes"
    TRUNCATE = "truncate"
    ZERO_BYTES = "zero_bytes"
    NOISE_OVERWRITE = "noise_overwrite"
    DUPLICATE_BYTES = "duplicate_bytes"
    INSERT_GARBAGE = "insert_garbage"

    # PDF Structure
    DAMAGE_XREF = "damage_xref"
    REMOVE_XREF_ENTRIES = "remove_xref_entries"
    DAMAGE_TRAILER = "damage_trailer"
    DAMAGE_OFFSETS = "damage_offsets"
    REMOVE_OBJECT = "remove_object"
    TRUNCATE_OBJECT = "truncate_object"
    DAMAGE_OBJECT_BOUNDARIES = "damage_object_boundaries"
    DAMAGE_LENGTH = "damage_length"

    # Stream
    TRUNCATE_STREAM = "truncate_stream"
    REMOVE_STREAM_PREFIX = "remove_stream_prefix"
    REMOVE_STREAM_SUFFIX = "remove_stream_suffix"
    CORRUPT_STREAM_BYTES = "corrupt_stream_bytes"
    DAMAGE_FLATEDECODE = "damage_flatedecode"
    DAMAGE_ASCII85 = "damage_ascii85"
    DAMAGE_STREAM_PAYLOAD_ONLY = "damage_stream_payload_only"

    # Text
    REMOVE_TEXT_OPERATORS = "remove_text_operators"
    REMOVE_TEXT_FRAGMENTS = "remove_text_fragments"
    TRUNCATE_TEXT_STREAMS = "truncate_text_streams"
    DAMAGE_CHAR_ENCODING = "damage_char_encoding"

    # Image
    REMOVE_IMAGE_OBJECT = "remove_image_object"
    TRUNCATE_IMAGE_STREAM = "truncate_image_stream"
    DAMAGE_IMAGE_BYTES = "damage_image_bytes"
    REMOVE_IMAGE_REFERENCES = "remove_image_references"

    # Font
    REMOVE_FONT_OBJECT = "remove_font_object"
    DAMAGE_FONT_REFERENCES = "damage_font_references"
    REMOVE_FONT_METADATA = "remove_font_metadata"
    REMOVE_TOUNICODE = "remove_tounicode"

    # Page / Layout
    REMOVE_PAGE_OBJECT = "remove_page_object"
    DAMAGE_PAGE_TREE = "damage_page_tree"
    REMOVE_CONTENT_REF = "remove_content_ref"
    DAMAGE_RESOURCES = "damage_resources"
    REMOVE_TABLE_FIGURE = "remove_table_figure"

    # Multi
    MULTI_CORRUPTION = "multi_corruption"


class CorruptionOperation(BaseModel):
    """Specification of an individual applied corruption operation."""
    operation_id: str
    type: CorruptionType
    object_id: Optional[str] = None
    page: Optional[int] = None
    offset_start: int = Field(ge=0)
    offset_end: int = Field(ge=0)
    original_length: int = Field(ge=0)
    corrupted_length: int = Field(ge=0)
    severity: float = Field(ge=0.0, le=1.0)
    recoverability: Recoverability
    reversible: bool = False
    details: Dict[str, Any] = Field(default_factory=dict)


class CorruptionManifest(BaseModel):
    """Authoritative manifest describing document corruption with exact parameters."""
    dataset_version: str = "1.0"
    sample_id: str
    source_sha256: str
    corrupted_sha256: str
    source_length: int = Field(ge=0)
    corrupted_length: int = Field(ge=0)
    seed: int
    source_format: str = "pdf"
    severity_level: CorruptionSeverity
    operations: List[CorruptionOperation] = Field(default_factory=list)
    provenance: str = "SYNTHETIC_GROUND_TRUTH"
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()
