"""Configuration and privacy controls for Google Gemini AI integration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Sequence

DEFAULT_MODEL_PREFERENCE = [
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-pro-preview",
    "gemini-3.1-flash-lite",
    "gemini-flash-latest",
]


@dataclass(frozen=True)
class GeminiSettings:
    """Runtime settings for Gemini API integration."""

    enabled: bool
    api_key: str
    model_preference: tuple[str, ...]
    max_retries_per_model: int = 2
    timeout_seconds: float = 30.0
    data_minimization: bool = True
    max_text_excerpt_bytes: int = 4096


def load_gemini_settings() -> GeminiSettings:
    """Read Gemini configuration from environment variables."""
    # Check both GEMINI_... and TRACE_GEMINI_...
    api_key = (
        os.environ.get("GEMINI_API_KEY")
        or os.environ.get("TRACE_GEMINI_API_KEY")
        or ""
    ).strip()

    enable_env = os.environ.get("GEMINI_ENABLE") or os.environ.get("TRACE_GEMINI_ENABLE")
    if enable_env is not None:
        enabled = enable_env.lower() in ("1", "true", "yes", "on")
    else:
        # Enabled by default if API key is provided
        enabled = bool(api_key)

    pref_env = os.environ.get("GEMINI_MODEL_PREFERENCE") or os.environ.get(
        "TRACE_GEMINI_MODEL_PREFERENCE"
    )
    if pref_env:
        models = [m.strip() for m in pref_env.split(",") if m.strip()]
    else:
        models = list(DEFAULT_MODEL_PREFERENCE)

    return GeminiSettings(
        enabled=enabled,
        api_key=api_key,
        model_preference=tuple(models),
    )
