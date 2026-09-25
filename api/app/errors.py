"""P3 API error vocabulary and exception types.

Framework-free on purpose: routers, services and adapters all raise these, and
``app.main`` is the only place that knows how to turn one into an HTTP response.

A failure is never downgraded to silence. Every error carries a machine-readable ``code``,
and every error response also carries the warnings that were collected before it happened,
so a partially completed pipeline is still visible to the investigator.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

#: P3-owned error codes.
ERROR_CODE_INVALID_INPUT = "invalid_input"
ERROR_CODE_UNSUPPORTED_MEDIA = "unsupported_media_type"
ERROR_CODE_EVIDENCE_TOO_LARGE = "evidence_too_large"
ERROR_CODE_BUNDLE_NOT_JSON = "bundle_not_json"
ERROR_CODE_BUNDLE_CONTRACT_VIOLATION = "bundle_contract_violation"
ERROR_CODE_SESSION_NOT_FOUND = "session_not_found"
ERROR_CODE_SESSION_STORAGE = "session_storage_error"
ERROR_CODE_REPORT_UNAVAILABLE = "report_unavailable"
ERROR_CODE_CONTRACT_NOT_FROZEN = "contract_not_frozen"
ERROR_CODE_EVIDENCE_UNAVAILABLE = "evidence_unavailable"
ERROR_CODE_FRAGMENT_NOT_FOUND = "fragment_not_found"
ERROR_CODE_FRAGMENT_AMBIGUOUS = "fragment_ambiguous"
ERROR_CODE_ARTIFACT_NOT_FOUND = "artifact_not_found"
ERROR_CODE_NOT_FOUND = "not_found"
ERROR_CODE_METHOD_NOT_ALLOWED = "method_not_allowed"
ERROR_CODE_HTTP_ERROR = "http_error"
ERROR_CODE_INTERNAL = "internal_error"

#: Fallback codes for responses produced by the framework itself rather than by P3 code.
_HTTP_STATUS_CODES: Mapping[int, str] = {
    400: ERROR_CODE_INVALID_INPUT,
    401: ERROR_CODE_HTTP_ERROR,
    403: ERROR_CODE_HTTP_ERROR,
    404: ERROR_CODE_NOT_FOUND,
    405: ERROR_CODE_METHOD_NOT_ALLOWED,
    406: ERROR_CODE_HTTP_ERROR,
    409: ERROR_CODE_HTTP_ERROR,
    413: ERROR_CODE_EVIDENCE_TOO_LARGE,
    415: ERROR_CODE_UNSUPPORTED_MEDIA,
    422: ERROR_CODE_INVALID_INPUT,
    500: ERROR_CODE_INTERNAL,
    501: ERROR_CODE_CONTRACT_NOT_FROZEN,
    503: ERROR_CODE_HTTP_ERROR,
}


def code_for_status(status_code: int) -> str:
    """The P3 error code used for an HTTP status produced outside P3 code."""
    return _HTTP_STATUS_CODES.get(status_code, ERROR_CODE_HTTP_ERROR)


class APIError(Exception):
    """Base class for every error the API reports deliberately."""

    code: str = ERROR_CODE_INTERNAL
    status_code: int = 500

    def __init__(
        self,
        message: str,
        *,
        detail: str | None = None,
        warnings: Iterable[Any] = (),
        code: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        if not isinstance(message, str) or not message.strip():
            raise ValueError("an APIError requires a non-empty message")
        self.message = message
        self.detail = detail
        self.warnings = tuple(warnings)
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = status_code

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message


class InvalidInputError(APIError):
    """A request the API refuses: bad parameter, bad body, bad option value."""

    code = ERROR_CODE_INVALID_INPUT
    status_code = 400


class UnsupportedMediaError(APIError):
    """The upload is not a media type the API accepts."""

    code = ERROR_CODE_UNSUPPORTED_MEDIA
    status_code = 415


class EvidenceTooLargeError(APIError):
    """The upload exceeds the configured evidence size limit."""

    code = ERROR_CODE_EVIDENCE_TOO_LARGE
    status_code = 413


class BundleNotJSONError(APIError):
    """The bundle upload is not UTF-8 JSON text."""

    code = ERROR_CODE_BUNDLE_NOT_JSON
    status_code = 400


class BundleContractViolationError(APIError):
    """The bundle violates a frozen canonicalization rule (5, 14, or the root shape)."""

    code = ERROR_CODE_BUNDLE_CONTRACT_VIOLATION
    status_code = 422


class SessionNotFoundError(APIError):
    """No session with the requested identifier."""

    code = ERROR_CODE_SESSION_NOT_FOUND
    status_code = 404


class ReportUnavailableError(APIError):
    """The session has no report body, and the reason is stated rather than hidden."""

    code = ERROR_CODE_REPORT_UNAVAILABLE
    status_code = 409


class EvidenceUnavailableError(APIError):
    """The session exists but its submitted evidence is not held, and the reason says why."""

    code = ERROR_CODE_EVIDENCE_UNAVAILABLE
    status_code = 409


class FragmentNotFoundError(APIError):
    """Zero fragment records carry the requested fragment_id: a zero-match grounding failure."""

    code = ERROR_CODE_FRAGMENT_NOT_FOUND
    status_code = 404


class FragmentAmbiguousError(APIError):
    """Multiple fragment records carry the same fragment_id: a multiple-match grounding
    failure under the frozen exactly-one-record rule."""

    code = ERROR_CODE_FRAGMENT_AMBIGUOUS
    status_code = 409


class ArtifactNotFoundError(APIError):
    """The requested artifact array index is outside the supplied bundle's artifacts."""

    code = ERROR_CODE_ARTIFACT_NOT_FOUND
    status_code = 404


class SessionStorageError(APIError):
    """A stored session exists but cannot be read back. Reported, never treated as absent."""

    code = ERROR_CODE_SESSION_STORAGE
    status_code = 500


class ContractNotFrozenError(APIError):
    """An operation that a still-pending contract amendment would make available."""

    code = ERROR_CODE_CONTRACT_NOT_FROZEN
    status_code = 501
