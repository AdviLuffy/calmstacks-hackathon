"""Tests verifying the TRACE multi-page architecture, brand consistency, and routes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture()
def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("TRACE_RECOVERY_ENGINE", "trace_evidence.engine:TraceEvidenceEngine")
    monkeypatch.setenv("TRACE_AI_ENGINE", "trace.intel.engine:TraceIntelligenceEngine")
    monkeypatch.setenv("TRACE_RECOVERY_MODE", "real")
    monkeypatch.setenv("TRACE_AI_MODE", "real")
    app = create_app()
    return TestClient(app)


def test_public_pages_and_navigation(client: TestClient):
    """Verify that all public brand pages exist, return 200, and include global navigation."""
    pages = [
        ("/", "Deterministic byte reconstruction"),
        ("/product", "The TRACE Forensic Pipeline Workflow"),
        ("/about", "About CalmStacks TRACE"),
        ("/privacy", "Evidentiary Privacy Policy"),
        ("/terms", "Terms of Examination"),
    ]

    for path, expected_text in pages:
        res = client.get(path)
        assert res.status_code == 200, f"Failed on path {path}"
        assert "CalmStacks TRACE" in res.text, f"Missing brand in {path}"
        assert expected_text in res.text, f"Missing text {expected_text!r} in {path}"

        # Global navigation must be present on every page
        assert 'href="/product"' in res.text
        assert 'href="/investigations"' in res.text
        assert 'href="/investigations/new"' in res.text
        assert 'href="/about"' in res.text
        assert 'href="/docs"' in res.text

        # Favicon reference
        assert 'href="/favicon.svg"' in res.text


def test_application_workspace_routes(client: TestClient):
    """Verify application pages for investigations and evidence ingestion."""
    # Investigations list
    r_inv = client.get("/investigations")
    assert r_inv.status_code == 200
    assert "Investigations Directory" in r_inv.text
    assert "Active In-Memory Sessions" in r_inv.text
    assert "DETERMINISTIC TEST FIXTURES" in r_inv.text

    # /dashboard alias
    r_dash = client.get("/dashboard")
    assert r_dash.status_code == 200
    assert "Investigations Directory" in r_dash.text

    # New Analysis Intake
    r_new = client.get("/investigations/new")
    assert r_new.status_code == 200
    assert "New Forensic Ingestion" in r_new.text
    assert "ISO/IEC 27037 Write-Block Verification" in r_new.text
    assert 'name="write_blocked"' in r_new.text

    # /new alias
    r_new_alias = client.get("/new")
    assert r_new_alias.status_code == 200


def test_investigation_detail_multipage_workflow(client: TestClient):
    """Verify that individual investigations have separate, navigable sub-pages."""
    # 1. Carve a real session
    r_carve = client.post(
        "/api/sessions/carve",
        data={
            "fixture_id": "synthetic_blob",
            "case_id": "CASE-PAGE-TEST",
            "case_title": "Multi-Page Verification",
            "write_blocked": True,
        },
    )
    assert r_carve.status_code == 201
    sid = r_carve.json()["session_id"]

    # 2. Overview Page
    r_over = client.get(f"/investigations/{sid}")
    assert r_over.status_code == 200
    assert sid in r_over.text
    assert "Investigation Overview" in r_over.text
    assert f"/investigations/{sid}/evidence" in r_over.text
    assert f"/investigations/{sid}/provenance" in r_over.text
    assert f"/investigations/{sid}/bundle" in r_over.text
    assert f"/api/sessions/{sid}/reconstruction/download" in r_over.text

    # 3. Evidence Explorer Page
    r_ev = client.get(f"/investigations/{sid}/evidence")
    assert r_ev.status_code == 200
    assert sid in r_ev.text
    assert "Carved Fragment &amp; DNA Explorer" in r_ev.text
    assert "Byte-Level Fragment Inspector" in r_ev.text
    assert "/evidence/fragments" in r_ev.text

    # 4. Provenance Ledger Page
    r_prov = client.get(f"/investigations/{sid}/provenance")
    assert r_prov.status_code == 200
    assert sid in r_prov.text
    assert "100% Byte-Level Provenance Ledger" in r_prov.text
    assert "Authentic Assembly Sequence" in r_prov.text
    assert "Candidate Only (contiguity=False)" in r_prov.text

    # 5. Evidence Bundle JSON & Grounding Page
    r_bun = client.get(f"/investigations/{sid}/bundle")
    assert r_bun.status_code == 200
    assert sid in r_bun.text
    assert "Evidence Bundle JSON &amp; Referential Grounding" in r_bun.text
    assert "Referential Grounding Resolver" in r_bun.text
    assert "/refs/ground" in r_bun.text
