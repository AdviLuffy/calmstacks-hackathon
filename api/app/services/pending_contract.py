"""Receipts for contract changes this API knows about, with their true status.

A receipt records a state. It is not a grammar and not a contract: no pattern, no validator
and no alternative identifier format is defined in this module. The fragment-EvidenceRef
amendment was pending until P1/P2 formally froze it together with the
``trace.evidence_bundle/1.0`` root contract; that freeze happened, the amendment is now
implemented inside the single normative EvidenceRef pattern (see M0-DEC-06 in
:mod:`app.contract.registry`), and the receipt says so with ``implemented=True``.
"""
from __future__ import annotations

from dataclasses import dataclass, field

#: The amendment existed and had a ruling, but P1 had not frozen it for implementation.
PENDING_STATUS_P1_FREEZE = "pending_p1_freeze"

#: P1/P2 froze the amendment (together with the trace.evidence_bundle/1.0 root contract).
FROZEN_STATUS = "frozen"


@dataclass(frozen=True)
class PendingContractItem:
    """One known, unimplemented contract change, with its true status."""

    item_id: str
    title: str
    status: str
    implemented: bool
    applies_to: str
    effect: str
    recorded_in: tuple[str, ...] = field(default_factory=tuple)
    note: str = ""


PENDING_CONTRACT_ITEMS: tuple[PendingContractItem, ...] = (
    PendingContractItem(
        item_id="P3-PENDING-01",
        title="Fragment EvidenceRef instance-ID grammar (P2 ruling: Option A)",
        status=FROZEN_STATUS,
        implemented=True,
        applies_to="fragments[...] references only",
        effect=(
            "P1/P2 froze the amendment together with the trace.evidence_bundle/1.0 root "
            "contract. The fragments slot of the single normative EvidenceRef pattern now "
            "admits the frozen fragment-instance form, and every fragments[...] reference is "
            "grounded against the supplied bundle under the exactly-one-record rule: zero or "
            "multiple matches are reported as grounding failures."
        ),
        recorded_in=(
            "app.contract.registry M0-AMB-07",
            "app.contract.registry M0-DEC-06",
            "app.contract.evidence_ref.EVIDENCE_REF_PATTERN",
            "app.contract.evidence_bundle.validate_evidence_bundle_root",
        ),
        note=(
            "The freeze is implemented inside the one normative pattern; no competing "
            "validator exists, and every other record ID format is unchanged."
        ),
    ),
)


def pending_item_ids() -> tuple[str, ...]:
    return tuple(item.item_id for item in PENDING_CONTRACT_ITEMS)


def pending_items_payload() -> tuple[dict[str, object], ...]:
    """Plain-dict view for documentation and tests; the router projects its own schema."""
    return tuple(
        {
            "item_id": item.item_id,
            "title": item.title,
            "status": item.status,
            "implemented": item.implemented,
            "applies_to": item.applies_to,
            "effect": item.effect,
            "recorded_in": list(item.recorded_in),
            "note": item.note,
        }
        for item in PENDING_CONTRACT_ITEMS
    )
