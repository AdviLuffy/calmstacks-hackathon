"""Configuration and privacy controls for Google Gemini AI integration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Sequence

from pathlib import Path

DEFAULT_MODEL_PREFERENCE = [
    "gemini-3.8-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-pro-preview",
    "gemini-3.1-flash-lite",
    "gemini-flash-latest",
]


def _load_env_file(skip_dotenv: bool = False) -> None:
    """Load local .env file if present in workspace without overwriting existing environment."""
    if skip_dotenv or os.environ.get("TRACE_SKIP_DOTENV") == "1":
        return
    repo_root = Path(__file__).resolve().parent.parent.parent
    env_path = repo_root / ".env"
    if env_path.is_file():
        try:
            from dotenv import load_dotenv

            load_dotenv(dotenv_path=env_path)
        except Exception:
            # Fallback direct line parser if python-dotenv fails
            try:
                for line in env_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("\"'")
                        if k and k not in os.environ:
                            os.environ[k] = v
            except Exception:
                pass


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


def load_gemini_settings(skip_dotenv: bool = False) -> GeminiSettings:
    """Read Gemini configuration from environment variables (loading .env if present)."""
    _load_env_file(skip_dotenv=skip_dotenv)

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
