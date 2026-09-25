from pathlib import Path

import pytest

from trace_evidence.hashing import content_id, sha256_bytes, sha256_file

EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
ABC_SHA256 = "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"


def test_sha256_bytes_known_vectors():
    assert sha256_bytes(b"") == EMPTY_SHA256
    assert sha256_bytes(b"abc") == ABC_SHA256


def test_sha256_file_matches_sha256_bytes(tmp_path: Path):
    payload = bytes(range(256)) * 1200  # 307_200 bytes: exercises chunking
    target = tmp_path / "payload.bin"
    target.write_bytes(payload)

    assert sha256_file(target) == sha256_bytes(payload)


def test_content_id_is_deterministic_and_formatted():
    digest = sha256_bytes(b"trace")

    first = content_id("frag", digest)
    second = content_id("frag", digest)

    assert first == second
    assert first.startswith("frag_")
    assert len(first) == len("frag_") + 16
    assert all(c in "0123456789abcdef" for c in first.split("_", 1)[1])


def test_content_id_rejects_bad_input():
    digest = sha256_bytes(b"trace")

    with pytest.raises(ValueError):
        content_id("", digest)
    with pytest.raises(ValueError):
        content_id("frag", digest, length=99)
