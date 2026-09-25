"""Engine wiring: the only module that imports the adapters.

Resolution follows the P3 configuration contract documented in :mod:`app.config`:

* ``mock``        a deterministic double is used; the stage reports ``mock``, never ``ok``;
* ``unavailable`` nothing is connected; the stage reports ``unavailable`` with its reason;
* ``real``        the configured engine is used. If it cannot be loaded the slot becomes
                  ``unavailable`` with the load note: ``real`` never silently becomes mock;
* ``auto``        a loadable engine is used, otherwise recovery falls back to the mock and
                  intelligence becomes unavailable, exactly as ``app.config`` documents.

Nothing here raises because an engine is missing. The absence is data: an :class:`EngineSlot`
with a note, which ``/api/health``, ``/api/meta`` and every session report. Routers never
import adapters or engines; they receive an :class:`EngineWiring` through ``app.dependencies``.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.adapters.ai_adapter import build_intelligence_service
from app.adapters.recovery_adapter import build_recovery_service
from app.config import Settings
from app.services.interfaces import (
    STAGE_INTELLIGENCE,
    STAGE_RECOVERY,
    EngineDeclaration,
    IntelligenceService,
    RecoveryService,
)
from app.services.mocks import MockIntelligenceService, MockRecoveryService
from app.services.unavailable import (
    UnavailableIntelligenceService,
    UnavailableRecoveryService,
)

RESOLVED_MODE_REAL = "real"
RESOLVED_MODE_MOCK = "mock"
RESOLVED_MODE_UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class EngineSlot:
    """One engine slot: what was asked for, what was wired, and why."""

    stage: str
    requested_mode: str
    resolved_mode: str
    service: RecoveryService | IntelligenceService
    note: str | None = None

    @property
    def available(self) -> bool:
        """True only when a real engine answered the probe."""
        return self.resolved_mode == RESOLVED_MODE_REAL

    @property
    def declaration(self) -> EngineDeclaration | None:
        return getattr(self.service, "declaration", None)

    @property
    def declaration_text(self) -> str | None:
        declaration = self.declaration
        if declaration is None:
            return None
        return "%s %s (run %s)" % (declaration.name, declaration.version, declaration.run_id)


@dataclass(frozen=True)
class EngineWiring:
    """Both engine slots, plus the two derived facts the API reports."""

    recovery: EngineSlot
    intelligence: EngineSlot

    def slots(self) -> tuple[EngineSlot, ...]:
        return (self.recovery, self.intelligence)

    def as_mapping(self) -> dict[str, EngineSlot]:
        return {"recovery": self.recovery, "intelligence": self.intelligence}

    @property
    def mock_data(self) -> bool:
        """True when a response may contain synthetic placeholder data."""
        return any(slot.resolved_mode == RESOLVED_MODE_MOCK for slot in self.slots())

    @property
    def notes(self) -> tuple[str, ...]:
        """Every wiring note, so no fallback is invisible."""
        return tuple(slot.note for slot in self.slots() if slot.note)


def build_recovery_slot(settings: Settings) -> EngineSlot:
    """Resolve the P1 slot. Never raises."""
    requested = settings.recovery_mode
    if requested == RESOLVED_MODE_MOCK:
        return EngineSlot(
            STAGE_RECOVERY,
            requested,
            RESOLVED_MODE_MOCK,
            MockRecoveryService(seed=settings.mock_seed),
            "TRACE_RECOVERY_MODE=mock was requested",
        )
    if requested == RESOLVED_MODE_UNAVAILABLE:
        reason = "TRACE_RECOVERY_MODE=unavailable was requested"
        return EngineSlot(
            STAGE_RECOVERY,
            requested,
            RESOLVED_MODE_UNAVAILABLE,
            UnavailableRecoveryService(reason),
            reason,
        )

    service, note = build_recovery_service(settings.recovery_engine)
    if service is not None:
        return EngineSlot(STAGE_RECOVERY, requested, RESOLVED_MODE_REAL, service, note)
    if requested == RESOLVED_MODE_REAL:
        reason = note or "the configured P1 recovery engine could not be loaded"
        return EngineSlot(
            STAGE_RECOVERY,
            requested,
            RESOLVED_MODE_UNAVAILABLE,
            UnavailableRecoveryService(reason),
            reason,
        )
    reason = note or "no P1 recovery engine is configured"
    return EngineSlot(
        STAGE_RECOVERY,
        requested,
        RESOLVED_MODE_MOCK,
        MockRecoveryService(seed=settings.mock_seed),
        "auto fallback to the mock recovery engine: %s" % reason,
    )


def build_intelligence_slot(settings: Settings) -> EngineSlot:
    """Resolve the P2 slot. Never raises. ``auto`` does not fall back to a mock here."""
    requested = settings.ai_mode
    if requested == RESOLVED_MODE_MOCK:
        return EngineSlot(
            STAGE_INTELLIGENCE,
            requested,
            RESOLVED_MODE_MOCK,
            MockIntelligenceService(seed=settings.mock_seed),
            "TRACE_AI_MODE=mock was requested",
        )
    if requested == RESOLVED_MODE_UNAVAILABLE:
        reason = "TRACE_AI_MODE=unavailable was requested"
        return EngineSlot(
            STAGE_INTELLIGENCE,
            requested,
            RESOLVED_MODE_UNAVAILABLE,
            UnavailableIntelligenceService(reason),
            reason,
        )

    service, note = build_intelligence_service(settings.ai_engine)
    if service is not None:
        return EngineSlot(STAGE_INTELLIGENCE, requested, RESOLVED_MODE_REAL, service, note)
    reason = note or "no P2 intelligence engine is configured"
    reason = (
        "the configured P2 intelligence engine could not be loaded: %s" % reason
        if requested == RESOLVED_MODE_REAL
        else "auto: %s" % reason
    )
    return EngineSlot(
        STAGE_INTELLIGENCE,
        requested,
        RESOLVED_MODE_UNAVAILABLE,
        UnavailableIntelligenceService(reason),
        reason,
    )


def build_engine_wiring(settings: Settings) -> EngineWiring:
    """Resolve both slots for one settings snapshot."""
    return EngineWiring(
        recovery=build_recovery_slot(settings),
        intelligence=build_intelligence_slot(settings),
    )
