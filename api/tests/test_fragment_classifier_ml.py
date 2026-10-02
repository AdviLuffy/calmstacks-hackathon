"""Comprehensive tests for TRACE Phase 7 Local ML Fragment Classifier.

Verifies:
- Feature extraction determinism and explainability
- Ground-truth label builder accuracy
- Zero split leakage (document partition isolation)
- Rule-based and majority baseline classifiers
- Multiclass evaluation metrics & confusion matrix
- Abstention threshold and confidence scoring
- Predictor fallback when model weights are uninitialized
- Zero Gemini calls and zero network requests
"""

from __future__ import annotations

import json
from pathlib import Path
import pytest

from trace.datasets.schemas.ground_truth import FragmentLabel
from trace.datasets.generators import SyntheticDocumentGenerator
from trace.ml.features.fragment_features import (
    FragmentFeatureExtractor,
    extract_fragment_features,
    FEATURE_NAMES,
)
from trace.ml.datasets.label_builder import (
    FragmentLabelBuilder,
    build_labeled_fragments_from_document,
)
from trace.ml.datasets.fragment_dataset import (
    FragmentDataset,
    FragmentSample,
    build_dataset_from_samples,
)
from trace.ml.models.fragment_classifier import (
    ForensicFragmentClassifier,
    FragmentPrediction,
    MajorityClassBaselineClassifier,
    RuleBasedBaselineClassifier,
)
from trace.ml.training.evaluation import (
    compare_models,
    evaluate_predictions,
    EvaluationReport,
)
from trace.ml.inference.fragment_predictor import FragmentPredictor


def test_feature_extractor_completeness():
    extractor = FragmentFeatureExtractor()
    assert len(extractor.feature_names) == 33
    assert "shannon_entropy" in extractor.feature_names
    assert "printable_ratio" in extractor.feature_names

    # Test empty fragment
    feats_empty = extractor.extract_features(b"")
    assert all(v == 0.0 for v in feats_empty.values())

    # Test PDF header fragment
    pdf_hdr = b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"
    feats_hdr = extractor.extract_features(pdf_hdr)
    assert feats_hdr["starts_with_pdf_magic"] == 1.0
    assert feats_hdr["length"] == len(pdf_hdr)
    assert feats_hdr["shannon_entropy"] > 0.0

    # Test text stream fragment
    text_frag = b"BT /F1 12 Tf 72 712 Td (Evidence Analysis) Tj ET"
    feats_text = extractor.extract_features(text_frag)
    assert feats_text["has_bt_et_text_ops"] == 1.0
    assert feats_text["token_count_bt"] == 1.0
    assert feats_text["token_count_et"] == 1.0
    assert feats_text["token_count_tj"] == 1.0


def test_label_builder_with_synthetic_pdf():
    generator = SyntheticDocumentGenerator()
    pdf_bytes = generator.generate(page_count=1, seed=101, doc_size="SMALL")
    assert len(pdf_bytes) > 0

    builder = FragmentLabelBuilder()
    smap = builder.build_structural_map(pdf_bytes, doc_id="test_doc_101")
    assert smap.total_bytes == len(pdf_bytes)
    assert len(smap.regions) > 0

    # Check that header region was found
    header_regs = [r for r in smap.regions if r.label == FragmentLabel.PDF_HEADER]
    assert len(header_regs) == 1
    assert header_regs[0].start == 0

    # Check fragment carving
    fragments = build_labeled_fragments_from_document(
        pdf_bytes,
        doc_id="test_doc_101",
        block_sizes=(256,),
    )
    assert len(fragments) > 0
    # First fragment should overlap header
    assert fragments[0]["label"] == FragmentLabel.PDF_HEADER.value
    assert fragments[0]["is_exact"] is True


def test_dataset_split_isolation_and_leakage_detection():
    samples_by_doc = {
        "doc_alpha": [
            {"fragment_id": "frag_a1", "offset": 0, "length": 256, "label": "PDF_HEADER", "bytes": b"%PDF-1.4\n"},
            {"fragment_id": "frag_a2", "offset": 256, "length": 256, "label": "PDF_OBJECT", "bytes": b"1 0 obj <<>> endobj"},
        ],
        "doc_beta": [
            {"fragment_id": "frag_b1", "offset": 0, "length": 256, "label": "PDF_HEADER", "bytes": b"%PDF-1.4\n"},
            {"fragment_id": "frag_b2", "offset": 256, "length": 256, "label": "PAGE_OBJECT", "bytes": b"/Type /Page"},
        ],
        "doc_gamma": [
            {"fragment_id": "frag_g1", "offset": 0, "length": 256, "label": "PDF_HEADER", "bytes": b"%PDF-1.4\n"},
            {"fragment_id": "frag_g2", "offset": 256, "length": 256, "label": "TRAILER", "bytes": b"trailer <<>>"},
        ],
    }

    dataset = build_dataset_from_samples(
        samples_by_doc=samples_by_doc,
        train_ratio=0.34,
        val_ratio=0.33,
        test_ratio=0.33,
        seed=42,
    )

    # Document isolation verification
    assert dataset.verify_no_document_leakage() is True

    # Intentionally introduce leakage to verify detector works
    leaked_sample = FragmentSample(
        sample_id="leaked",
        doc_id=dataset.train_split.doc_ids[0],
        fragment_id="leaked_frag",
        offset=0,
        length=256,
        label="UNKNOWN",
        is_exact=False,
        features={},
    )
    dataset.test_split.doc_ids.append(dataset.train_split.doc_ids[0])
    dataset.test_split.samples.append(leaked_sample)

    with pytest.raises(ValueError, match="Document leakage detected"):
        dataset.verify_no_document_leakage()


def test_rule_based_and_majority_baselines():
    rule_clf = RuleBasedBaselineClassifier()
    pred_hdr = rule_clf.predict_bytes(b"%PDF-1.7\n")
    assert pred_hdr.predicted_label == FragmentLabel.PDF_HEADER.value
    assert pred_hdr.provenance == "RULE_BASELINE"

    pred_xref = rule_clf.predict_bytes(b"xref\n0 5\n0000000000 65535 f \n")
    assert pred_xref.predicted_label == FragmentLabel.XREF.value

    pred_text = rule_clf.predict_bytes(b"BT /F1 10 Tf (hello) Tj ET")
    assert pred_text.predicted_label == FragmentLabel.TEXT_STREAM.value

    pred_unknown = rule_clf.predict_bytes(b"\x00\x01\x02\x03\x04\x05")
    assert pred_unknown.predicted_label == FragmentLabel.UNKNOWN.value

    # Majority baseline
    majority_clf = MajorityClassBaselineClassifier()
    majority_clf.fit(["PDF_STREAM", "PDF_STREAM", "PDF_OBJECT", "UNKNOWN"])
    assert majority_clf.majority_label == "PDF_STREAM"
    preds = majority_clf.predict(3)
    assert len(preds) == 3
    assert all(p.predicted_label == "PDF_STREAM" for p in preds)


def test_evaluation_metrics_and_comparison():
    y_true = ["PDF_HEADER", "PAGE_OBJECT", "TEXT_STREAM", "UNKNOWN", "TEXT_STREAM"]
    predictions = [
        FragmentPrediction(predicted_label="PDF_HEADER", confidence=0.95),
        FragmentPrediction(predicted_label="PAGE_OBJECT", confidence=0.88),
        FragmentPrediction(predicted_label="TEXT_STREAM", confidence=0.72),
        FragmentPrediction(predicted_label="UNKNOWN", confidence=0.40, abstained=True),
        FragmentPrediction(predicted_label="PDF_STREAM", confidence=0.55),  # Misclassified
    ]

    report = evaluate_predictions(
        y_true=y_true,
        predictions=predictions,
        model_name="TestModel",
        split_name="test",
        elapsed_time_sec=0.005,
    )

    assert report.sample_count == 5
    assert report.accuracy == 0.80  # 4/5
    assert report.abstention_rate == 0.20  # 1/5
    assert report.mean_latency_us > 0.0
    assert "PDF_HEADER" in report.per_class
    assert report.per_class["PDF_HEADER"].precision == 1.0
    assert report.per_class["PDF_HEADER"].recall == 1.0

    # Model comparison
    baseline_predictions = [
        FragmentPrediction(predicted_label="UNKNOWN", confidence=0.5) for _ in range(5)
    ]
    baseline_report = evaluate_predictions(
        y_true=y_true,
        predictions=baseline_predictions,
        model_name="BaselineModel",
        split_name="test",
    )

    comparison = compare_models([report, baseline_report])
    assert len(comparison["summary"]) == 2
    assert comparison["best_accuracy"]["model"] == "TestModel"


def test_fragment_predictor_fallback_and_telemetry(tmp_path):
    empty_dir = tmp_path / "nonexistent_model_dir"
    predictor = FragmentPredictor(model_dir=empty_dir, enable_fallback=True)

    assert predictor.is_ml_active is False
    telemetry = predictor.get_telemetry()
    assert telemetry["is_ml_active"] is False

    # Predict fragment should gracefully fall back to rule baseline without error
    pred = predictor.predict_fragment(b"%PDF-1.4\n")
    assert pred.predicted_label == FragmentLabel.PDF_HEADER.value
    assert pred.provenance == "FALLBACK_RULE"
    assert pred.confidence > 0.5


def test_zero_gemini_cloud_calls(monkeypatch):
    # Verify ML classifier operations function completely offline with zero API key
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("TRACE_GEMINI_API_KEY", raising=False)

    predictor = FragmentPredictor()
    pred = predictor.predict_fragment(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj")
    assert pred.predicted_label in ("PDF_HEADER", "PDF_OBJECT", "UNKNOWN")
    assert pred.provenance in ("ML_DETECTED", "FALLBACK_RULE")


def test_classifier_fit_save_load_and_abstention(tmp_path):
    # Prepare small training dataset
    X = [
        [100.0, 0.9, 0.1, 0.0, 0.0, 0.0, 4.5, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 20.0, 0.0],
        [256.0, 0.8, 0.2, 0.0, 0.0, 0.0, 5.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 5.0, 30.0, 0.0],
        [512.0, 0.1, 0.0, 0.0, 0.9, 0.0, 7.8, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 2.0, 1.0],
        [128.0, 0.9, 0.3, 0.0, 0.0, 0.5, 3.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 15.0, 0.0],
    ]
    y = ["PDF_HEADER", "PAGE_OBJECT", "PDF_STREAM", "XREF"]

    clf = ForensicFragmentClassifier(n_estimators=10, max_depth=4, abstention_threshold=0.40)
    clf.fit(X, y)

    assert clf.is_trained is True
    assert set(clf.classes_) == set(y)

    # Predict vector
    pred = clf.predict_features(X[0])
    assert pred.predicted_label == "PDF_HEADER"
    assert pred.confidence >= 0.40
    assert pred.abstained is False
    assert pred.provenance == "ML_DETECTED"

    # Abstention test with high cutoff
    clf.abstention_threshold = 0.999
    abstained_pred = clf.predict_features(X[0])
    assert abstained_pred.abstained is True
    assert abstained_pred.predicted_label == FragmentLabel.UNKNOWN.value

    # Reset threshold & Save model
    clf.abstention_threshold = 0.40
    saved = clf.save_model(tmp_path / "model_ckpt")
    assert Path(saved["model_file"]).exists()
    assert Path(saved["metadata_file"]).exists()

    # Load model
    loaded_clf = ForensicFragmentClassifier.load_model(tmp_path / "model_ckpt")
    assert loaded_clf.is_trained is True
    loaded_pred = loaded_clf.predict_features(X[0])
    assert loaded_pred.predicted_label == "PDF_HEADER"
    assert loaded_pred.confidence == pred.confidence


def test_local_provider_ml_enrichment(tmp_path):
    from trace.ml.providers.local import LocalProvider
    from trace.ml.inference import fragment_predictor

    # Train and save a model in tmp_path
    X = [
        [100.0, 0.9, 0.1, 0.0, 0.0, 0.0, 4.5, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 20.0, 0.0],
        [256.0, 0.8, 0.2, 0.0, 0.0, 0.0, 5.0, 0.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 5.0, 30.0, 0.0],
    ]
    y = ["PDF_HEADER", "PAGE_OBJECT"]

    model_dir = tmp_path / "test_provider_model"
    clf = ForensicFragmentClassifier(n_estimators=10, max_depth=4, abstention_threshold=0.30)
    clf.fit(X, y)
    clf.save_model(model_dir)

    # Set predictor singleton to use this test model
    test_predictor = FragmentPredictor(model_dir=model_dir)
    assert test_predictor.is_ml_active is True
    orig_predictor = fragment_predictor._GLOBAL_PREDICTOR
    fragment_predictor._GLOBAL_PREDICTOR = test_predictor

    try:
        provider = LocalProvider()
        res = provider.classify_fragment("frag_001", b"%PDF-1.4\n%header")
        assert res["likely_file_type"] == "pdf"
        assert "ml_enrichment" in res
        assert res["ml_enrichment"]["ml_provenance"] == "ML_DETECTED"
    finally:
        fragment_predictor._GLOBAL_PREDICTOR = orig_predictor

