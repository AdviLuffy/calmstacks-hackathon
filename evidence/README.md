# TRACE — Subsystem 1: Evidence & Reconstruction Engine

Python package `trace_evidence`. Reconstructs a fragmented file from a raw
evidence blob using the file format's own structure — not guesswork.

## Honesty invariants

1. **Never fabricate bytes.** Output is only ever a concatenation of real
   fragment bytes. A gap is reported, never filled.
2. **Never label a candidate relationship as proven.** Every relationship is
   `candidate`. Only the integrity report may say `verified`, and only after an
   independent byte-for-byte comparison against a known original.
3. **Preserve source evidence.** Evidence is opened read-only; the engine writes
   only into `datasets/output/`.
4. **Provenance is complete.** Every output byte maps back to the fragment and
   source offset it came from.

## Unfrozen contract items

The following items are intentionally **UNFROZEN** and must not be resolved
unilaterally by P1 — they require cross-team coordination with P2/P3:

- **`trace-cj/1.0` canonical serialization algorithm** and the resulting
  `bundle_sha256` field: the exact serialisation rules (key ordering, whitespace,
  encoding) are not yet frozen.
- **Bundle root version key** (`x-canonicalization` or another field): the name
  and semantics are not yet frozen.
- **Formal P3 integrity report schema** in `shared/schemas/`: no schema file has
  been agreed; P1 exposes `IntegrityReport.to_dict()` as a plain dict and
  documents the expected keys.

## MVP scope

One format (a deterministic synthetic PDF) and one vertical slice:
dataset → scan → DNA → relationships → reconstruct → provenance →
integrity/verification.

## Dataset model

`tools/make_dataset.py` reproducibly builds:

- `datasets/groundtruth/synthetic.pdf` — a 3-object PDF (Catalog, Pages, Page)
  with a real xref table, trailer and startxref. Deterministic: no timestamps,
  no randomness.
- `datasets/evidence/blob_1337.bin` — the same PDF split into 8 structure-aligned
  256-byte blocks, shuffled with seed 1337, concatenated. **The blob carries
  no metadata** and is the only input the engine may read in production.
- `datasets/manifest.json` — ground truth, used **only by tests**, never by the
  engine.

Known limitation: fragments are structure-aligned fixed-size blocks, which is
what makes the reconstruction deterministically exact. Arbitrary-offset
fragmentation is a stretch goal; there the engine must report a candidate
ordering instead of a verified one.

## Setup

Windows (PowerShell):

    py -m venv .venv
    .\.venv\Scripts\Activate.ps1
    py -m pip install -r requirements-dev.txt

Linux / macOS:

    python3 -m venv .venv
    source .venv/bin/activate
    python -m pip install -r requirements-dev.txt

> On Windows the bare `python` command may be the Microsoft Store placeholder.
> Use the `py` launcher instead.

## Tests

From the `evidence/` directory:

    py -m pytest -q

Or from the repository root (sets PYTHONPATH explicitly):

    $env:PYTHONPATH = "$PWD\evidence\src"; py -m pytest -v

All 147 tests should pass. Test fixture hashes are frozen:

| File | SHA-256 |
|------|---------|
| `datasets/groundtruth/synthetic.pdf` | `1ba5d499d667001095a9fefa4d57551538f742824bb2e2de1feae5e224d64caf` |
| `datasets/evidence/blob_1337.bin`    | `2ef92ac2f6546f4036fe0223cf55e9ddad03371e30e451837cac03bc7d83ead6` |

## CLI usage

### Generate the dataset (one-time)

    cd evidence
    py tools/make_dataset.py

### Run the end-to-end pipeline

    cd evidence
    py tools/run_pipeline.py

Or with explicit arguments:

    py tools/run_pipeline.py \
        --input datasets/evidence/blob_1337.bin \
        --out datasets/output

Optional flags:

| Flag | Default | Description |
|------|---------|-------------|
| `--input PATH` | `datasets/evidence/blob_1337.bin` | Raw evidence blob |
| `--out DIR` | `datasets/output` | Output directory |
| `--block-size N` | `256` | Fragment carving block size in bytes |
| `--run-id ID` | auto-generated | Volatile run identifier |

### Expected output (no oracle)

```
=== TRACE P1: Evidence & Reconstruction Engine ===
Input evidence media       : datasets/evidence/blob_1337.bin
Output directory           : datasets/output
Run ID                     : <volatile>
Media size                 : 2048 bytes (SHA-256: 2ef92ac2f6546f40...)
Carved fragments           : 8 fragments (256 bytes each)
Evidence bundle written    : datasets/output/evidence_bundle.json
DNA profiles derived       : 1 eof, 1 header, 1 startxref, 1 trailer, 2 body, 2 xref
Candidate relationships    : 7 candidate edges (0 unresolved joins)
Reconstruction status      : structurally_valid (PDF self-validation: PASSED)
Reconstructed file written : datasets/output/reconstructed.pdf (2048 bytes)
Reconstructed SHA-256      : 1ba5d499d667001095a9fefa4d57551538f742824bb2e2de1feae5e224d64caf
Integrity report written   : datasets/output/integrity_report.json
Provenance coverage        : 8 fragments (2048/2048 bytes mapped)
Pipeline complete          : True
==================================================
```

## Output artifacts (in `datasets/output/`)

| File | Contents |
|------|----------|
| `evidence_bundle.json` | Evidence Bundle conforming to `shared/schemas/evidence_bundle.schema.json` |
| `reconstructed.pdf` | Authentic-byte reconstruction (concatenation of original fragment blocks) |
| `integrity_report.json` | Byte provenance + structural validation + optional oracle comparison |

`reconstructed.pdf` bytes are byte-for-byte identical to `groundtruth/synthetic.pdf`.
No bytes are fabricated; the pipeline never reads the ground-truth file.

## Programmatic API

```python
from trace_evidence import run_pipeline, PipelineResult

result: PipelineResult = run_pipeline(
    media_path="datasets/evidence/blob_1337.bin",
    out_dir="datasets/output",
)

print(result.is_complete)            # True
print(result.reconstruction.status) # "structurally_valid"
print(result.integrity_report.reconstructed_sha256)

# Oracle comparison (caller supplies ground truth — engine never reads it)
gt = open("datasets/groundtruth/synthetic.pdf", "rb").read()
verified = run_pipeline(media_path="...", original_bytes=gt)
print(verified.integrity_report.status)  # "verified"
```

## Progress

- [x] Step 1 — skeleton and hashing primitives
- [x] Step 2 — deterministic synthetic PDF, shuffled blob, manifest
- [x] Step 3 — scanning
- [x] Step 4 — evidence DNA
- [x] Step 5 — relationship analysis
- [x] Step 6 — reconstruction and provenance
- [x] Step 7 — integrity and verification
- [x] Step 8 — end-to-end pipeline, CLI, docs
