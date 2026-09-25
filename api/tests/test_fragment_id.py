"""M0 fragment-ID amendment: frozen format, frozen semantics, and the recorded gaps.

Every assertion cites what it locks in: either the frozen grammar
``FRG-<16 lowercase hex>-<start>-<end>`` or one of the nine frozen semantics. Nothing here
asserts behaviour that the amendment does not state.
"""
from __future__ import annotations

import hashlib

import pytest

from app.contract.evidence_ref import (
    EVIDENCE_REF_COLLECTIONS,
    EVIDENCE_REF_RE,
    GROUNDING_REASON_SYNTAX_INVALID,
    INSTANCE_ID_RE,
    GroundingStatus,
    SessionEvidenceRefResolver,
)
from app.contract.fragment_id import (
    FRAGMENT_ID_DIGEST_HEX_LENGTH,
    FRAGMENT_ID_PATTERN,
    FRAGMENT_ID_PREFIX,
    FRAGMENT_ID_RANGE_DIGITS_MAX,
    FRAGMENT_ID_RANGE_DIGITS_MIN,
    FRAGMENT_ID_RE,
    FRAGMENTS_COLLECTION,
    SHA256_DIGEST_HEX_LENGTH,
    FragmentIdCollisionError,
    FragmentIdIndex,
    InvalidFragmentInstanceIdError,
    digest_hex_prefix,
    format_fragment_instance_id,
    fragment_instance_id_from_content,
    is_full_sha256_digest,
    is_valid_fragment_instance_id,
    parse_fragment_instance_id,
    validate_fragment_identity,
)

CONTENT = b"TRACE fragment content"
FULL_DIGEST = hashlib.sha256(CONTENT).hexdigest()

#: Identifiers that satisfy the frozen grammar.
VALID_IDS = (
    "FRG-0123456789abcdef-0-1",
    "FRG-ffffffffffffffff-0-1048576",
    "FRG-0000000000000000-0-9999999999",
    "FRG-0123456789abcdef-9-10",
    "FRG-deadbeefdeadbeef-4096-8192",
    # digits{1,10} admits leading zeros, and no canonical spelling is frozen (M0-AMB-08),
    # so this spelling is accepted and must not be rewritten.
    "FRG-0123456789abcdef-007-04096",
)

#: Identifiers the frozen grammar rejects.
GRAMMAR_INVALID_IDS = (
    "",
    "FRG-0123456789abcdef-0-1 ",
    "FRG-0123456789abcdef-0-1\n",
    "frg-0123456789abcdef-0-1",
    "FG-0123456789abcdef-0-1",
    "FRG0123456789abcdef-0-1",
    "FRG-0123456789ABCDEF-0-1",
    "FRG-0123456789abcde-0-1",
    "FRG-0123456789abcdefg-0-1",
    "FRG-0123456789abcdef-0",
    "FRG-0123456789abcdef-0-",
    "FRG-0123456789abcdef--0-1",
    "FRG-0123456789abcdef-0-10000000000",
    "FRG-0123456789abcdef-0-1-2",
    "FRG-0123456789abcdef-0-1.signature",
    "fragments[FRG-0123456789abcdef-0-1]",
)


def test_pattern_is_exactly_the_frozen_grammar():
    assert FRAGMENT_ID_PREFIX == "FRG-"
    assert FRAGMENT_ID_PATTERN == r"^FRG-[0-9a-f]{16}-\d{1,10}-\d{1,10}$"
    assert FRAGMENT_ID_DIGEST_HEX_LENGTH == 16
    assert (FRAGMENT_ID_RANGE_DIGITS_MIN, FRAGMENT_ID_RANGE_DIGITS_MAX) == (1, 10)
    assert SHA256_DIGEST_HEX_LENGTH == 64


@pytest.mark.parametrize("fragment_id", VALID_IDS)
def test_valid_ids_are_accepted(fragment_id):
    assert is_valid_fragment_instance_id(fragment_id) is True
    assert str(parse_fragment_instance_id(fragment_id)) == fragment_id


@pytest.mark.parametrize("fragment_id", GRAMMAR_INVALID_IDS)
def test_grammar_invalid_ids_are_rejected(fragment_id):
    assert is_valid_fragment_instance_id(fragment_id) is False
    with pytest.raises(InvalidFragmentInstanceIdError):
        parse_fragment_instance_id(fragment_id)


@pytest.mark.parametrize(
    "fragment_id",
    (
        "FRG-0123456789abcdef-1-1",  # semantics 5: end must be greater than start
        "FRG-0123456789abcdef-9-4",
        "FRG-0123456789abcdef-0-0",
    ),
)
def test_end_must_be_greater_than_start(fragment_id):
    """Semantics 5 is a range rule, not a grammar rule: the pattern still matches."""
    assert FRAGMENT_ID_RE.fullmatch(fragment_id) is not None  # only the range rule rejects it
    assert is_valid_fragment_instance_id(fragment_id) is False
    with pytest.raises(InvalidFragmentInstanceIdError):
        parse_fragment_instance_id(fragment_id)


def test_negative_start_is_not_representable_at_all():
    """Semantics 4 (start >= 0) needs no runtime check: the grammar admits no sign."""
    assert is_valid_fragment_instance_id("FRG-0123456789abcdef--1-4") is False
    with pytest.raises(InvalidFragmentInstanceIdError):
        parse_fragment_instance_id("FRG-0123456789abcdef--1-4")


def test_parse_decomposes_the_identifier_without_rewriting_it():
    parsed = parse_fragment_instance_id("FRG-0123456789abcdef-10-42")
    assert parsed.value == "FRG-0123456789abcdef-10-42"
    assert parsed.digest_hex == "0123456789abcdef"
    assert parsed.start == 10
    assert parsed.end == 42
    assert parsed.byte_range == (10, 42)  # semantics 3: [start, end)
    assert parsed.size_bytes == 32  # semantics 6: size_bytes = end - start
    assert parsed.occurrence == ("0123456789abcdef", 10, 42)  # semantics 1


@pytest.mark.parametrize("value", (None, 3, True, b"FRG-0123456789abcdef-0-1", ["x"]))
def test_parse_rejects_non_strings(value):
    assert is_valid_fragment_instance_id(value) is False
    with pytest.raises(InvalidFragmentInstanceIdError):
        parse_fragment_instance_id(value)


def test_format_builds_the_frozen_format():
    assert (
        format_fragment_instance_id(digest_hex="0123456789abcdef", start=0, end=4096)
        == "FRG-0123456789abcdef-0-4096"
    )
    assert (
        format_fragment_instance_id(digest_hex="0000000000000000", start=1, end=2)
        == "FRG-0000000000000000-1-2"
    )


def test_format_round_trips_through_parse():
    built = format_fragment_instance_id(digest_hex="deadbeefdeadbeef", start=7, end=9)
    parsed = parse_fragment_instance_id(built)
    assert parsed.byte_range == (7, 9)
    assert parsed.size_bytes == 2


@pytest.mark.parametrize(
    "kwargs",
    (
        pytest.param({"digest_hex": "0123456789abcde", "start": 0, "end": 1}, id="15-hex"),
        pytest.param({"digest_hex": "0123456789ABCDEF", "start": 0, "end": 1}, id="uppercase"),
        pytest.param({"digest_hex": None, "start": 0, "end": 1}, id="no-digest"),
        pytest.param({"digest_hex": "0123456789abcdef", "start": -1, "end": 1}, id="negative"),
        pytest.param({"digest_hex": "0123456789abcdef", "start": 1, "end": 1}, id="empty-range"),
        pytest.param({"digest_hex": "0123456789abcdef", "start": 9, "end": 4}, id="reversed"),
        pytest.param(
            {"digest_hex": "0123456789abcdef", "start": 0, "end": 10**10}, id="eleven-digits"
        ),
        pytest.param({"digest_hex": "0123456789abcdef", "start": True, "end": 2}, id="bool"),
        pytest.param({"digest_hex": "0123456789abcdef", "start": 0.0, "end": 1}, id="float"),
        pytest.param({"digest_hex": "0123456789abcdef", "start": 0, "end": "1"}, id="string"),
    ),
)
def test_format_rejects_arguments_the_grammar_cannot_carry(kwargs):
    with pytest.raises(InvalidFragmentInstanceIdError):
        format_fragment_instance_id(**kwargs)


def test_only_a_complete_sha256_digest_is_accepted_as_bytes_sha256():
    """Semantics 2."""
    assert len(FULL_DIGEST) == SHA256_DIGEST_HEX_LENGTH
    assert is_full_sha256_digest(FULL_DIGEST) is True
    assert is_full_sha256_digest(FULL_DIGEST.upper()) is True  # M0-AMB-08: case not frozen
    assert is_full_sha256_digest(FULL_DIGEST[:63]) is False
    assert is_full_sha256_digest(FULL_DIGEST + "0") is False
    assert is_full_sha256_digest(FULL_DIGEST[:63] + "z") is False
    assert is_full_sha256_digest(None) is False
    assert is_full_sha256_digest(b"a" * SHA256_DIGEST_HEX_LENGTH) is False


def test_digest_hex_prefix_lowercases_and_refuses_a_partial_digest():
    assert digest_hex_prefix(FULL_DIGEST) == FULL_DIGEST[:FRAGMENT_ID_DIGEST_HEX_LENGTH]
    assert digest_hex_prefix(FULL_DIGEST.upper()) == FULL_DIGEST[:FRAGMENT_ID_DIGEST_HEX_LENGTH]
    for value in ("0123456789abcdef", FULL_DIGEST[:63], None):
        with pytest.raises(InvalidFragmentInstanceIdError):
            digest_hex_prefix(value)


def test_content_constructor_is_stable_and_range_sensitive():
    """Semantics 8: identical bytes at different source ranges receive different IDs."""
    first = fragment_instance_id_from_content(bytes_sha256=FULL_DIGEST, start=0, end=4096)
    same = fragment_instance_id_from_content(bytes_sha256=FULL_DIGEST, start=0, end=4096)
    other_range = fragment_instance_id_from_content(bytes_sha256=FULL_DIGEST, start=4096, end=8192)

    assert first == same
    assert first == "FRG-%s-0-4096" % FULL_DIGEST[:FRAGMENT_ID_DIGEST_HEX_LENGTH]
    assert first != other_range
    assert parse_fragment_instance_id(first).digest_hex == (
        parse_fragment_instance_id(other_range).digest_hex
    )
    assert is_valid_fragment_instance_id(first) is True


def test_validate_fragment_identity_accepts_a_consistent_record():
    fragment_id = fragment_instance_id_from_content(bytes_sha256=FULL_DIGEST, start=100, end=356)
    parsed = validate_fragment_identity(
        fragment_id=fragment_id,
        bytes_sha256=FULL_DIGEST,
        start=100,
        end=356,
        size_bytes=256,
    )
    assert parsed.size_bytes == 256
    assert parsed.digest_hex == FULL_DIGEST[:FRAGMENT_ID_DIGEST_HEX_LENGTH]


def test_validate_fragment_identity_derives_size_bytes_when_it_is_absent():
    parsed = validate_fragment_identity(
        fragment_id="FRG-0123456789abcdef-8-16",
        bytes_sha256=FULL_DIGEST,
        start=8,
        end=16,
    )
    assert parsed.size_bytes == 8


@pytest.mark.parametrize(
    "overrides",
    (
        pytest.param({"start": 1}, id="range-start-does-not-match-the-identifier"),
        pytest.param({"end": 17}, id="range-end-does-not-match-the-identifier"),
        pytest.param({"size_bytes": 7}, id="size-bytes-is-not-end-minus-start"),
        pytest.param({"size_bytes": True}, id="size-bytes-is-not-an-integer"),
        pytest.param({"bytes_sha256": FULL_DIGEST[:63]}, id="digest-is-not-complete"),
        pytest.param({"bytes_sha256": 12345}, id="digest-is-not-a-string"),
        pytest.param({"start": "8"}, id="range-is-not-an-integer"),
        pytest.param({"end": 8}, id="end-not-greater-than-start"),
    ),
)
def test_validate_fragment_identity_rejects_inconsistent_records(overrides):
    arguments = {
        "fragment_id": "FRG-0123456789abcdef-8-16",
        "bytes_sha256": FULL_DIGEST,
        "start": 8,
        "end": 16,
    }
    arguments.update(overrides)
    with pytest.raises(InvalidFragmentInstanceIdError):
        validate_fragment_identity(**arguments)


def test_fragment_ids_are_unique_within_a_bundle():
    """Semantics 7."""
    index = FragmentIdIndex(["FRG-0123456789abcdef-0-4096"])
    assert len(index) == 1
    with pytest.raises(FragmentIdCollisionError):
        index.add("FRG-0123456789abcdef-0-4096")
    assert len(index) == 1
    with pytest.raises(FragmentIdCollisionError):
        FragmentIdIndex(
            ["FRG-0123456789abcdef-0-4096", "FRG-0123456789abcdef-0-4096"]
        )


def test_one_source_occurrence_cannot_carry_two_identifiers():
    """Semantics 1, including the leading-zero spelling gap recorded in M0-AMB-08."""
    index = FragmentIdIndex()
    index.add("FRG-0123456789abcdef-7-4096")
    assert index.defines("FRG-0123456789abcdef-7-4096") is True
    with pytest.raises(FragmentIdCollisionError):
        index.add("FRG-0123456789abcdef-007-04096")


def test_identical_bytes_at_different_ranges_are_distinct_identifiers():
    """Semantics 8."""
    first = fragment_instance_id_from_content(bytes_sha256=FULL_DIGEST, start=0, end=4096)
    second = fragment_instance_id_from_content(bytes_sha256=FULL_DIGEST, start=4096, end=8192)
    index = FragmentIdIndex([first, second])
    assert len(index) == 2
    assert index.defines(first) is True
    assert index.defines(second) is True


def test_resolve_returns_at_most_one_record():
    """Semantics 9."""
    record = {"fragment_id": "FRG-0123456789abcdef-0-4096"}
    index = FragmentIdIndex()
    index.add("FRG-0123456789abcdef-0-4096", record)

    assert index.resolve("FRG-0123456789abcdef-0-4096") is record
    assert index.resolve("FRG-0123456789abcdef-4096-8192") is None
    assert index.resolve("not-an-identifier") is None
    assert "FRG-0123456789abcdef-0-4096" in index
    assert None not in index
    assert list(index) == ["FRG-0123456789abcdef-0-4096"]
    assert index.ids == ("FRG-0123456789abcdef-0-4096",)


def test_index_rejects_a_malformed_identifier_before_registering_it():
    index = FragmentIdIndex()
    with pytest.raises(InvalidFragmentInstanceIdError):
        index.add("fragments[FRG-0123456789abcdef-0-4096]")
    with pytest.raises(InvalidFragmentInstanceIdError):
        index.add("FRG-0123456789abcdef-9-4")
    assert len(index) == 0


def test_collection_ids_uses_the_frozen_collection_name():
    index = FragmentIdIndex(["FRG-0123456789abcdef-0-4096"])
    assert FRAGMENTS_COLLECTION in EVIDENCE_REF_COLLECTIONS
    assert index.collection_ids() == {
        FRAGMENTS_COLLECTION: frozenset({"FRG-0123456789abcdef-0-4096"})
    }


def test_the_fragment_evidence_ref_gap_is_closed_by_option_a():
    """M0-AMB-07 closed by the frozen Option A amendment (M0-DEC-06), executed.

    The frozen FragmentInstanceId is now expressible inside the single normative pattern:
    the fragments slot admits it as an alternative, so a fragment reference parses and
    resolves to exactly one record instead of failing on syntax. The generic instance-id
    slot (INSTANCE_ID_RE) is untouched: the FRG shape is an alternative in the fragments
    slot, never a widening of the generic shape. If the pattern is ever narrowed again,
    this test fails loudly and forces the registry entry to be updated with it.
    """
    fragment_id = fragment_instance_id_from_content(bytes_sha256=FULL_DIGEST, start=0, end=4096)
    reference = "fragments[%s]" % fragment_id

    assert INSTANCE_ID_RE.fullmatch(fragment_id) is None
    assert EVIDENCE_REF_RE.fullmatch(reference) is not None

    resolver = SessionEvidenceRefResolver(
        collection_ids=FragmentIdIndex([fragment_id]).collection_ids()
    )
    result = resolver.resolve(reference)
    assert result.status is GroundingStatus.RESOLVED
    assert result.reason is None
    assert result.is_grounded is True


def test_the_gap_is_scoped_to_the_frozen_frg_format():
    """The normative pattern is untouched: it still accepts a fragment ref shaped as before."""
    resolver = SessionEvidenceRefResolver(collection_ids={"fragments": frozenset({"ART-0001"})})
    result = resolver.resolve("fragments[ART-0001]")
    assert result.status is GroundingStatus.RESOLVED
    assert result.reason is None
    assert result.is_grounded is True

