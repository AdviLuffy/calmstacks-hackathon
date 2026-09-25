"""TRACE P2 Bundle Loader.

Loads and validates Evidence Bundle JSON files against the frozen M0 schema.
Deterministic, no AI/model calls. Provides lookup helpers for bundle contents.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012


ROOT = Path(__file__).resolve().parents[2]
V1_DIR = ROOT / "trace" / "contracts" / "v1"
BUNDLE_SCHEMA_NAME = "evidence_bundle.schema.json"


class BundleLoadError(Exception):
    """Raised when bundle loading or validation fails."""

    def __init__(self, message: str, path: Optional[str] = None, validator: Optional[str] = None):
        self.path = path
        self.validator = validator
        super().__init__(message)


class BundleLoader:
    """Loads and provides access to a validated Evidence Bundle."""

    _registry: Optional[Registry] = None
    _validator: Optional[Draft202012Validator] = None

    def __init__(self, bundle_path: Path) -> None:
        self._bundle_path = Path(bundle_path)
        self._bundle: dict = {}
        self._load_and_validate()

    @classmethod
    def _get_registry(cls) -> Registry:
        if cls._registry is None:
            resources = []
            for path in sorted(V1_DIR.glob("*.schema.json")):
                document = json.loads(path.read_text(encoding="utf-8"))
                resources.append(
                    (document["$id"], Resource.from_contents(document, default_specification=DRAFT202012))
                )
            cls._registry = Registry().with_resources(resources)
        return cls._registry

    @classmethod
    def _get_validator(cls) -> Draft202012Validator:
        if cls._validator is None:
            schema_doc = json.loads((V1_DIR / BUNDLE_SCHEMA_NAME).read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(schema_doc)
            cls._validator = Draft202012Validator(schema_doc, registry=cls._get_registry())
        return cls._validator

    def _load_and_validate(self) -> None:
        try:
            raw = self._bundle_path.read_text(encoding="utf-8")
        except OSError as e:
            raise BundleLoadError(f"cannot read bundle: {e}") from e

        try:
            self._bundle = json.loads(raw)
        except json.JSONDecodeError as e:
            raise BundleLoadError(f"invalid JSON: {e.msg} at line {e.lineno}, column {e.colno}") from e

        validator = self._get_validator()
        errors = []
        for error in sorted(validator.iter_errors(self._bundle), key=lambda err: list(err.absolute_path)):
            errors.append({
                "path": "".join(f"/{part}" for part in error.absolute_path),
                "validator": error.validator,
                "message": error.message,
            })

        if errors:
            first = errors[0]
            raise BundleLoadError(
                f"schema validation failed: {first['message']} at {first['path']}",
                path=first["path"],
                validator=first["validator"],
            )

    @property
    def bundle(self) -> dict:
        return self._bundle

    @property
    def case(self) -> dict:
        return self._bundle.get("case", {})

    def _index_by_id(self, collection: str, key: str) -> dict[str, dict]:
        result = {}
        for item in self._bundle.get(collection, []):
            id_val = item.get(key)
            if isinstance(id_val, str):
                result[id_val] = item
        return result

    @property
    def artifacts(self) -> dict[str, dict]:
        return self._index_by_id("artifacts", "artifact_id")

    @property
    def fragments(self) -> dict[str, dict]:
        return self._index_by_id("fragments", "fragment_id")

    @property
    def reconstruction_groups(self) -> dict[str, dict]:
        return self._index_by_id("reconstruction_groups", "group_id")

    @property
    def timeline_events(self) -> dict[str, dict]:
        return self._index_by_id("timeline_events", "event_id")

    @property
    def known_file_matches(self) -> dict[str, dict]:
        return self._index_by_id("known_file_matches", "artifact_id")

    def get_artifact(self, artifact_id: str) -> Optional[dict]:
        return self.artifacts.get(artifact_id)

    def get_fragment(self, fragment_id: str) -> Optional[dict]:
        return self.fragments.get(fragment_id)

    def get_reconstruction_group(self, group_id: str) -> Optional[dict]:
        return self.reconstruction_groups.get(group_id)

    def get_timeline_event(self, event_id: str) -> Optional[dict]:
        return self.timeline_events.get(event_id)

    def get_known_file_match(self, artifact_id: str) -> Optional[dict]:
        return self.known_file_matches.get(artifact_id)