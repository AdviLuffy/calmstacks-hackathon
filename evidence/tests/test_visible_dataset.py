"""Tests for the visible-text synthetic PDF dataset generator and P1 reconstruction."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from trace_evidence.constants import BLOCK_SIZE
from trace_evidence.dataset import (
    VISIBLE_DEFAULT_SEED,
    VISIBLE_EXPECTED_FRAGMENT_COUNT,
    VISIBLE_OBJECT_COUNT,
    VISIBLE_TEXT_CONTENT,
    build_visible_text_pdf,
    split_blocks,
    write_visible_dataset,
)
from trace_evidence.pipeline import run_pipeline

EXPECTED_VISIBLE_PDF_SHA256 = "9decf803a2cc4688356ebe1f6788ab577c637ec0f54cfd9dd52fae3b236435f2"
EXPECTED_VISIBLE_BLOB_SHA256 = "58e7de08b02f1808492632ad09275ee141bab20d994651ef10e2bded8ecaf032"


def test_build_visible_text_pdf_deterministic():
    """Verify that build_visible_text_pdf produces identical bytes on every invocation."""
    pdf1 = build_visible_text_pdf()
    pdf2 = build_visible_text_pdf()

    assert pdf1 == pdf2
    assert len(pdf1) == VISIBLE_EXPECTED_FRAGMENT_COUNT * BLOCK_SIZE
    assert len(pdf1) == 2560
    assert hashlib.sha256(pdf1).hexdigest() == EXPECTED_VISIBLE_PDF_SHA256


def test_visible_pdf_contains_specified_text():
    """Verify that the generated PDF contains the required visible text operator."""
    pdf = build_visible_text_pdf()
    assert VISIBLE_TEXT_CONTENT.encode("ascii") in pdf
    assert b"BT\n/F1 16 Tf\n50 350 Td\n(TRACE FORENSIC RECONSTRUCTION TEST) Tj\nET" in pdf


def test_visible_dataset_disk_files_and_manifest(tmp_path):
    """Verify write_visible_dataset produces expected files, hashes, and manifest structure."""
    res = write_visible_dataset(tmp_path, seed=VISIBLE_DEFAULT_SEED)

    pdf_path = Path(res["pdf_path"])
    blob_path = Path(res["blob_path"])
    manifest = res["manifest"]

    assert pdf_path.is_file()
    assert blob_path.is_file()
    assert len(pdf_path.read_bytes()) == 2560
    assert len(blob_path.read_bytes()) == 2560

    assert manifest["seed"] == VISIBLE_DEFAULT_SEED
    assert manifest["fragment_count"] == 10
    assert manifest["text_content"] == VISIBLE_TEXT_CONTENT
    assert manifest["original"]["sha256"] == EXPECTED_VISIBLE_PDF_SHA256
    assert manifest["blob"]["sha256"] == EXPECTED_VISIBLE_BLOB_SHA256


def test_p1_end_to_end_reconstruction_on_visible_blob(tmp_path):
    """Verify P1 reconstructs the exact original visible-text PDF from the shuffled blob."""
    res = write_visible_dataset(tmp_path, seed=VISIBLE_DEFAULT_SEED)
    blob_path = Path(res["blob_path"])
    gt_bytes = Path(res["pdf_path"]).read_bytes()

    pipeline_result = run_pipeline(blob_path, run_id="RUN-VIS-001")

    assert len(pipeline_result.scan.fragments) == 10
    assert pipeline_result.reconstruction.status == "structurally_valid"
    assert pipeline_result.reconstruction.complete is True
    assert pipeline_result.reconstruction.validation.is_valid is True

    recon_bytes = pipeline_result.reconstruction.raw_bytes
    assert len(recon_bytes) == 2560
    assert hashlib.sha256(recon_bytes).hexdigest() == EXPECTED_VISIBLE_PDF_SHA256
    assert recon_bytes == gt_bytes, "Reconstructed bytes must be 100% byte-for-byte identical to ground truth"
    assert VISIBLE_TEXT_CONTENT.encode("ascii") in recon_bytes
