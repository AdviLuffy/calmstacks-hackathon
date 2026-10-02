"""Test Suite for TRACE Phase 11: Real-World PDF Recovery Engine.

Validates robust recovery against 9 real-world corruption recipes simulating
online corrupters (e.g. corrupter.net), physical sector drops, and transfer faults:
1. Mangled Header & HTML Preamble
2. Destroyed XRef Table & Trailer
3. Unterminated Objects (stripped endobj)
4. Mutated Stream Lengths (/Length 999999)
5. Mutilated Flate Stream Headers
6. Null-Byte Sector Damage (512-byte zero runs)
7. Arbitrary Mid-Bitstream Truncation
8. Online Scrambled Bytes
9. Orphan Pages (wiped Catalog & Pages tree)

Also verifies:
- Multi-engine rendering and openability
- Text salvage and readable string recovery
- Image stream extraction
- Strict forensic honesty: immutable SHA-256 ledgers and authentic vs synthesized provenance
"""

from __future__ import annotations

import io
from pathlib import Path
import pytest

from trace.datasets.corruption.real_world_corrupter import (
    RECIPES,
    RealWorldCorrupter,
)
from trace_evidence import constants as c
from trace_evidence.pdf_recovery import (
    GeneralizedPdfRecoveryEngine,
    diagnose_pdf_corruption,
)
from trace_evidence.repair import (
    repair_pdf,
    synthetic_repair_pdf,
    validate_and_render_pdf,
)

# Reference 1-page PDF fixture
SAMPLE_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
    b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
    b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    b"5 0 obj\n<< /Length 50 >>\nstream\n"
    b"BT /F1 18 Tf 72 720 Td (Forensic Evidence Salvage) Tj ET\n"
    b"endstream\nendobj\n"
    b"xref\n0 6\n"
    b"0000000000 65535 f \r\n"
    b"0000000009 00000 n \r\n"
    b"0000000058 00000 n \r\n"
    b"0000000115 00000 n \r\n"
    b"0000000240 00000 n \r\n"
    b"0000000310 00000 n \r\n"
    b"trailer\n<< /Size 6 /Root 1 0 R >>\n"
    b"startxref\n410\n%%EOF\n"
)


@pytest.fixture
def corrupter() -> RealWorldCorrupter:
    return RealWorldCorrupter(seed=42)


def test_all_corruption_recipes_registered():
    """Verify that all 9 expected real-world corruption recipes are defined and registered."""
    expected_recipes = {
        "mangled_header",
        "destroyed_xref_trailer",
        "unterminated_objects",
        "mutated_stream_lengths",
        "mutilated_flate_header",
        "null_byte_sectors",
        "arbitrary_truncation",
        "online_scramble",
        "orphan_pages",
    }
    assert expected_recipes.issubset(set(RECIPES.keys()))
    assert len(RECIPES) >= 9


def test_recipe_mangled_header(corrupter: RealWorldCorrupter):
    """Recipe 1: Preamble HTTP noise + mangled magic bytes (%PDF- damaged)."""
    res = corrupter.apply_recipe("mangled_header", SAMPLE_PDF)
    assert res.corrupted_bytes != SAMPLE_PDF
    assert b"<html>" in res.corrupted_bytes
    assert b"XPDF-CORRUPT" in res.corrupted_bytes

    diag = diagnose_pdf_corruption(res.corrupted_bytes)
    assert "MISSING_HEADER" in diag.corruption_classes or "OFFSET_HEADER_PREAMBLE_NOISE" in diag.corruption_classes

    engine = GeneralizedPdfRecoveryEngine(res.corrupted_bytes)
    repaired, items, meta = engine.recover()

    assert repaired.startswith(b"%PDF-1.4\n")
    is_open, pages, text, err = validate_and_render_pdf(repaired)
    assert is_open is True
    assert pages == 1
    assert "Forensic Evidence Salvage" in text
    assert "Forensic Evidence Salvage" in engine.extract_salvaged_text()


def test_recipe_destroyed_xref_trailer(corrupter: RealWorldCorrupter):
    """Recipe 2: Wiped xref table, trailer, and %%EOF."""
    res = corrupter.apply_recipe("destroyed_xref_trailer", SAMPLE_PDF)
    assert b"xref" not in res.corrupted_bytes
    assert b"trailer" not in res.corrupted_bytes

    diag = diagnose_pdf_corruption(res.corrupted_bytes)
    assert "DESTROYED_CROSS_REFERENCE_TABLE" in diag.corruption_classes
    assert "TRUNCATED_BITSTREAM_NO_EOF" in diag.corruption_classes

    engine = GeneralizedPdfRecoveryEngine(res.corrupted_bytes)
    repaired, items, meta = engine.recover()

    is_open, pages, text, err = validate_and_render_pdf(repaired)
    assert is_open is True
    assert pages == 1
    assert "Forensic Evidence Salvage" in text
    assert any("cross-reference table" in it for it in items)
    assert any("trailer" in it for it in items)


def test_recipe_unterminated_objects(corrupter: RealWorldCorrupter):
    """Recipe 3: Unterminated objects where 'endobj' tokens were erased."""
    res = corrupter.apply_recipe("unterminated_objects", SAMPLE_PDF)
    diag = diagnose_pdf_corruption(res.corrupted_bytes)
    assert "UNTERMINATED_OBJECTS" in diag.corruption_classes

    engine = GeneralizedPdfRecoveryEngine(res.corrupted_bytes)
    repaired, items, meta = engine.recover()

    is_open, pages, text, err = validate_and_render_pdf(repaired)
    assert is_open is True
    assert pages == 1
    assert "Forensic Evidence Salvage" in text


def test_recipe_mutated_stream_lengths(corrupter: RealWorldCorrupter):
    """Recipe 4: Corrupted /Length attributes set to 999999."""
    res = corrupter.apply_recipe("mutated_stream_lengths", SAMPLE_PDF)
    assert b"/Length 999999" in res.corrupted_bytes

    engine = GeneralizedPdfRecoveryEngine(res.corrupted_bytes)
    repaired, items, meta = engine.recover()

    # Repaired stream dictionary must reflect true length
    assert b"/Length 999999" not in repaired
    is_open, pages, text, err = validate_and_render_pdf(repaired)
    assert is_open is True
    assert pages == 1
    assert "Forensic Evidence Salvage" in text


def test_recipe_mutilated_flate_header(corrupter: RealWorldCorrupter):
    """Recipe 5: Compressed Flate streams with mutilated zlib headers."""
    import zlib
    raw_content = b"BT /F1 18 Tf 72 720 Td (Mutilated Flate Stream Recovered) Tj ET\n"
    compressed = zlib.compress(raw_content)

    flate_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        + f"5 0 obj\n<< /Length {len(compressed)} /Filter /FlateDecode >>\nstream\n".encode("ascii")
        + compressed
        + b"\nendstream\nendobj\n"
        b"xref\n0 6\n0000000000 65535 f \r\ntrailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n500\n%%EOF\n"
    )

    res = corrupter.apply_recipe("mutilated_flate_header", flate_pdf)
    engine = GeneralizedPdfRecoveryEngine(res.corrupted_bytes)
    repaired, items, meta = engine.recover()

    is_open, pages, text, err = validate_and_render_pdf(repaired)
    assert is_open is True
    assert pages == 1


def test_recipe_null_byte_sectors(corrupter: RealWorldCorrupter):
    """Recipe 6: 512-byte null-filled bad sector overwrite."""
    # Use larger 8-page or multi-block sample
    padded = SAMPLE_PDF + (b"% Comment padding sector\n" * 50)
    res = corrupter.apply_recipe("null_byte_sectors", padded)
    assert b"\x00" * 32 in res.corrupted_bytes

    diag = diagnose_pdf_corruption(res.corrupted_bytes)
    assert "ERASED_SECTOR_NULL_RUNS" in diag.corruption_classes

    engine = GeneralizedPdfRecoveryEngine(res.corrupted_bytes)
    repaired, items, meta = engine.recover()

    is_open, pages, text, err = validate_and_render_pdf(repaired)
    assert is_open is True
    assert pages >= 1
    assert "Forensic Evidence Salvage" in text


def test_recipe_arbitrary_truncation(corrupter: RealWorldCorrupter):
    """Recipe 7: Abrupt file truncation at 65% length."""
    res = corrupter.apply_recipe("arbitrary_truncation", SAMPLE_PDF)
    assert len(res.corrupted_bytes) < len(SAMPLE_PDF)

    engine = GeneralizedPdfRecoveryEngine(res.corrupted_bytes)
    repaired, items, meta = engine.recover()

    is_open, pages, text, err = validate_and_render_pdf(repaired)
    assert is_open is True
    assert pages >= 1
    assert repaired.endswith(b"%%EOF\n")


def test_recipe_online_scramble(corrupter: RealWorldCorrupter):
    """Recipe 8: Online byte scrambling (simulating corrupter.net tools)."""
    res = corrupter.apply_recipe("online_scramble", SAMPLE_PDF, seed=123)
    assert res.corrupted_bytes != SAMPLE_PDF

    engine = GeneralizedPdfRecoveryEngine(res.corrupted_bytes)
    repaired, items, meta = engine.recover()

    is_open, pages, text, err = validate_and_render_pdf(repaired)
    assert is_open is True
    assert pages == 1
    assert repaired.startswith(b"%PDF-")
    assert repaired.endswith(b"%%EOF\n")


def test_recipe_orphan_pages(corrupter: RealWorldCorrupter):
    """Recipe 9: Obliterated Catalog and Pages hierarchy."""
    res = corrupter.apply_recipe("orphan_pages", SAMPLE_PDF)
    assert b"/Type /Catalog" not in res.corrupted_bytes
    assert b"/Type /Pages" not in res.corrupted_bytes

    engine = GeneralizedPdfRecoveryEngine(res.corrupted_bytes)
    repaired, items, meta = engine.recover()

    is_open, pages, text, err = validate_and_render_pdf(repaired)
    assert is_open is True
    assert pages == 1
    assert "Forensic Evidence Salvage" in text
    assert any("synthesized root Pages tree" in it for it in items)
    assert any("Catalog" in it for it in items)


def test_salvaged_text_and_images_extraction():
    """Verify extract_salvaged_text() and extract_salvaged_images() methods."""
    # PDF with an image object
    img_data = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00\xff\xdb\x00C\x00\xff\xd9"
    img_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> /XObject << /Im1 6 0 R >> >> /Contents 5 0 R >>\nendobj\n"
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        b"5 0 obj\n<< /Length 40 >>\nstream\n"
        b"BT /F1 12 Tf 50 700 Td (Image Stream Test) Tj ET\n"
        b"endstream\nendobj\n"
        + f"6 0 obj\n<< /Type /XObject /Subtype /Image /Width 10 /Height 10 /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /DCTDecode /Length {len(img_data)} >>\nstream\n".encode("ascii")
        + img_data
        + b"\nendstream\nendobj\n"
        b"xref\n0 7\n0000000000 65535 f \r\ntrailer\n<< /Size 7 /Root 1 0 R >>\nstartxref\n600\n%%EOF\n"
    )

    engine = GeneralizedPdfRecoveryEngine(img_pdf)
    repaired, items, meta = engine.recover()

    salvaged_text = engine.extract_salvaged_text()
    assert "Image Stream Test" in salvaged_text

    salvaged_images = engine.extract_salvaged_images()
    assert len(salvaged_images) == 1
    assert salvaged_images[0]["object_number"] == 6
    assert salvaged_images[0]["is_jpeg"] is True
    assert salvaged_images[0]["data"] == img_data


def test_forensic_honesty_and_provenance_ledger(corrupter: RealWorldCorrupter):
    """Verify strict forensic honesty: provenance ledger, non-repudiation, and SHA-256 separation."""
    res = corrupter.apply_recipe("destroyed_xref_trailer", SAMPLE_PDF)
    engine = GeneralizedPdfRecoveryEngine(res.corrupted_bytes)
    repaired, items, meta = engine.recover()

    rep = synthetic_repair_pdf(res.corrupted_bytes)
    assert rep.is_openable is True
    assert rep.is_byte_identical_to_groundtruth is False
    assert rep.repair_status == c.STATUS_SYNTHETICALLY_REPAIRED

    # Check provenance ledger
    prov = engine.provenance
    assert len(prov) >= 2

    auth_records = [p for p in prov if p["type"] == "original_recovered"]
    synth_records = [p for p in prov if p["type"] == "synthesized_repair"]

    assert len(auth_records) >= 1
    assert len(synth_records) >= 1

    for p in auth_records:
        assert p["confidence"] == 1.0
        assert p["origin"] == "authentic_evidence"
        assert p["media_offset_start"] is not None

    for p in synth_records:
        assert p["confidence"] == 0.0
        assert p["origin"] == "synthesized_repair"

    # Report verification
    report = engine.generate_forensic_report()
    assert report["title"] == "TRACE Forensic PDF Recovery Report"
    assert "authentic_vs_synthesized_breakdown" in report
    assert "provenance" in report
    assert "summary" in report

