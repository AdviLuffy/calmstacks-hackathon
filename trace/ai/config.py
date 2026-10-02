"""Configuration and privacy controls for Google Gemini AI integration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Sequence

from pathlib import Path

DEFAULT_MODEL_PREFERENCE = [
    "gemini-3.5-flash-lite",
    "gemini-flash-latest",
    "gemini-3.8-flash",
    "gemini-3.1-flash-lite",
    "gemini-pro-latest",
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


DEFAULT_AI_PROVIDER = "local"
SUPPORTED_AI_PROVIDERS = ("local", "gemini", "disabled")


def is_cloud_ai_allowed(ai_provider: str, api_key: str) -> bool:
    """Explicit cloud-AI safety gate.
    
    Cloud AI may ONLY execute when:
    1. AI_PROVIDER is explicitly set to 'gemini'
    2. A valid server-side credential exists
    3. Not explicitly disabled by local/testing constraints
    """
    if ai_provider != "gemini":
        return False
    if not api_key:
        return False
    if os.environ.get("TRACE_FORCE_LOCAL") in ("1", "true", "yes"):
        return False
    return True


@dataclass(frozen=True)
class GeminiSettings:
    """Runtime settings for Gemini API integration."""

    enabled: bool
    api_key: str
    model_preference: tuple[str, ...]
    ai_provider: str = DEFAULT_AI_PROVIDER
    max_retries_per_model: int = 2
    timeout_seconds: float = 30.0
    data_minimization: bool = True
    max_text_excerpt_bytes: int = 4096


def load_gemini_settings(skip_dotenv: bool = False) -> GeminiSettings:
    """Read Gemini configuration from environment variables (loading .env if present).
    
    TRACE is LOCAL-FIRST and CLOUD-OPTIONAL.
    By default, AI_PROVIDER=local and cloud AI is gated off.
    """
    _load_env_file(skip_dotenv=skip_dotenv)

    # 1. Determine active AI provider (Default is "local")
    provider_env = os.environ.get("AI_PROVIDER") or os.environ.get("TRACE_AI_PROVIDER")
    enable_env = os.environ.get("GEMINI_ENABLE") or os.environ.get("TRACE_GEMINI_ENABLE")

    if provider_env:
        ai_provider = provider_env.strip().lower()
    elif enable_env is not None and enable_env.lower() in ("1", "true", "yes", "on"):
        # Backward-compatible explicit enable
        ai_provider = "gemini"
    else:
        ai_provider = DEFAULT_AI_PROVIDER

    # 2. Check server-side credentials
    api_key = (
        os.environ.get("GEMINI_API_KEY")
        or os.environ.get("TRACE_GEMINI_API_KEY")
        or ""
    ).strip()

    # 3. Apply Cloud-AI Safety Gate
    if ai_provider in ("local", "disabled"):
        enabled = False
    elif enable_env is not None and enable_env.lower() in ("0", "false", "no", "off"):
        enabled = False
    else:
        enabled = is_cloud_ai_allowed(ai_provider, api_key)

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
        ai_provider=ai_provider,
    )
