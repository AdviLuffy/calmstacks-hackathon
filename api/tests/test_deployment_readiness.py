"""Tests for TRACE Phase 11: Production Deployment & Integration Verification.

Validates:
1. Vercel deployment configuration (vercel.json syntax, includeFiles, maxDuration, serverless ASGI entrypoint).
2. api/index.py ASGI entrypoint exports and runtime path resolution.
3. Dependency synchronization across root requirements.txt and api/requirements.txt.
4. Serverless ephemeral filesystem resilience (VERCEL=1 environment handling).
5. CORS configuration safety (wildcard origin handling with allow_credentials).
6. Secret isolation (no tracked credentials, .env properly ignored).
7. Complete end-to-end production mode routes (HTML UI, OpenAPI, Health, REST API).
"""

from __future__ import annotations

import importlib
import json
import os
from pathlib import Path
import pytest
from starlette.testclient import TestClient

from app.config import load_settings
from app.main import create_app

REPO_ROOT = Path(__file__).resolve().parents[2]


class TestVercelConfiguration:
    """Validate vercel.json deployment specifications."""

    def test_vercel_json_structure(self):
        """Verify vercel.json configuration, builds, routes, and includeFiles."""
        v_path = REPO_ROOT / "vercel.json"
        assert v_path.is_file(), "vercel.json must exist in repository root"
        data = json.loads(v_path.read_text(encoding="utf-8"))

        assert data.get("version") == 2
        builds = data.get("builds", [])
        assert len(builds) >= 1

        py_build = next((b for b in builds if b.get("use") == "@vercel/python"), None)
        assert py_build is not None, "Missing @vercel/python build in vercel.json"
        assert py_build.get("src") == "api/index.py"

        # Verify includeFiles is configured so repository packages are bundled
        cfg = py_build.get("config", {})
        includes = cfg.get("includeFiles", [])
        assert any("trace/**" in inc for inc in includes), "trace/** must be in includeFiles"
        assert any("evidence/**" in inc for inc in includes), "evidence/** must be in includeFiles"
        assert cfg.get("maxDuration", 0) >= 30, "maxDuration must be configured for forensic operations"

        # Verify routing
        routes = data.get("routes", [])
        assert any(r.get("dest") == "api/index.py" for r in routes)


class TestVercelEntrypoint:
    """Validate api/index.py serverless entrypoint."""

    def test_entrypoint_exports_app(self, monkeypatch):
        """Verify api/index.py exports a valid FastAPI ASGI app instance."""
        monkeypatch.setenv("VERCEL", "1")
        monkeypatch.setenv("TRACE_PERSIST_SESSIONS", "false")

        import api.index as vercel_entry
        assert hasattr(vercel_entry, "app")
        assert vercel_entry.app.title == "TRACE Investigator API"

        # Test request against index.app
        client = TestClient(vercel_entry.app)
        res_health = client.get("/api/health")
        assert res_health.status_code == 200

        res_home = client.get("/")
        assert res_home.status_code == 200
        assert "TRACE" in res_home.text


class TestDependencySynchronization:
    """Verify that root and api requirements files remain synchronized."""

    def test_requirements_sync(self):
        """Verify critical runtime dependencies are in both requirements.txt and api/requirements.txt."""
        root_req = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
        api_req = (REPO_ROOT / "api" / "requirements.txt").read_text(encoding="utf-8").lower()

        critical_packages = [
            "fastapi",
            "pydantic",
            "pypdf",
            "pymupdf",
            "scikit-learn",
            "joblib",
            "google-genai",
            "python-multipart",
        ]

        for pkg in critical_packages:
            assert pkg in root_req, f"Missing {pkg} in root requirements.txt"
            assert pkg in api_req, f"Missing {pkg} in api/requirements.txt"


class TestServerlessStorageAndConfig:
    """Validate behavior under serverless read-only filesystem conditions."""

    def test_serverless_temp_storage_resolution(self, monkeypatch):
        """Verify storage paths point to /tmp when VERCEL=1."""
        monkeypatch.setenv("VERCEL", "1")
        monkeypatch.delenv("TRACE_SESSION_ROOT", raising=False)
        monkeypatch.delenv("TRACE_EVIDENCE_ROOT", raising=False)

        settings = load_settings()
        assert str(settings.session_root).startswith("/tmp") or str(settings.session_root).startswith("\\tmp")
        assert str(settings.evidence_root).startswith("/tmp") or str(settings.evidence_root).startswith("\\tmp")

    def test_wildcard_cors_safety(self, monkeypatch):
        """Verify CORS allows wildcard origin without colliding with allow_credentials."""
        monkeypatch.setenv("TRACE_CORS_ORIGINS", "*")
        settings = load_settings()
        assert "*" in settings.cors_origins

        # App creation must not raise ValueError
        app_instance = create_app(settings=settings)
        client = TestClient(app_instance)
        res = client.get("/api/health")
        assert res.status_code == 200


class TestSecretIsolation:
    """Verify that secrets are protected from Git tracking."""

    def test_gitignore_protects_env(self):
        """Verify .env and credentials are listed in .gitignore."""
        gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
        assert ".env" in gitignore
        assert ".env.local" in gitignore
        assert "var/" in gitignore


class TestProductionRoutesAndWorkflows:
    """Verify production behavior across all core website workflows."""

    def test_production_navigation_and_pages(self):
        """Verify that all production pages render with native brand, navigation, and footer."""
        app_instance = create_app()
        client = TestClient(app_instance)

        routes_to_test = [
            ("/", "Deterministic byte reconstruction"),
            ("/product", "The TRACE Forensic Pipeline Workflow"),
            ("/about", "About TRACE"),
            ("/privacy", "Evidentiary Privacy Policy"),
            ("/terms", "Terms of Examination"),
            ("/investigations", "Investigations Directory"),
            ("/investigations/new", "New Forensic Ingestion"),
            ("/benchmark", "TRACE Forensic Benchmarking"),
        ]

        for path, expected in routes_to_test:
            res = client.get(path)
            assert res.status_code == 200, f"Route {path} failed"
            assert expected in res.text, f"Route {path} missing expected content"
            assert 'href="/benchmark"' in res.text, f"Route {path} missing benchmark nav"
            assert "site-header" in res.text, f"Route {path} missing site-header"
            assert "site-footer" in res.text, f"Route {path} missing site-footer"

    def test_production_benchmark_workflow(self):
        """Verify benchmark API endpoints work in production configuration."""
        app_instance = create_app()
        client = TestClient(app_instance)

        # 1. Registry API
        res_reg = client.get("/api/datasets/real-world/registry")
        assert res_reg.status_code == 200
        reg_data = res_reg.json()
        assert "documents" in reg_data
        assert len(reg_data["documents"]) >= 5

        # 2. Damaged Corpus API
        res_dam = client.get("/api/datasets/real-world/damaged-corpus")
        assert res_dam.status_code == 200
        dam_data = res_dam.json()
        assert dam_data["sample_count"] >= 2
        assert "NO FABRICATED GROUND TRUTH" in dam_data["verified_ground_truth_policy"]

        # 3. Status API
        res_stat = client.get("/api/datasets/benchmark/status")
        assert res_stat.status_code == 200

        # 4. Small benchmark execution
        res_run = client.post("/api/datasets/benchmark/run?samples_per_doc=1&max_docs=1")
        assert res_run.status_code == 200
        run_data = res_run.json()
        assert run_data["benchmark_version"] == "1.0.0"
        assert "controlled_benchmark_summary" in run_data
