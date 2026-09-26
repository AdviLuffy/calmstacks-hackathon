"""Explainable recovery scoring, prioritization ranking, and integrity categorization."""

from __future__ import annotations

from typing import Sequence

from trace.recovery.models import RecoveredArtifact, RecoveryCategory


class RecoveryPrioritizer:
    """Calculates explainable confidence scores and prioritizes recovered evidence."""

    @staticmethod
    def calculate_score(
        category: RecoveryCategory,
        is_valid: bool,
        integrity_score: float,
        fragments_placed: int,
        fragments_total: int,
        has_corruption: bool = False,
        is_ground_truth_matched: bool = False,
    ) -> tuple[float, str]:
        """Compute transparent 0-100 score and explainable rationale.

        Components:
        - Category baseline:
            VERIFIED: 100
            RECOVERED: 80-95 based on format integrity
            PARTIAL: 40-70 based on fragment placement ratio
            CANDIDATE: 20-40 based on plausibility
            UNRECOVERABLE: 0-10
        - Placement ratio: up to 30 points
        - Structural integrity: up to 40 points
        - Verification bonus: up to 30 points
        """
        if is_ground_truth_matched and category == RecoveryCategory.VERIFIED:
            return 100.0, "Cryptographically verified byte-for-byte against independent ground truth."

        total = max(1, fragments_total)
        ratio = fragments_placed / total

        # Baseline by category
        if category == RecoveryCategory.RECOVERED:
            score = 75.0 + (integrity_score * 20.0) + (ratio * 5.0)
            reason = (
                f"Structurally valid {integrity_score*100:.0f}% format integrity. "
                f"100% fragments placed ({fragments_placed}/{fragments_total}). Ground truth unavailable."
            )
        elif category == RecoveryCategory.PARTIAL:
            score = 30.0 + (ratio * 35.0) + (integrity_score * 15.0)
            reason = (
                f"Incomplete reconstruction: {fragments_placed}/{fragments_total} fragments placed "
                f"({ratio*100:.1f}%). Missing or damaged structures remain."
            )
        elif category == RecoveryCategory.CANDIDATE:
            score = 20.0 + (ratio * 20.0)
            reason = (
                f"Plausible candidate chain established ({fragments_placed}/{fragments_total} fragments), "
                "pending format validation."
            )
        else:  # UNRECOVERABLE
            score = max(0.0, ratio * 10.0)
            reason = "No valid structural chain could be formed within search boundaries."

        if has_corruption:
            score = max(5.0, score - 15.0)
            reason += " (Penalty: structural corruption detected in stream)"

        return min(100.0, max(0.0, score)), reason

    @classmethod
    def prioritize_artifacts(
        cls, artifacts: Sequence[RecoveredArtifact]
    ) -> list[RecoveredArtifact]:
        """Rank artifacts by evidentiary confidence and completeness."""

        # Priority order of categories: VERIFIED > RECOVERED > PARTIAL > CANDIDATE > UNRECOVERABLE
        category_weights = {
            RecoveryCategory.VERIFIED: 1000.0,
            RecoveryCategory.RECOVERED: 500.0,
            RecoveryCategory.PARTIAL: 200.0,
            RecoveryCategory.CANDIDATE: 100.0,
            RecoveryCategory.UNRECOVERABLE: 0.0,
        }

        def sort_key(art: RecoveredArtifact) -> tuple[float, float, int]:
            cat_weight = category_weights.get(art.category, 0.0)
            return (cat_weight + art.confidence_score, art.confidence_score, art.size_bytes)

        return sorted(artifacts, key=sort_key, reverse=True)
