# TRACE P1 Forensic Reconstruction Engine: Judge Demonstration Guide

## Executive Overview

The TRACE P1 deterministic reconstruction engine recovers fragmented digital evidence without guessing, padding, or fabricating missing bytes. It operates strictly on authentic carved blocks using structural DNA markers (PDF headers, objects, xref tables, trailers, and EOF terminators) to build deterministic candidate graphs.

This benchmark provides **three independently testable, reproducible scenarios** with documented ground truth:

| Scenario | Evidence Blob | Ground Truth Reference | Expected State | Coverage | Integrity Verification |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **A. Complete Shuffled** | `judge_complete_shuffled.bin` | `judge_groundtruth.pdf` | `COMPLETE AND VERIFIED` | 100.0% | Exact byte-for-byte SHA-256 match |
| **B. Missing Fragments** | `judge_missing_fragment.bin` | `judge_groundtruth.pdf` | `PARTIAL` | 80.0% | Authentic partial prefix; non-verified |
| **C. Corrupted Fragment** | `judge_corrupted_fragment.bin` | `judge_groundtruth.pdf` | `CORRUPTED` | N/A | Integrity failure detected; refused verification |

---

## The 4 Truthful Recovery States

TRACE strictly prohibits deceptive reporting:
1. **`COMPLETE AND VERIFIED`**: All expected structural blocks are present, graph reassembly is complete with zero unplaced fragments, PDF syntax validates, and independent byte-for-byte comparison matches ground truth.
2. **`PARTIAL`**: Missing fragments are identified, an authentic partial artifact is produced from placed blocks, byte coverage is truthfully reported as `< 100%`, and the artifact is NEVER marked as verified or complete.
3. **`CORRUPTED`**: Available evidence contains altered bytes, hash mismatches, or syntax conflicts. TRACE reports the exact failure and refuses to claim recovery.
4. **`UNRECOVERABLE`**: Missing headers, cycle conflicts, or 0-byte media prevent reconstruction. Handled gracefully without crashing.

---

## Scenario Walkthrough & How to Reproduce

### Method 1: Web Interface (One-Click Reproduction)

1. Start the TRACE server:
   ```bash
   py run_trace.py
   ```
2. Open your browser at **`http://127.0.0.1:8000`**.
3. In the **`[FAST-INGEST] DETERMINISTIC TEST FIXTURES`** panel, click any of the judge buttons:

#### Scenario A — Complete Shuffled Recovery:
- Click **`[JUDGE A] Complete Shuffled (10 frags • 100% Verified)`**.
- **Result**:
  - State: **`COMPLETE AND VERIFIED`** (green badge).
  - Fragments: **`10 / 10 placed (0 unplaced)`**.
  - Byte Coverage: **`100.0%`**.
  - Reconstructed SHA-256: Matches ground truth `d0a111d5f4eb45b2da317762d95d7a32a54eac00593ece9cc4b7c494c0367483`.
  - Artifact Download: Valid PDF opens cleanly in Adobe Acrobat / browser, displaying text:
    `"TRACE FORENSIC RECONSTRUCTION BENCHMARK - JUDGE EVALUATION"`.

#### Scenario B — Missing Fragment Partial Recovery:
- Click **`[JUDGE B] Missing Fragment (8 frags • Partial)`**.
- **Result**:
  - State: **`PARTIAL`** (amber badge).
  - Fragments: **`8 / 8 placed`** (missing trailing blocks: Startxref and EOF).
  - Byte Coverage: **`80.0%`** (2,048 of 2,560 bytes).
  - Missing Elements: Clearly lists:
    - `• missing structural fragment: startxref pointer`
    - `• missing structural fragment: EOF terminator (%%EOF)`
  - Verification: **`NOT VERIFIED`** (no false claim of completeness).
  - Artifact Download: Downloads partial authentic prefix.

#### Scenario C — Corrupted Fragment Detection:
- Click **`[JUDGE C] Corrupted Fragment (10 frags • Detected)`**.
- **Result**:
  - State: **`CORRUPTED`** (red badge).
  - Detection: Detects deliberate byte alteration in Object 1.
  - Notice: Integrity failure reported at offset 289; verification refused.
  - Verification: **`NOT VERIFIED`** (prevents poisoned evidence acceptance).

---

### Method 2: Automated CLI / Test Suite

Run the dedicated automated judge regression suite:
```bash
py -m pytest evidence/tests/test_judge_fixture.py -v
```

Expected output:
```text
test_scenario_a_complete_shuffled_reconstruction PASSED
test_scenario_b_missing_fragment_partial_reconstruction PASSED
test_scenario_c_corrupted_fragment_detection PASSED
test_empty_evidence_handled_truthfully PASSED
test_validate_fragment_collection_detects_anomalies PASSED
test_fragment_tamper_raises_corruption_error PASSED
6 passed in 0.25s
```

Run the complete project test suite:
```bash
py -m pytest evidence/tests trace/intel/tests api/tests
```
**Total Passing: 379 / 379 tests.**

---

### Method 3: Python Interactive Script

Execute directly via Python:
```python
from pathlib import Path
from trace_evidence.pipeline import run_pipeline

gt = Path("evidence/datasets/groundtruth/judge_groundtruth.pdf").read_bytes()

# Scenario A:
res_a = run_pipeline("evidence/datasets/evidence/judge_complete_shuffled.bin", original_bytes=gt)
print("A:", res_a.recovery_state, res_a.integrity_report.is_verified)
# Output: A: COMPLETE AND VERIFIED True

# Scenario B:
res_b = run_pipeline("evidence/datasets/evidence/judge_missing_fragment.bin", original_bytes=gt)
print("B:", res_b.recovery_state, res_b.integrity_report.missing_elements)
# Output: B: PARTIAL ('missing structural fragment: startxref pointer', 'missing structural fragment: EOF terminator (%%EOF)')

# Scenario C:
res_c = run_pipeline("evidence/datasets/evidence/judge_corrupted_fragment.bin", original_bytes=gt)
print("C:", res_c.recovery_state, res_c.integrity_report.warnings)
# Output: C: CORRUPTED ('byte mismatch against original at offset 289...', )
```

---

## Known Boundaries & Remaining Limitations

1. **Block Boundary Alignment**: The deterministic P1 structural carver relies on fixed-block boundaries (256-byte sectors). Arbitrary, non-aligned cuts through binary markers without sector indexing requires multi-pass probabilistic carving.
2. **Supported Formats**: The structural DNA graph reassembly is currently tailored to PDF grammar (ISO 32000-1). Other media formats (ZIP, PNG, SQLite) use the Multi-Format File Header Carver without topological graph reassembly.
