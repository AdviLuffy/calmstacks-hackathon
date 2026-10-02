"""Provider Manager and Cloud-AI Safety Gate for TRACE.

Ensures TRACE is LOCAL-FIRST by default. Cloud AI is only executed when explicitly
configured and authorized.
"""

from __future__ import annotations

import os
from typing import Dict, Optional

from trace.ai.config import DEFAULT_AI_PROVIDER, is_cloud_ai_allowed, load_gemini_settings
from trace.ml.providers.base import (
    BaseAIProvider,
    ProviderTelemetry,
    ProviderType,
)
from trace.ml.providers.future import FutureCloudProvider
from trace.ml.providers.gemini import GeminiProvider
from trace.ml.providers.local import LocalProvider

_GLOBAL_PROVIDERS: Dict[str, BaseAIProvider] = {}


def get_provider(provider_name: Optional[str] = None) -> BaseAIProvider:
    """Retrieve intelligence provider adhering to local-first architecture.
    
    Order of precedence:
    1. Explicit provider_name argument
    2. AI_PROVIDER / TRACE_AI_PROVIDER environment variable
    3. DEFAULT_AI_PROVIDER ('local')
    
    Cloud AI safety gate:
    If 'gemini' is requested but credentials or explicit permission are absent,
    automatically returns LocalProvider without failing.
    """
    settings = load_gemini_settings()

    target = (
        provider_name
        or os.environ.get("AI_PROVIDER")
        or os.environ.get("TRACE_AI_PROVIDER")
        or settings.ai_provider
        or DEFAULT_AI_PROVIDER
    ).strip().lower()

    if target in ("local", "disabled"):
        if "local" not in _GLOBAL_PROVIDERS:
            _GLOBAL_PROVIDERS["local"] = LocalProvider()
        return _GLOBAL_PROVIDERS["local"]

    if target == "gemini":
        # Cloud AI safety gate check
        if is_cloud_ai_allowed("gemini", settings.api_key) and settings.enabled:
            if "gemini" not in _GLOBAL_PROVIDERS:
                _GLOBAL_PROVIDERS["gemini"] = GeminiProvider(settings=settings)
            return _GLOBAL_PROVIDERS["gemini"]
        else:
            # Gated: Return local provider as safe fallback
            if "local" not in _GLOBAL_PROVIDERS:
                _GLOBAL_PROVIDERS["local"] = LocalProvider()
            return _GLOBAL_PROVIDERS["local"]

    if target == "future_cloud":
        if "future_cloud" not in _GLOBAL_PROVIDERS:
            _GLOBAL_PROVIDERS["future_cloud"] = FutureCloudProvider()
        return _GLOBAL_PROVIDERS["future_cloud"]

    # Fallback to local
    if "local" not in _GLOBAL_PROVIDERS:
        _GLOBAL_PROVIDERS["local"] = LocalProvider()
    return _GLOBAL_PROVIDERS["local"]


def get_active_provider_telemetry() -> ProviderTelemetry:
    """Retrieve execution telemetry for active provider without secret leakage."""
    provider = get_provider()
    return provider.get_telemetry()
