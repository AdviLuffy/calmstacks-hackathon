import inspect
import json
from pathlib import Path

import pytest

from trace_evidence import constants as c
from trace_evidence import dna
from trace_evidence.dna import (
    FragmentProfile,
    ProfileMismatchError,
    classify_block,
    detect_tokens,
    profile_fragment,
)
from trace_evidence.hashing import sha256_bytes, sha256_file
from trace_evidence.models import Fragment, make_fragment_id
from trace_evidence.scanning import scan_media

BLOCK = c.BLOCK_SIZE


def _blob_path(dataset_dir: Path, seed: int) -> Path:
    return dataset_dir / "evidence" / f"blob_{seed}.bin"


def _blocks(data: bytes) -> list[bytes]:
    return [data[start:start + BLOCK] for start in range(0, len(data), BLOCK)]


def _padded(content: bytes) -> bytes:
    """Right-pad a synthetic unit to one block, mirroring the fixture layout."""
    return content.ljust(BLOCK, b" ")


@pytest.fixture()
def scanned(dataset_dir, default_seed):
    blob_path = _blob_path(dataset_dir, default_seed)
    return blob_path, scan_media(blob_path), _blocks(blob_path.read_bytes())


@pytest.fixture()
def profiles(scanned):
    _, scan, blocks = scanned
    return tuple(
        profile_fragment(fragment, block)
        for fragment, block in zip(scan.fragments, blocks)
    )


def test_profiles_one_structural_unit_per_fragment(profiles):
    kinds = [profile.kind for profile in profiles]

    assert len(profiles) == 8
    assert kinds.count(c.KIND_HEADER) == 1
    assert kinds.count(c.KIND_OBJECT) == 3
    assert kinds.count(c.KIND_XREF) == 1
    assert kinds.count(c.KIND_TRAILER) == 1
    assert kinds.count(c.KIND_STARTXREF) == 1
    assert kinds.count(c.KIND_EOF) == 1
    assert c.KIND_UNKNOWN not in kinds


def test_object_numbers_are_recovered_from_content(profiles):
    numbers = sorted(
        profile.object_number for profile in profiles if profile.kind == c.KIND_OBJECT
    )

    assert numbers == [1, 2, 3]


def test_header_block_is_detected(profiles):
    headers = [profile for profile in profiles if profile.kind == c.KIND_HEADER]

    assert len(headers) == 1
    assert headers[0].tokens == (dna.TOKEN_PDF_HEADER,)
    assert headers[0].object_number is None


def test_startxref_block_is_not_misclassified_as_xref(profiles):
    """TRAP: 'startxref' contains 'xref' as a substring."""
    with_startxref = [
        profile for profile in profiles if dna.TOKEN_STARTXREF in profile.tokens
    ]
    with_xref = [profile for profile in profiles if dna.TOKEN_XREF in profile.tokens]

    assert len(with_startxref) == 1
    assert len(with_xref) == 1
    assert with_startxref[0].kind == c.KIND_STARTXREF
    assert with_startxref[0].tokens == (dna.TOKEN_STARTXREF,)
    assert with_xref[0].kind == c.KIND_XREF
    assert with_xref[0].tokens == (dna.TOKEN_XREF,)


def test_left_padded_eof_block_is_detected(scanned, profiles):
    """TRAP: the eof block is left-padded, so %%EOF sits at the block's end."""
    _, scan, blocks = scanned
    eof_profiles = [profile for profile in profiles if profile.kind == c.KIND_EOF]

    assert len(eof_profiles) == 1
    eof_profile = eof_profiles[0]

    index = next(
        position
        for position, fragment in enumerate(scan.fragments)
        if fragment.fragment_id == eof_profile.fragment_id
    )
    eof_block = blocks[index]

    assert not eof_block.startswith(b"%%EOF")
    assert eof_block.strip(b" ") == b"%%EOF\n"
    assert eof_profile.tokens == (dna.TOKEN_EOF,)


def test_profiles_agree_with_the_ground_truth_manifest(dataset_dir, profiles):
    manifest = json.loads((dataset_dir / "manifest.json").read_text(encoding="utf-8"))

    assert len(profiles) == len(manifest["fragments"]) == 8
    for profile, ground_truth in zip(profiles, manifest["fragments"]):
        assert profile.byte_range[0] == ground_truth["blob_offset"]
        assert profile.size_bytes == ground_truth["length"]
        assert profile.kind == ground_truth["kind"]
        assert profile.object_number == ground_truth["object_number"]


def test_profiling_is_deterministic(scanned):
    _, scan, blocks = scanned

    first = tuple(profile_fragment(f, b) for f, b in zip(scan.fragments, blocks))
    second = tuple(profile_fragment(f, b) for f, b in zip(scan.fragments, blocks))

    assert first == second


def test_classify_block_uses_line_anchored_object_detection():
    kind, number = classify_block(_padded(b"1 0 obj\n<< /Type /Catalog >>\nendobj\n"))
    assert (kind, number) == (c.KIND_OBJECT, 1)

    # TRAP: 'endobj' alone must never be read as an object header
    kind, number = classify_block(_padded(b"endobj\n"))
    assert (kind, number) == (c.KIND_UNKNOWN, None)


def test_classify_block_ignores_xref_entry_lines_as_objects():
    block = _padded(b"xref\n0 4\n0000000000 65535 f \n0000000256 00000 n \n")

    kind, number = classify_block(block)

    assert kind == c.KIND_XREF
    assert number is None


def test_classify_block_returns_unknown_for_unrecognised_bytes():
    assert classify_block(b"\x00\x01\x02\x03".ljust(BLOCK, b"\x00")) == (
        c.KIND_UNKNOWN,
        None,
    )
    assert classify_block(b"") == (c.KIND_UNKNOWN, None)


def test_detect_tokens_reports_a_fixed_order():
    assert detect_tokens(_padded(b"startxref\n1024\n")) == (dna.TOKEN_STARTXREF,)
    assert detect_tokens(_padded(b"1 0 obj\n<< >>\nendobj\n")) == (
        dna.TOKEN_OBJ,
        dna.TOKEN_ENDOBJ,
    )


def test_profile_requires_object_number_if_and_only_if_object_kind():
    with pytest.raises(ValueError):
        FragmentProfile(
            fragment_id="FRG-0123456789abcdef-0-256",
            byte_range=(0, 256),
            kind=c.KIND_OBJECT,
        )

    with pytest.raises(ValueError):
        FragmentProfile(
            fragment_id="FRG-0123456789abcdef-0-256",
            byte_range=(0, 256),
            kind=c.KIND_HEADER,
            object_number=7,
        )


def test_profile_size_bytes_is_derived_from_the_range():
    profile = FragmentProfile(
        fragment_id="FRG-0123456789abcdef-256-512",
        byte_range=(256, 512),
        kind=c.KIND_TRAILER,
        tokens=(dna.TOKEN_TRAILER,),
    )

    assert profile.size_bytes == BLOCK
    assert profile.is_object is False


def test_profile_rejects_bytes_that_do_not_match_the_fragment(scanned):
    _, scan, blocks = scanned

    with pytest.raises(ProfileMismatchError):
        profile_fragment(scan.fragments[0], blocks[1])

    with pytest.raises(ProfileMismatchError):
        profile_fragment(scan.fragments[0], blocks[0] + b"\x00")


def test_identical_content_at_different_ranges_profiles_identically():
    block = _padded(b"1 0 obj\n<< >>\nendobj\n")
    digest = sha256_bytes(block)

    first = Fragment(
        fragment_id=make_fragment_id(digest, 0, BLOCK),
        byte_range=(0, BLOCK),
        bytes_sha256=digest,
    )
    second = Fragment(
        fragment_id=make_fragment_id(digest, BLOCK, 2 * BLOCK),
        byte_range=(BLOCK, 2 * BLOCK),
        bytes_sha256=digest,
    )

    first_profile = profile_fragment(first, block)
    second_profile = profile_fragment(second, block)

    assert first.fragment_id != second.fragment_id
    assert first_profile.byte_range != second_profile.byte_range
    assert (
        first_profile.kind,
        first_profile.object_number,
        first_profile.tokens,
    ) == (
        second_profile.kind,
        second_profile.object_number,
        second_profile.tokens,
    )


def test_profiling_has_no_filesystem_or_fixture_dependency():
    source = inspect.getsource(dna)

    assert "from .dataset" not in source
    assert "import json" not in source
    assert "pathlib" not in source
    assert "open(" not in source
    assert list(inspect.signature(dna.profile_fragment).parameters) == [
        "fragment",
        "block",
    ]


def test_profiling_leaves_the_fixture_untouched(scanned):
    blob_path, scan, blocks = scanned
    before = (blob_path.stat().st_mtime_ns, sha256_file(blob_path))

    for fragment, block in zip(scan.fragments, blocks):
        profile_fragment(fragment, block)

    after = (blob_path.stat().st_mtime_ns, sha256_file(blob_path))
    assert before == after
