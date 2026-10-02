"""Base abstract interface and telemetry models for TRACE intelligence providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from trace.multimodal.representation import (
    DocumentElement,
    DocumentPage,
    NormalizedDocument,
    ProvenanceCategory,
)


class ProviderType(str, Enum):
    """Enumeration of recognized intelligence providers."""
    LOCAL = "local"
    GEMINI = "gemini"
    DISABLED = "disabled"
    FUTURE_CLOUD = "future_cloud"


class ProviderTelemetry(BaseModel):
    """Execution telemetry and audit provenance for an AI/ML provider.
    
    CRITICAL: Never store, log, or serialize API keys, secrets, or tokens.
    """
    provider: str = Field(description="'local', 'gemini', 'future_cloud', etc.")
    model: str = Field(description="Active model name or identifier")
    local_or_cloud: str = Field(description="'local' vs 'cloud'")
    request_count: int = Field(default=0, ge=0)
    failure_reason: Optional[str] = Field(default=None, description="Safe error/fallback reason")
    fallback_used: bool = Field(default=False)
    latency_ms: float = Field(default=0.0, ge=0.0)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to safe dictionary guaranteed not to leak secrets."""
        return {
            "provider": self.provider,
            "model": self.model,
            "local_or_cloud": self.local_or_cloud,
            "request_count": self.request_count,
            "failure_reason": self.failure_reason,
            "fallback_used": self.fallback_used,
            "latency_ms": round(self.latency_ms, 2),
        }


class BaseAIProvider(ABC):
    """Abstract contract for intelligence and document reconstruction providers."""

    @property
    @abstractmethod
    def provider_type(self) -> ProviderType:
        """Return the category of provider (LOCAL, GEMINI, etc.)."""
        raise NotImplementedError

    @property
    @abstractmethod
    def is_cloud(self) -> bool:
        """Return True if this provider communicates with external cloud APIs."""
        raise NotImplementedError

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the provider is currently ready to process requests."""
        raise NotImplementedError

    @abstractmethod
    def get_telemetry(self) -> ProviderTelemetry:
        """Retrieve aggregated execution telemetry."""
        raise NotImplementedError

    @abstractmethod
    def classify_fragment(
        self,
        fragment_id: str,
        data: bytes,
    ) -> Dict[str, Any]:
        """Classify a carved binary fragment."""
        raise NotImplementedError

    @abstractmethod
    def infer_relationship(
        self,
        frag_a_id: str,
        frag_a_data: bytes,
        frag_b_id: str,
        frag_b_data: bytes,
    ) -> Dict[str, Any]:
        """Infer affinity and relationship between two fragments."""
        raise NotImplementedError

    @abstractmethod
    def generate_reconstruction_plan(
        self,
        case_id: str,
        features: Dict[str, Any],
        media_size: int,
        authentic_bytes: int,
        unplaced_count: int,
        session_metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Any, str, str, bool, str]:
        """Generate PDF reconstruction plan.
        
        Returns:
            Tuple of (plan, model_used, provider_name, ai_invoked, inference_result)
        """
        raise NotImplementedError

    @abstractmethod
    def detect_layout(
        self,
        page: DocumentPage,
        raw_evidence: Optional[bytes] = None,
    ) -> List[DocumentElement]:
        """Segment page into layout elements."""
        raise NotImplementedError

    @abstractmethod
    def detect_tables(
        self,
        page: DocumentPage,
        raw_evidence: Optional[bytes] = None,
    ) -> List[DocumentElement]:
        """Identify structured tables."""
        raise NotImplementedError

    @abstractmethod
    def classify_document(
        self,
        document: NormalizedDocument,
    ) -> Dict[str, Any]:
        """Classify overall document genre."""
        raise NotImplementedError
