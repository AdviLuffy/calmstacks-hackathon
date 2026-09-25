#!/usr/bin/env python
"""TRACE M0 contract checker.

Dev-only tool. NOT part of any runtime TRACE module. Verifies the frozen M0
contract:

  1. JSON Schema self-validation (Draft 2020-12)
  2. Positive fixture validation (zero errors)
  3. Negative fixture validation (declared violations; exact count for the
     version-routing fixture)
  4. EvidenceRef validation and resolution
  5. Fragment ID validation (frozen M0 fragment ID amendment)
  6. trace-cj/1.0 canonicalization golden vectors
  7. report_id / outputs_hash rules, including volatility invariance
  8. Contract semantic checks (SM-1 .. SM-16, where mechanically checkable)

Offline and deterministic: no network access, no clock dependence. The only
third-party imports are jsonschema + referencing, which are DEV-ONLY.

Run:  py scripts/check_contracts.py
Exit: 0 = all checks passed, 1 = at least one check failed.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
V1_DIR = ROOT / "trace" / "contracts" / "v1"
FIX_DIR = ROOT / "trace" / "contracts" / "fixtures"

BUNDLE_SCHEMA = "evidence_bundle.schema.json"
REPORT_SCHEMA = "intelligence_report.schema.json"
COMMON_SCHEMA = "common.schema.json"

CANON_PROFILE = "trace-cj/1.0"
REPORT_DOMAIN = "trace.intelligence_report/1.0"
DECIMAL_PLACES = Decimal("0.000001")


# --------------------------------------------------------------------------
# tiny check harness
# --------------------------------------------------------------------------

class Checks:
    def __init__(self) -> None:
        self.passed = 0
        self.failures: list[str] = []

    def check(self, name: str, condition: bool, detail: str = "") -> bool:
        if condition:
            self.passed += 1
            print(f"  PASS  {name}")
        else:
            self.failures.append(name if not detail else f"{name} :: {detail}")
            print(f"  FAIL  {name}" + (f" :: {detail}" if detail else ""))
        return bool(condition)

    def section(self, title: str) -> None:
        print(f"\n=== {title} ===")

    def report(self) -> int:
        print("\n" + "-" * 72)
        if self.failures:
            print(f"RESULT: FAILED  ({self.passed} passed, {len(self.failures)} failed)")
            for failure in self.failures:
                print(f"  - {failure}")
            return 1
        print(f"RESULT: ALL CHECKS PASSED  ({self.passed} checks)")
        return 0


# --------------------------------------------------------------------------
# trace-cj/1.0 canonicalization (the normative profile)
# --------------------------------------------------------------------------

def canonical_number(value: object) -> str:
    """Numeric form per trace-cj/1.0.

    Integers: base-10, no leading zeros, -0 normalised to 0.
    Non-integers: quantized to 6 decimal places, plain decimal notation, no
    exponent, trailing zeros stripped, no trailing decimal point.
    """
    if isinstance(value, bool):
        raise TypeError("booleans are not numbers in trace-cj/1.0")
    if isinstance(value, int):
        return str(value)
    number = Decimal(repr(float(value))).quantize(DECIMAL_PLACES, rounding=ROUND_HALF_UP)
    text = format(number.normalize(), "f")
    if text.startswith("-") and float(text) == 0.0:
        return "0"
    return text


def canonical_text(document: object, *, drop_reserved_root_keys: bool = True) -> str:
    """trace-cj/1.0 canonical JSON text."""
    return _canon(document, top=drop_reserved_root_keys)


def _canon(node: object, top: bool = False) -> str:
    if node is None:
        return "null"
    if node is True:
        return "true"
    if node is False:
        return "false"
    if isinstance(node, str):
        return json.dumps(node, ensure_ascii=False)
    if isinstance(node, (int, float)):
        return canonical_number(node)
    if isinstance(node, list):
        return "[" + ",".join(_canon(item) for item in node) + "]"
    if isinstance(node, dict):
        keys = sorted(key for key in node if not (top and key.startswith("_")))
        members = ",".join(
            f"{json.dumps(key, ensure_ascii=False)}:{_canon(node[key])}" for key in keys
        )
        return "{" + members + "}"
    raise TypeError(f"cannot canonicalize {type(node).__name__}")


def canonical_sha256(document: object, **kwargs: object) -> str:
    return hashlib.sha256(canonical_text(document, **kwargs).encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Golden vectors
# --------------------------------------------------------------------------
# The expected canonical TEXT is hand-verifiable and is the primary regression
# anchor. expected_sha256 is recorded by the reference implementation and is
# compared on every run thereafter.

GOLDEN_VECTORS: list[dict] = [
    {
        "name": "key-order-invariance",
        "input": {"b": 1, "a": 2},
        "expected_canonical": '{"a":2,"b":1}',
    },
    {
        "name": "nested-arrays-and-mixed-types",
        "input": {"z": [1, 2.5, True, None], "a": {"y": "x", "b": 0.82}},
        "expected_canonical": '{"a":{"b":0.82,"y":"x"},"z":[1,2.5,true,null]}',
    },
    {
        "name": "number-normalisation",
        "input": {"a": 2.0, "b": 0.820000, "c": 7.999, "d": -0.0, "e": 1e3},
        "expected_canonical": '{"a":2,"b":0.82,"c":7.999,"d":0,"e":1000}',
    },
    {
        "name": "string-escaping",
        "input": {"a": "caf\u00e9", "b": "line\nbreak", "c": 'quote"only', "d": "tab\there"},
        "expected_canonical": '{"a":"caf\u00e9","b":"line\\nbreak","c":"quote\\"only","d":"tab\\there"}',
    },
    {
        "name": "reserved-root-keys-excluded",
        "input": {"_comment": "ignored", "_expected_violations": [1], "a": 1},
        "expected_canonical": '{"a":1}',
    },
]


def golden_vector_checks(checks: Checks) -> None:
    checks.section("6. trace-cj/1.0 canonicalization golden vectors")
    for vector in GOLDEN_VECTORS:
        actual = canonical_text(vector["input"])
        checks.check(
            f"canonical text :: {vector['name']}",
            actual == vector["expected_canonical"],
            f"expected {vector['expected_canonical']!r} got {actual!r}",
        )
        digest = hashlib.sha256(actual.encode("utf-8")).hexdigest()
        expected_digest = vector.get("expected_sha256")
        if expected_digest:
            checks.check(
                f"sha256 :: {vector['name']}",
                digest == expected_digest,
                f"expected {expected_digest} got {digest}",
            )
        else:
            print(f"  NOTE  sha256 :: {vector['name']} = {digest}")

    forward = {"alpha": 1, "beta": {"x": 1, "y": 2}, "gamma": [3, 4]}
    reverse = {key: forward[key] for key in reversed(list(forward))}
    checks.check(
        "source key order does not change the digest",
        canonical_sha256(forward) == canonical_sha256(reverse),
    )


# --------------------------------------------------------------------------
# schema loading
# --------------------------------------------------------------------------

def load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def build_registry():
    from referencing import Registry, Resource
    from referencing.jsonschema import DRAFT202012

    resources = []
    for path in sorted(V1_DIR.glob("*.schema.json")):
        document = load_json(path)
        resources.append(
            (document["$id"], Resource.from_contents(document, default_specification=DRAFT202012))
        )
    return Registry().with_resources(resources)


def schema_validator(schema_name: str, registry):
    from jsonschema import Draft202012Validator

    document = load_json(V1_DIR / schema_name)
    Draft202012Validator.check_schema(document)
    return Draft202012Validator(document, registry=registry)


def json_pointer(path) -> str:
    return "".join(f"/{part}" for part in path)


def validation_errors(validator, document) -> list[dict]:
    found = []
    for error in sorted(validator.iter_errors(document), key=lambda err: list(err.absolute_path)):
        found.append(
            {
                "path": json_pointer(error.absolute_path),
                "validator": error.validator,
                "message": error.message,
            }
        )
    return found


# --------------------------------------------------------------------------
# EvidenceRef and identifier handling
# --------------------------------------------------------------------------

INSTANCE_ID_RE = re.compile(r"^[A-Z]{2,6}(-[A-Z0-9]{1,12})*-\d{2,10}$")
FRAGMENT_ID_RE = re.compile(r"^FRG-([0-9a-f]{16})-(\d{1,10})-(\d{1,10})$")
DERIVED_ID_RE = re.compile(r"^RPT-[0-9a-f]{12}$")
ACTION_ID_RE = re.compile(r"^ACT(-[A-Z0-9]{2,16}){1,4}$")
VOCAB_CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{2,48}$")
VOCAB_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,48}$")

EVIDENCE_REF_RE = re.compile(
    r"^(bundle|case|(artifacts|reconstruction_groups|timeline_events|known_file_matches)"
    r"\[[A-Z]{2,6}(-[A-Z0-9]{1,12})*-\d{2,10}\]"
    r"|fragments\[FRG-[0-9a-f]{16}-\d{1,10}-\d{1,10}\])"
    r"(\.[a-z][a-z0-9_]*(\[\d+\])?){0,2}$"
)

COLLECTION_KEY = {
    "artifacts": "artifact_id",
    "fragments": "fragment_id",
    "reconstruction_groups": "group_id",
    "timeline_events": "event_id",
    "known_file_matches": "artifact_id",
}

COLLECTION_ID_RE = {
    "artifacts": INSTANCE_ID_RE,
    "fragments": FRAGMENT_ID_RE,
    "reconstruction_groups": INSTANCE_ID_RE,
    "timeline_events": INSTANCE_ID_RE,
    "known_file_matches": INSTANCE_ID_RE,
}

SEGMENT_RE = re.compile(r"^([a-z][a-z0-9_]*)(?:\[(\d+)\])?$")


def fragment_id_parts(fragment_id: str):
    match = FRAGMENT_ID_RE.match(fragment_id)
    if not match:
        return None
    return match.group(1), int(match.group(2)), int(match.group(3))


def resolve_evidence_ref(bundle: dict, ref: str) -> tuple[bool, str]:
    """Resolve an EvidenceRef to exactly one record. Returns (ok, detail)."""
    if not EVIDENCE_REF_RE.match(ref):
        return False, "does not match the frozen EvidenceRef grammar"
    if ref == "bundle":
        return True, "bundle"
    if ref == "case" or ref.startswith("case."):
        node = bundle.get("case")
        if node is None:
            return False, "case block absent"
        return _walk_fields(node, [segment for segment in ref.split(".")[1:] if segment])
    match = re.match(r"^([a-z_]+)\[([^\]]+)\](.*)$", ref)
    if not match:
        return False, "malformed reference"
    collection, record_id, rest = match.group(1), match.group(2), match.group(3)
    key = COLLECTION_KEY.get(collection)
    if key is None:
        return False, f"unknown collection {collection}"
    if not COLLECTION_ID_RE[collection].match(record_id):
        return False, f"record id {record_id} does not match its identifier pattern"
    records = bundle.get(collection) or []
    matches = [record for record in records if record.get(key) == record_id]
    if not matches:
        return False, f"{collection}[{record_id}] not present"
    if len(matches) > 1:
        return False, f"{collection}[{record_id}] resolves to {len(matches)} records, not exactly one"
    return _walk_fields(matches[0], [segment for segment in rest.split(".") if segment])


def _walk_fields(node, segments: list[str]) -> tuple[bool, str]:
    for segment in segments:
        match = SEGMENT_RE.match(segment)
        if not match:
            return False, f"bad segment {segment!r}"
        name, index = match.group(1), match.group(2)
        if not isinstance(node, dict) or name not in node:
            return False, f"field {name!r} not present"
        node = node[name]
        if index is not None:
            if not isinstance(node, list):
                return False, f"{name!r} is not an array"
            position = int(index)
            if position >= len(node):
                return False, f"{name}[{position}] out of range"
            node = node[position]
    return True, "resolved"


def collect_bundle_evidence_refs(bundle: dict) -> list[tuple[str, str]]:
    found = []
    for index, event in enumerate(bundle.get("timeline_events") or []):
        ref = event.get("basis_path")
        if isinstance(ref, str):
            found.append((f"timeline_events/{index}/basis_path", ref))
    return found


# --------------------------------------------------------------------------
# semantic checks (SM-1 .. SM-16, mechanically checkable subset)
# --------------------------------------------------------------------------

CONFIDENCE_CEILING_BY_COMPLETENESS = {
    "complete": 1.0,
    "truncated": 0.85,
    "fragmented": 0.8,
    "partial_overlap": 0.7,
    "unknown": 0.3,
}
CONFIDENCE_FLOOR_BY_COMPLETENESS = {"complete": 0.6}


def _finding(code: str, path: str, detail: str) -> dict:
    return {"code": code, "path": path, "detail": detail}


def semantic_checks(bundle: dict) -> list[dict]:
    findings: list[dict] = []

    media_by_id: dict = {}
    for index, media in enumerate(bundle.get("acquisition", {}).get("media") or []):
        media_by_id[media.get("media_id")] = media
        if not isinstance(media.get("size_bytes"), int) or media.get("size_bytes", 0) < 1:
            findings.append(_finding("MEDIA_SIZE_INVALID", f"acquisition/media/{index}/size_bytes", "size_bytes must be a positive integer"))

    # SM-4: identifier uniqueness and pattern conformance per collection
    for collection, key in COLLECTION_KEY.items():
        pattern = COLLECTION_ID_RE[collection]
        seen: dict = {}
        for index, record in enumerate(bundle.get(collection) or []):
            record_id = record.get(key)
            if not isinstance(record_id, str):
                continue
            if record_id in seen:
                findings.append(_finding("DUPLICATE_ID", f"{collection}/{index}/{key}", f"{record_id} already declared at index {seen[record_id]}"))
            else:
                seen[record_id] = index
            if not pattern.match(record_id):
                findings.append(_finding("IDENTIFIER_PATTERN", f"{collection}/{index}/{key}", f"{record_id} does not match its declared pattern"))

    artifact_ids = {item.get("artifact_id") for item in (bundle.get("artifacts") or [])}
    fragment_ids = {item.get("fragment_id") for item in (bundle.get("fragments") or [])}

    # SM-5 / SM-7: byte ranges, media bounds, offset relativity
    for index, artifact in enumerate(bundle.get("artifacts") or []):
        _check_range(artifact.get("byte_range"), media_by_id, f"artifacts/{index}/byte_range", findings)
        media_id = artifact.get("media_id")
        if isinstance(media_id, str) and media_id not in media_by_id:
            findings.append(_finding("MEDIA_NOT_DECLARED", f"artifacts/{index}/media_id", f"{media_id} is not declared in acquisition.media"))
        parent = artifact.get("parent_artifact_id")
        if parent is not None and parent not in artifact_ids:
            findings.append(_finding("DANGLING_REFERENCE", f"artifacts/{index}/parent_artifact_id", f"{parent} is not declared in artifacts"))
        for link_index, link in enumerate(artifact.get("linked_fragment_ids") or []):
            if link not in fragment_ids:
                findings.append(_finding("DANGLING_REFERENCE", f"artifacts/{index}/linked_fragment_ids/{link_index}", f"{link} is not declared in fragments"))
        for gap_index, gap in enumerate(artifact.get("recovery", {}).get("byte_gaps") or []):
            _check_range(gap, media_by_id, f"artifacts/{index}/recovery/byte_gaps/{gap_index}", findings, relative=True)
        _check_recovery_confidence(artifact, index, findings)

    # Frozen M0 fragment ID amendment: the id must encode this record's range
    for index, fragment in enumerate(bundle.get("fragments") or []):
        _check_range(fragment.get("byte_range"), media_by_id, f"fragments/{index}/byte_range", findings)
        media_id = fragment.get("media_id")
        if isinstance(media_id, str) and media_id not in media_by_id:
            findings.append(_finding("MEDIA_NOT_DECLARED", f"fragments/{index}/media_id", f"{media_id} is not declared in acquisition.media"))
        fragment_id = fragment.get("fragment_id")
        parts = fragment_id_parts(fragment_id) if isinstance(fragment_id, str) else None
        if parts is None:
            findings.append(_finding("FRAGMENT_ID_UNPARSEABLE", f"fragments/{index}/fragment_id", f"{fragment_id!r} is not FRG-<lowercase_hex16>-<start>-<end>"))
            continue
        _, start, end = parts
        span = fragment.get("byte_range") or {}
        if span.get("start") != start or span.get("end") != end:
            findings.append(
                _finding(
                    "FRAGMENT_ID_RANGE_MISMATCH",
                    f"fragments/{index}/fragment_id",
                    f"id encodes [{start}, {end}) but byte_range is [{span.get('start')}, {span.get('end')})",
                )
            )

    # SM-6 / SM-10: cross references and group gap arithmetic
    for index, group in enumerate(bundle.get("reconstruction_groups") or []):
        missing: list[str] = []
        for member in list(group.get("member_fragment_ids") or []) + list(group.get("ordering") or []):
            if member not in fragment_ids and member not in missing:
                missing.append(member)
        for member in missing:
            findings.append(_finding("DANGLING_REFERENCE", f"reconstruction_groups/{index}/member_fragment_ids", f"{member} is not declared in fragments"))
        artifact_id = group.get("artifact_id")
        if artifact_id is not None and artifact_id not in artifact_ids:
            findings.append(_finding("DANGLING_REFERENCE", f"reconstruction_groups/{index}/artifact_id", f"{artifact_id} is not declared in artifacts"))
        declared_gaps = group.get("gaps_bytes")
        if isinstance(declared_gaps, int) and not missing:
            spans = []
            for member in group.get("member_fragment_ids") or []:
                for fragment in bundle.get("fragments") or []:
                    if fragment.get("fragment_id") == member:
                        span = fragment.get("byte_range") or {}
                        spans.append((span.get("start"), span.get("end")))
            spans.sort()
            computed = sum(max(0, spans[i + 1][0] - spans[i][1]) for i in range(len(spans) - 1))
            if computed != declared_gaps:
                findings.append(_finding("GROUP_GAP_MISMATCH", f"reconstruction_groups/{index}/gaps_bytes", f"declared {declared_gaps} computed {computed}"))

    # SM-1: every EvidenceRef in the bundle must resolve to exactly one record
    for path, ref in collect_bundle_evidence_refs(bundle):
        ok, detail = resolve_evidence_ref(bundle, ref)
        if not ok:
            findings.append(_finding("UNRESOLVED_EVIDENCE_REF", path, f"{ref} :: {detail}"))

    return findings


def _range_parts(span):
    if not isinstance(span, dict):
        return None
    start, end = span.get("start"), span.get("end")
    if not isinstance(start, int) or not isinstance(end, int):
        return None
    return start, end, span.get("size_bytes")


def _check_range(span, media_by_id: dict, path: str, findings: list[dict], relative: bool = False) -> None:
    parts = _range_parts(span)
    if parts is None:
        return
    start, end, size = parts
    if start < 0 or end <= start:
        findings.append(_finding("RANGE_INVALID", path, f"[{start}, {end}) is not a valid half-open interval"))
    if isinstance(size, int) and size != end - start:
        findings.append(_finding("SIZE_MISMATCH", path, f"size_bytes {size} != end - start {end - start}"))
    if relative:
        return
    media_id = span.get("media_id")
    if media_id is None:
        return
    media = media_by_id.get(media_id)
    if media is None:
        findings.append(_finding("MEDIA_NOT_DECLARED", path, f"media_id {media_id} is not declared"))
        return
    limit = media.get("size_bytes")
    if isinstance(limit, int) and end > limit:
        findings.append(_finding("RANGE_BEYOND_MEDIA", path, f"end {end} exceeds media size_bytes {limit}"))


def _check_recovery_confidence(artifact: dict, index: int, findings: list[dict]) -> None:
    """SM-8: completeness and recovery confidence must be mutually consistent."""
    recovery = artifact.get("recovery") or {}
    completeness = recovery.get("completeness")
    confidence = recovery.get("confidence")
    if not isinstance(confidence, (int, float)):
        return
    ceiling = CONFIDENCE_CEILING_BY_COMPLETENESS.get(completeness, 1.0)
    if recovery.get("method") == "none":
        ceiling = min(ceiling, 0.3)
    floor = CONFIDENCE_FLOOR_BY_COMPLETENESS.get(completeness)
    if confidence > ceiling:
        findings.append(
            _finding(
                "CONFIDENCE_INCOMPATIBLE_WITH_COMPLETENESS",
                f"artifacts/{index}/recovery/confidence",
                f"{confidence} exceeds the ceiling {ceiling} for completeness {completeness!r} (SM-8)",
            )
        )
    if floor is not None and confidence < floor:
        findings.append(
            _finding(
                "CONFIDENCE_INCOMPATIBLE_WITH_COMPLETENESS",
                f"artifacts/{index}/recovery/confidence",
                f"{confidence} is below the floor {floor} for completeness 'complete' (SM-8)",
            )
        )


# --------------------------------------------------------------------------
# x-volatile discovery: the outputs_hash exclusion set is derived from the
# schema, not hand-maintained.
# --------------------------------------------------------------------------

def collect_volatile_paths(schema: dict) -> list[str]:
    found: list[str] = []

    def resolve(node):
        hops = 0
        while (
            isinstance(node, dict)
            and isinstance(node.get("$ref"), str)
            and node["$ref"].startswith("#/")
            and hops < 32
        ):
            target = schema
            for part in node["$ref"][2:].split("/"):
                if not isinstance(target, dict) or part not in target:
                    return {}
                target = target[part]
            node = target
            hops += 1
        return node if isinstance(node, dict) else {}

    def walk(node, path: str, depth: int) -> None:
        if depth > 24:
            return
        node = resolve(node)
        if not node:
            return
        if node.get("x-volatile") is True and path:
            found.append(path)
        for name, child in (node.get("properties") or {}).items():
            walk(child, f"{path}.{name}" if path else name, depth + 1)
        if "items" in node:
            walk(node["items"], f"{path}[]" if path else "[]", depth + 1)
        for keyword in ("allOf", "anyOf", "oneOf"):
            for sub in node.get(keyword) or []:
                walk(sub, path, depth + 1)

    walk(schema, "", 0)
    unique: list[str] = []
    for path in found:
        if path not in unique:
            unique.append(path)
    return unique


def strip_volatile(document: dict, volatile_paths: list[str], *, drop_reserved_root_keys: bool = True) -> dict:
    """Remove x-volatile properties, audit.outputs_hash and reserved root keys."""
    import copy

    stripped = copy.deepcopy(document)
    if drop_reserved_root_keys:
        for key in [key for key in stripped if key.startswith("_")]:
            del stripped[key]
    audit = stripped.get("audit")
    if isinstance(audit, dict):
        audit.pop("outputs_hash", None)
    for path in volatile_paths:
        _remove_path(stripped, path)
    return stripped


def _remove_path(node, path: str) -> None:
    parts = path.split(".")
    if not parts:
        return
    for index, part in enumerate(parts[:-1]):
        if part.endswith("[]"):
            name = part[:-2]
            if not isinstance(node, dict) or name not in node:
                return
            entries = node[name]
            if not isinstance(entries, list):
                return
            remainder = ".".join(parts[index + 1 :])
            for entry in entries:
                _remove_path(entry, remainder)
            return
        if not isinstance(node, dict) or part not in node:
            return
        node = node[part]
    last = parts[-1]
    if isinstance(node, dict):
        node.pop(last, None)


MODULE_VERSION = "0.1.0"
CASE_ID = "CASE-ATLAS-01"


def derive_report_id(case_id: str, bundle_sha256: str, module_version: str) -> str:
    """report_id per the frozen rule: RPT- + hex(sha256(domain || 0x1F || case_id
    || 0x1F || bundle_sha256 || 0x1F || module_version))[:12]."""
    payload = "\x1f".join([REPORT_DOMAIN, case_id, bundle_sha256, module_version])
    return "RPT-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def compute_outputs_hash(report: dict, volatile_paths: list[str]) -> str:
    """outputs_hash: canonical hash of the report with audit.outputs_hash, every
    x-volatile property and every reserved root key removed."""
    return canonical_sha256(strip_volatile(report, volatile_paths))


def _claim(claim_id: str, text: str, status: str, produced_by: str, confidence: float,
           basis: str, refs: list[str], **extra: object) -> dict:
    claim = {
        "claim_id": claim_id,
        "text": text,
        "status": status,
        "produced_by": produced_by,
        "confidence": confidence,
        "confidence_basis": basis,
        "evidence_refs": refs,
        "validator_status": "passed",
    }
    claim.update(extra)
    return claim


def build_sample_report(bundle_sha256: str, module_version: str = MODULE_VERSION,
                        generated_utc: str = "2026-09-25T09:00:00Z",
                        runtime_ms: int = 128,
                        provider_latency_ms: int = 0) -> dict:
    """A complete, schema-valid trace.intelligence_report/1.0 used to verify the
    deterministic identity rules. Built in memory: M0 ships no report fixture."""
    fragment_a = "FRG-1a2b3c4d5e6f7081-1048576-1056768"
    fragment_b = "FRG-2b3c4d5e6f708192-1056768-1063936"

    claims = {
        "CLM-0001": _claim(
            "CLM-0001",
            "ART-0001 is consistent with a JPEG image container.",
            "COMPUTED",
            "deterministic",
            0.82,
            "min(evidence confidence 0.82, method reliability 0.95)",
            [
                "artifacts[ART-0001].signature.matched",
                "artifacts[ART-0001].recovery.confidence",
            ],
            assumptions=["a file signature identifies the container family"],
            cannot_conclude=["does not establish authenticity of the file"],
            alternatives=[{"text": "truncated JPEG container", "confidence": 0.18}],
        ),
        "CLM-0002": _claim(
            "CLM-0002",
            "The two fragments are consistent with a single contiguous source region.",
            "INFERRED",
            "ai",
            0.6,
            "interpretation ceiling applied; engine contiguity was not reported",
            ["reconstruction_groups[RGRP-01].byte_contiguity"],
            cannot_conclude=["does not establish common origin or possession"],
        ),
        "CLM-0003": _claim(
            "CLM-0003",
            "No integrity digest is available for ART-0007.",
            "MISSING",
            "deterministic",
            0.0,
            "absence of a hashes block in a bundle that declares hash_verification capability",
            ["artifacts[ART-0007]"],
            why_missing="artifacts[ART-0007] carries no hashes block",
            what_would_resolve="re-run hashing over the recovered byte range",
        ),
    }

    report = {
        "schema_version": "trace.intelligence_report/1.0",
        "report_id": derive_report_id(CASE_ID, bundle_sha256, module_version),
        "case_id": CASE_ID,
        "generated_utc": generated_utc,
        "source_bundle": {
            "schema_version": "trace.evidence_bundle/1.0",
            "bundle_id": "BND-REALISTIC-001",
            "bundle_sha256": bundle_sha256,
            "engine": "trace-core 0.4.1",
        },
        "mode": {
            "provider": "offline",
            "model": None,
            "ai_used": False,
            "degraded": True,
            "degraded_reasons": ["no_provider_configured"],
            "ai_calls": 0,
        },
        "doctrine": {
            "epistemic_states": ["OBSERVED", "COMPUTED", "INFERRED", "MISSING"],
            "confidence_ceilings": {"INFERRED": 0.7},
            "ai_role": "narrative_only",
            "policy": "ai_never_invents_evidence",
            "not_asserted": [
                "file authenticity or integrity beyond the supplied digests",
                "user or device attribution",
                "intent or intent-based causation",
            ],
        },
        "classifications": [
            {
                "artifact_id": "ART-0001",
                "label": "image/jpeg",
                "family": "image",
                "status": "COMPUTED",
                "confidence": 0.82,
                "score_components": [
                    {"factor": "signature_match", "weight": 0.5, "value": 1.0, "contribution": 0.5, "basis_ref": "artifacts[ART-0001].signature.matched"},
                    {"factor": "footer_match", "weight": 0.15, "value": 1.0, "contribution": 0.15, "basis_ref": "artifacts[ART-0001].signature.footer_matched"},
                    {"factor": "entropy_band", "weight": 0.1, "value": 1.0, "contribution": 0.1, "basis_ref": "artifacts[ART-0001].entropy.shannon_bits_per_byte"},
                    {"factor": "metadata_present", "weight": 0.07, "value": 1.0, "contribution": 0.07, "basis_note": "EXIF camera keys present"},
                ],
                "alternative_labels": [{"label": "unknown", "confidence": 0.18}],
                "abstained": False,
                "explanation_claim_id": "CLM-0001",
            },
            {
                "artifact_id": "ART-0007",
                "label": "unknown",
                "family": "unknown",
                "status": "MISSING",
                "confidence": 0.3,
                "score_components": [
                    {"factor": "signature_match", "weight": 0.5, "value": 0.0, "contribution": 0.0, "basis_ref": "artifacts[ART-0007].signature.matched"},
                    {"factor": "entropy_band", "weight": 0.1, "value": 0.0, "contribution": 0.0, "basis_note": "entropy 7.999 is uninformative between compressed and encrypted content"},
                ],
                "abstained": True,
                "abstention_reason": "no signature match and uninformative entropy; insufficient signal to classify",
            },
        ],
        "relationships": [
            {
                "relationship_id": "REL-0001",
                "type": "COMPUTED_ADJACENCY",
                "members": [fragment_a, fragment_b],
                "status": "COMPUTED",
                "strength": 0.4,
                "strength_components": [
                    {"factor": "byte_adjacency", "weight": 0.4, "value": 1.0, "contribution": 0.4, "basis_ref": "fragments[FRG-1a2b3c4d5e6f7081-1048576-1056768].byte_range"}
                ],
                "is_definitive": False,
                "cannot_conclude": ["does not establish that the fragments formed one original file"],
            }
        ],
        "priorities": [
            {
                "rank": 1,
                "artifact_id": "ART-0001",
                "priority": "high",
                "score": 0.62,
                "score_components": [
                    {"factor": "investigative_relevance", "weight": 0.25, "value": 1.0, "contribution": 0.25, "basis_ref": "case.investigation_profile.focus_categories"},
                    {"factor": "timeline_centrality", "weight": 0.15, "value": 1.0, "contribution": 0.15, "basis_ref": "timeline_events[EVT-0005].ts_utc"},
                    {"factor": "recoverability", "weight": 0.15, "value": 0.82, "contribution": 0.12, "basis_ref": "artifacts[ART-0001].recovery.confidence"},
                    {"factor": "integrity_verifiability", "weight": 0.1, "value": 1.0, "contribution": 0.1, "basis_ref": "artifacts[ART-0001].hashes.verified_against_source"},
                ],
                "forced_review": False,
                "recommended_action_ids": ["ACT-HASH-VERIFY", "ACT-INCLUDE-TIMELINE"],
                "rationale_claim_id": "CLM-0001",
                "evidence_refs": ["artifacts[ART-0001].recovery.confidence"],
            }
        "brief": {
            "headline": "Recovered partition image: one high-priority image artifact and one unclassifiable region.",
            "case_summary_claims": ["CLM-0003"],
            "key_findings": ["CLM-0001", "CLM-0002"],
            "evidence_gaps": [
                {
                    "gap_id": "GAP-001",
                    "statement": "No integrity digest is available for ART-0007.",
                    "status": "MISSING",
                    "why_missing": "the artifact record carries no hashes block",
                    "what_would_resolve": "re-run hashing over the recovered byte range",
                    "evidence_refs": ["artifacts[ART-0007]"],
                }
            ],
            "recommended_next_steps": [
                {
                    "action_id": "ACT-HASH-VERIFY",
                    "action": "Verify the digest of ART-0001 against the acquired media.",
                    "evidence_refs": ["artifacts[ART-0001].hashes"],
                }
            ],
            "open_questions": ["Was any encryption in use on the source volume?"],
            "brief_generated_by": "offline_template",
        },
        "explainability": {
            "reasoning_trace": [
                {
                    "step_id": "S1",
                    "op": "classify",
                    "deterministic": True,
                    "inputs": ["ART-0001"],
                    "method": "signature_table+entropy_bands",
                    "params": {"knowledge_version": "kb-1.0.0", "abstain_threshold": 0.45},
                    "outputs": ["CLM-0001"],
                    "rejected_alternatives": [{"label": "unknown", "score": 0.18}],
                }
            ],
            "claims_index": claims,
            "provenance_map": {
                "CLM-0001": ["artifacts[ART-0001].signature.matched", "artifacts[ART-0001].recovery.confidence"],
                "CLM-0002": ["reconstruction_groups[RGRP-01].byte_contiguity"],
                "CLM-0003": ["artifacts[ART-0007]"],
            },
            "validator": {
                "passed": True,
                "checks_run": 14,
                "checks_failed": [],
                "rejected_claims": [],
                "downgraded_claims": [
                    {"claim_id": "CLM-0002", "reason": "INFERRED ceiling applied", "from": 0.7, "to": 0.6}
                ],
            },
        },
        "uncertainty_summary": {
            "observed_count": 0,
            "computed_count": 1,
            "inferred_count": 1,
            "missing_count": 1,
            "mean_by_status": {"COMPUTED": 0.82, "INFERRED": 0.6},
            "low_confidence_artifact_ids": ["ART-0007"],
            "abstentions": [
                {"artifact_id": "ART-0007", "reason": "insufficient signal to classify"}
            ],
        },
        "validation": {
            "bundle_conforms": True,
            "violations": [
                {
                    "kind": "semantic",
                    "path": "reconstruction_groups/2/member_fragment_ids",
                    "rule": "SM-6",
                    "action_taken": "group retained as a candidate; the undeclared member was excluded from gap arithmetic",
                }
            ],
        },
        "limitations": {
            "engine_limitations": ["no AES volume decryption", "no memory analysis"],
            "module_limitations": ["classification is signature and entropy based; no content decoding"],
            "not_asserted": [
                "file authenticity or integrity beyond the supplied digests",
                "user or device attribution",
                "intent or intent-based causation",
            ],
        },
        "audit": {
            "module_version": module_version,
            "outputs_hash": "0" * 64,
            "runtime_ms": runtime_ms,
            "prompt_version": "p1.0.0",
            "knowledge_version": "kb-1.0.0",
            "provider_calls": [
                {
                    "task": "brief_render",
                    "provider": "offline",
                    "ok": True,
                    "latency_ms": provider_latency_ms,
                }
            ],
        },
    }
    return report


def _load_fixture(name: str) -> dict:
    return json.loads((FIX_DIR / name).read_text(encoding="utf-8"))


def _codes(findings: list[dict]) -> list[str]:
    return [finding["code"] for finding in findings]


def _walk_hex_literals(node, path: str = "") -> list[tuple[str, str, int]]:
    """Collect (path, value, required_length) for digest fields."""
    found: list[tuple[str, str, int]] = []
    expected = {"sha256": 64, "bytes_sha256": 64, "md5": 32}
    if isinstance(node, dict):
        for key, value in node.items():
            child_path = f"{path}.{key}" if path else key
            if key in expected and isinstance(value, str):
                found.append((child_path, value, expected[key]))
            else:
                found.extend(_walk_hex_literals(value, child_path))
    elif isinstance(node, list):
        for index, entry in enumerate(node):
            found.extend(_walk_hex_literals(entry, f"{path}[{index}]"))
    return found


def report_identity_checks(checks: Checks, report_schema: dict, bundle: dict,
                           report_validator) -> None:
    checks.section("7. report_id and outputs_hash rules")

    volatile = collect_volatile_paths(report_schema)
    expected_volatile = [
        "generated_utc",
        "audit.runtime_ms",
        "audit.provider_calls[].latency_ms",
    ]
    checks.check(
        "x-volatile discovery matches the frozen exclusion set",
        volatile == expected_volatile,
        f"expected {expected_volatile} got {volatile}",
    )

    bundle_sha = canonical_sha256(bundle)
    report = build_sample_report(bundle_sha)
    report["audit"]["outputs_hash"] = compute_outputs_hash(report, volatile)

    errors = validation_errors(report_validator, report)
    checks.check("sample report is schema-valid", not errors, f"{len(errors)} error(s): {errors[:2]}")

    recomputed = compute_outputs_hash(report, volatile)
    checks.check("outputs_hash is idempotent", recomputed == report["audit"]["outputs_hash"])

    # Volatile execution metadata must not change the digest.
    volatile_variants = {
        "generated_utc": build_sample_report(bundle_sha, generated_utc="2026-09-25T23:59:59Z"),
        "runtime_ms": build_sample_report(bundle_sha, runtime_ms=999999),
        "provider_latency_ms": build_sample_report(bundle_sha, provider_latency_ms=4242),
    }
    for label, variant in volatile_variants.items():
        variant["audit"]["outputs_hash"] = compute_outputs_hash(variant, volatile)
        checks.check(
            f"{label} is excluded from outputs_hash",
            compute_outputs_hash(variant, volatile) == recomputed,
        )
        checks.check(
            f"{label} keeps report_id stable",
            variant["report_id"] == report["report_id"],
        )

    # Content changes must change the digest.
    changed = build_sample_report(bundle_sha)
    changed["explainability"]["claims_index"]["CLM-0001"]["text"] = "A different narrative sentence."
    changed["audit"]["outputs_hash"] = compute_outputs_hash(changed, volatile)
    checks.check(
        "narrative change alters outputs_hash",
        compute_outputs_hash(changed, volatile) != recomputed,
    )
    checks.check("narrative change keeps report_id stable", changed["report_id"] == report["report_id"])

    other_version = build_sample_report(bundle_sha, module_version="0.2.0")
    checks.check(
        "module_version change alters report_id",
        other_version["report_id"] != report["report_id"],
    )
    other_bundle = build_sample_report(canonical_sha256({"different": True}))
    checks.check(
        "bundle_sha256 change alters report_id",
        other_bundle["report_id"] != report["report_id"],
    )
    checks.check("report_id matches DerivedId", bool(DERIVED_ID_RE.match(report["report_id"])), report["report_id"])

    expected_report_id = derive_report_id(CASE_ID, bundle_sha, MODULE_VERSION)
    checks.check("report_id matches the frozen formula", report["report_id"] == expected_report_id)

    # The doctrine must be enforced by the SCHEMA, not by convention.
    mutated = build_sample_report(bundle_sha)
    mutated["explainability"]["claims_index"]["CLM-0001"]["produced_by"] = "ai"
    mutated["audit"]["outputs_hash"] = compute_outputs_hash(mutated, volatile)
    checks.check("schema rejects: AI claim marked COMPUTED", bool(validation_errors(report_validator, mutated)))

    mutated = build_sample_report(bundle_sha)
    mutated["explainability"]["claims_index"]["CLM-0001"]["produced_by"] = "deterministic"
    mutated["explainability"]["claims_index"]["CLM-0001"]["status"] = "INFERRED"
    mutated["explainability"]["claims_index"]["CLM-0001"]["confidence"] = 0.9
    mutated["audit"]["outputs_hash"] = compute_outputs_hash(mutated, volatile)
    checks.check("schema rejects: INFERRED claim above the 0.70 ceiling", bool(validation_errors(report_validator, mutated)))

    mutated = build_sample_report(bundle_sha)
    del mutated["explainability"]["claims_index"]["CLM-0003"]["why_missing"]
    mutated["audit"]["outputs_hash"] = compute_outputs_hash(mutated, volatile)
    checks.check("schema rejects: MISSING without why_missing", bool(validation_errors(report_validator, mutated)))

    mutated = build_sample_report(bundle_sha)
    mutated["explainability"]["claims_index"]["CLM-0001"]["evidence_refs"] = []
    mutated["audit"]["outputs_hash"] = compute_outputs_hash(mutated, volatile)
    checks.check("schema rejects: claim without evidence_refs", bool(validation_errors(report_validator, mutated)))


# __CHUNK_SENTINEL__







