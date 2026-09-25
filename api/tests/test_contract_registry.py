"""M0 contract registry: it must import, and every record must be self-consistent.

The registry is the only place M0 gaps are allowed to live, so it is tested rather than
trusted. The interrupted write that left ``AMBIGUITIES`` unclosed is exactly the class of
failure the first test catches.
"""
from __future__ import annotations

from app.contract.registry import (
    AMBIGUITIES,
    AMBIGUITY_IDS,
    BLOCKING_AMBIGUITIES,
    DECISIONS,
    DECISION_IDS,
)


def test_registry_records_load_with_unique_ids():
    assert DECISION_IDS == tuple(decision.decision_id for decision in DECISIONS)
    assert AMBIGUITY_IDS == tuple(ambiguity.ambiguity_id for ambiguity in AMBIGUITIES)
    assert len(set(DECISION_IDS)) == len(DECISION_IDS)
    assert len(set(AMBIGUITY_IDS)) == len(AMBIGUITY_IDS)
    assert BLOCKING_AMBIGUITIES == tuple(
        ambiguity for ambiguity in AMBIGUITIES if ambiguity.blocking
    )


def test_the_five_authorized_decisions_are_still_present():
    assert DECISION_IDS[:5] == (
        "M0-DEC-01",
        "M0-DEC-02",
        "M0-DEC-03",
        "M0-DEC-04",
        "M0-DEC-05",
    )


def test_every_decision_is_authorized_and_encoded():
    assert DECISIONS
    for decision in DECISIONS:
        assert decision.status == "authorized"
        assert decision.authorized_by.strip()
        assert decision.statement.strip()
        assert decision.consequence.strip()
        assert decision.encoded_in
        assert all(item.strip() for item in decision.encoded_in)


def test_every_ambiguity_records_impact_and_current_handling():
    assert AMBIGUITIES
    for ambiguity in AMBIGUITIES:
        assert ambiguity.title.strip()
        assert ambiguity.detail.strip()
        assert ambiguity.impact.strip()
        assert ambiguity.current_handling.strip()
        assert isinstance(ambiguity.blocking, bool)
        assert all(item.strip() for item in ambiguity.recorded_in)


def test_resolutions_name_the_decision_that_closed_them():
    for ambiguity in AMBIGUITIES:
        if ambiguity.resolution is not None:
            assert "M0-DEC-" in ambiguity.resolution


def test_the_fragment_id_evidence_ref_gap_is_recorded_and_resolved():
    """M0-AMB-07, closed by M0-DEC-06 (the frozen Option A amendment).

    The gap used to block: the frozen FragmentInstanceId could not be written in any form
    the normative EvidenceRef pattern accepted. The Option A freeze widened the fragments
    slot inside the single pattern, so the registry must now carry the closure; this test
    holds the registry entry and that decision together, and is never deleted quietly.
    """
    recorded = {ambiguity.ambiguity_id: ambiguity for ambiguity in AMBIGUITIES}
    assert "M0-AMB-07" in recorded
    assert recorded["M0-AMB-07"].blocking is False
    assert "M0-DEC-06" in (recorded["M0-AMB-07"].resolution or "")
    assert "M0-AMB-07" in set(AMBIGUITY_IDS)
    assert "M0-AMB-07" not in {
        ambiguity.ambiguity_id for ambiguity in BLOCKING_AMBIGUITIES
    }
