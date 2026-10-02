"""Forensic relationship scorer for document fragments.

Computes multi-component affinity scores, categorized evidence trails,
uncertainty factors, and relationship types between candidate fragments.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Sequence, Tuple

from trace.ml.relationships.features import (
    FragmentInput,
    PairwiseFeatureExtractor,
    PairwiseRelationshipFeatures,
)

logger = logging.getLogger(__name__)


class RelationshipType(str, Enum):
    """Categorical classification of pairwise relationship."""
    ADJACENT = "ADJACENT"
    STREAM_CONTINUATION = "STREAM_CONTINUATION"
    OBJECT_REFERENCE = "OBJECT_REFERENCE"
    STRUCTURAL_TRANSITION = "STRUCTURAL_TRANSITION"
    DICT_CONTINUATION = "DICT_CONTINUATION"
    DISJOINT = "DISJOINT"


class ConfidenceTier(str, Enum):
    """Calibrated confidence tier reflecting evidence strength."""
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NEGLIGIBLE = "NEGLIGIBLE"


@dataclass
class CandidateRelationship:
    """Detailed relationship proposal between two fragments."""
    from_fragment_id: str
    to_fragment_id: str
    affinity_score: float
    relationship_type: RelationshipType
    confidence_tier: ConfidenceTier
    component_scores: Dict[str, float] = field(default_factory=dict)
    evidence_observed: List[str] = field(default_factory=list)
    inferred_compatibility: List[str] = field(default_factory=list)
    negative_signals: List[str] = field(default_factory=list)
    uncertainty_limitations: List[str] = field(default_factory=list)
    provenance: str = "HEURISTIC_AFFINITY"

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["relationship_type"] = self.relationship_type.value
        data["confidence_tier"] = self.confidence_tier.value
        return data


class ForensicRelationshipScorer:
    """Calculates explainable affinity scores between candidate forensic fragments."""

    def __init__(
        self,
        weight_physical: float = 0.35,
        weight_syntax: float = 0.30,
        weight_object_ref: float = 0.20,
        weight_structural: float = 0.15,
        weight_ml_advisory: float = 0.10,
        feature_extractor: Optional[PairwiseFeatureExtractor] = None,
    ) -> None:
        self.w_physical = weight_physical
        self.w_syntax = weight_syntax
        self.w_object_ref = weight_object_ref
        self.w_structural = weight_structural
        self.w_ml = weight_ml_advisory
        self.extractor = feature_extractor or PairwiseFeatureExtractor()

    def score_pair(
        self,
        frag_a: FragmentInput,
        frag_b: FragmentInput,
    ) -> CandidateRelationship:
        """Calculate directed affinity from frag_a to frag_b."""
        if frag_a.fragment_id == frag_b.fragment_id:
            return CandidateRelationship(
                from_fragment_id=frag_a.fragment_id,
                to_fragment_id=frag_b.fragment_id,
                affinity_score=0.0,
                relationship_type=RelationshipType.DISJOINT,
                confidence_tier=ConfidenceTier.NEGLIGIBLE,
                negative_signals=["self_referential_link"],
            )

        features = self.extractor.extract_features(frag_a, frag_b)

        # 1. Physical Spatial Component
        s_physical = 0.0
        if features.is_physically_adjacent:
            s_physical = 1.0
        elif features.same_source and features.is_forward_ordered:
            s_physical = features.spatial_proximity_score

        # 2. Syntax & Boundary Continuity Component
        s_syntax = 0.0
        if features.token_boundary_continuity:
            s_syntax = max(s_syntax, 1.0)
        if features.stream_continuation_signal:
            s_syntax = max(s_syntax, 0.85)
        if features.dict_continuation_signal:
            s_syntax = max(s_syntax, 0.75)
        if features.text_continuation_signal:
            s_syntax = max(s_syntax, 0.70)
        if features.ascii_boundary_continuity:
            s_syntax = max(s_syntax, 0.30)

        # 3. Object Reference Component
        s_obj = 0.0
        if features.a_references_b:
            s_obj = max(s_obj, 0.85)
        if features.has_ascending_object_id:
            s_obj = max(s_obj, 0.65)
        if features.b_references_a:
            s_obj = max(s_obj, 0.50)

        # 4. Structural Transition Component
        s_struct = 0.0
        if features.is_xref_to_trailer:
            s_struct = 0.95
        elif features.is_trailer_to_eof:
            s_struct = 0.90
        elif features.is_header_to_body:
            s_struct = 0.80
        elif features.is_body_to_xref:
            s_struct = 0.75

        # 5. Advisory ML Component
        s_ml = features.ml_advisory_compatibility

        # 6. Negative Penalties
        penalty = 0.0
        if features.is_contradictory_header_pair:
            penalty += 0.90
        if features.is_contradictory_eof_pair:
            penalty += 0.80
        if features.stream_conflict_signal:
            penalty += 0.40
        if features.same_source and not features.is_forward_ordered:
            penalty += 0.70

        # Forensic rule hierarchy based on direct observed physical and structural evidence
        if features.same_source and features.offset_distance is not None:
            if features.offset_distance == 0:
                base_score = 0.85
                if s_syntax >= 0.5 or s_obj >= 0.5 or s_struct >= 0.5:
                    base_score = 0.95
            elif features.offset_distance > 0:
                # Non-contiguous gap in same evidence source
                if features.token_boundary_continuity:
                    base_score = 0.90
                elif features.a_references_b:
                    base_score = 0.45
                elif features.is_xref_to_trailer:
                    base_score = 0.50
                elif features.is_trailer_to_eof:
                    base_score = 0.50
                elif features.has_ascending_object_id and features.offset_distance <= 256:
                    base_score = 0.40
                else:
                    base_score = min(0.35, s_physical * 0.35)
            else:
                base_score = 0.0
        elif features.token_boundary_continuity:
            base_score = 0.90
        elif features.stream_continuation_signal:
            base_score = 0.85
        elif features.is_xref_to_trailer:
            base_score = 0.85
        elif features.is_trailer_to_eof:
            base_score = 0.85
        elif features.is_header_to_body:
            base_score = 0.75
        elif features.a_references_b:
            base_score = 0.75
        elif features.dict_continuation_signal:
            base_score = 0.70
        elif features.text_continuation_signal:
            base_score = 0.65
        elif features.has_ascending_object_id:
            base_score = 0.60
        elif s_ml >= 0.60:
            base_score = s_ml
        else:
            base_score = 0.05

        final_score = max(0.0, min(1.0, base_score - penalty))
        final_score = round(final_score, 4)

        # Determine Primary Relationship Type
        if features.token_boundary_continuity or features.is_physically_adjacent:
            rel_type = RelationshipType.ADJACENT
        elif features.stream_continuation_signal:
            rel_type = RelationshipType.STREAM_CONTINUATION
        elif features.a_references_b or features.has_ascending_object_id:
            rel_type = RelationshipType.OBJECT_REFERENCE
        elif features.dict_continuation_signal:
            rel_type = RelationshipType.DICT_CONTINUATION
        elif features.is_header_to_body or features.is_xref_to_trailer or features.is_trailer_to_eof:
            rel_type = RelationshipType.STRUCTURAL_TRANSITION
        else:
            rel_type = RelationshipType.DISJOINT

        # Confidence Tier
        if final_score >= 0.80:
            conf_tier = ConfidenceTier.HIGH
        elif final_score >= 0.55:
            conf_tier = ConfidenceTier.MEDIUM
        elif final_score >= 0.35:
            conf_tier = ConfidenceTier.LOW
        else:
            conf_tier = ConfidenceTier.NEGLIGIBLE

        # Uncertainty Limitations
        uncertainties = list(features.uncertainty_factors)
        if not features.same_source:
            uncertainties.append("fragments_not_verifiably_from_same_source_file")
        if final_score < 0.55:
            uncertainties.append("weak_evidence_corroboration")

        return CandidateRelationship(
            from_fragment_id=frag_a.fragment_id,
            to_fragment_id=frag_b.fragment_id,
            affinity_score=final_score,
            relationship_type=rel_type,
            confidence_tier=conf_tier,
            component_scores={
                "physical_spatial": round(s_physical, 4),
                "syntax_boundary": round(s_syntax, 4),
                "object_reference": round(s_obj, 4),
                "structural_transition": round(s_struct, 4),
                "ml_advisory": round(s_ml, 4),
                "negative_penalty": round(penalty, 4),
            },
            evidence_observed=features.observed_evidence,
            inferred_compatibility=features.inferred_compatibility,
            negative_signals=features.negative_signals,
            uncertainty_limitations=uncertainties,
            provenance="HEURISTIC_AFFINITY",
        )

    def score_all_pairs(
        self,
        fragments: Sequence[FragmentInput],
        min_threshold: float = 0.35,
        top_k: Optional[int] = None,
    ) -> List[CandidateRelationship]:
        """Score all directed pairs of fragments and return sorted candidates."""
        candidates: List[CandidateRelationship] = []

        for i, a in enumerate(fragments):
            for j, b in enumerate(fragments):
                if i == j:
                    continue
                cand = self.score_pair(a, b)
                if cand.affinity_score >= min_threshold:
                    candidates.append(cand)

        # Deterministic stable tie-breaking:
        # 1. affinity_score descending
        # 2. from_fragment_id ascending
        # 3. to_fragment_id ascending
        candidates.sort(
            key=lambda c: (-c.affinity_score, c.from_fragment_id, c.to_fragment_id)
        )

        if top_k is not None and top_k > 0:
            return candidates[:top_k]
        return candidates
