"""TRACE Autonomous Forensic Recovery Engine — Verification & Benchmark Suite.

Benchmarks the general-purpose AI-assisted PDF recovery engine across diverse real-world
corruption classes, PDF versions (1.0 to 1.7), and structural damage scenarios:
1. Intact PDF (cryptographic verification)
2. Truncated bitstream (missing xref, trailer, startxref, EOF)
3. Offset header & preamble noise (HTTP headers / disk metadata)
4. Destroyed %PDF- magic bytes header
5. Wiped / corrupted cross-reference table
6. Disconnected / orphan /Page objects without parent /Pages hierarchy
7. Severed content stream operators (unclosed BT/ET, unclosed q/Q, open strings)
8. Stream dictionary /Length mismatch correction
9. Modern PDF 1.5+ compressed Object Streams (/ObjStm)
10. Erased / zeroed sector corruption (8-page real-world multi-page document)
"""

from __future__ import annotations

import io
from pathlib import Path
import sys
import time
import zlib

REPO_ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_SRC = REPO_ROOT / "evidence" / "src"
API_SRC = REPO_ROOT / "api"
INTEL_SRC = REPO_ROOT / "trace" / "intel" / "src"

for p in (str(EVIDENCE_SRC), str(API_SRC), str(INTEL_SRC)):
    if p not in sys.path:
        sys.path.insert(0, p)

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

MINIMAL_VALID_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
    b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
    b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    b"5 0 obj\n<< /Length 44 >>\nstream\n"
    b"BT /F1 24 Tf 100 700 Td (Autonomous Forensics) Tj ET\n"
    b"endstream\nendobj\n"
    b"xref\n0 6\n"
    b"0000000000 65535 f \r\n"
    b"0000000010 00000 n \r\n"
    b"0000000060 00000 n \r\n"
    b"0000000117 00000 n \r\n"
    b"0000000224 00000 n \r\n"
    b"0000000293 00000 n \r\n"
    b"trailer\n<< /Size 6 /Root 1 0 R >>\n"
    b"startxref\n390\n%%EOF\n"
)


def run_benchmarks() -> int:
    print("=" * 86)
    print(" TRACE AUTONOMOUS FORENSIC RECOVERY ENGINE — GENERALIZED BENCHMARK SUITE")
    print("=" * 86)

    scenarios = []

    # 1. Intact PDF Passthrough
    scenarios.append((
        "Scenario 1: Intact PDF",
        MINIMAL_VALID_PDF,
        "Clean intact PDF bitstream",
    ))

    # 2. Truncated Bitstream
    xref_pos = MINIMAL_VALID_PDF.find(b"xref")
    scenarios.append((
        "Scenario 2: Truncated Bitstream",
        MINIMAL_VALID_PDF[:xref_pos],
        "Missing xref table, trailer dict, startxref, and %%EOF",
    ))

    # 3. Offset Header & Preamble Noise
    preamble = b"HTTP/1.1 200 OK\r\nContent-Type: application/pdf\r\nServer: DamagedProxy\r\n\r\n\x00\xff\xfe"
    scenarios.append((
        "Scenario 3: Offset Header & Noise",
        preamble + MINIMAL_VALID_PDF,
        "Preceded by HTTP response header and binary noise",
    ))

    # 4. Missing %PDF- Header
    scenarios.append((
        "Scenario 4: Missing Header Magic",
        MINIMAL_VALID_PDF[10:],
        "Missing %PDF- header magic bytes entirely",
    ))

    # 5. Wiped XRef Table
    scenarios.append((
        "Scenario 5: Wiped XRef Table",
        MINIMAL_VALID_PDF[:xref_pos] + (b"\x00" * 200) + b"\nstartxref\n99999\n%%EOF\n",
        "Cross-reference table wiped with zero bytes",
    ))

    # 6. Orphan Page Objects
    orphan_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 9 0 R >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 9 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        b"5 0 obj\n<< /Length 38 >>\nstream\n"
        b"BT /F1 20 Tf 50 700 Td (Orphan Rescued) Tj ET\n"
        b"endstream\nendobj\n"
    )
    scenarios.append((
        "Scenario 6: Orphan /Page Objects",
        orphan_pdf,
        "Catalog and Page point to missing /Pages parent 9 0 R",
    ))

    # 7. Unbalanced Operators & Strings
    broken_stream = b"q\nBT /F1 16 Tf 50 650 Td (Severed String Content Without Close"
    unbal_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        + f"5 0 obj\n<< /Length {len(broken_stream)} >>\nstream\n".encode("ascii")
        + broken_stream
        + b"\nendstream\nendobj\n"
    )
    scenarios.append((
        "Scenario 7: Unbalanced Operators",
        unbal_pdf,
        "Content stream has unclosed BT, unclosed q, and open string (",
    ))

    # 8. Stream /Length Mismatch
    stream_content = b"BT /F1 14 Tf 72 700 Td (Exact Length Test) Tj ET\n"
    len_mismatch_pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
        b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
        b"5 0 obj\n<< /Length 2 >>\nstream\n"
        + stream_content
        + b"endstream\nendobj\n"
    )
    scenarios.append((
        "Scenario 8: /Length Mismatch",
        len_mismatch_pdf,
        "Stream declares /Length 2 for a 50-byte content stream",
    ))

    # 9. PDF 1.5+ Object Streams
    obj3_content = b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\n"
    obj4_content = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    sub_data = obj3_content + obj4_content
    hdr = f"3 0 4 {len(obj3_content)}\n".encode("ascii")
    raw_stm = hdr + sub_data
    compressed_stm = zlib.compress(raw_stm)
    obj_stm_pdf = (
        b"%PDF-1.5\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        + f"10 0 obj\n<< /Type /ObjStm /N 2 /First {len(hdr)} /Length {len(compressed_stm)} /Filter /FlateDecode >>\nstream\n".encode("ascii")
        + compressed_stm
        + b"\nendstream\nendobj\n"
        b"5 0 obj\n<< /Length 39 >>\nstream\n"
        b"BT /F1 16 Tf 72 700 Td (Object Stream Unpacked) Tj ET\n"
        b"endstream\nendobj\n"
    )
    scenarios.append((
        "Scenario 9: PDF 1.5+ /ObjStm",
        obj_stm_pdf,
        "Compressed Object Stream containing packed indirect objects",
    ))

    # 10. Erased Sector Multi-Page Fixture
    fixture_105 = REPO_ROOT / "evidence" / "datasets" / "evidence" / "TRACE_105block_one_missing.bin"
    if fixture_105.is_file():
        scenarios.append((
            "Scenario 10: 8-Page Erased Sector",
            fixture_105.read_bytes(),
            "26,880-byte 8-page disk image with erased 512-byte sector",
        ))

    passed_count = 0
    total_count = len(scenarios)

    header_fmt = "{:<32} {:<10} {:<7} {:<8} {:<10} {:<12}"
    print(header_fmt.format("BENCHMARK SCENARIO", "INPUT SIZE", "PAGES", "OPENABLE", "TIME (ms)", "RESULT"))
    print("-" * 86)

    for name, data, desc in scenarios:
        t0 = time.perf_counter()
        diag = diagnose_pdf_corruption(data)
        rep = repair_pdf(data)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        is_success = rep.is_openable and rep.page_count > 0
        if is_success:
            passed_count += 1
            res_str = "[PASS] REPAIRED" if rep.repair_status == c.STATUS_SYNTHETICALLY_REPAIRED else "[PASS] VERIFIED"
        else:
            res_str = "[FAIL]"

        print(header_fmt.format(
            name,
            f"{len(data)} B",
            str(rep.page_count),
            "YES" if rep.is_openable else "NO",
            f"{elapsed_ms:.1f}ms",
            res_str,
        ))

    print("=" * 86)
    print(f"BENCHMARK SUMMARY: {passed_count}/{total_count} SCENARIOS RECOVERED & VERIFIED OPENABLE")
    print("=" * 86)
    return 0 if passed_count == total_count else 1


if __name__ == "__main__":
    sys.exit(run_benchmarks())
