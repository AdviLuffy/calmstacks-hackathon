import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, ValidationError
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from trace_evidence.bundle import (
    BUNDLE_CANONICALIZATION,
    build_bundle,
    bundle_to_json,
    new_run_id,
)
from trace_evidence.scanning import scan_media

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = REPO_ROOT / "shared" / "schemas"
FIXED_RUN_ID = "0" * 32
FROZEN_ROOT_KEYS = {"x-canonicalization", "engine", "media", "fragments", "warnings"}


def _load_schema(filename: str) -> dict:
    return json.loads((SCHEMA_DIR / filename).read_text(encoding="utf-8"))


@pytest.fixture()
def fragment_schema() -> dict:
    return _load_schema("fragment.schema.json")


@pytest.fixture()
def bundle_schema() -> dict:
    return _load_schema("evidence_bundle.schema.json")


@pytest.fixture()
def registry(fragment_schema, bundle_schema) -> Registry:
    return Registry().with_resources(
        [
            (
                fragment_schema["$id"],
                Resource.from_contents(fragment_schema, default_specification=DRAFT202012),
            ),
            (
                bundle_schema["$id"],
                Resource.from_contents(bundle_schema, default_specification=DRAFT202012),
            ),
        ]
    )


@pytest.fixture()
def validator(bundle_schema, registry) -> Draft202012Validator:
    return Draft202012Validator(bundle_schema, registry=registry)


@pytest.fixture()
def bundle(dataset_dir, default_seed) -> dict:
    scan = scan_media(dataset_dir / "evidence" / f"blob_{default_seed}.bin")
    return build_bundle(scan, run_id=FIXED_RUN_ID)


def test_bundle_validates_against_the_frozen_schema(bundle, validator):
    validator.validate(bundle)


def test_every_fragment_validates_against_the_fragment_schema(
    bundle, fragment_schema, registry
):
    fragment_validator = Draft202012Validator(fragment_schema, registry=registry)

    assert len(bundle["fragments"]) == 8
    for record in bundle["fragments"]:
        fragment_validator.validate(record)


def test_bundle_uses_only_frozen_root_keys(bundle, bundle_schema):
    assert set(bundle) == FROZEN_ROOT_KEYS
    assert set(bundle) == set(bundle_schema["required"])
    assert bundle["x-canonicalization"] == BUNDLE_CANONICALIZATION
    assert bundle["engine"]["run_id"] == FIXED_RUN_ID


def test_fragment_schema_declares_only_frozen_fields(fragment_schema):
    assert set(fragment_schema["properties"]) == {
        "fragment_id",
        "byte_range",
        "size_bytes",
        "bytes_sha256",
        "warnings",
    }
    assert set(fragment_schema["required"]) == set(fragment_schema["properties"])
    assert "label" not in fragment_schema["properties"]
    assert fragment_schema["x-canonicalization"] == BUNDLE_CANONICALIZATION


def test_bundle_contains_no_oracle_or_ground_truth_data(bundle):
    payload = json.dumps(bundle, sort_keys=True)

    for oracle_token in (
        "permutation",
        "original_index",
        "source_offset",
        "groundtruth",
        "ground_truth",
        "object_number",
        "synthetic.pdf",
        "application/pdf",
    ):
        assert oracle_token not in payload


def test_media_size_is_the_media_size_not_a_fragment_size(bundle):
    assert bundle["media"]["size_bytes"] == 2048

    fragment_sizes = [record["size_bytes"] for record in bundle["fragments"]]
    assert all(size == 256 for size in fragment_sizes)
    assert sum(fragment_sizes) == bundle["media"]["size_bytes"]


def test_missing_required_root_key_fails(bundle, validator):
    broken = {key: value for key, value in bundle.items() if key != "warnings"}

    with pytest.raises(ValidationError):
        validator.validate(broken)


def test_wrong_canonicalization_value_fails(bundle, validator):
    broken = dict(bundle, **{"x-canonicalization": "trace-cj/2.0"})

    with pytest.raises(ValidationError):
        validator.validate(broken)


def test_legacy_style_fragment_id_fails_the_frozen_pattern(bundle, validator):
    broken = dict(bundle, fragments=[dict(bundle["fragments"][0], fragment_id="FRG-0005")])

    with pytest.raises(ValidationError):
        validator.validate(broken)


def test_zero_size_fragment_fails(bundle, validator):
    broken = dict(bundle, fragments=[dict(bundle["fragments"][0], size_bytes=0)])

    with pytest.raises(ValidationError):
        validator.validate(broken)


def test_bundle_json_refuses_non_finite_numbers(bundle):
    broken = dict(bundle, media={"size_bytes": float("nan")})

    with pytest.raises(ValueError):
        bundle_to_json(broken)


def test_bundle_to_json_round_trips(bundle):
    assert json.loads(bundle_to_json(bundle)) == bundle


def test_new_run_id_is_volatile_and_clock_free():
    first = new_run_id()
    second = new_run_id()

    assert first != second
    assert len(first) == 32
    assert all(character in "0123456789abcdef" for character in first)
