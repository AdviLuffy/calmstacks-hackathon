import hashlib
import json
from pathlib import Path

import pytest

from trace_evidence.constants import BLOCK_SIZE
from trace_evidence.scanning import scan_media

FROZEN_FIELDS = {"fragment_id", "byte_range", "size_bytes", "bytes_sha256", "warnings"}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _blob_path(dataset_dir: Path, seed: int) -> Path:
    return dataset_dir / "evidence" / f"blob_{seed}.bin"


def _manifest(dataset_dir: Path) -> dict:
    return json.loads((dataset_dir / "manifest.json").read_text(encoding="utf-8"))


def test_scanning_covers_the_media_exactly(dataset_dir, default_seed):
    blob_path = _blob_path(dataset_dir, default_seed)
    result = scan_media(blob_path)

    assert len(result.fragments) == 8
    assert result.media_size_bytes == blob_path.stat().st_size == 2048
    assert result.fragments[0].byte_range == (0, BLOCK_SIZE)

    for previous, current in zip(result.fragments, result.fragments[1:]):
        assert previous.end == current.start

    assert result.fragments[-1].end == result.media_size_bytes
    assert sum(fragment.size_bytes for fragment in result.fragments) == result.media_size_bytes


def test_scanned_fragments_match_the_ground_truth_manifest(dataset_dir, default_seed):
    blob = _blob_path(dataset_dir, default_seed).read_bytes()
    manifest = _manifest(dataset_dir)
    result = scan_media(_blob_path(dataset_dir, default_seed))

    assert result.media_sha256 == manifest["blob"]["sha256"]
    assert result.media_size_bytes == manifest["blob"]["size"]

    by_range = {fragment.byte_range: fragment for fragment in result.fragments}
    assert len(by_range) == len(result.fragments)

    for ground_truth in manifest["fragments"]:
        start = ground_truth["blob_offset"]
        end = start + ground_truth["length"]
        fragment = by_range[(start, end)]
        assert fragment.bytes_sha256 == ground_truth["sha256"]
        assert fragment.bytes_sha256 == _sha256(blob[start:end])


def test_scanning_preserves_the_evidence(dataset_dir, default_seed):
    blob_path = _blob_path(dataset_dir, default_seed)
    before = (blob_path.stat().st_mtime_ns, _sha256(blob_path.read_bytes()))

    scan_media(blob_path)

    after = (blob_path.stat().st_mtime_ns, _sha256(blob_path.read_bytes()))
    assert before == after


def test_no_warnings_for_a_whole_block_multiple(dataset_dir, default_seed):
    result = scan_media(_blob_path(dataset_dir, default_seed))

    assert result.warnings == ()
    assert all(fragment.warnings == () for fragment in result.fragments)


def test_partial_trailing_block_is_surfaced_in_warnings(dataset_dir, default_seed, tmp_path):
    blob = _blob_path(dataset_dir, default_seed).read_bytes()
    truncated = tmp_path / "truncated.bin"
    truncated.write_bytes(blob[:-100])

    result = scan_media(truncated)

    assert result.media_size_bytes == len(blob) - 100
    assert len(result.warnings) == 1
    assert "partial trailing block" in result.warnings[0]
    assert result.fragments[-1].warnings == (result.warnings[0],)
    assert result.fragments[-1].size_bytes == (len(blob) - 100) - (7 * BLOCK_SIZE)


def test_empty_media_is_surfaced(tmp_path):
    empty = tmp_path / "empty.bin"
    empty.write_bytes(b"")

    result = scan_media(empty)

    assert result.fragments == ()
    assert result.media_size_bytes == 0
    assert result.warnings == ("media is empty: no fragments carved",)


def test_fragment_records_carry_no_label_or_classification(dataset_dir, default_seed):
    result = scan_media(_blob_path(dataset_dir, default_seed))

    for fragment in result.fragments:
        record = fragment.to_dict()
        assert set(record) == FROZEN_FIELDS
        assert "label" not in record
        assert "application/pdf" not in json.dumps(record)


def test_every_fragment_id_resolves_to_exactly_one_record(dataset_dir, default_seed):
    result = scan_media(_blob_path(dataset_dir, default_seed))

    index: dict[str, list] = {}
    for fragment in result.fragments:
        index.setdefault(fragment.fragment_id, []).append(fragment)

    assert len(result.fragments) == 8
    for fragment in result.fragments:
        assert len(index[fragment.fragment_id]) == 1

    fragment_id = result.fragments[3].fragment_id
    reference = f"fragments[{fragment_id}].byte_range"
    resolved = reference.split("[", 1)[1].split("]", 1)[0]
    assert resolved == fragment_id
    assert len(index[resolved]) == 1


@pytest.mark.parametrize("block_size", [0, -1])
def test_rejects_non_positive_block_size(dataset_dir, default_seed, block_size):
    with pytest.raises(ValueError):
        scan_media(_blob_path(dataset_dir, default_seed), block_size=block_size)


def test_scan_result_to_dict_is_json_serializable(dataset_dir, default_seed):
    result = scan_media(_blob_path(dataset_dir, default_seed))
    payload = json.dumps(result.to_dict(), sort_keys=True, allow_nan=False)

    assert result.fragments[0].fragment_id in payload
    assert "application/pdf" not in payload
