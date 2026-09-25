"""Engine boundary: a missing or broken engine is data, never an exception or a mock fallback."""
from __future__ import annotations

import sys
import types

from app.adapters.ai_adapter import RealIntelligenceService, build_intelligence_service
from app.adapters.recovery_adapter import RealRecoveryService, build_recovery_service
from app.services.interfaces import (
    FAILURE_CODE_ENGINE_CONTRACT_VIOLATION,
    FAILURE_CODE_ENGINE_DECLARATION_INVALID,
    FAILURE_CODE_ENGINE_FAILED,
    STAGE_INTELLIGENCE,
    STAGE_RECOVERY,
    StageRequest,
    StageResult,
    StageStatus,
    EngineDeclaration,
)
from app.services.registry import build_engine_wiring
from p3_helpers import (
    ARBITRARY_BUNDLE,
    ExplodingEngine,
    FakeEngine,
    SilentEngine,
    UndeclaredEngine,
    make_settings,
)


def _request() -> StageRequest:
    return StageRequest(
        session_id="abc",
        case_id="CASE",
        module_version="0.1.0",
        evidence=dict(ARBITRARY_BUNDLE),
        evidence_sha256="e" * 64,
        bundle_sha256="b" * 64,
        options={},
    )


def test_empty_spec_is_a_note_not_an_exception():
    service, note = build_recovery_service(None)
    assert service is None
    assert note and "empty" in note
    service, note = build_intelligence_service("   ")
    assert service is None
    assert note and "empty" in note


def test_real_engine_mapping_becomes_ok_and_stays_opaque():
    service = RealIntelligenceService(
        FakeEngine(stage=STAGE_INTELLIGENCE, payload={"opaque": {"claims": "not-ours"}}),
        "tests:fake",
    )
    result = service.analyse(_request())
    assert result.status is StageStatus.OK
    assert result.data == {"opaque": {"claims": "not-ours"}}
    assert result.engine.name == "fake-engine"
    assert result.provenance[0].origin == "computed"


def test_undeclared_engine_fails_a10_instead_of_succeeding():
    result = RealRecoveryService(UndeclaredEngine(), "tests:undeclared").analyse(_request())
    assert result.status is StageStatus.FAILED
    assert result.failure.code == FAILURE_CODE_ENGINE_DECLARATION_INVALID
    assert result.data is None
    assert "A10" in (result.failure.detail or "")


def test_engine_without_analyse_is_a_contract_violation():
    result = RealRecoveryService(SilentEngine(), "tests:silent").analyse(_request())
    assert result.status is StageStatus.FAILED
    assert result.failure.code == FAILURE_CODE_ENGINE_CONTRACT_VIOLATION
    assert result.engine is not None
    assert result.engine.name == "silent-engine"


def test_engine_exception_becomes_a_failed_stage():
    result = RealIntelligenceService(
        ExplodingEngine(stage=STAGE_INTELLIGENCE, name="boom"), "tests:boom"
    ).analyse(_request())
    assert result.status is StageStatus.FAILED
    assert result.failure.code == FAILURE_CODE_ENGINE_FAILED
    assert "secret detail" in (result.failure.detail or "")
    assert result.engine.name == "boom"


def test_non_mapping_result_is_refused():
    class Weird:
        name = "weird"
        version = "1"
        run_id = "r"

        def analyse(self, request: StageRequest) -> str:
            return "not a mapping"

    result = RealRecoveryService(Weird(), "tests:weird").analyse(_request())
    assert result.status is StageStatus.FAILED
    assert result.failure.code == FAILURE_CODE_ENGINE_CONTRACT_VIOLATION


def test_stage_result_for_the_wrong_stage_is_refused():
    class WrongStage:
        name = "wrong"
        version = "1"
        run_id = "r"

        def analyse(self, request: StageRequest) -> StageResult:
            return StageResult(
                stage=STAGE_INTELLIGENCE,
                status=StageStatus.OK,
                data={"x": 1},
                engine=EngineDeclaration(name="wrong", version="1", run_id="r"),
            )

    result = RealRecoveryService(WrongStage(), "tests:wrong").analyse(_request())
    assert result.status is StageStatus.FAILED
    assert result.failure.code == FAILURE_CODE_ENGINE_CONTRACT_VIOLATION


def test_factory_callable_spec_is_instantiated():
    probe = types.ModuleType("p3_probe_engine")

    class Engine:
        name = "probed"
        version = "9"
        run_id = "probe-run"

        def analyse(self, request: StageRequest) -> dict:
            return {"probed": True}

    def factory() -> Engine:
        return Engine()

    probe.factory = factory
    sys.modules["p3_probe_engine"] = probe
    try:
        service, note = build_recovery_service("p3_probe_engine:factory")
    finally:
        sys.modules.pop("p3_probe_engine", None)
    assert note is None
    assert service is not None
    result = service.analyse(_request())
    assert result.status is StageStatus.OK
    assert result.data == {"probed": True}
    assert result.engine.name == "probed"


def test_real_mode_never_falls_back_to_mock():
    """``real`` with a broken spec is unavailable, never a silent mock."""
    settings = make_settings(
        recovery_mode="real",
        recovery_engine="no.such.recovery:Engine",
        ai_mode="real",
        ai_engine="no.such.intelligence:Engine",
    )
    wiring = build_engine_wiring(settings)
    assert wiring.recovery.resolved_mode == "unavailable"
    assert wiring.intelligence.resolved_mode == "unavailable"
    assert wiring.mock_data is False
    assert "could not be loaded" in (wiring.recovery.note or "")
    assert "could not be loaded" in (wiring.intelligence.note or "")


def test_auto_recovery_may_mock_but_auto_intelligence_does_not():
    settings = make_settings(recovery_mode="auto", ai_mode="auto")
    wiring = build_engine_wiring(settings)
    assert wiring.recovery.resolved_mode == "mock"
    assert "auto fallback" in (wiring.recovery.note or "")
    assert wiring.intelligence.resolved_mode == "unavailable"
    assert (wiring.intelligence.note or "").startswith("auto:")
    assert wiring.mock_data is True


def test_explicit_mock_and_unavailable_modes_are_honoured():
    settings = make_settings(recovery_mode="mock", ai_mode="unavailable", mock_seed=3)
    wiring = build_engine_wiring(settings)
    assert wiring.recovery.resolved_mode == "mock"
    assert wiring.recovery.declaration is not None
    assert wiring.recovery.declaration.run_id == "mock-3"
    assert wiring.intelligence.resolved_mode == "unavailable"
    assert wiring.intelligence.available is False


def test_missing_module_is_a_note():
    service, note = build_recovery_service("no.such.recovery.module:Engine")
    assert service is None
    assert "could not be loaded" in note
    assert "ModuleNotFoundError" in note
