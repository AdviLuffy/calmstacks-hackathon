"""P1 recovery engine boundary. ``app.services.registry`` is the only module that imports it.

``build_recovery_service`` probes the dotted spec in ``TRACE_RECOVERY_ENGINE`` (wired through
``app.config.Settings.recovery_engine``). Nothing here runs at import time, and a missing or
broken P1 engine is reported as a note instead of an exception.
"""
from __future__ import annotations

from app.adapters.engine_adapter import AdaptedStageService, build_service_from_spec
from app.services.interfaces import STAGE_RECOVERY
from app.services.unavailable import SUBJECT_RECOVERY


class RealRecoveryService(AdaptedStageService):
    """The P1 engine, adapted to the P3 :class:`~app.services.interfaces.RecoveryService`."""

    stage = STAGE_RECOVERY
    subject = SUBJECT_RECOVERY
    engine_label = "P1 recovery"


def build_recovery_service(
    spec: str | None,
) -> tuple[RealRecoveryService | None, str | None]:
    """Probe ``spec``: return ``(service, None)`` or ``(None, note)``. Never raises."""
    service, note = build_service_from_spec(spec, RealRecoveryService)
    return service, note
