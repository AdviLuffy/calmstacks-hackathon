"""``GET /api/meta``: the frozen vocabulary P3 honours, plus every recorded gap.

This is where the M0 registry's promise is discharged: the authorized decisions, the recorded
ambiguities, the blocking ambiguity identifiers, P3's configuration and storage warnings, and
the *receipt* for the fragment-EvidenceRef amendment all appear here, so nothing is
invisible at runtime.

The receipt is a state report. It defines no grammar and no identifier format: it now shows
``implemented=true`` with ``status=frozen`` because P1/P2 froze the amendment together with
the ``trace.evidence_bundle/1.0`` root contract, and the implementation lives in the single
normative pattern, never in this router.
"""
from __future__ import annotations

from dataclasses import asdict

from fastapi import APIRouter

from app.contract.assumptions import CONFIDENCE_CEILINGS
from app.contract.canonical import CANONICALIZATION_PROFILE, REPORT_SCHEMA_ID
from app.contract.registry import AMBIGUITIES, BLOCKING_AMBIGUITIES, DECISIONS
from app.dependencies import SettingsDep, StoreDep, WiringDep, api_warnings, engine_statuses
from app.schemas.common import BOOKKEEPING_TIMESTAMP_FIELDS, DataOrigin, project_warnings
from app.schemas.system import MetaResponse, PendingContractItem
from app.services.interfaces import SessionStatus
from app.services.pending_contract import PENDING_CONTRACT_ITEMS

router = APIRouter(tags=["system"])


@router.get(
    "/meta",
    response_model=MetaResponse,
    summary="Contract vocabulary, recorded gaps and engine wiring",
)
def meta(settings: SettingsDep, wiring: WiringDep, store: StoreDep) -> MetaResponse:
    return MetaResponse(
        api_version=settings.api_version,
        contract_version=settings.contract_version,
        canonicalization_profile=CANONICALIZATION_PROFILE,
        report_schema_id=REPORT_SCHEMA_ID,
        report_schema_frozen=False,
        data_origins=tuple(DataOrigin(value) for value in DataOrigin.frozen_values()),
        bookkeeping_timestamp_fields=BOOKKEEPING_TIMESTAMP_FIELDS,
        confidence_ceilings={
            origin: ceiling for origin, ceiling in CONFIDENCE_CEILINGS.items()
        },
        decisions=tuple(asdict(decision) for decision in DECISIONS),
        ambiguities=tuple(asdict(ambiguity) for ambiguity in AMBIGUITIES),
        blocking_ambiguity_ids=tuple(item.ambiguity_id for item in BLOCKING_AMBIGUITIES),
        pending_contract_items=tuple(
            PendingContractItem(
                item_id=item.item_id,
                title=item.title,
                status=item.status,
                implemented=item.implemented,
                applies_to=item.applies_to,
                effect=item.effect,
                recorded_in=item.recorded_in,
                note=item.note,
            )
            for item in PENDING_CONTRACT_ITEMS
        ),
        engines=engine_statuses(wiring),
        mock_data=wiring.mock_data,
        session_statuses=tuple(status.value for status in SessionStatus),
        warnings=project_warnings(api_warnings(settings, store)),
    )
