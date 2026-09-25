"""P2 intelligence engine boundary. ``app.services.registry`` is the only module that imports it.

``build_intelligence_service`` probes the dotted spec in ``TRACE_AI_ENGINE`` (wired through
``app.config.Settings.ai_engine``). The P2 report body is passed through opaquely: P3 does not
model claims, findings or any other P2 field, so nothing here has to change when the P2
``intelligence_report.schema.json`` is frozen and integrated.
"""
from __future__ import annotations

from app.adapters.engine_adapter import AdaptedStageService, build_service_from_spec
from app.services.interfaces import STAGE_INTELLIGENCE
from app.services.unavailable import SUBJECT_INTELLIGENCE


class RealIntelligenceService(AdaptedStageService):
    """The P2 engine, adapted to the P3 :class:`~app.services.interfaces.IntelligenceService`."""

    stage = STAGE_INTELLIGENCE
    subject = SUBJECT_INTELLIGENCE
    engine_label = "P2 intelligence"


def build_intelligence_service(
    spec: str | None,
) -> tuple[RealIntelligenceService | None, str | None]:
    """Probe ``spec``: return ``(service, None)`` or ``(None, note)``. Never raises."""
    service, note = build_service_from_spec(spec, RealIntelligenceService)
    return service, note
