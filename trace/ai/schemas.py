"""Pydantic schemas for structured output from Gemini models."""

from __future__ import annotations

from typing import Any, List, Optional
from pydantic import BaseModel, Field


class AIFragmentClassification(BaseModel):
    """Structured classification for a carved fragment candidate."""

    fragment_id: str
    likely_file_type: str = Field(description="Identified format, e.g. pdf, png, jpeg, zip, text, binary")
    structural_role: str = Field(description="Structural role: header, footer, stream, table, catalog, data")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score from 0.0 to 1.0")
    key_markers_found: List[str] = Field(default_factory=list, description="Signatures or tokens identified")
    reasoning: str = Field(description="Explainable rationale grounded in byte features")


class AIRelationshipInference(BaseModel):
    """Inferred structural relationship between two fragments."""

    source_fragment_id: str
    target_fragment_id: str
    affinity_score: float = Field(ge=0.0, le=1.0, description="Continuity or affinity score")
    relationship_type: str = Field(description="Sequential, structural_link, object_reference, or disjoint")
    can_precede: bool = Field(description="Whether source fragment can directly precede target")
    reasoning: str = Field(description="Explainable syntactic or structural justification")


class AIAmbiguityResolution(BaseModel):
    """Evaluation of competing reconstruction candidate chains."""

    selected_chain_index: int = Field(description="Zero-based index of the most plausible candidate chain")
    selection_confidence: float = Field(ge=0.0, le=1.0)
    rejection_reasons: List[str] = Field(default_factory=list, description="Why other chains were rejected")
    integrity_assessment: str = Field(description="Assessment of structural continuity and completeness")


class AIEvidenceExplanation(BaseModel):
    """Human-readable factual explanation of forensic recovery findings."""

    executive_summary: str
    recovered_artifacts_overview: str
    missing_data_assessment: str
    evidentiary_integrity_statement: str
    risk_factors: List[str] = Field(default_factory=list)


class AIRecoveryRecommendations(BaseModel):
    """Actionable recommendations for the forensic investigator."""

    recommended_next_steps: List[str]
    cautions: List[str]
    additional_carving_targets: List[str] = Field(default_factory=list)
