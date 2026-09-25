"""P3's evidence layer: the frozen root contract, the held bundle, and grounding.

The freeze (M0-DEC-06) turned two gaps into obligations: the ``trace.evidence_bundle/1.0``
root contract is enforced at ingestion, and a fragment EvidenceRef grounds to exactly one
supplied record. These tests execute both instead of describing them, and they hold the
memory-only promise: the bundle is served from this process and never written to disk.
"""
from __future__ import annotations

from pathlib import Path

from app.contract.evidence_bundle import (
    EVIDENCE_BUNDLE_SCHEMA_VERSION,
    validate_evidence_bundle_root,
)
from app.contract.evidence_ref import (
    GROUNDING_REASON_FIELD_NAMESPACE_NOT_FROZEN,
    GROUNDING_REASON_INSTANCE_ID_NAMESPACE_NOT_FROZEN,
    GROUNDING_REASON_INSTANCE_ID_NOT_FOUND,
    GROUNDING_REASON_MULTIPLE_MATCHES,
    GROUNDING_REASON_SYNTAX_INVALID,
    GroundingStatus,
)
from app.services.evidence import (
    BundleEvidenceResolver,
    duplicate_fragment_ids,
    fragment_records,
)
from app.services.interfaces import WARNING_DUPLICATE_FRAGMENT_IDS
from app.services.session_store import FileSessionStore
from p3_helpers import make_bundle, make_settings, make_wiring, upload

#: A frozen fragment-instance form (Option A / M0-DEC-06), used throughout.
FRG_ID = "FRG-0123456789abcdef-0-4096"

#: An id that matches the frozen shape but belongs to no supplied record.
FRG_UNKNOWN = "FRG-ffffffffffffffff-0-1"


def test_the_frozen_root_contract_accepts_a_valid_bundle():
    assert validate_evidence_bundle_root(make_bundle()) == ()


def test_the_frozen_root_contract_names_every_problem():
    problems = validate_evidence_bundle_root(
        {"schema_version": "trace.evidence_bundle/0.9", "case": [], "surprise": True}
    )
    joined = " | ".join(problems)
    assert "required root field 'bundle_id' is missing" in joined
    assert "required root field 'artifacts' is missing" in joined
    assert "schema_version must be" in joined
    assert "'case' must be a JSON object" in joined
    assert "'surprise' is not authorized" in joined


def test_uploading_a_bundle_that_breaks_the_root_contract_is_refused(make_client):
    response = upload(make_client(), {"schema_version": EVIDENCE_BUNDLE_SCHEMA_VERSION})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "bundle_contract_violation"
    assert "required root field 'bundle_id' is missing" in error["detail"]


def test_duplicate_fragment_ids_become_a_visible_session_notice(make_client):
    bundle = make_bundle(
        fragments=[
            {"fragment_id": FRG_ID, "range": [0, 10]},
            {"fragment_id": FRG_ID, "range": [10, 20]},
        ]
    )
    created = upload(make_client(), bundle).json()
    assert WARNING_DUPLICATE_FRAGMENT_IDS in {
        notice["code"] for notice in created["warnings"]
    }
    assert duplicate_fragment_ids(bundle) == (FRG_ID,)
    assert len(fragment_records(bundle, FRG_ID)) == 2


def test_multiple_matches_never_resolve_by_preference():
    bundle = make_bundle(
        fragments=[
            {"fragment_id": FRG_ID, "range": [0, 10]},
            {"fragment_id": FRG_ID, "range": [10, 20]},
        ]
    )
    resolver = BundleEvidenceResolver(bundle)
    result = resolver.resolve("fragments[%s]" % FRG_ID)
    assert result.status is GroundingStatus.UNRESOLVED
    assert result.reason == GROUNDING_REASON_MULTIPLE_MATCHES
    assert "exactly one" in (result.detail or "")
    assert resolver.resolve("fragments[%s]" % FRG_UNKNOWN).reason == (
        GROUNDING_REASON_INSTANCE_ID_NOT_FOUND
    )


def test_the_bundle_root_is_served_and_never_written_to_disk(make_client, tmp_path):
    settings = make_settings(persist_sessions=True, session_root=tmp_path)
    client = make_client(
        settings=settings,
        wiring=make_wiring(),
        store=FileSessionStore(tmp_path),
    )
    marker = "opaque-marker-123456"
    created = upload(client, make_bundle(bundle_id=marker), case_id="CASE-DISK").json()
    session_id = created["session_id"]

    root = client.get("/api/sessions/%s/evidence" % session_id)
    assert root.status_code == 200
    body = root.json()
    assert body["session_id"] == session_id
    assert body["schema_version"] == EVIDENCE_BUNDLE_SCHEMA_VERSION
    assert body["bundle_id"] == marker
    assert "case" in body["root_fields"]
    assert "extensions" in body["root_fields"]
    assert body["array_counts"]["artifacts"] == 0
    assert body["array_counts"]["fragments"] is None  # absent and empty are different facts
    assert body["bundle_sha256"] == created["bundle_sha256"]

    # The session itself IS stored; what must be absent is the bundle: its identifier and
    # its interior content. (Provenance prose may legitimately name the frozen schema.)
    stored_files = [path for path in Path(tmp_path).rglob("*.json") if path.is_file()]
    assert stored_files
    for path in stored_files:
        text = path.read_text(encoding="utf-8", errors="ignore")
        assert marker not in text
        assert "arbitrary document" not in text


def test_a_reloaded_session_reports_evidence_unavailable(make_client, tmp_path):
    settings = make_settings(persist_sessions=True, session_root=tmp_path)
    first = make_client(settings=settings, store=FileSessionStore(tmp_path))
    created = upload(first, make_bundle()).json()

    # A fresh application over the same store: the bundle was never persisted, and the
    # endpoint says why instead of inventing an empty document.
    second = make_client(settings=settings, store=FileSessionStore(tmp_path))
    for path in ("/evidence", "/evidence/fragments", "/evidence/artifacts"):
        response = second.get("/api/sessions/%s%s" % (created["session_id"], path))
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "evidence_unavailable"
        assert "never written to disk" in response.json()["error"]["detail"]

    grounded = second.post(
        "/api/sessions/%s/refs/ground" % created["session_id"], json={"refs": ["bundle"]}
    )
    assert grounded.status_code == 409
    assert grounded.json()["error"]["code"] == "evidence_unavailable"


def test_fragments_and_artifacts_are_served_opaquely(make_client):
    bundle = make_bundle(
        artifacts=[{"path": "a.bin"}, {"path": "b.bin"}],
        fragments=[{"fragment_id": FRG_ID, "range": [0, 10]}],
    )
    client = make_client()
    session_id = upload(client, bundle).json()["session_id"]

    fragments = client.get("/api/sessions/%s/evidence/fragments" % session_id).json()
    assert fragments["total"] == 1
    assert fragments["session_id"] == session_id
    assert fragments["fragments"][0]["fragment_id"] == FRG_ID
    assert fragments["fragments"][0]["record"]["range"] == [0, 10]

    item = client.get("/api/sessions/%s/evidence/fragments/%s" % (session_id, FRG_ID))
    assert item.status_code == 200
    assert item.json()["record"]["range"] == [0, 10]

    missing = client.get(
        "/api/sessions/%s/evidence/fragments/%s" % (session_id, FRG_UNKNOWN)
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "fragment_not_found"

    artifacts = client.get("/api/sessions/%s/evidence/artifacts" % session_id).json()
    assert artifacts["total"] == 2
    single = client.get("/api/sessions/%s/evidence/artifacts/1" % session_id)
    assert single.status_code == 200
    assert single.json()["record"]["path"] == "b.bin"

    absent = client.get("/api/sessions/%s/evidence/artifacts/7" % session_id)
    assert absent.status_code == 404
    assert absent.json()["error"]["code"] == "artifact_not_found"


def test_a_duplicated_fragment_id_is_ambiguous_over_http(make_client):
    bundle = make_bundle(
        fragments=[
            {"fragment_id": FRG_ID, "range": [0, 10]},
            {"fragment_id": FRG_ID, "range": [10, 20]},
        ]
    )
    client = make_client()
    session_id = upload(client, bundle).json()["session_id"]
    response = client.get(
        "/api/sessions/%s/evidence/fragments/%s" % (session_id, FRG_ID)
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "fragment_ambiguous"


def test_grounding_reports_status_reason_and_decomposition(make_client):
    bundle = make_bundle(
        artifacts=[{"path": "a.bin"}],
        fragments=[{"fragment_id": FRG_ID, "range": [0, 10]}],
    )
    client = make_client()
    session_id = upload(client, bundle).json()["session_id"]
    known = "fragments[%s]" % FRG_ID

    response = client.post(
        "/api/sessions/%s/refs/ground" % session_id,
        json={
            "refs": [
                "bundle",
                known,
                "fragments[%s]" % FRG_UNKNOWN,
                "artifacts[ART-0001]",
                "case.timestamp",
                "not a ref",
            ]
        },
    )
    assert response.status_code == 200
    payload = response.json()
    results = {item["ref"]: item for item in payload["results"]}
    assert results["bundle"]["status"] == "resolved"
    assert results[known]["status"] == "resolved"
    assert results[known]["collection"] == "fragments"
    assert results[known]["instance_id"] == FRG_ID
    assert results["fragments[%s]" % FRG_UNKNOWN]["reason"] == (
        GROUNDING_REASON_INSTANCE_ID_NOT_FOUND
    )
    assert results["artifacts[ART-0001]"]["reason"] == (
        GROUNDING_REASON_INSTANCE_ID_NAMESPACE_NOT_FROZEN
    )
    assert results["case.timestamp"]["reason"] == (
        GROUNDING_REASON_FIELD_NAMESPACE_NOT_FROZEN
    )
    assert results["not a ref"]["reason"] == GROUNDING_REASON_SYNTAX_INVALID
    assert payload["grounded_count"] == 2
    assert payload["all_grounded"] is False


def test_grounding_requires_at_least_one_reference(make_client):
    client = make_client()
    session_id = upload(client, make_bundle()).json()["session_id"]
    response = client.post(
        "/api/sessions/%s/refs/ground" % session_id, json={"refs": []}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_input"


def test_evidence_endpoints_require_an_existing_session(client):
    assert client.get("/api/sessions/none/evidence").status_code == 404
    assert (
        client.post(
            "/api/sessions/none/refs/ground", json={"refs": ["bundle"]}
        ).status_code
        == 404
    )



