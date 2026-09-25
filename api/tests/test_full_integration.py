"""End-to-end integration tests connecting P1, P2, and P3."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from trace.intel.bundle_loader import BundleLoader
from trace.intel.evidence_ref import EvidenceRefResolver

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def integrated_client(monkeypatch) -> TestClient:
    monkeypatch.setenv("TRACE_RECOVERY_ENGINE", "trace_evidence.engine:TraceEvidenceEngine")
    monkeypatch.setenv("TRACE_AI_ENGINE", "trace.intel.engine:TraceIntelligenceEngine")
    monkeypatch.setenv("TRACE_RECOVERY_MODE", "real")
    monkeypatch.setenv("TRACE_AI_MODE", "real")
    app = create_app()
    return TestClient(app)


def test_dashboard_and_fixtures_served(integrated_client):
    r_root = integrated_client.get("/")
    assert r_root.status_code == 200
    assert "CalmStacks TRACE" in r_root.text

    r_dash = integrated_client.get("/dashboard")
    assert r_dash.status_code == 200
    assert "CalmStacks TRACE" in r_dash.text

    r_fix = integrated_client.get("/api/fixtures")
    assert r_fix.status_code == 200
    data = r_fix.json()
    assert "fixtures" in data
    assert len(data["fixtures"]) >= 3
    assert any(f["fixture_id"] == "synthetic_blob" for f in data["fixtures"])


def test_p1_carve_and_reconstruct_end_to_end(integrated_client):
    r_carve = integrated_client.post(
        "/api/sessions/carve",
        data={
            "fixture_id": "synthetic_blob",
            "case_id": "CASE-INT-01",
            "case_title": "End-to-end P1 Carving Test",
            "investigator": "Agent-01",
            "write_blocked": True,
            "acquisition_method": "file_copy",
        },
    )
    assert r_carve.status_code == 201
    session_data = r_carve.json()
    session_id = session_data["session_id"]
    assert session_data["status"] == "complete"
    assert session_data["case_id"] == "CASE-INT-01"

    # Verify Stage 1: P1 Recovery
    rec_stage = next(s for s in session_data["stages"] if s["stage"] == "recovery")
    assert rec_stage["status"] == "ok"
    assert rec_stage["engine"]["name"] == "trace-evidence"

    # Verify Stage 2: P2 Intelligence
    intel_stage = next(s for s in session_data["stages"] if s["stage"] == "intelligence")
    assert intel_stage["status"] == "ok"
    assert intel_stage["engine"]["name"] == "trace-intel"

    # Verify Reconstructed PDF Metadata
    r_recon = integrated_client.get(f"/api/sessions/{session_id}/reconstruction")
    assert r_recon.status_code == 200
    recon_meta = r_recon.json()
    assert recon_meta["reconstructed_sha256"] == "1ba5d499d667001095a9fefa4d57551538f742824bb2e2de1feae5e224d64caf"
    assert len(recon_meta["provenance"]) == 8
    assert recon_meta["byte_coverage"] == "100%"

    # Verify Download of Reconstructed PDF
    r_dl = integrated_client.get(f"/api/sessions/{session_id}/reconstruction/download")
    assert r_dl.status_code == 200
    assert r_dl.headers["content-type"] == "application/pdf"
    assert len(r_dl.content) == 2048
    assert "attachment" in r_dl.headers["content-disposition"]


def test_bundle_schema_conformance_with_p2_loader(integrated_client):
    """Verify that P1-emitted bundle strictly passes P2's frozen schema validator."""
    r_carve = integrated_client.post(
        "/api/sessions/carve",
        data={"fixture_id": "synthetic_blob", "case_id": "CASE-SCHEMA-01"},
    )
    session_id = r_carve.json()["session_id"]

    r_ev = integrated_client.get(f"/api/sessions/{session_id}/evidence")
    assert r_ev.status_code == 200
    bundle = r_ev.json()

    # Required P2 Root fields in projected view
    for field in [
        "schema_version", "bundle_id", "generated_utc", "case",
        "acquisition", "capabilities", "artifacts", "engine"
    ]:
        assert field in bundle["root_fields"]

    assert bundle["schema_version"] == "trace.evidence_bundle/1.0"
    assert bundle["array_counts"]["artifacts"] == 0  # Authentic: no fabricated artifact records
    assert bundle["array_counts"]["fragments"] == 8
    assert bundle["array_counts"]["reconstruction_groups"] == 1


def test_grounding_refs_against_carved_session(integrated_client):
    r_carve = integrated_client.post(
        "/api/sessions/carve",
        data={"fixture_id": "synthetic_blob", "case_id": "CASE-GROUND-01"},
    )
    session_id = r_carve.json()["session_id"]

    # Retrieve first fragment_id
    r_frags = integrated_client.get(f"/api/sessions/{session_id}/evidence/fragments")
    frag_id = r_frags.json()["fragments"][0]["fragment_id"]

    # Ground root refs and fragment ref
    r_gr = integrated_client.post(
        f"/api/sessions/{session_id}/refs/ground",
        json={"refs": ["bundle", "case", f"fragments[{frag_id}]"]},
    )
    assert r_gr.status_code == 200
    data = r_gr.json()
    assert data["grounded_count"] == 3
    assert data["all_grounded"] is True


def test_empty_bundle_minimal_fixture(integrated_client):
    """Verify contract floor: empty evidence degrades gracefully without failure."""
    r_sub = integrated_client.post(
        "/api/sessions/carve",
        data={"fixture_id": "bundle_minimal", "case_id": "CASE-MIN-01"},
    )
    assert r_sub.status_code == 201
    data = r_sub.json()
    assert data["status"] in ("complete", "partial")


def test_realistic_fixture_end_to_end(integrated_client):
    r_sub = integrated_client.post(
        "/api/sessions/carve",
        data={"fixture_id": "bundle_realistic", "case_id": "CASE-ATLAS-01"},
    )
    assert r_sub.status_code == 201
    data = r_sub.json()
    assert data["status"] == "complete"

    r_rep = integrated_client.get(f"/api/sessions/{data['session_id']}/report")
    assert r_rep.status_code == 200
    report = r_rep.json()
    assert report["report_id"].startswith("RPT-")
