import re

import pytest

from trace_evidence.models import (
    DIGEST_HEX_LENGTH,
    FRAGMENT_ID_HEX_LENGTH,
    FRAGMENT_ID_PATTERN,
    Fragment,
    FragmentRangeError,
    make_fragment_id,
    parse_fragment_id,
    validate_range,
)

DIGEST_A = "0123456789abcdef" * 4
DIGEST_B = "fedcba9876543210" * 4

FROZEN_FIELDS = {"fragment_id", "byte_range", "size_bytes", "bytes_sha256", "warnings"}
FORBIDDEN_FIELDS = {
    "label",
    "artifact_label",
    "confidence",
    "confidence_basis",
    "engine",
    "run_id",
    "path_hint",
    "name_hint",
    "timestamp",
    "timestamp_utc",
    "source_offset",
    "original_index",
    "kind",
    "object_number",
    "classification",
}


def test_id_matches_the_frozen_format():
    fragment_id = make_fragment_id(DIGEST_A, 0, 256)

    assert fragment_id == f"FRG-{DIGEST_A[:FRAGMENT_ID_HEX_LENGTH]}-0-256"
    assert FRAGMENT_ID_PATTERN == r"^FRG-[0-9a-f]{16}-[0-9]+-[0-9]+$"
    assert re.fullmatch(FRAGMENT_ID_PATTERN, fragment_id) is not None


def test_id_embeds_the_first_16_lowercase_hex_of_the_digest():
    fragment_id = make_fragment_id(DIGEST_B, 512, 1024)

    digest_segment = fragment_id.split("-")[1]
    assert digest_segment == DIGEST_B[:FRAGMENT_ID_HEX_LENGTH]
    assert len(digest_segment) == FRAGMENT_ID_HEX_LENGTH
    assert digest_segment == digest_segment.lower()


def test_identical_bytes_at_different_ranges_get_different_ids():
    first = make_fragment_id(DIGEST_A, 0, 256)
    second = make_fragment_id(DIGEST_A, 256, 512)

    assert first != second
    assert first.rsplit("-", 2)[0] == second.rsplit("-", 2)[0]  # same content prefix


def test_same_content_and_range_is_stable():
    assert make_fragment_id(DIGEST_A, 256, 512) == make_fragment_id(DIGEST_A, 256, 512)


@pytest.mark.parametrize(
    ("start", "end"),
    [(-1, 10), (0, 0), (10, 5), (5, 5)],
)
def test_range_validation_rejects_invalid_ranges(start, end):
    with pytest.raises(FragmentRangeError):
        validate_range(start, end)


@pytest.mark.parametrize("value", [True, False, None, 1.5, "0"])
def test_range_validation_rejects_non_integer_inputs(value):
    with pytest.raises(FragmentRangeError):
        validate_range(value, 10)


@pytest.mark.parametrize(
    "bad_digest",
    ["", "abc", "A" * 64, "0123456789abcdef" * 3 + "zzzz", "0" * 63, "0" * 65],
)
def test_make_fragment_id_rejects_bad_digests(bad_digest):
    with pytest.raises(ValueError):
        make_fragment_id(bad_digest, 0, 256)


def test_parse_round_trips_make():
    for digest, start, end in [
        (DIGEST_A, 0, 256),
        (DIGEST_B, 256, 1792),
        (DIGEST_A, 1792, 2048),
    ]:
        fragment_id = make_fragment_id(digest, start, end)
        assert parse_fragment_id(fragment_id) == (
            digest[:FRAGMENT_ID_HEX_LENGTH],
            start,
            end,
        )


@pytest.mark.parametrize(
    "bad_id",
    [
        "FRG-0123456789abcdef-0",
        "FRG-0123456789abcdef-0-256-extra",
        "XXX-0123456789abcdef-0-256",
        "FRG-0123456789ABCDEF-0-256",
        "FRG-0123456789abcde-0-256",
        "FRG-0123456789abcdef-00-256",
        "FRG-0123456789abcdef-0-0256",
        "FRG-0123456789abcdef-\u0662-256",
        "FRG-0123456789abcdef-256-256",
        "FRG-0123456789abcdef-512-256",
    ],
)
def test_parse_rejects_malformed_ids(bad_id):
    with pytest.raises(ValueError):
        parse_fragment_id(bad_id)


def test_digest_hex_length_constant_is_64():
    assert DIGEST_HEX_LENGTH == 64
    assert len(DIGEST_A) == DIGEST_HEX_LENGTH


def _fragment(digest=DIGEST_A, start=0, end=256, warnings=()):
    return Fragment(
        fragment_id=make_fragment_id(digest, start, end),
        byte_range=(start, end),
        bytes_sha256=digest,
        warnings=warnings,
    )


def test_fragment_size_bytes_is_end_minus_start():
    assert _fragment(start=0, end=256).size_bytes == 256
    assert _fragment(start=1792, end=2048).size_bytes == 256
    assert _fragment(start=2048, end=2049).size_bytes == 1


def test_fragment_rejects_id_that_disagrees_with_content_or_range():
    with pytest.raises(ValueError):
        Fragment(
            fragment_id=make_fragment_id(DIGEST_B, 0, 256),
            byte_range=(0, 256),
            bytes_sha256=DIGEST_A,
        )
    with pytest.raises(ValueError):
        Fragment(
            fragment_id=make_fragment_id(DIGEST_A, 0, 256),
            byte_range=(0, 512),
            bytes_sha256=DIGEST_A,
        )


def test_fragment_rejects_invalid_range():
    with pytest.raises(FragmentRangeError):
        Fragment(
            fragment_id="FRG-0000000000000000-0-0",
            byte_range=(0, 0),
            bytes_sha256=DIGEST_A,
        )


def test_fragment_rejects_byte_range_without_exactly_two_values():
    with pytest.raises(FragmentRangeError):
        Fragment(
            fragment_id=make_fragment_id(DIGEST_A, 0, 256),
            byte_range=(0, 128, 256),
            bytes_sha256=DIGEST_A,
        )


def test_fragment_record_exposes_only_frozen_fields():
    record = _fragment(warnings=("partial trailing block",)).to_dict()

    assert set(record) == FROZEN_FIELDS
    assert not FORBIDDEN_FIELDS & set(record)
    assert record["byte_range"] == [0, 256]
    assert isinstance(record["byte_range"], list)
    assert record["size_bytes"] == 256
    assert record["bytes_sha256"] == DIGEST_A
    assert record["warnings"] == ["partial trailing block"]


def test_fragment_ids_are_unique_when_identical_content_repeats_at_other_ranges():
    digests = [DIGEST_A] * 4 + [DIGEST_B] * 4
    fragments = [
        _fragment(digest=digest, start=index * 256, end=(index + 1) * 256)
        for index, digest in enumerate(digests)
    ]

    ids = [fragment.fragment_id for fragment in fragments]
    assert len(ids) == len(set(ids)) == 8
    assert len({fragment.digest_prefix for fragment in fragments}) == 2


def test_fragment_records_are_immutable():
    fragment = _fragment()
    with pytest.raises(AttributeError):
        fragment.byte_range = (0, 512)

