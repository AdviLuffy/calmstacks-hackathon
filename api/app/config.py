"""Runtime configuration for the TRACE investigator API (Person 3).

All values come from environment variables with a ``TRACE_`` prefix. No third-party
settings library is used, so the API stays importable with a minimal dependency
surface and with no teammate code present at all.

This module owns the *API* contract version only. Every M0 vocabulary, assumption and
canonicalization rule lives in :mod:`app.contract`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

#: Root of the ``api/`` package directory (two levels up from this file).
API_ROOT: Path = Path(__file__).resolve().parents[1]

#: Version of the API surface itself.
API_VERSION = "0.1.0"

#: Version of the investigator-facing contract implemented here. A11 requires a major
#: bump before any *required* field is added.
CONTRACT_VERSION = "1.0"

#: Canonicalization profile identifier, taken verbatim from the M0 material.
CANONICALIZATION_PROFILE = "trace-cj/1.0"

#: Accepted engine wiring modes. "auto" picks up a real engine if importable, otherwise
#: falls back to mock (recovery) or not-connected (AI).
RECOVERY_MODES = ("auto", "real", "mock", "unavailable")
AI_MODES = ("auto", "real", "mock", "unavailable")

DEFAULT_MAX_EVIDENCE_BYTES = 64 * 1024 * 1024
DEFAULT_PAGE_LIMIT = 50
DEFAULT_MAX_PAGE_LIMIT = 500
DEFAULT_MOCK_SEED = 20260925


def _env(name: str, default: str) -> str:
    return os.environ.get("TRACE_" + name, default)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get("TRACE_" + name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get("TRACE_" + name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    """Immutable configuration snapshot."""

    api_version: str
    contract_version: str
    #: Value used as ``module_version`` in the frozen M0 report_id derivation.
    module_version: str

    recovery_mode: str
    ai_mode: str
    #: Dotted ``"module:attribute"`` spec for the P1 recovery engine
    #: (TRACE_RECOVERY_ENGINE). None means "no engine module is configured".
    recovery_engine: str | None
    #: Dotted ``"module:attribute"`` spec for the P2 intelligence engine
    #: (TRACE_AI_ENGINE). None means "no engine module is configured".
    ai_engine: str | None

    api_root: Path
    evidence_root: Path
    session_root: Path
    fixture_root: Path

    max_evidence_bytes: int
    mock_seed: int

    default_page_limit: int
    max_page_limit: int

    cors_origins: tuple[str, ...]
    persist_sessions: bool

    #: Non-fatal problems detected while reading the environment. Surfaced by /api/meta.
    config_warnings: tuple[str, ...]

    @property
    def mock_data(self) -> bool:
        """True when a response may contain synthetic placeholder data."""
        return self.recovery_mode == "mock" or self.ai_mode == "mock"


def load_settings() -> Settings:
    """Read settings from the environment, collecting non-fatal warnings."""
    problems: list[str] = []

    recovery_mode = _env("RECOVERY_MODE", "auto").strip().lower()
    if recovery_mode not in RECOVERY_MODES:
        problems.append(
            "TRACE_RECOVERY_MODE=%r is not one of %s; 'auto' used." % (recovery_mode, RECOVERY_MODES)
        )
        recovery_mode = "auto"

    ai_mode = _env("AI_MODE", "auto").strip().lower()
    if ai_mode not in AI_MODES:
        problems.append("TRACE_AI_MODE=%r is not one of %s; 'auto' used." % (ai_mode, AI_MODES))
        ai_mode = "auto"

    max_evidence_bytes = _env_int("MAX_EVIDENCE_BYTES", DEFAULT_MAX_EVIDENCE_BYTES)
    if max_evidence_bytes <= 0:
        problems.append("TRACE_MAX_EVIDENCE_BYTES must be positive; default used.")
        max_evidence_bytes = DEFAULT_MAX_EVIDENCE_BYTES

    default_page_limit = _env_int("DEFAULT_PAGE_LIMIT", DEFAULT_PAGE_LIMIT)
    max_page_limit = _env_int("MAX_PAGE_LIMIT", DEFAULT_MAX_PAGE_LIMIT)
    if default_page_limit <= 0:
        problems.append("TRACE_DEFAULT_PAGE_LIMIT must be positive; default used.")
        default_page_limit = DEFAULT_PAGE_LIMIT
    if max_page_limit < default_page_limit:
        problems.append("TRACE_MAX_PAGE_LIMIT must be >= TRACE_DEFAULT_PAGE_LIMIT; raised.")
        max_page_limit = default_page_limit

    cors_origins = tuple(
        origin.strip()
        for origin in _env("CORS_ORIGINS", "http://localhost:3000,http://localhost:5173").split(",")
        if origin.strip()
    )

    return Settings(
        api_version=API_VERSION,
        contract_version=CONTRACT_VERSION,
        module_version=_env("MODULE_VERSION", API_VERSION).strip() or API_VERSION,
        recovery_mode=recovery_mode,
        ai_mode=ai_mode,
        recovery_engine=_env("RECOVERY_ENGINE", "").strip() or None,
        ai_engine=_env("AI_ENGINE", "").strip() or None,
        api_root=API_ROOT,
        evidence_root=Path(_env("EVIDENCE_ROOT", "")) if _env("EVIDENCE_ROOT", "") else (Path("/tmp/trace_evidence") if os.environ.get("VERCEL") else API_ROOT / "var" / "evidence"),
        session_root=Path(_env("SESSION_ROOT", "")) if _env("SESSION_ROOT", "") else (Path("/tmp/trace_sessions") if os.environ.get("VERCEL") else API_ROOT / "var" / "sessions"),
        fixture_root=API_ROOT / "fixtures",
        max_evidence_bytes=max_evidence_bytes,
        mock_seed=_env_int("MOCK_SEED", DEFAULT_MOCK_SEED),
        default_page_limit=default_page_limit,
        max_page_limit=max_page_limit,
        cors_origins=cors_origins,
        persist_sessions=_env_bool("PERSIST_SESSIONS", False),
        config_warnings=tuple(problems),
    )