"""M0 EvidenceRef: the single normative validator, and the D-2 tri-state resolver.

``PARSE_PATTERN`` is only a decomposer, but the module states that it must accept exactly
the same language as the normative pattern. That equivalence is not decoration: if the two
diverge, ``parse_evidence_ref`` raises its "internal error" branch for a reference the
normative validator already accepted, and every collection reference silently becomes
unresolvable. These tests hold the two patterns together.
"""
from __future__ import annotations

import pytest

from app.contract.evidence_ref import (
    EVIDENCE_REF_RE,
    GROUNDING_REASON_CASE_BLOCK_ABSENT,
    GROUNDING_REASON_FIELD_NAMESPACE_NOT_FROZEN,
    GROUNDING_REASON_INSTANCE_ID_NOT_FOUND,
    GROUNDING_REASON_SYNTAX_INVALID,
    PARSE_RE,
    GroundingStatus,
    SessionEvidenceRefResolver,
    all_grounded,
    is_valid_evidence_ref,
    parse_evidence_ref,
    ungrounded,
)

#: References the M0 material enumerates as valid, plus the shapes M0-AMB-03 describes.
#: These enumerate the language of the NORMATIVE EvidenceRef pattern, whose fragments slot
#: admits the frozen FRG fragment-instance form as an alternative (M0-DEC-06).
VALID_REFS = (
    "bundle",
    "case",
    "artifacts[ART-0001]",
    "artifacts[ART-0005].timestamps[0].value_utc",
    "fragments[FRG-0001]",
    "fragments[FRG-0001].byte_range",
    "fragments[FRG-0123456789abcdef-0-4096]",
    "fragments[FRG-0123456789abcdef-0-4096].byte_range",
    "reconstruction_groups[RG-00000001].result",
    "timeline_events[EVT-00000001].ts_utc",
    "known_file_matches[KFM-00000001].matched",
    "artifacts[ART-0001].signature[3].matched",
    "bundle.signature.matched",
    "case.signature",
)

INVALID_REFS = (
    "",
    "artifacts",
    "fragments[FRG-0001",
    "artifacts[ART-0001].Signature",
    "artifacts[ART-0001].a.b.c",
    "[ART-0001]",
    None,
    17,
)

COLLECTION_IDS = {
    "artifacts": frozenset({"ART-0001"}),
    "fragments": frozenset({"FRG-0001"}),
}


@pytest.mark.parametrize("ref", VALID_REFS)
def test_both_patterns_accept_the_same_valid_references(ref):
    assert EVIDENCE_REF_RE.fullmatch(ref) is not None
    assert PARSE_RE.fullmatch(ref) is not None
    assert is_valid_evidence_ref(ref) is True


@pytest.mark.parametrize("ref", INVALID_REFS)
def test_neither_pattern_accepts_an_invalid_reference(ref):
    if isinstance(ref, str):
        assert EVIDENCE_REF_RE.fullmatch(ref) is None
        assert PARSE_RE.fullmatch(ref) is None
    assert is_valid_evidence_ref(ref) is False


def test_parse_decomposes_head_collection_and_segments():
    parsed = parse_evidence_ref("artifacts[ART-0005].timestamps[0].value_utc")
    assert parsed.root == "artifacts"
    assert parsed.collection == "artifacts"
    assert parsed.instance_id == "ART-0005"
    assert parsed.segments == ("timestamps", "value_utc")
    assert parsed.segment_indexes == (0, None)
    assert parsed.has_trailing_segments is True
    assert parsed.is_root_reference is False

    root = parse_evidence_ref("bundle")
    assert root.root == "bundle"
    assert root.collection is None
    assert root.instance_id is None
    assert root.has_trailing_segments is False
    assert root.is_root_reference is True


def test_resolver_resolves_a_known_collection_reference():
    result = SessionEvidenceRefResolver(collection_ids=COLLECTION_IDS).resolve(
        "artifacts[ART-0001]"
    )
    assert result.status is GroundingStatus.RESOLVED
    assert result.collection == "artifacts"
    assert result.instance_id == "ART-0001"
    assert result.segments == ()
    assert result.is_grounded is True


def test_resolver_reports_an_unknown_identifier_as_unresolved():
    result = SessionEvidenceRefResolver(collection_ids=COLLECTION_IDS).resolve(
        "artifacts[ART-9999]"
    )
    assert result.status is GroundingStatus.UNRESOLVED
    assert result.reason == GROUNDING_REASON_INSTANCE_ID_NOT_FOUND
    assert result.instance_id == "ART-9999"


def test_resolver_reports_a_syntax_error_as_unresolved():
    result = SessionEvidenceRefResolver(collection_ids=COLLECTION_IDS).resolve(
        "artifacts[ART-0001"
    )
    assert result.status is GroundingStatus.UNRESOLVED
    assert result.reason == GROUNDING_REASON_SYNTAX_INVALID


def test_resolver_withholds_a_trailing_field_name_as_unverifiable():
    """D-2: the field namespace is not frozen, so a qualified reference is not verifiable."""
    result = SessionEvidenceRefResolver(collection_ids=COLLECTION_IDS).resolve(
        "artifacts[ART-0001].timestamps[0].value_utc"
    )
    assert result.status is GroundingStatus.UNVERIFIABLE
    assert result.reason == GROUNDING_REASON_FIELD_NAMESPACE_NOT_FROZEN
    assert result.segments == ("timestamps", "value_utc")
    assert result.is_grounded is False


def test_bundle_is_always_resolvable_and_case_needs_its_block():
    resolver = SessionEvidenceRefResolver(case_block_present=False)
    assert resolver.resolve("bundle").status is GroundingStatus.RESOLVED

    absent = resolver.resolve("case")
    assert absent.status is GroundingStatus.UNRESOLVED
    assert absent.reason == GROUNDING_REASON_CASE_BLOCK_ABSENT

    present = SessionEvidenceRefResolver(case_block_present=True).resolve("case")
    assert present.status is GroundingStatus.RESOLVED


def test_grounding_helpers_require_every_reference():
    resolver = SessionEvidenceRefResolver(collection_ids=COLLECTION_IDS)

    grounded = resolver.resolve_all(["bundle", "artifacts[ART-0001]"])
    assert all_grounded(grounded) is True
    assert ungrounded(grounded) == ()
    assert all_grounded(()) is False

    mixed = resolver.resolve_all(["bundle", "artifacts[ART-9999]"])
    assert all_grounded(mixed) is False
    assert len(ungrounded(mixed)) == 1
