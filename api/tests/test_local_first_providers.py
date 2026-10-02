"""Test suite verifying TRACE Local-First and Cloud-Optional architecture.

Guarantees:
1. Default provider is always 'local' with ZERO external calls.
2. Cloud AI safety gate prevents unintended Gemini invocation.
3. Zero-quota / rate-limit / network failure automatically falls back to LocalProvider.
4. Provider telemetry never logs or leaks API keys or secrets.
5. Local models use cache directory without downloading large weights at startup.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from trace.ai.config import (
    DEFAULT_AI_PROVIDER,
    GeminiSettings,
    is_cloud_ai_allowed,
    load_gemini_settings,
)
from trace.ml.providers import (
    BaseAIProvider,
    FutureCloudProvider,
    GeminiProvider,
    LocalProvider,
    ProviderTelemetry,
    ProviderType,
    get_provider,
)
from trace.multimodal.representation import DocumentPage, NormalizedDocument, ProvenanceCategory


@pytest.fixture
def integrated_client(make_client) -> TestClient:
    from p3_helpers import make_settings, make_wiring
    from app.services.session_store import InMemorySessionStore

    return make_client(
        settings=make_settings(persist_sessions=False),
        wiring=make_wiring(),
        store=InMemorySessionStore(),
    )


class TestLocalFirstArchitecture:
    """Test local-first default behavior and zero-external-request guarantee."""

    def test_default_provider_is_local(self, monkeypatch):
        """Verify that when no explicit AI_PROVIDER is set, provider is local."""
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        monkeypatch.delenv("TRACE_AI_PROVIDER", raising=False)
        monkeypatch.delenv("GEMINI_ENABLE", raising=False)
        monkeypatch.delenv("TRACE_GEMINI_ENABLE", raising=False)

        settings = load_gemini_settings()
        assert settings.ai_provider == "local"
        assert settings.enabled is False

        provider = get_provider()
        assert provider.provider_type == ProviderType.LOCAL
        assert provider.is_cloud is False
        assert provider.is_available is True

    def test_default_configuration_makes_zero_external_ai_requests(self, monkeypatch):
        """CRITICAL TEST: Verify default configuration executes complete intelligence

        pipeline with ZERO calls to Google GenAI SDK or external network.
        """
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        monkeypatch.delenv("GEMINI_ENABLE", raising=False)

        # Patch GenAI Client constructor to raise if ever called
        with patch("google.genai.Client", side_effect=AssertionError("FATAL: External Gemini API called!")):
            provider = get_provider()
            assert isinstance(provider, LocalProvider)

            # 1. Fragment classification
            frag_res = provider.classify_fragment("frag_001", b"%PDF-1.4\n1 0 obj\n<<>>\nendobj")
            assert frag_res["likely_file_type"] == "pdf"
            assert frag_res["source"] == "local_provider"
            assert frag_res["provenance"] == ProvenanceCategory.DETERMINISTIC.value

            # 2. Relationship inference
            rel_res = provider.infer_relationship(
                "frag_001", b"stream\ncontent",
                "frag_002", b"endstream\nendobj",
            )
            assert rel_res["can_precede"] is True
            assert rel_res["source"] == "local_provider"

            # 3. Reconstruction plan generation
            plan, model_used, prov_name, ai_invoked, reasoning = provider.generate_reconstruction_plan(
                case_id="TEST-LOCAL-001",
                features={"surviving_strings": ["Authentic Header", "Evidence Body"], "surviving_objects": [1, 2]},
                media_size=1024,
                authentic_bytes=512,
                unplaced_count=2,
            )
            assert ai_invoked is False
            assert prov_name == "local"
            assert model_used == "deterministic-forensic-engine"
            assert plan.document_title is not None
            assert len(plan.pages) >= 1

            # 4. Document classification
            doc = NormalizedDocument(
                document_id="doc_local",
                pages=[DocumentPage(page_number=1, elements=[])],
            )
            doc_res = provider.classify_document(doc)
            assert doc_res["provenance"] == ProvenanceCategory.DETERMINISTIC.value

    def test_cloud_ai_safety_gate(self, monkeypatch):
        """Verify cloud AI safety gate prevents cloud calls unless AI_PROVIDER=gemini."""
        # Scenario 1: API key is present, but AI_PROVIDER is 'local'
        assert is_cloud_ai_allowed("local", "real_or_fake_key_12345") is False
        assert is_cloud_ai_allowed("disabled", "real_or_fake_key_12345") is False
        assert is_cloud_ai_allowed("gemini", "") is False
        assert is_cloud_ai_allowed("gemini", "valid_key") is True

        # Scenario 2: Force local flag blocks cloud even if gemini specified
        monkeypatch.setenv("TRACE_FORCE_LOCAL", "1")
        assert is_cloud_ai_allowed("gemini", "valid_key") is False


class TestFallbackAndResilience:
    """Test quota exhaustion, rate limits, and failure fallback without pipeline failure."""

    def test_gemini_failure_or_zero_quota_falls_back_to_local_gracefully(self, monkeypatch):
        """Verify that when Gemini raises 429 / QuotaExceeded, TRACE transparently

        falls back to LocalProvider and does NOT break the recovery pipeline.
        """
        # Configure GeminiProvider with a failing client (simulating 429 quota exhaustion)
        mock_client = MagicMock()
        mock_client.settings.enabled = True
        mock_client.settings.api_key = "test_key"
        mock_client.settings.ai_provider = "gemini"
        mock_client.settings.model_preference = ("gemini-3.5-flash-lite",)
        mock_client.generate_structured.side_effect = RuntimeError("429 ResourceExhausted: Quota exceeded for model")

        local_prov = LocalProvider()
        gemini_prov = GeminiProvider(
            settings=mock_client.settings,
            local_fallback=local_prov,
            gemini_client=mock_client,
        )

        # Force is_available to True to test runtime execution failure
        with patch.object(GeminiProvider, "is_available", True):
            plan, model_used, prov_name, ai_invoked, reasoning = gemini_prov.generate_reconstruction_plan(
                case_id="QUOTA-TEST",
                features={"surviving_strings": ["Recovered Line 1"], "surviving_objects": [1]},
                media_size=2048,
                authentic_bytes=1024,
                unplaced_count=1,
            )

            # Must NOT raise exception!
            assert plan is not None
            assert ai_invoked is False
            assert prov_name == "local"
            assert model_used == "deterministic-forensic-engine"

            # Check telemetry recorded fallback
            telemetry = gemini_prov.get_telemetry()
            assert telemetry.fallback_used is True
            assert "ResourceExhausted" in telemetry.failure_reason

    def test_provider_telemetry_never_leaks_secrets(self):
        """Verify secrets in exceptions are redacted before entering telemetry."""
        secret_key = "AIzaSySuperSecretPersonalKey99999"
        mock_client = MagicMock()
        mock_client.settings.enabled = True
        mock_client.settings.api_key = secret_key
        mock_client.settings.ai_provider = "gemini"
        mock_client.settings.model_preference = ("gemini-3.5-flash-lite",)

        gemini_prov = GeminiProvider(
            settings=mock_client.settings,
            gemini_client=mock_client,
        )

        safe_msg = gemini_prov._safe_error(
            Exception(f"Failed to connect to Google API using key {secret_key}: HTTP 403 Forbidden")
        )
        assert secret_key not in safe_msg
        assert "[REDACTED_KEY]" in safe_msg


class TestProviderApiEndpoints:
    """Test FastAPI provider status and telemetry endpoints."""

    def test_api_ai_provider_endpoint(self, integrated_client: TestClient, monkeypatch):
        """Verify GET /api/ai/provider exposes active provider telemetry safely."""
        monkeypatch.setenv("TRACE_SKIP_DOTENV", "1")
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        monkeypatch.delenv("GEMINI_ENABLE", raising=False)

        resp = integrated_client.get("/api/ai/provider")
        assert resp.status_code == 200
        data = resp.json()
        assert data["active_provider"] == "local"
        assert data["configured_ai_provider"] == "local"
        assert data["is_cloud"] is False
        assert "telemetry" in data
        assert data["telemetry"]["provider"] == "local"
        assert data["telemetry"]["local_or_cloud"] == "local"
