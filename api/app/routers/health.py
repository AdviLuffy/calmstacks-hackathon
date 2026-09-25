"""``GET /api/health``: liveness plus the truth about what is wired up.

The endpoint never claims more than it knows: an engine slot that fell back to a mock or to
"unavailable" is reported as such, and every configuration or storage problem recorded at
startup is repeated here instead of being buried in a log.
"""
from __future__ import annotations

from fastapi import APIRouter

from app.dependencies import SettingsDep, StoreDep, WiringDep, api_warnings, engine_statuses
from app.schemas.common import CANONICALIZATION_PROFILE, project_warnings
from app.schemas.system import HealthResponse

router = APIRouter(tags=["system"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness and engine wiring status",
)
def health(settings: SettingsDep, wiring: WiringDep, store: StoreDep) -> HealthResponse:
    warnings = api_warnings(settings, store)
    ready = any(slot.available for slot in wiring.slots())
    return HealthResponse(
        status="ok" if ready else "degraded",
        ready=ready,
        api_version=settings.api_version,
        contract_version=settings.contract_version,
        canonicalization_profile=CANONICALIZATION_PROFILE,
        mock_data=wiring.mock_data,
        engines=engine_statuses(wiring),
        warnings=project_warnings(warnings),
    )
