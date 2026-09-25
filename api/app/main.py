"""The FastAPI application: composition, middleware and centralised error handling.

``create_app`` is a factory, so tests can build an application with their own settings, engine
wiring and store. The module-level ``app`` is what ``uvicorn app.main:app`` serves.

Error handling lives here and nowhere else:

* :class:`~app.errors.APIError` becomes its own status code in the P3 error envelope, which
  also carries the warnings collected before the failure;
* a request-validation failure becomes ``invalid_input`` naming the offending locations;
* framework 404/405 responses get the same envelope, so every failure looks the same;
* an unexpected exception becomes ``internal_error`` with no internal detail in the body,
  while the exception itself goes to the server log.
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.config import Settings, load_settings
from app.dependencies import api_warnings
from app.errors import (
    APIError,
    ERROR_CODE_INTERNAL,
    ERROR_CODE_INVALID_INPUT,
    code_for_status,
)
from app.routers import health as health_routes
from app.routers import meta as meta_routes
from app.routers import evidence as evidence_routes
from app.routers import sessions as session_routes
from app.schemas.common import api_error_payload, project_warning
from app.services.interfaces import SessionStore, StageWarning
from app.services.pipeline import SessionPipeline
from app.services.registry import EngineWiring, build_engine_wiring
from app.services.session_store import FileSessionStore, InMemorySessionStore

logger = logging.getLogger("trace.investigator_api")

#: Every router is mounted under this prefix.
API_PREFIX = "/api"

DESCRIPTION = (
    "Investigator-facing API for the TRACE evidence pipeline. P1 produces the Evidence Bundle, "
    "P2 produces the Intelligence Report, and this API runs and reports that pipeline without "
    "modelling either artefact's internals. Stage warnings, stage failures and provenance are "
    "always reported, never omitted."
)


def build_store(settings: Settings) -> SessionStore:
    """The store implied by configuration. Persistence is opt-in (TRACE_PERSIST_SESSIONS)."""
    if settings.persist_sessions:
        return FileSessionStore(settings.session_root)
    return InMemorySessionStore()


def _warning_payloads(request: Request, extra: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    """API-level warnings plus the warnings an error collected on its way out."""
    collected: tuple[Any, ...] = tuple(getattr(request.app.state, "api_warnings", ()))
    return [
        project_warning(warning).model_dump(mode="json") for warning in collected + tuple(extra)
    ]


async def _api_error_handler(request: Request, exc: APIError) -> JSONResponse:
    payload = api_error_payload(exc)
    payload["warnings"] = _warning_payloads(request, exc.warnings)
    return JSONResponse(status_code=exc.status_code, content=payload)


async def _validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    problems = []
    for error in exc.errors():
        location = ".".join(str(part) for part in error.get("loc", ()))
        problems.append("%s: %s" % (location or "request", error.get("msg", "invalid value")))
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": ERROR_CODE_INVALID_INPUT,
                "message": "the request could not be validated",
                "detail": "; ".join(problems) or None,
            },
            "warnings": _warning_payloads(request),
        },
    )


async def _http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "the request could not be completed"
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": code_for_status(exc.status_code),
                "message": message,
                "detail": None,
            },
            "warnings": _warning_payloads(request),
        },
    )


async def _unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled error serving %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": ERROR_CODE_INTERNAL,
                "message": "the API failed to complete this request",
                "detail": None,
            },
            "warnings": _warning_payloads(request),
        },
    )


def create_app(
    *,
    settings: Settings | None = None,
    wiring: EngineWiring | None = None,
    store: SessionStore | None = None,
) -> FastAPI:
    """Build the application. Every collaborator can be injected for tests."""
    resolved_settings = settings if settings is not None else load_settings()
    resolved_wiring = wiring if wiring is not None else build_engine_wiring(resolved_settings)
    resolved_store = store if store is not None else build_store(resolved_settings)

    application = FastAPI(
        title="TRACE Investigator API",
        version=__version__,
        description=DESCRIPTION,
    )
    application.state.settings = resolved_settings
    application.state.wiring = resolved_wiring
    application.state.store = resolved_store
    application.state.pipeline = SessionPipeline(
        settings=resolved_settings, wiring=resolved_wiring, store=resolved_store
    )
    application.state.api_warnings = api_warnings(resolved_settings, resolved_store)

    if resolved_settings.cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(resolved_settings.cors_origins),
            allow_credentials=True,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["*"],
        )

    application.add_exception_handler(APIError, _api_error_handler)
    application.add_exception_handler(RequestValidationError, _validation_error_handler)
    application.add_exception_handler(StarletteHTTPException, _http_error_handler)
    application.add_exception_handler(Exception, _unexpected_error_handler)

    application.include_router(health_routes.router, prefix=API_PREFIX)
    application.include_router(meta_routes.router, prefix=API_PREFIX)
    application.include_router(session_routes.router, prefix=API_PREFIX)
    application.include_router(evidence_routes.router, prefix=API_PREFIX)
    return application


#: The object an ASGI server serves: ``uvicorn app.main:app``.
app = create_app()

__all__ = ["API_PREFIX", "StageWarning", "app", "build_store", "create_app"]
