"""Unit tests for TRACE P2 EvidenceRef Resolver."""

from __future__ import annotations

from pathlib import Path

import pytest

from trace.intel.bundle_loader import BundleLoader
from trace.intel.evidence_ref import EvidenceRefResolver, EvidenceRefError

FIXTURE_DIR = Path(__file__).resolve().parents[2] / "contracts" / "fixtures"


def test_resolve_valid_fragment_ref():
    """Test resolving a valid fragment reference."""
    loader = BundleLoader(FIXTURE_DIR / "bundle_realistic.json")
    resolver = EvidenceRefResolver(loader)

    value = resolver.resolve("fragments[FRG-1a2b3c4d5e6f7081-1048576-1056768]")
    assert value is not None
    assert value["fragment_id"] == "FRG-1a2b3c4d5e6f7081-1048576-1056768"
    assert value["media_id"] == "MED-01"


def test_resolve_valid_fragment_field_ref():
    """Test resolving a valid fragment field reference."""
    loader = BundleLoader(FIXTURE_DIR / "bundle_realistic.json")
    resolver = EvidenceRefResolver(loader)

    value = resolver.resolve("fragments[FRG-1a2b3c4d5e6f7081-1048576-1056768].byte_range")
    assert value is not None
    assert value["start"] == 1048576
    assert value["end"] == 1056768


def test_resolve_bundle_ref():
    """Test resolving the bundle root reference."""
    loader = BundleLoader(FIXTURE_DIR / "bundle_minimal.json")
    resolver = EvidenceRefResolver(loader)

    value = resolver.resolve("bundle")
    assert value is not None
    assert value["bundle_id"] == "BND-MINIMAL-001"


def test_resolve_case_ref():
    """Test resolving the case reference."""
    loader = BundleLoader(FIXTURE_DIR / "bundle_minimal.json")
    resolver = EvidenceRefResolver(loader)

    value = resolver.resolve("case")
    assert value is not None
    assert value["case_id"] == "CASE-MIN-01"


def test_resolve_case_field_ref():
    """Test resolving a case field reference."""
    loader = BundleLoader(FIXTURE_DIR / "bundle_realistic.json")
    resolver = EvidenceRefResolver(loader)

    value = resolver.resolve("case.investigation_profile.focus_categories")
    assert value is not None
    assert "document" in value
    assert "text" in value


def test_resolve_unresolved_ref_fails():
    """Test that unresolved reference raises EvidenceRefError."""
    loader = BundleLoader(FIXTURE_DIR / "bundle_minimal.json")
    resolver = EvidenceRefResolver(loader)

    with pytest.raises(EvidenceRefError) as exc:
        resolver.resolve("fragments[FRG-0000000000000000-0-0]")
    assert "not present" in str(exc.value)


def test_resolve_malformed_ref_fails():
    """Test that malformed reference raises EvidenceRefError."""
    loader = BundleLoader(FIXTURE_DIR / "bundle_minimal.json")
    resolver = EvidenceRefResolver(loader)

    with pytest.raises(EvidenceRefError) as exc:
        resolver.resolve("not-a-valid-ref")
    assert "frozen EvidenceRef grammar" in str(exc.value)


def test_resolve_multiple_matches_fails():
    """Test that duplicate IDs in collection cause grounding failure."""
    # Create a bundle with duplicate artifact IDs
    import tempfile
    import json
    from pathlib import Path

    bundle = {
        "schema_version": "trace.evidence_bundle/1.0",
        "bundle_id": "BND-DUP-001",
        "generated_utc": "2026-09-25T06:00:00Z",
        "case": {"case_id": "CASE-DUP-01", "title": "Duplicate test"},
        "acquisition": {"media": [{"media_id": "MED-01", "kind": "file_copy", "source_ref": "dup.bin", "size_bytes": 1024, "write_blocked": True, "acquisition_method": "file_copy", "image_hashes": {"sha256": "a" * 64, "verified": False}}]},
        "capabilities": {"byte_recovery": False, "carving_methods": [], "hash_verification": False, "hash_sets": [], "filesystem_parsers": [], "timestamp_sources": [], "slack_space": False, "encrypted_containers": False, "limitations": ["test"]},
        "artifacts": [
            {"artifact_id": "ART-0001", "origin": "recovered", "media_id": "MED-01", "byte_range": {"start": 0, "end": 512, "size_bytes": 512, "media_id": "MED-01"}, "signature": {"matched": False, "signature_id": None, "footer_matched": False}, "recovery": {"method": "none", "completeness": "unknown", "confidence": 0, "confidence_basis": "test basis"}},
            {"artifact_id": "ART-0001", "origin": "recovered", "media_id": "MED-01", "byte_range": {"start": 512, "end": 1024, "size_bytes": 512, "media_id": "MED-01"}, "signature": {"matched": False, "signature_id": None, "footer_matched": False}, "recovery": {"method": "none", "completeness": "unknown", "confidence": 0, "confidence_basis": "test basis"}},
        ],
        "engine": {"name": "test", "version": "1.0", "determinism": "best_effort"}
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(bundle, f)
        path = Path(f.name)

    try:
        loader = BundleLoader(path)
        resolver = EvidenceRefResolver(loader)
        with pytest.raises(EvidenceRefError) as exc:
            resolver.resolve("artifacts[ART-0001]")
        assert "resolves to 2 records" in str(exc.value)
    finally:
        path.unlink()


def test_resolve_unknown_collection_fails():
    """Test that unknown collection name fails at grammar level."""
    loader = BundleLoader(FIXTURE_DIR / "bundle_minimal.json")
    resolver = EvidenceRefResolver(loader)

    with pytest.raises(EvidenceRefError) as exc:
        resolver.resolve("unknown_collection[ART-0001]")
    assert "frozen EvidenceRef grammar" in str(exc.value)


def test_resolve_artifact_by_id():
    """Test resolving artifact by InstanceId."""
    loader = BundleLoader(FIXTURE_DIR / "bundle_realistic.json")
    resolver = EvidenceRefResolver(loader)

    value = resolver.resolve("artifacts[ART-0001]")
    assert value is not None
    assert value["artifact_id"] == "ART-0001"
    assert value["origin"] == "recovered"


def test_resolve_artifact_field_ref():
    """Test resolving artifact field reference."""
    loader = BundleLoader(FIXTURE_DIR / "bundle_realistic.json")
    resolver = EvidenceRefResolver(loader)

    value = resolver.resolve("artifacts[ART-0001].signature.matched")
    assert value is True


def test_resolve_timeline_event_ref():
    """Test resolving timeline event reference."""
    loader = BundleLoader(FIXTURE_DIR / "bundle_realistic.json")
    resolver = EvidenceRefResolver(loader)

    value = resolver.resolve("timeline_events[EVT-0001]")
    assert value is not None
    assert value["event_id"] == "EVT-0001"


def test_resolve_known_file_match_ref():
    """Test resolving known_file_match by artifact_id."""
    loader = BundleLoader(FIXTURE_DIR / "bundle_realistic.json")
    resolver = EvidenceRefResolver(loader)

    value = resolver.resolve("known_file_matches[ART-0009]")
    assert value is not None
    assert value["artifact_id"] == "ART-0009"
    assert value["result"] == "known"


def test_resolve_reconstruction_group_ref():
    """Test resolving reconstruction group reference."""
    loader = BundleLoader(FIXTURE_DIR / "bundle_realistic.json")
    resolver = EvidenceRefResolver(loader)

    value = resolver.resolve("reconstruction_groups[RGRP-01]")
    assert value is not None
    assert value["group_id"] == "RGRP-01"


def test_fragment_id_validation():
    """Test FragmentInstanceId format validation."""
    assert EvidenceRefResolver.validate_fragment_id("FRG-1a2b3c4d5e6f7081-1048576-1056768") is True
    assert EvidenceRefResolver.validate_fragment_id("FRG-1a2b3c4d5e6f7081-1048576-1056768") is True
    assert EvidenceRefResolver.validate_fragment_id("FRG-0001") is False
    assert EvidenceRefResolver.validate_fragment_id("frg-1a2b3c4d5e6f7081-1048576-1056768") is False
    assert EvidenceRefResolver.validate_fragment_id("FRG-1A2B3C4D5E6F7081-1048576-1056768") is False


def test_instance_id_validation():
    """Test InstanceId format validation."""
    assert EvidenceRefResolver.validate_instance_id("ART-0001") is True
    assert EvidenceRefResolver.validate_instance_id("CASE-ATLAS-01") is True
    assert EvidenceRefResolver.validate_instance_id("ART-001") is True  # 3 digits is valid (2-10)
    assert EvidenceRefResolver.validate_instance_id("art-0001") is False  # lowercase prefix invalid
    assert EvidenceRefResolver.validate_instance_id("ART-01") is True  # 2 digits valid
    assert EvidenceRefResolver.validate_instance_id("ART-0") is False  # 1 digit invalid


def test_parse_fragment_id():
    """Test parsing fragment ID components."""
    result = EvidenceRefResolver.parse_fragment_id("FRG-1a2b3c4d5e6f7081-1048576-1056768")
    assert result is not None
    hex16, start, end = result
    assert hex16 == "1a2b3c4d5e6f7081"
    assert start == 1048576
    assert end == 1056768

    assert EvidenceRefResolver.parse_fragment_id("FRG-0001") is None


def test_try_resolve_returns_tuple():
    """Test try_resolve returns (ok, detail, value)."""
    loader = BundleLoader(FIXTURE_DIR / "bundle_minimal.json")
    resolver = EvidenceRefResolver(loader)

    ok, detail, value = resolver.try_resolve("bundle")
    assert ok is True
    assert detail == "bundle"
    assert value["bundle_id"] == "BND-MINIMAL-001"

    ok, detail, value = resolver.try_resolve("invalid-ref")
    assert ok is False
    assert "frozen EvidenceRef grammar" in detail
    assert value is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])