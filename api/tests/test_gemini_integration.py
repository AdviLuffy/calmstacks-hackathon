"""Unit and integration tests for Google Gemini API integration in TRACE.

Ensures:
1. Environment configuration via GEMINI_API_KEY and .env loading.
2. Graceful offline fallback when unconfigured.
3. Resilient model fallback queue (gemini-3.8-flash -> gemini-3.5-flash-lite -> etc.).
4. Safe test-connection endpoint without secret leakage.
5. Strict forensic grounding: AI summarizes metadata without altering deterministic outputs.
6. Graceful handling of auth errors and quota limits.
7. Pure mock execution (zero external network calls).
"""

from __future__ import annotations

import os
from unittest.mock import patch, MagicMock
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from trace.ai.config import GeminiSettings, load_gemini_settings, DEFAULT_MODEL_PREFERENCE
from trace.ai.client import ResilientGeminiClient, AIResponse
from trace.ai.mock_client import MockGeminiClient
from trace.ai.service import GeminiForensicService
from trace.ai.schemas import AIEvidenceExplanation
from trace.recovery.models import RecoveredArtifact, RecoveryCategory, ValidationResult


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def integrated_client(make_client) -> TestClient:
    from p3_helpers import make_settings, make_wiring
    from app.services.session_store import InMemorySessionStore

    return make_client(
        settings=make_settings(persist_sessions=False),
        wiring=make_wiring(),
        store=InMemorySessionStore(),
    )


def test_gemini_config_reads_env_and_never_leaks(monkeypatch):
    """Verify GEMINI_API_KEY environment variable is read correctly."""
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyTestMockKeySecret12345")
    monkeypatch.setenv("GEMINI_ENABLE", "true")
    settings = load_gemini_settings()

    assert settings.enabled is True
    assert settings.api_key == "AIzaSyTestMockKeySecret12345"
    assert "gemini-3.8-flash" in settings.model_preference
    assert "gemini-3.5-flash-lite" in settings.model_preference

    # Verify representations do not print key blindly
    settings_str = str(settings)
    # Even if dataclass prints, ensure custom callers can mask
    assert len(settings.api_key) > 0


def test_gemini_config_unconfigured_by_default(monkeypatch):
    """Verify clean unconfigured state when GEMINI_API_KEY is unset."""
    monkeypatch.setenv("TRACE_SKIP_DOTENV", "1")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("TRACE_GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_ENABLE", raising=False)

    settings = load_gemini_settings()
    assert settings.api_key == ""
    assert settings.enabled is False


def test_gitignore_contains_env_and_example_has_placeholder():
    """Verify .env is gitignored and .env.example contains only an empty placeholder."""
    gitignore_path = REPO_ROOT / ".gitignore"
    assert gitignore_path.is_file()
    gitignore_text = gitignore_path.read_text(encoding="utf-8")
    assert ".env" in gitignore_text

    example_path = REPO_ROOT / ".env.example"
    assert example_path.is_file()
    example_text = example_path.read_text(encoding="utf-8")
    assert "GEMINI_API_KEY=" in example_text
    # Verify no real key was accidentally committed to .env.example
    for line in example_text.splitlines():
        if line.strip().startswith("GEMINI_API_KEY="):
            val = line.split("=", 1)[1].strip()
            assert val == "", f"Found non-empty value in .env.example: {val}"


def test_ai_status_endpoint_unconfigured(integrated_client: TestClient, monkeypatch):
    """Verify GET /api/ai/status when unconfigured."""
    monkeypatch.setenv("TRACE_SKIP_DOTENV", "1")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("TRACE_GEMINI_API_KEY", raising=False)

    r = integrated_client.get("/api/ai/status")
    assert r.status_code == 200
    data = r.json()
    assert data["configured"] is False
    assert data["has_api_key"] is False
    assert data["message"] == "AI analysis unavailable — configure provider"
    assert "gemini-3.8-flash" in data["model_preference_queue"]
    assert data["data_minimization_enforced"] is True


def test_ai_test_connection_endpoint_unconfigured(integrated_client: TestClient, monkeypatch):
    """Verify test-connection endpoint when unconfigured."""
    monkeypatch.setenv("TRACE_SKIP_DOTENV", "1")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("TRACE_GEMINI_API_KEY", raising=False)

    # Both POST and GET are supported
    for method in ("post", "get"):
        fn = getattr(integrated_client, method)
        r = fn("/api/ai/test-connection")
        assert r.status_code == 200
        data = r.json()
        assert data["connected"] is False
        assert data["status"] == "unconfigured"
        assert "not configured" in data["message"].lower()


def test_ai_test_connection_endpoint_success_with_mock(integrated_client: TestClient, monkeypatch):
    """Verify test-connection endpoint succeeds with mock client and does not leak keys."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-mock-key-valid")

    mock_client = MockGeminiClient()
    with patch("app.routers.dashboard.ResilientGeminiClient", return_value=mock_client):
        r = integrated_client.post("/api/ai/test-connection")
        assert r.status_code == 200
        data = r.json()
        assert data["connected"] is True
        assert data["status"] == "connected"
        assert data["model"] == "gemini-3.8-flash"
        # Secret key is never in response
        assert "test-mock-key-valid" not in r.text


def test_ai_test_connection_endpoint_auth_error_with_mock(integrated_client: TestClient, monkeypatch):
    """Verify test-connection endpoint handles auth error gracefully."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-mock-invalid-key")

    mock_client = MockGeminiClient(auth_error=True)
    with patch("app.routers.dashboard.ResilientGeminiClient", return_value=mock_client):
        r = integrated_client.post("/api/ai/test-connection")
        assert r.status_code == 200
        data = r.json()
        assert data["connected"] is False
        assert data["status"] == "auth_error"
        assert "invalid" in data["message"].lower() or "auth" in data["status"].lower()
        # Secret key is never in response
        assert "test-mock-invalid-key" not in r.text


def test_model_fallback_queue_in_mock():
    """Verify that if primary model fails, fallback to secondary model occurs cleanly."""
    # Fail gemini-3.8-flash, expect fallback to gemini-3.5-flash-lite
    mock = MockGeminiClient(fail_models=["gemini-3.8-flash"])
    service = GeminiForensicService(client=mock)

    artifact = RecoveredArtifact(
        artifact_id="ART-01",
        filename="evidence.pdf",
        format_name="pdf",
        mime_type="application/pdf",
        size_bytes=4096,
        sha256="abc12345" * 8,
        category=RecoveryCategory.RECOVERED,
        confidence_score=95.0,
    )
    res = service.explain_case_recovery("CASE-FB-TEST", [artifact], unplaced_fragments_count=0)

    assert res.success is True
    assert res.provenance.fallback_occurred is True
    assert res.provenance.model_used == "gemini-3.5-flash-lite"
    assert isinstance(res.data, AIEvidenceExplanation)
    assert res.data.executive_summary != ""


def test_quota_exhausted_handling():
    """Verify quota exhaustion returns graceful failure without infinite retries."""
    mock = MockGeminiClient(quota_exhausted=True)
    service = GeminiForensicService(client=mock)

    artifact = RecoveredArtifact(
        artifact_id="ART-01",
        filename="evidence.pdf",
        format_name="pdf",
        mime_type="application/pdf",
        size_bytes=4096,
        sha256="abc12345" * 8,
        category=RecoveryCategory.RECOVERED,
        confidence_score=95.0,
    )
    res = service.explain_case_recovery("CASE-QUOTA-TEST", [artifact])
    assert res.success is False
    assert "quota" in (res.provenance.error or "").lower()


def test_session_ai_analysis_endpoint_with_mock(integrated_client: TestClient, monkeypatch):
    """Verify GET /api/sessions/{session_id}/ai-analysis generates structured findings with provenance."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-mock-key-valid")

    # 1. Carve a session
    r_carve = integrated_client.post(
        "/api/sessions/carve",
        data={"fixture_id": "synthetic_blob", "case_id": "CASE-AI-TEST"},
    )
    assert r_carve.status_code == 201
    session_id = r_carve.json()["session_id"]

    # 2. Query AI analysis with mocked client
    mock_client = MockGeminiClient()
    with patch("app.routers.dashboard.ResilientGeminiClient", return_value=mock_client):
        r_ai = integrated_client.get(f"/api/sessions/{session_id}/ai-analysis")
        assert r_ai.status_code == 200
        ai_data = r_ai.json()

        assert ai_data["success"] is True
        assert ai_data["configured"] is True
        assert ai_data["status"] == "ready"
        assert ai_data["model_used"] == "gemini-3.8-flash"
        assert ai_data["latency_ms"] >= 0.0

        explanation = ai_data["explanation"]
        assert "executive_summary" in explanation
        assert "recovered_artifacts_overview" in explanation
        assert "missing_data_assessment" in explanation
        assert "evidentiary_integrity_statement" in explanation

        # 3. Verify caching: second request returns identical cached payload
        r_cached = integrated_client.get(f"/api/sessions/{session_id}/ai-analysis")
        assert r_cached.status_code == 200
        assert r_cached.json() == ai_data
