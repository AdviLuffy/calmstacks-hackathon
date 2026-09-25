"""Shared helpers for the P3 test suite.

The bundle and report payloads used here are deliberately arbitrary. P3 treats P1's bundle and
P2's report as opaque documents, so no P3 test may depend on the internals of either: these
tests exercise P3's lifecycle, warnings, failures and provenance, not another team's schema.
"""
from __future__ import annotations

import dataclasses
import json
from typing import Any

from app.adapters.ai_adapter import RealIntelligenceService
from app.adapters.recovery_adapter import RealRecoveryService
from app.config import Settings, load_settings
from app.services.interfaces import (
    STAGE_INTELLIGENCE,
    STAGE_RECOVERY,
    StageRequest,
)
from app.services.mocks import MockIntelligenceService, MockRecoveryService
from app.services.registry import EngineSlot, EngineWiring
from app.services.unavailable import (
    UnavailableIntelligenceService,
    UnavailableRecoveryService,
)

#: A bundle satisfying the frozen trace.evidence_bundle/1.0 root contract (M0-DEC-06).
#: P3 enforces that root contract at ingestion and still never interprets the interiors.
def make_bundle(**overrides: Any) -> dict[str, Any]:
    """A bundle that satisfies the frozen root contract.

    ``overrides`` lets a test corrupt, remove or add a root field without restating the
    contract: fragments, artifacts and the other frozen arrays pass straight through.
    """
    bundle: dict[str, Any] = {
        "schema_version": "trace.evidence_bundle/1.0",
        "bundle_id": "BND-TEST-0001",
        "generated_utc": "2026-01-01T00:00:00Z",
        "case": {},
        "acquisition": {},
        "capabilities": {},
        "artifacts": [],
        "engine": {},
        "extensions": {
            "note": "arbitrary document: P3 treats bundle interiors as opaque",
            "values": [1, 2, 3],
        },
    }
    bundle.update(overrides)
    return bundle


#: An opaque stand-in for P1's Evidence Bundle: valid at the root, opaque below it.
ARBITRARY_BUNDLE: dict[str, Any] = make_bundle()

#: An opaque stand-in for P2's report body. P3 must not interpret it either.
ARBITRARY_REPORT: dict[str, Any] = {
    "note": "arbitrary document: the P2 report schema is not frozen yet",
    "items": [{"whatever": "P2 will define this"}],
}


class FakeEngine:
    """A well-behaved engine double: it declares itself (A10) and returns a mapping."""

    def __init__(
        self,
        *,
        stage: str,
        name: str = "fake-engine",
        version: str = "1.2.3",
        run_id: str = "run-1",
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.stage = stage
        self.name = name
        self.version = version
        self.run_id = run_id
        self.payload = dict(payload) if payload is not None else {"from": name}
        self.requests: list[StageRequest] = []

    def analyse(self, request: StageRequest) -> dict[str, Any]:
        self.requests.append(request)
        return dict(self.payload)


class ExplodingEngine(FakeEngine):
    """An engine that raises. P3 must turn this into a failed stage, never a 500."""

    def analyse(self, request: StageRequest) -> dict[str, Any]:
        self.requests.append(request)
        raise RuntimeError("engine exploded: secret detail")


class SilentEngine:
    """An engine without the method P3 calls."""

    name = "silent-engine"
    version = "1.0.0"
    run_id = "run-silent"


class UndeclaredEngine:
    """An engine that never declares itself, so A10 cannot be met."""

    def analyse(self, request: StageRequest) -> dict[str, Any]:
        return {"undeclared": True}


def make_settings(**overrides: Any) -> Settings:
    """Settings with P3's test defaults (no engines, no persistence) plus the overrides."""
    defaults: dict[str, Any] = {
        "recovery_mode": "unavailable",
        "ai_mode": "unavailable",
        "recovery_engine": None,
        "ai_engine": None,
        "persist_sessions": False,
        "config_warnings": (),
    }
    defaults.update(overrides)
    return dataclasses.replace(load_settings(), **defaults)


def unavailable_slot(stage: str, reason: str = "no engine is wired in this test") -> EngineSlot:
    service: Any = (
        UnavailableRecoveryService(reason) if stage == STAGE_RECOVERY else UnavailableIntelligenceService(reason)
    )
    return EngineSlot(stage, "unavailable", "unavailable", service, reason)


def mock_slot(stage: str, *, seed: int = 7) -> EngineSlot:
    service: Any = (
        MockRecoveryService(seed=seed) if stage == STAGE_RECOVERY else MockIntelligenceService(seed=seed)
    )
    return EngineSlot(stage, "mock", "mock", service, "test mock was requested")


def real_slot(stage: str, engine: Any, spec: str = "tests:engine") -> EngineSlot:
    service: Any = (
        RealRecoveryService(engine, spec)
        if stage == STAGE_RECOVERY
        else RealIntelligenceService(engine, spec)
    )
    return EngineSlot(stage, "real", "real", service)


def make_wiring(**overrides: Any) -> EngineWiring:
    """Wiring built from injected services, never from the environment."""
    defaults: dict[str, Any] = {
        "recovery": unavailable_slot(STAGE_RECOVERY),
        "intelligence": unavailable_slot(STAGE_INTELLIGENCE),
    }
    defaults.update(overrides)
    return EngineWiring(**defaults)


def complete_wiring(
    *, recovery_payload: dict[str, Any] | None = None, report: dict[str, Any] | None = None
) -> EngineWiring:
    """Both stages produce real output, so a session can be ``complete``."""
    return make_wiring(
        recovery=real_slot(
            STAGE_RECOVERY,
            FakeEngine(
                stage=STAGE_RECOVERY,
                name="fake-p1",
                payload=recovery_payload if recovery_payload is not None else {"recovered": True},
            ),
        ),
        intelligence=real_slot(
            STAGE_INTELLIGENCE,
            FakeEngine(
                stage=STAGE_INTELLIGENCE,
                name="fake-p2",
                payload=report if report is not None else dict(ARBITRARY_REPORT),
            ),
        ),
    )


def upload(
    client: Any,
    payload: Any,
    *,
    case_id: str | None = None,
    options: str | None = None,
    filename: str = "bundle.json",
    content_type: str = "application/json",
) -> Any:
    """POST a bundle the way an investigator client would."""
    form: dict[str, str] = {}
    if case_id is not None:
        form["case_id"] = case_id
    if options is not None:
        form["options"] = options
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
    return client.post(
        "/api/sessions",
        files={"file": (filename, body, content_type)},
        data=form,
    )
