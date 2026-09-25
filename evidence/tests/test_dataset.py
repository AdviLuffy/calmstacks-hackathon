import hashlib
import json
from pathlib import Path

from trace_evidence import constants as c
from trace_evidence.dataset import (
    build_synthetic_pdf,
    keyed_permutation,
    shuffle_fragments,
    split_blocks,
    write_dataset,
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_pdf_generation_is_deterministic():
    first = build_synthetic_pdf()
    second = build_synthetic_pdf()

    assert first == second
    assert _sha(first) == _sha(second)


def test_pdf_is_one_block_per_structural_unit():
    pdf = build_synthetic_pdf()
    blocks = split_blocks(pdf)

    assert len(pdf) == c.EXPECTED_FRAGMENT_COUNT * c.BLOCK_SIZE
    assert len(blocks) == c.EXPECTED_FRAGMENT_COUNT
    assert pdf.startswith(b"%PDF-")
    assert pdf.endswith(b"%%EOF\n")
    assert b"1 0 obj" in blocks[1]
    assert b"endobj" in blocks[1]
    assert b"3 0 obj" in blocks[3]


def test_xref_offsets_point_at_real_object_starts():
    pdf = build_synthetic_pdf()
    text = pdf.decode("latin-1")

    for number in range(1, c.OBJECT_COUNT + 1):
        offset = number * c.BLOCK_SIZE
        marker = f"{number} 0 obj".encode("ascii")
        assert pdf[offset:offset + len(marker)] == marker
        assert f"{offset:010d} 00000 n " in text

    xref_offset = (c.OBJECT_COUNT + 1) * c.BLOCK_SIZE
    assert pdf[xref_offset:xref_offset + 5] == b"xref\n"
    assert f"startxref\n{xref_offset}\n" in text


def test_permutation_is_reproducible_and_not_the_identity():
    order = keyed_permutation(c.EXPECTED_FRAGMENT_COUNT, c.DEFAULT_SEED)
    again = keyed_permutation(c.EXPECTED_FRAGMENT_COUNT, c.DEFAULT_SEED)

    assert order == again
    assert sorted(order) == list(range(c.EXPECTED_FRAGMENT_COUNT))
    assert order != list(range(c.EXPECTED_FRAGMENT_COUNT))


def test_blob_is_deterministic_shuffled_and_same_blocks():
    pdf = build_synthetic_pdf()
    first, _ = shuffle_fragments(pdf, c.DEFAULT_SEED)
    second, _ = shuffle_fragments(pdf, c.DEFAULT_SEED)

    assert first == second
    assert first != pdf
    assert len(first) == len(pdf)
    assert sorted(split_blocks(first)) == sorted(split_blocks(pdf))


def test_seed_changes_the_blob_but_never_the_pdf():
    pdf = build_synthetic_pdf()
    blob_a, order_a = shuffle_fragments(pdf, c.DEFAULT_SEED)
    blob_b, order_b = shuffle_fragments(pdf, c.DEFAULT_SEED + 1)

    assert blob_a != blob_b
    assert order_a != order_b
    assert sorted(split_blocks(blob_a)) == sorted(split_blocks(blob_b))
    assert _sha(pdf) == _sha(build_synthetic_pdf())


def test_write_dataset_is_byte_for_byte_reproducible(tmp_path):
    first = write_dataset(tmp_path / "a", seed=c.DEFAULT_SEED)
    second = write_dataset(tmp_path / "b", seed=c.DEFAULT_SEED)

    assert Path(first["pdf_path"]).read_bytes() == Path(second["pdf_path"]).read_bytes()
    assert Path(first["blob_path"]).read_bytes() == Path(second["blob_path"]).read_bytes()
    assert Path(first["manifest_path"]).read_bytes() == Path(second["manifest_path"]).read_bytes()


def test_manifest_maps_every_blob_block_back_to_the_original(dataset_dir):
    manifest = _load(dataset_dir / "manifest.json")
    pdf = (dataset_dir / "groundtruth" / "synthetic.pdf").read_bytes()
    blob = (dataset_dir / "evidence" / manifest["blob"]["name"]).read_bytes()

    assert manifest["fragment_count"] == c.EXPECTED_FRAGMENT_COUNT
    assert len(manifest["fragments"]) == c.EXPECTED_FRAGMENT_COUNT
    assert manifest["original"]["sha256"] == _sha(pdf)
    assert manifest["blob"]["sha256"] == _sha(blob)

    for index, fragment in enumerate(manifest["fragments"]):
        start = fragment["blob_offset"]
        assert start == index * c.BLOCK_SIZE
        assert fragment["length"] == c.BLOCK_SIZE
        assert fragment["sha256"] == _sha(blob[start:start + c.BLOCK_SIZE])
        assert (
            blob[start:start + c.BLOCK_SIZE]
            == pdf[fragment["source_offset"]:fragment["source_offset"] + c.BLOCK_SIZE]
        )


def test_manifest_kinds_describe_the_known_pdf_layout(dataset_dir):
    manifest = _load(dataset_dir / "manifest.json")
    ordered = sorted(manifest["fragments"], key=lambda fragment: fragment["original_index"])

    assert [fragment["kind"] for fragment in ordered] == [
        c.KIND_HEADER,
        c.KIND_OBJECT,
        c.KIND_OBJECT,
        c.KIND_OBJECT,
        c.KIND_XREF,
        c.KIND_TRAILER,
        c.KIND_STARTXREF,
        c.KIND_EOF,
    ]
    assert [fragment["object_number"] for fragment in ordered] == [
        None,
        1,
        2,
        3,
        None,
        None,
        None,
        None,
    ]


def test_blob_generation_never_reads_the_manifest(tmp_path):
    """The blob is derived from (pdf, seed) only, never from ground truth."""
    first = write_dataset(tmp_path / "first", seed=c.DEFAULT_SEED)
    Path(first["manifest_path"]).unlink()

    second = write_dataset(tmp_path / "second", seed=c.DEFAULT_SEED)

    assert Path(first["blob_path"]).read_bytes() == Path(second["blob_path"]).read_bytes()
    assert (
        _sha(Path(first["blob_path"]).read_bytes())
        == second["manifest"]["blob"]["sha256"]
    )
