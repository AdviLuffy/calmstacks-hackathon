"""trace-cj/1.0 canonicalization, bundle hashing and report identity.

Implements the canonicalization profile exactly as supplied in the M0 material. A
generic JSON canonicalization library is deliberately NOT used: the supplied numeric
rules (plain-decimal only, 6-decimal rounding, trailing-zero removal, negative-zero
normalisation, root "_" key exclusion) are specific, so they are implemented
explicitly and auditable against the contract text.

Rules as supplied:
 1  UTF-8 encoding.
 2  No UTF-8 BOM.
 3  JSON separators are "," and ":" with no insignificant whitespace.
 4  Object keys are sorted by Unicode codepoint.
 5  Duplicate object keys are a contract violation.
 6  Strings use minimal JSON escaping.
 7  Non-ASCII characters remain literal UTF-8.
 8  Integers use base-10 representation with no leading zeros.
 9  -0 becomes 0.
10  Non-integers are rounded using round(v, 6).
11  Non-integers use plain decimal notation, never exponent notation.
12  Trailing zeros are stripped.
13  No number may contain more than 6 decimal places.
14  NaN, Infinity, and -0 are forbidden.
15  Arrays preserve their original order.
16  Root keys beginning with "_" are excluded from hashing and interpretation.

Known, recorded implementation points (see app.contract.registry):
* Rule 10 names the host's ``round`` function. This module uses Python's builtin,
  which is round-half-to-even over binary floats. Pinning it exactly matters for
  cross-language reproducibility and is recorded as an open ambiguity.
* Rules 11 and 12 together mean ``1.0`` canonicalizes to ``1``, which is token
  identical to an integer. That is the literal consequence of the supplied rules; it
  is recorded as an open ambiguity rather than silently "fixed".
* Rules 9 and 14 both address negative zero, so this module normalises ``-0.0`` to
  ``0`` (satisfying rule 9) which also removes the forbidden form (rule 14).
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any, Final

#: Canonicalization profile identifier, verbatim from the M0 material.
CANONICALIZATION_PROFILE: Final[str] = "trace-cj/1.0"

#: Report schema identifier used as the report_id digest prefix.
REPORT_SCHEMA_ID: Final[str] = "trace.intelligence_report/1.0"

#: The 0x1F unit separator between report_id digest inputs.
DERIVED_ID_SEPARATOR: Final[bytes] = b"\x1f"

DERIVED_REPORT_ID_PREFIX: Final[str] = "RPT-"

#: Frozen pattern for derived report identifiers.
DERIVED_REPORT_ID_PATTERN: Final[str] = r"^RPT-[0-9a-f]{12}$"

DERIVED_REPORT_ID_RE: Final[Any] = re.compile(DERIVED_REPORT_ID_PATTERN)

#: digest[0:12] => 12 lowercase hex characters (48 bits).
DERIVED_REPORT_ID_HEX_LENGTH: Final[int] = 12

MAX_DECIMAL_PLACES: Final[int] = 6

#: Volatile paths excluded from outputs_hash, exactly as listed by the M0 material.
VOLATILE_OUTPUT_PATHS: Final[tuple[str, ...]] = (
    "generated_utc",
    "audit.runtime_ms",
    "audit.provider_calls[].latency_ms",
    "audit.outputs_hash",
)


class CanonicalizationError(ValueError):
    """Raised when a value cannot be canonicalized under trace-cj/1.0."""


class DuplicateKeyError(CanonicalizationError):
    """Rule 5: duplicate object keys are a contract violation."""


_STRING_ESCAPES: Final[dict[str, str]] = {
    chr(34): chr(92) + chr(34),
    chr(92): chr(92) + chr(92),
    "\b": "\\b",
    "\f": "\\f",
    "\n": "\\n",
    "\r": "\\r",
    "\t": "\\t",
}


def _encode_string(value: str) -> str:
    """Rules 6 and 7: minimal escaping, non-ASCII kept literal UTF-8."""
    out = [chr(34)]
    for char in value:
        escape = _STRING_ESCAPES.get(char)
        if escape is not None:
            out.append(escape)
        elif char < "\u0020":
            # RFC 8259 requires U+0000..U+001F to be escaped, so "minimal" means the
            # shortest legal form, which the two-character escapes above already are.
            out.append("\\u%04x" % ord(char))
        else:
            out.append(char)
    out.append(chr(34))
    return "".join(out)


def _encode_integer(value: int) -> str:
    """Rule 8: base-10, no leading zeros. Python's repr already satisfies this."""
    return str(value)


def _encode_float(value: float) -> str:
    """Rules 9 to 14 for non-integers."""
    if math.isnan(value) or math.isinf(value):
        raise CanonicalizationError("rule 14: NaN and Infinity are forbidden")
    rounded = round(value, MAX_DECIMAL_PLACES)  # rule 10
    if rounded == 0:
        return "0"  # rules 9 and 14: -0.0 normalises to 0
    # Rule 11: plain decimal notation only. Fixed-point formatting never emits exponent
    # notation, unlike repr() and json.dumps(), which do for small magnitudes.
    text = format(rounded, ".%df" % MAX_DECIMAL_PLACES)
    # Rule 12: trailing zeros stripped. Rule 13 is satisfied by the fixed precision.
    text = text.rstrip("0").rstrip(".")
    return text or "0"


def _write(value: Any, parts: list[str], *, is_root: bool) -> None:
    if value is None:
        parts.append("null")
        return
    if value is True:
        parts.append("true")
        return
    if value is False:
        parts.append("false")
        return
    if isinstance(value, str):
        parts.append(_encode_string(value))
        return
    if isinstance(value, int):  # bool already handled above
        parts.append(_encode_integer(value))
        return
    if isinstance(value, float):
        parts.append(_encode_float(value))
        return
    if isinstance(value, (list, tuple)):
        parts.append("[")
        for index, item in enumerate(value):  # rule 15: order preserved
            if index:
                parts.append(",")
            _write(item, parts, is_root=False)
        parts.append("]")
        return
    if isinstance(value, dict):
        items: list[tuple[str, Any]] = []
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalizationError(
                    "object keys must be strings, got %s" % type(key).__name__
                )
            if is_root and key.startswith("_"):
                continue  # rule 16
            items.append((key, item))
        items.sort(key=lambda pair: pair[0])  # rule 4: Unicode codepoint order
        parts.append("{")
        for index, (key, item) in enumerate(items):
            if index:
                parts.append(",")  # rule 3
            parts.append(_encode_string(key))
            parts.append(":")
            _write(item, parts, is_root=False)
        parts.append("}")
        return
    raise CanonicalizationError(
        "unsupported type %s; trace-cj/1.0 defines only the JSON data model"
        % type(value).__name__
    )


def canonicalize(value: Any) -> bytes:
    """Return the trace-cj/1.0 canonical UTF-8 byte form of ``value``."""
    parts: list[str] = []
    _write(value, parts, is_root=True)
    try:
        return "".join(parts).encode("utf-8")  # rules 1 and 2 (no BOM)
    except UnicodeEncodeError as exc:
        raise CanonicalizationError(
            "rule 1: value is not encodable as UTF-8 (lone surrogate or undecodable "
            "bytes); the M0 material does not define a policy for this case"
        ) from exc


def _reject_constant(token: str) -> Any:
    raise CanonicalizationError("rule 14: %s is forbidden in canonical JSON" % token)


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKeyError("rule 5: duplicate object key %r" % (key,))
        result[key] = value
    return result


def parse_json_strict(text: str | bytes) -> Any:
    """Parse JSON text enforcing rules 5 and 14 where they are checkable.

    Rule 5 cannot be enforced on an already-parsed dict, so this function is the
    enforcement point for JSON text originating from P1.
    """
    if isinstance(text, bytes):
        text = text.decode("utf-8")
    return json.loads(text, object_pairs_hook=_unique_pairs, parse_constant=_reject_constant)


def bundle_sha256(bundle: Any) -> str:
    """A18: SHA-256 over the trace-cj/1.0 canonical form of the evidence bundle."""
    return hashlib.sha256(canonicalize(bundle)).hexdigest()


def strip_volatile(report: Any) -> Any:
    """Return a deep copy of ``report`` with the M0 volatile paths removed."""
    result = copy.deepcopy(report)
    if not isinstance(result, dict):
        return result
    result.pop("generated_utc", None)
    audit = result.get("audit")
    if isinstance(audit, dict):
        audit.pop("runtime_ms", None)
        audit.pop("outputs_hash", None)
        provider_calls = audit.get("provider_calls")
        if isinstance(provider_calls, list):
            for call in provider_calls:
                if isinstance(call, dict):
                    call.pop("latency_ms", None)
    return result


def outputs_hash(report: Any) -> str:
    """SHA-256 over the report minus volatile fields minus root "_" keys."""
    return hashlib.sha256(canonicalize(strip_volatile(report))).hexdigest()


def report_id(case_id: str, bundle_sha256_hex: str, module_version: str) -> str:
    """The frozen report_id derivation. The algorithm must not be changed."""
    for name, value in (
        ("case_id", case_id),
        ("bundle_sha256", bundle_sha256_hex),
        ("module_version", module_version),
    ):
        if not isinstance(value, str) or not value:
            raise ValueError("report_id requires a non-empty %s" % name)
    digest = hashlib.sha256(
        REPORT_SCHEMA_ID.encode("utf-8")
        + DERIVED_ID_SEPARATOR
        + case_id.encode("utf-8")
        + DERIVED_ID_SEPARATOR
        + bundle_sha256_hex.encode("utf-8")
        + DERIVED_ID_SEPARATOR
        + module_version.encode("utf-8")
    ).hexdigest()
    return DERIVED_REPORT_ID_PREFIX + digest[:DERIVED_REPORT_ID_HEX_LENGTH]


@dataclass(frozen=True)
class ReproducibilityTuple:
    """The reproducibility tuple named by the M0 material."""

    bundle_sha256: str
    module_version: str
    prompt_version: str | None = None
    knowledge_version: str | None = None
    provider: str | None = None
    model: str | None = None