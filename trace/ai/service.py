"""High-level AI service orchestrating forensic intelligence tasks with data minimization."""

from __future__ import annotations

import math
from typing import Any, Mapping, Sequence

from trace.ai.client import AIResponse, ResilientGeminiClient
from trace.ai.prompts import (
    build_evidence_explanation_prompt,
    build_fragment_classification_prompt,
    build_relationship_prompt,
)
from trace.ai.schemas import (
    AIAmbiguityResolution,
    AIEvidenceExplanation,
    AIFragmentClassification,
    AIRecoveryRecommendations,
    AIRelationshipInference,
)
from trace.recovery.models import FragmentCandidate, RecoveredArtifact


class GeminiForensicService:
    """Intelligent digital forensics assistant powered by Google Gemini with deterministic verification."""

    def __init__(self, client: ResilientGeminiClient | None = None) -> None:
        self.client = client or ResilientGeminiClient()

    @property
    def is_available(self) -> bool:
        return self.client.settings.enabled and bool(self.client.settings.api_key)

    @staticmethod
    def calculate_entropy(data: bytes) -> float:
        """Compute Shannon entropy (0.0 to 8.0) over byte sequence."""
        if not data:
            return 0.0
        counts = [0] * 256
        for b in data:
            counts[b] += 1
        entropy = 0.0
        for count in counts:
            if count > 0:
                p = count / len(data)
                entropy -= p * math.log2(p)
        return round(entropy, 2)

    def classify_fragment(self, fragment: FragmentCandidate) -> AIResponse:
        """Classify fragment candidate using minimized metadata and safe byte excerpt."""
        entropy = fragment.entropy or self.calculate_entropy(fragment.data)
        ascii_preview = "".join(
            chr(b) if 32 <= b <= 126 else "." for b in fragment.data[:256]
        )
        prompt = build_fragment_classification_prompt(
            fragment_id=fragment.fragment_id,
            size_bytes=fragment.size_bytes,
            entropy=entropy,
            tokens=fragment.tokens,
            ascii_preview=ascii_preview,
        )
        return self.client.generate_structured(prompt, AIFragmentClassification)

    def infer_fragment_relationship(
        self, frag_a: FragmentCandidate, frag_b: FragmentCandidate
    ) -> AIResponse:
        """Infer whether frag_a can directly precede frag_b based on boundary tokens."""
        tail_preview = "".join(
            chr(b) if 32 <= b <= 126 else "." for b in frag_a.data[-128:]
        )
        head_preview = "".join(
            chr(b) if 32 <= b <= 126 else "." for b in frag_b.data[:128]
        )
        prompt = build_relationship_prompt(
            frag_a_id=frag_a.fragment_id,
            frag_a_role=frag_a.structural_role,
            frag_a_tail=tail_preview,
            frag_b_id=frag_b.fragment_id,
            frag_b_role=frag_b.structural_role,
            frag_b_head=head_preview,
        )
        return self.client.generate_structured(prompt, AIRelationshipInference)

    def explain_case_recovery(
        self,
        case_id: str,
        artifacts: Sequence[RecoveredArtifact],
        unplaced_fragments_count: int = 0,
    ) -> AIResponse:
        """Generate factual investigator summary for recovered evidence."""
        summary = [
            {
                "filename": a.filename,
                "format_name": a.format_name,
                "size_bytes": a.size_bytes,
                "category": a.category.value,
                "integrity_score": a.validation.integrity_score,
            }
            for a in artifacts
        ]
        prompt = build_evidence_explanation_prompt(
            case_id=case_id,
            artifacts_summary=summary,
            unplaced_count=unplaced_fragments_count,
        )
        return self.client.generate_structured(prompt, AIEvidenceExplanation)
