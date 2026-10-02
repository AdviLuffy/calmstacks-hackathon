# TRACE Forensic Fragment Classifier (Phase 7)

## Overview

The **TRACE Forensic Fragment Classifier** is a lightweight, local-first machine learning pipeline designed to classify raw binary evidence fragments and candidate objects carved from damaged documents into structural forensic categories.

Categories classified:
- `PDF_HEADER`: File magic and PDF header signatures (`%PDF-1.x`)
- `PDF_OBJECT`: Indirect object dictionary containers (`obj ... endobj`)
- `PDF_STREAM`: Generic compressed or raw data streams
- `TEXT_STREAM`: Content streams containing visual text rendering operators (`BT ... ET`, `Tj`, `TJ`)
- `IMAGE_STREAM`: Embedded raster graphics or DCT/JPX compressed streams
- `FONT_OBJECT`: Embedded fonts and glyph metric definitions (`/Type /Font`)
- `PAGE_OBJECT`: Document page dictionary and layout nodes (`/Type /Page`)
- `XREF`: Cross-reference tables and subsections
- `TRAILER`: Document trailer dictionaries, `startxref`, and `%%EOF`
- `METADATA`: Extensible Metadata Platform (XMP) and document information streams
- `UNKNOWN`: Unstructured binary noise, corrupted payloads, or padding bytes

---

## Key Principles & Guardrails

1. **Local-First & Offline**: Executes on local CPU using standard scikit-learn models. Requires zero GPU, zero internet connection, and zero Gemini API calls.
2. **Deterministic Precedence**: The ML model serves as an advisory enrichment layer (`ML_DETECTED`). The deterministic forensic recovery engine remains the final authority for physical byte reassembly.
3. **Zero Split Leakage**: Dataset splits (`train`, `validation`, `test`, `hard_test`) are strictly partitioned at the **document level**. Fragments originating from the same document never cross partition boundaries.
4. **Transparent Baselines**: The ML classifier is continuously benchmarked against both a **Rule-Based Structural Baseline** and a **Majority-Class Baseline**.
5. **Confidence & Abstention**: Predictions below the configured confidence threshold (default `0.50`) are rejected as abstentions (`UNKNOWN`), preventing speculative false positives.
6. **Graceful Fallback**: If the model artifact is missing or corrupted, the runtime inference engine seamlessly falls back to deterministic rule-based classification (`FALLBACK_RULE`).

---

## Feature Extraction (33 Explainable Features)

The feature extractor (`FragmentFeatureExtractor`) computes deterministic, byte-level and structural indicators without label leakage:

| Feature Name | Description |
| :--- | :--- |
| `length` | Byte size of the carved fragment |
| `printable_ratio` | Fraction of printable ASCII characters (32-126, \r, \n, \t) |
| `whitespace_ratio` | Fraction of space and newline characters |
| `null_byte_ratio` | Fraction of `0x00` null padding bytes |
| `high_byte_ratio` | Fraction of high-order bytes (>127, indicating binary/compressed streams) |
| `digit_ratio` | Fraction of ASCII digit characters |
| `shannon_entropy` | Byte-level Shannon entropy (0.0 to 8.0 bits/byte) |
| `starts_with_pdf_magic` | Flag indicating `%PDF` magic at start |
| `starts_with_dict_open` | Flag indicating `<<` dictionary delimiter at start |
| `has_dict_open` / `close` | Presence of dictionary boundary tokens |
| `token_count_obj` / `endobj` | Count of indirect object delimiters |
| `token_count_stream` / `endstream` | Count of stream boundary markers |
| `token_count_xref` / `trailer` | Count of cross-reference and trailer tokens |
| `token_count_startxref` / `eof` | Count of file termination signatures |
| `has_type_page` / `font` / `catalog` | Detection of PDF `/Type` dictionary keys |
| `has_subtype_image` | Detection of `/Subtype /Image` or DCT/JPX filters |
| `has_bt_et_text_ops` | Detection of text block operators (`BT`, `ET`, `Tj`, `TJ`) |
| `slash_name_count` | Number of PDF name tokens (`/Name`) |
| `is_compressed_candidate` | Detection of zlib compression headers (`0x789c`, `0x7801`) or high entropy |

---

## Artifact Directory Layout

```
trace/ml/artifacts/fragment_classifier/
├── model.joblib             # Serialized scikit-learn ensemble model
├── metadata.json            # Model version, hyperparameters, class labels, feature importances
├── feature_config.json      # Ordered feature definitions
├── training_dataset.json    # Cached partition dataset (splits: train, validation, test)
├── evaluation_report.json   # Precision, recall, F1, confusion matrix, and latency
└── model_comparison.json    # Comparative metrics vs. Rule-Based & Majority baselines
```

---

## CLI Usage (PowerShell)

### 1. Train Classifier & Evaluate Baselines

```powershell
$env:PYTHONPATH=".;evidence/src;trace;api"
py -3.14 -m trace.ml.training.train_fragment_classifier `
    --output-dir "trace/ml/artifacts/fragment_classifier" `
    --n-estimators 100 `
    --max-depth 16 `
    --abstention-threshold 0.50 `
    --sample-count 12 `
    --seed 42
```

### 2. Run Inference in Python

```python
from trace.ml.inference.fragment_predictor import get_default_fragment_predictor

predictor = get_default_fragment_predictor()
prediction = predictor.predict_fragment(b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj")

print(f"Predicted: {prediction.predicted_label}")
print(f"Confidence: {prediction.confidence:.2%}")
print(f"Provenance: {prediction.provenance}")
print(f"Abstained: {prediction.abstained}")
```
