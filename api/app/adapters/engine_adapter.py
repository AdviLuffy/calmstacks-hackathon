"""Generic engine adapter: probe a dotted spec, wrap what is found, never raise at runtime.

P3 does not import a teammate module at import time. It probes a dotted ``"module:name"``
spec, wraps the object it finds, and reports back either a service or a note explaining why
there is none. A missing or broken engine therefore reaches the investigator as an explicit
``unavailable``/``failed`` stage with a reason: never a silent success, never an HTTP 500.

The expected engine shape is P3's side of the boundary, and this module is the only place it
is expressed, so it can change here without touching routers, schemas or the pipeline:

* the named attribute is an engine object, a class, or a zero-argument factory;
* the engine declares ``name``, ``version`` and ``run_id`` (A10), either as attributes or in
  an ``engine_info`` mapping;
* the engine exposes ``analyse(request)`` returning either a mapping (its own output, passed
  through opaquely) or a ready-made :class:`StageResult`.
"""
from __future__ import annotations

import importlib
from collections.abc import Mapping
from typing import Any

from app.contract.assumptions import AssumptionViolation
from app.services.interfaces import (
    FAILURE_CODE_ENGINE_CONTRACT_VIOLATION,
    FAILURE_CODE_ENGINE_DECLARATION_INVALID,
    FAILURE_CODE_ENGINE_FAILED,
    ORIGIN_COMPUTED_VALUE,
    ORIGIN_UNAVAILABLE_VALUE,
    EngineDeclaration,
    ProvenanceDeclaration,
    StageFailure,
    StageRequest,
    StageResult,
    StageStatus,
    StageWarning,
    WARNING_ENGINE_FAILED,
    utc_now,
)

#: The one method P3 calls on an engine. P1/P2 may implement anything behind it.
ENGINE_METHOD_NAME = "analyse"

DECLARATION_KEYS: tuple[str, ...] = ("name", "version", "run_id")


def split_spec(spec: str) -> tuple[str, str | None]:
    """Split ``"package.module:attribute"`` into its two parts."""
    module_name, _, attribute = spec.partition(":")
    return module_name.strip(), attribute.strip() or None


def load_engine(spec: str) -> Any:
    """Import and instantiate the object named by ``spec``. Raises on any problem."""
    module_name, attribute = split_spec(spec)
    if not module_name:
        raise ValueError("engine spec %r does not name a module" % (spec,))
    module = importlib.import_module(module_name)
    if attribute is None:
        return module
    target = getattr(module, attribute)
    if isinstance(target, type) or (callable(target) and not hasattr(target, ENGINE_METHOD_NAME)):
        return target()
    return target


def describe_engine(engine: object) -> tuple[EngineDeclaration | None, str | None]:
    """Read the A10 declaration from an engine, returning ``(declaration, problem)``."""
    info = getattr(engine, "engine_info", None)
    if isinstance(info, Mapping):
        source: Mapping[str, Any] = info
    else:
        source = {key: getattr(engine, key, None) for key in DECLARATION_KEYS}
    values = {key: source.get(key) for key in DECLARATION_KEYS}
    missing = [
        key for key, value in values.items() if not isinstance(value, str) or not value.strip()
    ]
    if missing:
        return None, "the engine does not declare %s, which A10 requires" % ", ".join(missing)
    try:
        return EngineDeclaration(**values), None
    except AssumptionViolation as exc:
        return None, "the engine declaration violates A10: %s" % exc


class AdaptedStageService:
    """Wraps one engine as one stage. Every failure path becomes a failed StageResult.

    Concrete adapters set ``stage``, ``subject`` and ``engine_label`` and nothing else, so
    the whole boundary is defined once, in this module.
    """

    stage: str = ""
    subject: str = ""
    engine_label: str = "engine"

    def __init__(self, engine: object, spec: str) -> None:
        self._engine = engine
        self._spec = spec

    @property
    def spec(self) -> str:
        """The dotted spec this service was built from, for diagnostics."""
        return self._spec

    @property
    def declaration(self) -> EngineDeclaration | None:
        return describe_engine(self._engine)[0]

    def _failed(
        self,
        code: str,
        message: str,
        *,
        detail: str | None = None,
        engine: EngineDeclaration | None = None,
    ) -> StageResult:
        return StageResult(
            stage=self.stage,
            status=StageStatus.FAILED,
            engine=engine,
            warnings=(StageWarning(WARNING_ENGINE_FAILED, message, detail=detail),),
            failure=StageFailure(code, message, detail=detail),
            provenance=(
                ProvenanceDeclaration(
                    subject=self.subject,
                    origin=ORIGIN_UNAVAILABLE_VALUE,
                    produced_at=utc_now(),
                ),
            ),
            note=detail,
        )

    def analyse(self, request: StageRequest) -> StageResult:
        """Run the engine. Any engine or contract problem becomes an explicit failure."""
        declaration, problem = describe_engine(self._engine)
        if declaration is None:
            return self._failed(
                FAILURE_CODE_ENGINE_DECLARATION_INVALID,
                "engine %r cannot be used: %s" % (self._spec, problem),
                detail=problem,
            )

        method = getattr(self._engine, ENGINE_METHOD_NAME, None)
        if not callable(method):
            return self._failed(
                FAILURE_CODE_ENGINE_CONTRACT_VIOLATION,
                "engine %r does not expose %s(request)" % (declaration.name, ENGINE_METHOD_NAME),
                detail="expected a callable %s" % ENGINE_METHOD_NAME,
                engine=declaration,
            )

        try:
            outcome = method(request)
        except Exception as exc:  # an engine bug must surface as a failed stage, not a 500
            return self._failed(
                FAILURE_CODE_ENGINE_FAILED,
                "engine %r raised %s" % (declaration.name, type(exc).__name__),
                detail=str(exc),
                engine=declaration,
            )

        try:
            return self._normalise(outcome, declaration)
        except Exception as exc:
            return self._failed(
                FAILURE_CODE_ENGINE_CONTRACT_VIOLATION,
                "engine %r returned a result P3 cannot accept" % declaration.name,
                detail="%s: %s" % (type(exc).__name__, exc),
                engine=declaration,
            )

    def _normalise(self, outcome: object, declaration: EngineDeclaration) -> StageResult:
        if isinstance(outcome, StageResult):
            if outcome.stage != self.stage:
                raise ValueError(
                    "engine %r answered for stage %r, not %r"
                    % (declaration.name, outcome.stage, self.stage)
                )
            # P3 owns the declaration, so an engine cannot claim a different identity.
            return replace(outcome, engine=declaration)
        if isinstance(outcome, Mapping):
            return StageResult(
                stage=self.stage,
                status=StageStatus.OK,
                data=dict(outcome),
                engine=declaration,
                provenance=(
                    ProvenanceDeclaration(
                        subject=self.subject,
                        origin=ORIGIN_COMPUTED_VALUE,
                        produced_at=utc_now(),
                    ),
                ),
            )
        raise ValueError("expected a mapping or a StageResult, got %s" % type(outcome).__name__)


def build_service_from_spec(
    spec: str | None, service_class: type[AdaptedStageService]
) -> tuple[AdaptedStageService | None, str | None]:
    """Probe ``spec``: return ``(service, None)`` or ``(None, note)``. Never raises."""
    if spec is None or not str(spec).strip():
        return None, "no %s module is configured (the engine spec is empty)" % (
            service_class.engine_label,
        )
    try:
        engine = load_engine(str(spec))
    except Exception as exc:
        return None, "%s module %r could not be loaded: %s: %s" % (
            service_class.engine_label,
            spec,
            type(exc).__name__,
            exc,
        )
    return service_class(engine, str(spec)), None

