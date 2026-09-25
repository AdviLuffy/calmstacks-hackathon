"""System responses: health and meta. These describe the running API, not the evidence.

``/api/meta`` is where P3 discharges the M0 registry's promise that "everything here is
exposed by ``GET /api/meta`` so no gap is invisible at runtime", and where the
fragment-EvidenceRef amendment receipt reports its frozen state. The receipt records a
state, it does not define a grammar: the single normative EvidenceRef pattern lives in
``app.contract.evidence_ref``.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from app.schemas.common import APIWarning, DataOrigin


class EngineStatus(BaseModel):
    """How one engine slot resolved, including why."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    requested_mode: str
    resolved_mode: str
    available: bool
    declaration: str | None = None
    note: str | None = None


class HealthResponse(BaseModel):
    """Liveness plus the truth about what is wired up."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str
    ready: bool
    api_version: str
    contract_version: str
    canonicalization_profile: str
    mock_data: bool
    engines: dict[str, EngineStatus]
    warnings: tuple[APIWarning, ...] = ()


class PendingContractItem(BaseModel):
    """A change this API knows about but has not implemented, with its true status."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    item_id: str
    title: str
    status: str
    implemented: bool
    applies_to: str
    effect: str
    recorded_in: tuple[str, ...] = ()
    note: str = ""


class MetaResponse(BaseModel):
    """The frozen vocabulary P3 honours, the recorded gaps, and what is not yet frozen."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    api_version: str
    contract_version: str
    canonicalization_profile: str
    report_schema_id: str
    report_schema_frozen: bool
    data_origins: tuple[DataOrigin, ...]
    bookkeeping_timestamp_fields: tuple[str, ...]
    confidence_ceilings: dict[str, float | None]
    decisions: tuple[dict[str, Any], ...]
    ambiguities: tuple[dict[str, Any], ...]
    blocking_ambiguity_ids: tuple[str, ...]
    pending_contract_items: tuple[PendingContractItem, ...]
    engines: dict[str, EngineStatus]
    mock_data: bool
    session_statuses: tuple[str, ...]
    warnings: tuple[APIWarning, ...] = ()
