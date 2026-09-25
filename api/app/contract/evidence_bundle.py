"""The frozen Evidence Bundle root contract: ``trace.evidence_bundle/1.0``.

P1/P2 froze the authoritative root contract for the bundle this API ingests, so P3 now
validates exactly the root of the document and nothing deeper:

* the eight required root fields must be present with their frozen JSON types, and
  ``schema_version`` must carry the exact value ``trace.evidence_bundle/1.0`` (it and
  ``bundle_id`` are permanently required within the 1.x contract);
* the six optional root fields are checked only when present;
* any other root field is refused, because the freeze authorizes no additional root
  fields; no field is invented, renamed or defaulted;
* the INTERIORS of ``case``, ``acquisition``, ``capabilities``, ``engine``, ``extensions``
  and every array element remain P1/P2-owned and opaque: this module never reads them.

A violation is reported as a list of problems and becomes a ``bundle_contract_violation``
(422) at the ingestion boundary. Nothing here ever rewrites the submitted document.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Final

#: The frozen schema version, permanently required within the 1.x contract.
EVIDENCE_BUNDLE_SCHEMA_VERSION: Final[str] = "trace.evidence_bundle/1.0"

#: Frozen root field name -> frozen JSON type, for the required fields.
REQUIRED_ROOT_FIELDS: Final[dict[str, str]] = {
    "schema_version": "string",
    "bundle_id": "string",
    "generated_utc": "string",
    "case": "object",
    "acquisition": "object",
    "capabilities": "object",
    "artifacts": "array",
    "engine": "object",
}

#: Frozen root field name -> frozen JSON type, for the optional fields.
OPTIONAL_ROOT_FIELDS: Final[dict[str, str]] = {
    "fragments": "array",
    "reconstruction_groups": "array",
    "timeline_events": "array",
    "known_file_matches": "array",
    "warnings": "array",
    "extensions": "object",
}

#: Every root field the freeze authorizes, required first in contract order.
FROZEN_ROOT_FIELDS: Final[tuple[str, ...]] = tuple(REQUIRED_ROOT_FIELDS) + tuple(
    OPTIONAL_ROOT_FIELDS
)

_JSON_TYPE_NAMES: Final[dict[str, type | tuple[type, ...]]] = {
    "string": str,
    "object": Mapping,
    "array": (list, tuple),
}


def _has_json_type(value: Any, type_name: str) -> bool:
    expected = _JSON_TYPE_NAMES[type_name]
    if isinstance(expected, tuple):
        return isinstance(value, expected)
    # A boolean is not a JSON string, even though bool subclasses int, which str rejects.
    return isinstance(value, expected) and not (type_name == "string" and isinstance(value, bool))


def validate_evidence_bundle_root(bundle: Any) -> tuple[str, ...]:
    """Return every frozen-root-contract problem with ``bundle``; an empty tuple is valid.

    The check is strict and exhaustive: required fields, the exact ``schema_version``
    value, optional-field types when present, and refusal of any unauthorized root field.
    The returned problems are stable, human-readable and never speculative: they describe
    only the frozen contract.
    """
    if not isinstance(bundle, Mapping):
        return (
            "the bundle root must be a JSON object under trace.evidence_bundle/1.0, got %s"
            % type(bundle).__name__,
        )

    problems: list[str] = []

    unknown = [
        key
        for key in bundle
        if key not in FROZEN_ROOT_FIELDS and not str(key).startswith("_")
    ]
    for key in sorted(unknown, key=str):
        problems.append(
            "root field %r is not authorized by the frozen trace.evidence_bundle/1.0 "
            "root contract" % (key,)
        )

    for name, type_name in REQUIRED_ROOT_FIELDS.items():
        if name not in bundle:
            problems.append("required root field %r is missing" % name)
            continue
        value = bundle[name]
        if type_name == "string":
            if not isinstance(value, str):
                problems.append(
                    "root field %r must be a string, got %s" % (name, type(value).__name__)
                )
        elif not _has_json_type(value, type_name):
            problems.append(
                "root field %r must be a JSON %s, got %s"
                % (name, type_name, type(value).__name__)
            )

    schema_version = bundle.get("schema_version")
    if isinstance(schema_version, str) and schema_version != EVIDENCE_BUNDLE_SCHEMA_VERSION:
        problems.append(
            "schema_version must be %r, got %r"
            % (EVIDENCE_BUNDLE_SCHEMA_VERSION, schema_version)
        )

    for name, type_name in OPTIONAL_ROOT_FIELDS.items():
        if name not in bundle:
            continue
        if not _has_json_type(bundle[name], type_name):
            problems.append(
                "root field %r must be a JSON %s, got %s"
                % (name, type_name, type(bundle[name]).__name__)
            )

    return tuple(problems)


def root_field_names(bundle: Mapping[str, Any]) -> tuple[str, ...]:
    """The root fields actually present, in frozen contract order (never invented)."""
    return tuple(name for name in FROZEN_ROOT_FIELDS if name in bundle)


def array_field_counts(bundle: Mapping[str, Any]) -> dict[str, int | None]:
    """Counts for the five frozen array fields; ``None`` marks an absent optional array.

    Absence and emptiness are different facts and both are preserved: an absent optional
    field is ``None``, a present empty array is ``0``.
    """
    counts: dict[str, int | None] = {}
    for name in ("artifacts", "fragments", "reconstruction_groups", "timeline_events", "known_file_matches"):
        value = bundle.get(name)
        counts[name] = len(value) if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else None
    return counts
