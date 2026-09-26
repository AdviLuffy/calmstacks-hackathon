"""Resilient Google Gemini client with model fallback queue, retry logic, and provenance."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping, Optional, Type, TypeVar
from pydantic import BaseModel

from trace.ai.config import GeminiSettings, load_gemini_settings
from trace.ai.prompts import SYSTEM_INSTRUCTION_BASE

T = TypeVar("T", bound=BaseModel)

try:
    from google import genai
    from google.genai import types
    SDK_AVAILABLE = True
except ImportError:
    SDK_AVAILABLE = False


@dataclass
class AIModelProvenance:
    """Audit provenance for AI model execution."""

    model_used: str | None = None
    fallback_occurred: bool = False
    attempts: list[dict[str, Any]] = field(default_factory=list)
    latency_ms: float = 0.0
    timestamp_utc: str = field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    )
    structured_validation_passed: bool = False
    error: str | None = None


@dataclass
class AIResponse:
    """Unified response containing validated structured output and provenance."""

    success: bool
    data: Any | None = None
    raw_text: str = ""
    provenance: AIModelProvenance = field(default_factory=AIModelProvenance)
    is_disabled: bool = False


class ResilientGeminiClient:
    """Client implementing the official model fallback queue and forensic safety policies."""

    def __init__(self, settings: GeminiSettings | None = None) -> None:
        self.settings = settings or load_gemini_settings()
        self._genai_client = None
        if self.settings.enabled and self.settings.api_key and SDK_AVAILABLE:
            try:
                self._genai_client = genai.Client(api_key=self.settings.api_key)
            except Exception:
                pass

    def generate_structured(
        self,
        prompt: str,
        response_schema: Type[T],
        system_instruction: str = SYSTEM_INSTRUCTION_BASE,
    ) -> AIResponse:
        """Execute request across configured model fallback queue, returning validated Pydantic model."""
        prov = AIModelProvenance()
        start_time = time.time()

        if not self.settings.enabled or not self.settings.api_key:
            prov.latency_ms = (time.time() - start_time) * 1000
            prov.error = "Gemini AI is disabled or GEMINI_API_KEY is not configured."
            return AIResponse(
                success=False,
                data=None,
                raw_text="",
                provenance=prov,
                is_disabled=True,
            )

        models = list(self.settings.model_preference)
        last_error = ""

        for idx, model_name in enumerate(models):
            attempt_info = {"model": model_name, "attempt_index": idx, "status": "pending"}
            prov.attempts.append(attempt_info)

            # Up to max_retries_per_model for transient errors
            for retry in range(self.settings.max_retries_per_model + 1):
                try:
                    if not self._genai_client and SDK_AVAILABLE:
                        self._genai_client = genai.Client(api_key=self.settings.api_key)

                    if self._genai_client:
                        # Use official google-genai SDK
                        config = types.GenerateContentConfig(
                            system_instruction=system_instruction,
                            response_mime_type="application/json",
                            response_schema=response_schema,
                            temperature=0.1,
                        )
                        response = self._genai_client.models.generate_content(
                            model=model_name,
                            contents=prompt,
                            config=config,
                        )
                        raw_text = response.text or ""
                    else:
                        raise RuntimeError("google-genai SDK not initialized")

                    # Validate structured output (supports direct response.parsed or clean JSON)
                    if hasattr(response, "parsed") and isinstance(response.parsed, response_schema):
                        validated_obj = response.parsed
                    else:
                        clean_text = raw_text.strip()
                        if clean_text.startswith("```json"):
                            clean_text = clean_text[7:]
                        elif clean_text.startswith("```"):
                            clean_text = clean_text[3:]
                        if clean_text.endswith("```"):
                            clean_text = clean_text[:-3]
                        clean_text = clean_text.strip()

                        parsed_json = json.loads(clean_text)
                        validated_obj = response_schema.model_validate(parsed_json)

                    attempt_info["status"] = "success"
                    prov.model_used = model_name
                    prov.fallback_occurred = idx > 0
                    prov.structured_validation_passed = True
                    prov.latency_ms = (time.time() - start_time) * 1000

                    return AIResponse(
                        success=True,
                        data=validated_obj,
                        raw_text=raw_text,
                        provenance=prov,
                    )

                except Exception as exc:
                    err_str = str(exc).lower()
                    last_error = str(exc)

                    # Check for permanent authentication or quota exhaustion: DO NOT FALL BACK ENDLESSLY
                    if "api_key" in err_str or "unauthorized" in err_str or "401" in err_str or "403" in err_str:
                        attempt_info["status"] = "auth_error"
                        prov.error = f"Authentication failure: {exc}"
                        prov.latency_ms = (time.time() - start_time) * 1000
                        return AIResponse(success=False, provenance=prov)

                    if "quota" in err_str or "exhausted" in err_str:
                        attempt_info["status"] = "quota_exhausted"
                        prov.error = f"API Quota exhausted: {exc}"
                        prov.latency_ms = (time.time() - start_time) * 1000
                        return AIResponse(success=False, provenance=prov)

                    # Check for rate limit / 429
                    if "429" in err_str or "rate limit" in err_str:
                        attempt_info["status"] = f"rate_limit_retry_{retry}"
                        if retry < self.settings.max_retries_per_model:
                            time.sleep(1.0 * (2**retry))  # Exponential backoff
                            continue

                    # Check for model not found / unsupported / 404
                    if "not found" in err_str or "404" in err_str or "unsupported" in err_str:
                        attempt_info["status"] = "model_not_found"
                        break  # Fall back to next model immediately

                    # Transient error (503 / timeout)
                    if retry < self.settings.max_retries_per_model:
                        time.sleep(0.5 * (2**retry))
                        continue
                    else:
                        attempt_info["status"] = f"failed: {exc}"
                        break  # Move to next model

        prov.error = f"All configured Gemini models failed. Last error: {last_error}"
        prov.latency_ms = (time.time() - start_time) * 1000
        return AIResponse(success=False, provenance=prov)

    def test_connection(self) -> dict[str, Any]:
        """Test API connectivity using a minimal prompt without exposing secrets."""
        start_time = time.time()
        if not self.settings.enabled or not self.settings.api_key:
            return {
                "connected": False,
                "status": "unconfigured",
                "message": "GEMINI_API_KEY is not configured",
                "latency_ms": 0.0,
            }

        if not SDK_AVAILABLE:
            return {
                "connected": False,
                "status": "sdk_missing",
                "message": "google-genai SDK is not installed",
                "latency_ms": 0.0,
            }

        models = list(self.settings.model_preference)
        for model_name in models:
            try:
                if not self._genai_client:
                    self._genai_client = genai.Client(api_key=self.settings.api_key)

                response = self._genai_client.models.generate_content(
                    model=model_name,
                    contents="Ping",
                )
                latency = round((time.time() - start_time) * 1000, 1)
                return {
                    "connected": True,
                    "status": "connected",
                    "model": model_name,
                    "message": "Successfully connected to Google Gemini API",
                    "latency_ms": latency,
                }
            except Exception as exc:
                err_str = str(exc).lower()
                if "api_key" in err_str or "unauthorized" in err_str or "401" in err_str or "403" in err_str:
                    return {
                        "connected": False,
                        "status": "auth_error",
                        "error": "Authentication failed: invalid or unauthorized API key",
                        "message": "Invalid API key",
                        "latency_ms": round((time.time() - start_time) * 1000, 1),
                    }
                if "quota" in err_str or "exhausted" in err_str:
                    return {
                        "connected": False,
                        "status": "quota_exhausted",
                        "error": "API Quota exhausted",
                        "message": "API Quota exhausted",
                        "latency_ms": round((time.time() - start_time) * 1000, 1),
                    }
                # Model not found or unsupported -> try next model in preference queue
                continue

        return {
            "connected": False,
            "status": "error",
            "error": "Failed to connect to any configured Gemini model",
            "message": "Connection test failed",
            "latency_ms": round((time.time() - start_time) * 1000, 1),
        }

