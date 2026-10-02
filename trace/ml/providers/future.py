"""Extensible Future Cloud Provider Stub for TRACE.

Ensures TRACE is not locked into any single cloud model provider, while maintaining
local-first fallback safety.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from trace.ml.providers.base import (
    BaseAIProvider,
    ProviderTelemetry,
    ProviderType,
)
from trace.ml.providers.local import LocalProvider
from trace.multimodal.representation import (
    DocumentElement,
    DocumentPage,
    NormalizedDocument,
)


class FutureCloudProvider(BaseAIProvider):
    """Stub/template for future cloud AI models (e.g. Claude, Azure, Vertex)."""

    def __init__(
        self,
        provider_name: str = "future_cloud",
        api_key: Optional[str] = None,
        local_fallback: Optional[LocalProvider] = None,
    ) -> None:
        self._provider_name = provider_name
        self._api_key = api_key or ""
        self.local_fallback = local_fallback or LocalProvider()
        self._telemetry = ProviderTelemetry(
            provider=self._provider_name,
            model="cloud-future-stub",
            local_or_cloud="cloud",
            request_count=0,
            failure_reason="Future cloud provider not configured",
            fallback_used=True,
            latency_ms=0.0,
        )

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.FUTURE_CLOUD

    @property
    def is_cloud(self) -> bool:
        return True

    @property
    def is_available(self) -> bool:
        return bool(self._api_key)

    def get_telemetry(self) -> ProviderTelemetry:
        return self._telemetry

    def classify_fragment(self, fragment_id: str, data: bytes) -> Dict[str, Any]:
        return self.local_fallback.classify_fragment(fragment_id, data)

    def infer_relationship(
        self, frag_a_id: str, frag_a_data: bytes, frag_b_id: str, frag_b_data: bytes
    ) -> Dict[str, Any]:
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
        return self.local_fallback.generate_reconstruction_plan(
            case_id, features, media_size, authentic_bytes, unplaced_count, session_metadata
        )

    def detect_layout(
        self, page: DocumentPage, raw_evidence: Optional[bytes] = None
    ) -> List[DocumentElement]:
        return self.local_fallback.detect_layout(page, raw_evidence)

    def detect_tables(
        self, page: DocumentPage, raw_evidence: Optional[bytes] = None
    ) -> List[DocumentElement]:
        return self.local_fallback.detect_tables(page, raw_evidence)

    def classify_document(self, document: NormalizedDocument) -> Dict[str, Any]:
        return self.local_fallback.classify_document(document)
