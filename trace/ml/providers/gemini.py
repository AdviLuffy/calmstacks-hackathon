"""Cloud-Optional Gemini Intelligence Provider for TRACE.

Gated behind explicit configuration (AI_PROVIDER=gemini) with automatic local fallback
when unconfigured, rate-limited, or quota-exhausted.
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional, Tuple

from trace.ai.client import ResilientGeminiClient
from trace.ai.config import GeminiSettings, is_cloud_ai_allowed, load_gemini_settings
from trace.ml.providers.base import (
    BaseAIProvider,
    ProviderTelemetry,
    ProviderType,
)
from trace.ml.providers.local import LocalProvider
from trace.multimodal.adapter_gemini import GeminiMultimodalAdapter
from trace.multimodal.representation import (
    DocumentElement,
    DocumentPage,
    NormalizedDocument,
    ProvenanceCategory,
)


class GeminiProvider(BaseAIProvider):
    """Optional cloud provider wrapping Gemini with automatic local fallback."""

    def __init__(
        self,
        settings: Optional[GeminiSettings] = None,
        local_fallback: Optional[LocalProvider] = None,
        gemini_client: Optional[ResilientGeminiClient] = None,
    ) -> None:
        self.settings = settings or load_gemini_settings()
        self.local_fallback = local_fallback or LocalProvider()
        self.client = gemini_client or ResilientGeminiClient(settings=self.settings)
        self._adapter = GeminiMultimodalAdapter(gemini_client=self.client)
        self._telemetry = ProviderTelemetry(
            provider="gemini",
            model=self.settings.model_preference[0] if self.settings.model_preference else "gemini-3.5-flash-lite",
            local_or_cloud="cloud",
            request_count=0,
            failure_reason=None,
            fallback_used=False,
            latency_ms=0.0,
        )

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.GEMINI

    @property
    def is_cloud(self) -> bool:
        return True

    @property
    def is_available(self) -> bool:
        """Available ONLY when safety gate passes."""
        return is_cloud_ai_allowed(self.settings.ai_provider, self.settings.api_key) and self.settings.enabled

    def get_telemetry(self) -> ProviderTelemetry:
        return self._telemetry

    def _safe_error(self, exc: Exception) -> str:
        """Strip possible secrets or tokens from error strings."""
        msg = str(exc)
        if self.settings.api_key and self.settings.api_key in msg:
            msg = msg.replace(self.settings.api_key, "[REDACTED_KEY]")
        return msg[:200]

    def classify_fragment(
        self,
        fragment_id: str,
        data: bytes,
    ) -> Dict[str, Any]:
        """Classify fragment via Gemini if available, else local fallback."""
        if not self.is_available:
            self._telemetry.fallback_used = True
            self._telemetry.failure_reason = "Gemini provider gated: falling back to local"
            return self.local_fallback.classify_fragment(fragment_id, data)

        start = time.time()
        try:
            self._telemetry.request_count += 1
            res = self._adapter.classify_fragment(fragment_id, data)
            self._telemetry.latency_ms += (time.time() - start) * 1000
            return res
        except Exception as exc:
            self._telemetry.fallback_used = True
            self._telemetry.failure_reason = self._safe_error(exc)
            return self.local_fallback.classify_fragment(fragment_id, data)

    def infer_relationship(
        self,
        frag_a_id: str,
        frag_a_data: bytes,
        frag_b_id: str,
        frag_b_data: bytes,
    ) -> Dict[str, Any]:
        """Infer relationship via Gemini if available, else local fallback."""
        if not self.is_available:
            self._telemetry.fallback_used = True
            self._telemetry.failure_reason = "Gemini provider gated: falling back to local"
            return self.local_fallback.infer_relationship(frag_a_id, frag_a_data, frag_b_id, frag_b_data)

        start = time.time()
        try:
            self._telemetry.request_count += 1
            res = self._adapter.score_relationship(frag_a_id, frag_a_data, frag_b_id, frag_b_data)
            self._telemetry.latency_ms += (time.time() - start) * 1000
            return res
        except Exception as exc:
            self._telemetry.fallback_used = True
            self._telemetry.failure_reason = self._safe_error(exc)
            return self.local_fallback.infer_relationship(frag_a_id, frag_a_data, frag_b_id, frag_b_data)

    def generate_reconstruction_plan(
        self,
        case_id: str,
        features: Dict[str, Any],
        media_size: int,
        authentic_bytes: int,
        unplaced_count: int,
        session_metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Any, str, str, bool, str]:
        """Obtain reconstruction plan from Gemini or local fallback."""
        if not self.is_available:
            self._telemetry.fallback_used = True
            self._telemetry.failure_reason = "Gemini provider gated: falling back to local"
            return self.local_fallback.generate_reconstruction_plan(
                case_id, features, media_size, authentic_bytes, unplaced_count, session_metadata
            )

        start = time.time()
        try:
            from trace.ai.prompts import build_pdf_reconstruction_prompt
            from trace.ai.schemas import AIPdfReconstructionPlan
            from trace.ai.reconstruction import estimate_fidelity_confidence

            prompt = build_pdf_reconstruction_prompt(
                case_id=case_id,
                surviving_tokens=features.get("surviving_tokens", ["%PDF", "obj", "endobj"]),
                surviving_strings=features.get("surviving_strings", []),
                surviving_objects=features.get("surviving_objects", []),
                media_size=media_size,
                authentic_bytes_count=authentic_bytes,
                unplaced_fragments_count=unplaced_count,
                fonts_found=features.get("fonts_found", ["Helvetica"]),
                session_metadata=session_metadata or {},
                metadata_info=features.get("metadata"),
                page_info=features.get("page_info"),
                object_relationships=features.get("object_relationships"),
                image_info=features.get("image_info"),
                content_streams=features.get("content_streams"),
                recovered_objects_summary=features.get("recovered_objects_summary"),
            )

            self._telemetry.request_count += 1
            ai_resp = self.client.generate_structured(prompt, AIPdfReconstructionPlan)
            self._telemetry.latency_ms += (time.time() - start) * 1000

            if ai_resp.success and ai_resp.data:
                plan = ai_resp.data
                model_used = ai_resp.provenance.model_used or self.settings.model_preference[0]
                return plan, model_used, "google-genai", True, f"Live inference via {model_used}"

            # Quota exhausted or structured validation error
            self._telemetry.fallback_used = True
            self._telemetry.failure_reason = ai_resp.provenance.error or "Gemini response unvalidated"
            return self.local_fallback.generate_reconstruction_plan(
                case_id, features, media_size, authentic_bytes, unplaced_count, session_metadata
            )
        except Exception as exc:
            self._telemetry.fallback_used = True
            self._telemetry.failure_reason = self._safe_error(exc)
            return self.local_fallback.generate_reconstruction_plan(
                case_id, features, media_size, authentic_bytes, unplaced_count, session_metadata
            )

    def detect_layout(
        self,
        page: DocumentPage,
        raw_evidence: Optional[bytes] = None,
    ) -> List[DocumentElement]:
        if not self.is_available:
            self._telemetry.fallback_used = True
            return self.local_fallback.detect_layout(page, raw_evidence)
        try:
            self._telemetry.request_count += 1
            elements = self._adapter.detect_layout(page, raw_evidence)
            if not elements:
                return self.local_fallback.detect_layout(page, raw_evidence)
            return elements
        except Exception as exc:
            self._telemetry.fallback_used = True
            self._telemetry.failure_reason = self._safe_error(exc)
            return self.local_fallback.detect_layout(page, raw_evidence)

    def detect_tables(
        self,
        page: DocumentPage,
        raw_evidence: Optional[bytes] = None,
    ) -> List[DocumentElement]:
        if not self.is_available:
            self._telemetry.fallback_used = True
            return self.local_fallback.detect_tables(page, raw_evidence)
        try:
            self._telemetry.request_count += 1
            tables = self._adapter.detect_tables(page, raw_evidence)
            if not tables:
                return self.local_fallback.detect_tables(page, raw_evidence)
            return tables
        except Exception as exc:
            self._telemetry.fallback_used = True
            self._telemetry.failure_reason = self._safe_error(exc)
            return self.local_fallback.detect_tables(page, raw_evidence)

    def classify_document(
        self,
        document: NormalizedDocument,
    ) -> Dict[str, Any]:
        if not self.is_available:
            self._telemetry.fallback_used = True
            return self.local_fallback.classify_document(document)
        try:
            self._telemetry.request_count += 1
            return self._adapter.classify_document(document)
        except Exception as exc:
            self._telemetry.fallback_used = True
            self._telemetry.failure_reason = self._safe_error(exc)
            return self.local_fallback.classify_document(document)
