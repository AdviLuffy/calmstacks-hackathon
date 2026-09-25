"""Unit tests for TRACE P2 Bundle Loader."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from trace.intel.bundle_loader import BundleLoader, BundleLoadError


FIXTURE_DIR = Path(__file__).resolve().parents[2] / "contracts" / "fixtures"


def test_load_valid_bundle_minimal():
    """Test loading the minimal valid bundle."""
    loader = BundleLoader(FIXTURE_DIR / "bundle_minimal.json")

    assert loader.bundle["schema_version"] == "trace.evidence_bundle/1.0"
    assert loader.bundle["bundle_id"] == "BND-MINIMAL-001"
    assert loader.case["case_id"] == "CASE-MIN-01"
    assert len(loader.artifacts) == 1
    assert "ART-0001" in loader.artifacts
    assert len(loader.fragments) == 0
    assert len(loader.reconstruction_groups) == 0
    assert len(loader.timeline_events) == 0
    assert len(loader.known_file_matches) == 0


def test_load_valid_bundle_realistic():
    """Test loading the realistic valid bundle."""
    loader = BundleLoader(FIXTURE_DIR / "bundle_realistic.json")

    assert loader.bundle["bundle_id"] == "BND-REALISTIC-001"
    assert loader.case["case_id"] == "CASE-ATLAS-01"
    assert len(loader.artifacts) == 9
    assert len(loader.fragments) == 5
    assert len(loader.reconstruction_groups) == 3
    assert len(loader.timeline_events) == 5
    assert len(loader.known_file_matches) == 3


def test_load_valid_bundle_adversarial():
    """Test loading the adversarial valid bundle."""
    loader = BundleLoader(FIXTURE_DIR / "bundle_adversarial.json")

    assert loader.bundle["bundle_id"] == "BND-ADVERSARIAL-001"
    assert len(loader.artifacts) == 4
    assert len(loader.fragments) == 1
    assert len(loader.reconstruction_groups) == 1
    assert len(loader.timeline_events) == 1
    assert len(loader.known_file_matches) == 0


def test_invalid_json_raises_error():
    """Test that invalid JSON raises BundleLoadError with clear message."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        f.write("{ invalid json ")
        path = Path(f.name)

    try:
        with pytest.raises(BundleLoadError) as exc:
            BundleLoader(path)
        assert "invalid json" in str(exc.value).lower()
    finally:
        path.unlink()


def test_schema_invalid_bundle_raises_error():
    """Test that schema-invalid bundle raises BundleLoadError with path and validator."""
    loader = None
    try:
        loader = BundleLoader(FIXTURE_DIR / "bundle_broken.json")
    except BundleLoadError as e:
        assert e.path is not None
        assert e.validator is not None
        assert "schema validation failed" in str(e).lower()
    else:
        if loader is not None:
            pytest.fail("Expected BundleLoadError for bundle_broken.json")


def test_unsupported_version_raises_error():
    """Test that unsupported version bundle raises error at schema_version."""
    try:
        BundleLoader(FIXTURE_DIR / "bundle_unsupported_version.json")
    except BundleLoadError as e:
        assert e.path == "/schema_version"
        assert e.validator == "const"
    else:
        pytest.fail("Expected BundleLoadError for bundle_unsupported_version.json")


def test_artifact_lookup_by_id():
    """Test deterministic artifact lookup by InstanceId."""
    loader = BundleLoader(FIXTURE_DIR / "bundle_realistic.json")

    art = loader.get_artifact("ART-0001")
    assert art is not None
    assert art["artifact_id"] == "ART-0001"
    assert art["origin"] == "recovered"

    missing = loader.get_artifact("ART-9999")
    assert missing is None


def test_fragment_lookup_by_fragment_instance_id():
    """Test deterministic fragment lookup by FragmentInstanceId."""
    loader = BundleLoader(FIXTURE_DIR / "bundle_realistic.json")

    frag = loader.get_fragment("FRG-1a2b3c4d5e6f7081-1048576-1056768")
    assert frag is not None
    assert frag["fragment_id"] == "FRG-1a2b3c4d5e6f7081-1048576-1056768"
    assert frag["media_id"] == "MED-01"

    missing = loader.get_fragment("FRG-0000000000000000-0-0")
    assert missing is None


def test_reconstruction_group_lookup():
    """Test reconstruction group lookup by group_id."""
    loader = BundleLoader(FIXTURE_DIR / "bundle_realistic.json")

    grp = loader.get_reconstruction_group("RGRP-01")
    assert grp is not None
    assert grp["group_id"] == "RGRP-01"
    assert len(grp["member_fragment_ids"]) == 2

    missing = loader.get_reconstruction_group("RGRP-999")
    assert missing is None


def test_timeline_event_lookup():
    """Test timeline event lookup by event_id."""
    loader = BundleLoader(FIXTURE_DIR / "bundle_realistic.json")

    evt = loader.get_timeline_event("EVT-0001")
    assert evt is not None
    assert evt["event_id"] == "EVT-0001"
    assert evt["source"] == "zip_directory"

    missing = loader.get_timeline_event("EVT-9999")
    assert missing is None


def test_known_file_match_lookup():
    """Test known_file_match lookup by artifact_id."""
    loader = BundleLoader(FIXTURE_DIR / "bundle_realistic.json")

    kfm = loader.get_known_file_match("ART-0009")
    assert kfm is not None
    assert kfm["artifact_id"] == "ART-0009"
    assert kfm["result"] == "known"

    missing = loader.get_known_file_match("ART-9999")
    assert missing is None


def test_bundle_properties_exposed():
    """Test that raw bundle and case are exposed without modification."""
    loader = BundleLoader(FIXTURE_DIR / "bundle_minimal.json")

    assert loader.bundle is not None
    assert loader.case is not None
    assert loader.bundle["bundle_id"] == "BND-MINIMAL-001"
    assert loader.case["title"] == "Minimum viable bundle (contract floor)"


def test_file_not_found_raises_error():
    """Test that non-existent file raises BundleLoadError."""
    with pytest.raises(BundleLoadError) as exc:
        BundleLoader(Path("/nonexistent/bundle.json"))
    assert "cannot read bundle" in str(exc.value).lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])