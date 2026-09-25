"""TRACE P2 EvidenceRef Resolver.

Deterministic resolution of EvidenceRef strings against a validated Evidence Bundle.
Implements the frozen M0 EvidenceRef grammar exactly.
"""

from __future__ import annotations

import re
from typing import Any, Optional

from trace.intel.bundle_loader import BundleLoader


# Frozen M0 EvidenceRef grammar (from common.schema.json)
EVIDENCE_REF_RE = re.compile(
    r"^(bundle|case|(artifacts|reconstruction_groups|timeline_events|known_file_matches)"
    r"\[[A-Z]{2,6}(-[A-Z0-9]{1,12})*-\d{2,10}\]"
    r"|fragments\[FRG-[0-9a-f]{16}-\d{1,10}-\d{1,10}\])"
    r"(\.[a-z][a-z0-9_]*(\[\d+\])?){0,2}$"
)

FRAGMENT_ID_RE = re.compile(r"^FRG-([0-9a-f]{16})-(\d{1,10})-(\d{1,10})$")
INSTANCE_ID_RE = re.compile(r"^[A-Z]{2,6}(-[A-Z0-9]{1,12})*-\d{2,10}$")

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


class EvidenceRefError(Exception):
    """Raised when EvidenceRef resolution fails."""

    def __init__(self, message: str, ref: Optional[str] = None):
        self.ref = ref
        super().__init__(message)


class EvidenceRefResolver:
    """Resolves EvidenceRef strings to exact bundle locations."""

    def __init__(self, loader: BundleLoader) -> None:
        self._loader = loader
        self._bundle = loader.bundle

    def resolve(self, ref: str) -> Any:
        """Resolve an EvidenceRef to its value. Raises EvidenceRefError on failure."""
        ok, detail, value = self._resolve_internal(ref)
        if not ok:
            raise EvidenceRefError(detail, ref=ref)
        return value

    def try_resolve(self, ref: str) -> tuple[bool, str, Any]:
        """Try to resolve; returns (ok, detail, value)."""
        return self._resolve_internal(ref)

    def _resolve_internal(self, ref: str) -> tuple[bool, str, Any]:
        if not EVIDENCE_REF_RE.match(ref):
            return False, f"does not match frozen EvidenceRef grammar: {ref}", None

        if ref == "bundle":
            return True, "bundle", self._bundle

        if ref == "case" or ref.startswith("case."):
            node = self._bundle.get("case")
            if node is None:
                return False, "case block absent", None
            segments = [s for s in ref.split(".")[1:] if s]
            return self._walk_fields(node, segments)

        # Collection reference: artifacts[ID], fragments[FRG-...], etc.
        match = re.match(r"^([a-z_]+)\[([^\]]+)\](.*)$", ref)
        if not match:
            return False, f"malformed reference: {ref}", None

        collection, record_id, rest = match.group(1), match.group(2), match.group(3)

        key = COLLECTION_KEY.get(collection)
        if key is None:
            return False, f"unknown collection: {collection}", None

        id_re = COLLECTION_ID_RE.get(collection)
        if id_re is None or not id_re.match(record_id):
            return False, f"record id {record_id} does not match identifier pattern for {collection}", None

        records = self._bundle.get(collection) or []
        matches = [r for r in records if r.get(key) == record_id]

        if not matches:
            return False, f"{collection}[{record_id}] not present", None
        if len(matches) > 1:
            return False, f"{collection}[{record_id}] resolves to {len(matches)} records, not exactly one", None

        node = matches[0]
        if not rest:
            return True, "resolved", node

        segments = [s for s in rest.split(".") if s]
        return self._walk_fields(node, segments)

    def _walk_fields(self, node: Any, segments: list[str]) -> tuple[bool, str, Any]:
        for segment in segments:
            match = SEGMENT_RE.match(segment)
            if not match:
                return False, f"bad segment: {segment!r}", None
            name, index = match.group(1), match.group(2)
            if not isinstance(node, dict) or name not in node:
                return False, f"field {name!r} not present", None
            node = node[name]
            if index is not None:
                if not isinstance(node, list):
                    return False, f"{name!r} is not an array", None
                position = int(index)
                if position >= len(node):
                    return False, f"{name}[{position}] out of range", None
                node = node[position]
        return True, "resolved", node

    @staticmethod
    def validate_fragment_id(fragment_id: str) -> bool:
        """Validate FragmentInstanceId format: FRG-<16 lowercase hex>-<start>-<end>."""
        return FRAGMENT_ID_RE.match(fragment_id) is not None

    @staticmethod
    def validate_instance_id(instance_id: str) -> bool:
        """Validate InstanceId format."""
        return INSTANCE_ID_RE.match(instance_id) is not None

    @staticmethod
    def parse_fragment_id(fragment_id: str) -> Optional[tuple[str, int, int]]:
        """Parse FRG-<hex16>-<start>-<end> into (hex, start, end)."""
        match = FRAGMENT_ID_RE.match(fragment_id)
        if not match:
            return None
        return match.group(1), int(match.group(2)), int(match.group(3))