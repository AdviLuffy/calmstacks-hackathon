"""FastAPI dependencies: the only place a router gets its collaborators from.

Everything comes from ``request.app.state``, which :func:`app.main.create_app` fills in. A
router therefore never reads the environment, never builds a store and never imports an
adapter.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.config import Settings
from app.schemas.system import EngineStatus
from app.services.interfaces import (
    SessionStore,
    StageWarning,
    WARNING_CONFIG_INVALID,
    WARNING_SESSION_PERSISTENCE_FAILED,
)
from app.services.pipeline import SessionPipeline
from app.services.registry import EngineWiring


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_wiring(request: Request) -> EngineWiring:
    return request.app.state.wiring


def get_store(request: Request) -> SessionStore:
    return request.app.state.store


def get_pipeline(request: Request) -> SessionPipeline:
    return request.app.state.pipeline


SettingsDep = Annotated[Settings, Depends(get_settings)]
WiringDep = Annotated[EngineWiring, Depends(get_wiring)]
StoreDep = Annotated[SessionStore, Depends(get_store)]
PipelineDep = Annotated[SessionPipeline, Depends(get_pipeline)]


def settings_warnings(settings: Settings) -> tuple[StageWarning, ...]:
    """Environment problems the configuration layer recorded instead of hiding."""
    return tuple(
        StageWarning(
            WARNING_CONFIG_INVALID,
            "a configuration value was rejected and the default was used",
            detail=problem,
        )
        for problem in settings.config_warnings
    )


def store_warnings(store: SessionStore) -> tuple[StageWarning, ...]:
    """Stored sessions this process refused to load. Visible, never skipped silently."""
    return tuple(
        StageWarning(
            WARNING_SESSION_PERSISTENCE_FAILED,
            "a stored session could not be loaded and is not available",
            detail=problem,
        )
        for problem in getattr(store, "load_errors", ())
    )


def api_warnings(settings: Settings, store: SessionStore) -> tuple[StageWarning, ...]:
    """Every API-level warning: configuration first, then storage."""
    return settings_warnings(settings) + store_warnings(store)


def engine_statuses(wiring: EngineWiring) -> dict[str, EngineStatus]:
    """Project both engine slots for ``/api/health`` and ``/api/meta``."""
    return {
        name: EngineStatus(
            requested_mode=slot.requested_mode,
            resolved_mode=slot.resolved_mode,
            available=slot.available,
            declaration=slot.declaration_text,
            note=slot.note,
        )
        for name, slot in wiring.as_mapping().items()
    }
