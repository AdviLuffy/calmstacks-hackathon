"""TRACE AI and ML Provider Abstraction.

Implements local-first, cloud-optional execution with strict provenance and telemetry.
"""

from trace.ml.providers.base import (
    BaseAIProvider,
    ProviderTelemetry,
    ProviderType,
)
from trace.ml.providers.local import LocalProvider
from trace.ml.providers.gemini import GeminiProvider
from trace.ml.providers.future import FutureCloudProvider
from trace.ml.providers.manager import (
    get_provider,
    is_cloud_ai_allowed,
    get_active_provider_telemetry,
)

__all__ = [
    "BaseAIProvider",
    "ProviderTelemetry",
    "ProviderType",
    "LocalProvider",
    "GeminiProvider",
    "FutureCloudProvider",
    "get_provider",
    "is_cloud_ai_allowed",
    "get_active_provider_telemetry",
]
