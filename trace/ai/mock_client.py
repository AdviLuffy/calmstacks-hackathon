"""Deterministic mock client for testing Gemini fallback queues, rate limits, and provenance."""

from __future__ import annotations

import time
from typing import Any, Mapping, Sequence, Type, TypeVar
from pydantic import BaseModel

from trace.ai.client import AIModelProvenance, AIResponse, ResilientGeminiClient
from trace.ai.config import GeminiSettings
from trace.ai.schemas import (
    AIAmbiguityResolution,
    AIEvidenceExplanation,
    AIFragmentClassification,
    AIRecoveryRecommendations,
    AIRelationshipInference,
)

T = TypeVar("T", bound=BaseModel)


class MockGeminiClient(ResilientGeminiClient):
    """Deterministic mock client simulating model failures, fallbacks, and responses."""

    def __init__(
        self,
        settings: GeminiSettings | None = None,
        fail_models: Sequence[str] = (),
        auth_error: bool = False,
        quota_exhausted: bool = False,
        rate_limit_models: Sequence[str] = (),
    ) -> None:
        mock_settings = settings or GeminiSettings(
            enabled=True,
            api_key="test-mock-key-12345",
            model_preference=(
                "gemini-3.8-flash",
                "gemini-3.5-flash-lite",
                "gemini-3.1-pro-preview",
            ),
        )
        super().__init__(settings=mock_settings)
        self.fail_models = set(fail_models)
        self.auth_error = auth_error
        self.quota_exhausted = quota_exhausted
        self.rate_limit_models = set(rate_limit_models)

    def generate_structured(
        self,
        prompt: str,
        response_schema: Type[T],
        system_instruction: str = "",
    ) -> AIResponse:
        prov = AIModelProvenance()
        start = time.time()

        if self.auth_error:
            prov.error = "Authentication failure: 401 Unauthorized"
            prov.attempts.append({"model": self.settings.model_preference[0], "status": "auth_error"})
            return AIResponse(success=False, provenance=prov)

        if self.quota_exhausted:
            prov.error = "API Quota exhausted: 429 Quota Exceeded"
            prov.attempts.append({"model": self.settings.model_preference[0], "status": "quota_exhausted"})
            return AIResponse(success=False, provenance=prov)

        for idx, model_name in enumerate(self.settings.model_preference):
            if model_name in self.fail_models:
                prov.attempts.append({"model": model_name, "status": "model_not_found"})
                continue

            # Model succeeds
            prov.attempts.append({"model": model_name, "status": "success"})
            prov.model_used = model_name
            prov.fallback_occurred = idx > 0
            prov.structured_validation_passed = True
            prov.latency_ms = (time.time() - start) * 1000

            # Synthesize deterministic schema-compliant instance
            if response_schema is AIFragmentClassification:
                data = AIFragmentClassification(
                    fragment_id="FRAG-TEST-01",
                    likely_file_type="pdf",
                    structural_role="header",
                    confidence=0.95,
                    key_markers_found=["%PDF-1.4"],
                    reasoning="Detected standard PDF magic header and version string.",
                )
            elif response_schema is AIRelationshipInference:
                data = AIRelationshipInference(
                    source_fragment_id="FRAG-0001",
                    target_fragment_id="FRAG-0002",
                    affinity_score=0.9,
                    relationship_type="sequential",
                    can_precede=True,
                    reasoning="Fragment A ends with stream data; Fragment B continues stream syntax.",
                )
            elif response_schema is AIEvidenceExplanation:
                data = AIEvidenceExplanation(
                    executive_summary="Forensic analysis recovered multiple digital artifacts.",
                    recovered_artifacts_overview="Successfully reconstructed PDF and image files.",
                    missing_data_assessment="0 missing fragments in complete chain.",
                    evidentiary_integrity_statement="Byte-for-byte deterministic verification confirmed.",
                    risk_factors=[],
                )
            elif response_schema is AIAmbiguityResolution:
                data = AIAmbiguityResolution(
                    selected_chain_index=0,
                    selection_confidence=0.88,
                    rejection_reasons=["Candidate chain 1 contained out-of-order object IDs."],
                    integrity_assessment="High structural coherence.",
                )
            elif response_schema is AIRecoveryRecommendations:
                data = AIRecoveryRecommendations(
                    recommended_next_steps=["Export forensic evidence report", "Store raw evidence image"],
                    cautions=["Ensure write-blocker was enabled during acquisition"],
                )
            else:
                data = None

            return AIResponse(
                success=True,
                data=data,
                raw_text=data.model_dump_json() if data else "{}",
                provenance=prov,
            )

        prov.error = "All configured Gemini models failed."
        return AIResponse(success=False, provenance=prov)

    def test_connection(self) -> dict[str, Any]:
        """Simulate connection test without external network calls."""
        if not self.settings.enabled or not self.settings.api_key:
            return {
                "connected": False,
                "status": "unconfigured",
                "message": "GEMINI_API_KEY is not configured",
                "latency_ms": 0.0,
            }
        if self.auth_error:
            return {
                "connected": False,
                "status": "auth_error",
                "error": "Authentication failed: 401 Unauthorized",
                "message": "Invalid API key",
                "latency_ms": 1.5,
            }
        if self.quota_exhausted:
            return {
                "connected": False,
                "status": "quota_exhausted",
                "error": "API Quota exhausted: 429 Quota Exceeded",
                "message": "API Quota exhausted",
                "latency_ms": 1.5,
            }
        for model in self.settings.model_preference:
            if model in self.fail_models:
                continue
            return {
                "connected": True,
                "status": "connected",
                "model": model,
                "message": "Successfully connected to Google Gemini API",
                "latency_ms": 5.0,
            }
        return {
            "connected": False,
            "status": "error",
            "error": "All configured Gemini models failed.",
            "message": "Connection test failed",
            "latency_ms": 5.0,
        }

