"""Schemas for ground-truth forensic records and future ML training labels."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class FragmentLabel(str, Enum):
    """Categorical structural label for a 256B-4KB carved fragment candidate."""
    PDF_HEADER = "PDF_HEADER"
    PDF_OBJECT = "PDF_OBJECT"
    PDF_STREAM = "PDF_STREAM"
    TEXT_STREAM = "TEXT_STREAM"
    IMAGE_STREAM = "IMAGE_STREAM"
    FONT_OBJECT = "FONT_OBJECT"
    PAGE_OBJECT = "PAGE_OBJECT"
    XREF = "XREF"
    TRAILER = "TRAILER"
    METADATA = "METADATA"
    UNKNOWN = "UNKNOWN"


class RecoveryState(str, Enum):
    """Ground-truth forensic recovery state of an element or object."""
    INTACT = "INTACT"
    PARTIALLY_DAMAGED = "PARTIALLY_DAMAGED"
    CORRUPTED = "CORRUPTED"
    MISSING = "MISSING"
    RECOVERED = "RECOVERED"
    UNRECOVERABLE = "UNRECOVERABLE"


class RelationshipLabel(str, Enum):
    """Pairwise relational ground-truth between two carved fragments or objects."""
    SAME_OBJECT = "SAME_OBJECT"
    SAME_STREAM = "SAME_STREAM"
    SAME_PAGE = "SAME_PAGE"
    SAME_RESOURCE_GROUP = "SAME_RESOURCE_GROUP"
    ADJACENT = "ADJACENT"
    UNRELATED = "UNRELATED"


class GroundTruthInventory(BaseModel):
    """Object and structural inventory of a document before/after corruption."""
    total_objects: int = Field(ge=0)
    object_numbers: List[int] = Field(default_factory=list)
    streams_count: int = Field(ge=0)
    pages_count: int = Field(ge=0)
    fonts_count: int = Field(ge=0)
    images_count: int = Field(ge=0)
    tables_count: int = Field(ge=0)
    figures_count: int = Field(ge=0)
    equations_count: int = Field(ge=0)
    total_text_length: int = Field(ge=0)


class GroundTruthRecord(BaseModel):
    """Exhaustive ground truth record preserving full pre- and post-corruption states."""
    sample_id: str
    seed: int
    provenance: str = "SYNTHETIC_GROUND_TRUTH"

    # Integrity
    original_sha256: str
    corrupted_sha256: str
    original_size_bytes: int = Field(ge=0)
    corrupted_size_bytes: int = Field(ge=0)

    # Inventories
    original_inventory: GroundTruthInventory
    corrupted_inventory: GroundTruthInventory

    # Content Ground Truth
    original_text: List[str] = Field(default_factory=list)
    original_images: List[Dict[str, Any]] = Field(default_factory=list)
    original_tables: List[Dict[str, Any]] = Field(default_factory=list)
    original_figures: List[Dict[str, Any]] = Field(default_factory=list)
    original_equations: List[Dict[str, Any]] = Field(default_factory=list)
    original_metadata: Dict[str, Any] = Field(default_factory=dict)

    # Delta & Recoverability
    removed_objects: List[int] = Field(default_factory=list)
    surviving_objects: List[int] = Field(default_factory=list)
    damaged_objects: List[int] = Field(default_factory=list)
    corrupted_byte_regions: List[List[int]] = Field(default_factory=list)

    expected_recoverable_content: Dict[str, Any] = Field(default_factory=dict)
    expected_unrecoverable_content: Dict[str, Any] = Field(default_factory=dict)

    # Future ML Training Labels
    ml_fragment_labels: Dict[str, str] = Field(
        default_factory=dict,
        description="Fragment ID -> FragmentLabel mapping"
    )
    ml_recovery_states: Dict[str, str] = Field(
        default_factory=dict,
        description="Object/Fragment ID -> RecoveryState mapping"
    )
    ml_pairwise_relationships: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="[{'frag_a': id, 'frag_b': id, 'label': RelationshipLabel, 'affinity': float}]"
    )

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump()
