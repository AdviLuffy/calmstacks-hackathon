"""CLI and pipeline for training the TRACE Forensic Fragment Classifier.

Features:
- Deterministic training on CPU
- Transparent comparison against Rule-Based and Majority Baselines
- Zero Gemini / external network dependencies
- Verifies document-level partition isolation (zero split leakage)
- Exports versioned model, metadata, and evaluation reports
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from trace.datasets.generators import SyntheticDocumentGenerator
from trace.ml.datasets.fragment_dataset import (
    FragmentDataset,
    build_dataset_from_samples,
)
from trace.ml.datasets.label_builder import build_labeled_fragments_from_document
from trace.ml.models.fragment_classifier import (
    ForensicFragmentClassifier,
    MajorityClassBaselineClassifier,
    RuleBasedBaselineClassifier,
)
from trace.ml.training.evaluation import (
    compare_models,
    evaluate_predictions,
    EvaluationReport,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("train_fragment_classifier")


def generate_training_corpus(
    sample_count: int = 15,
    seed: int = 42,
    block_sizes: Sequence[int] = (256, 512),
) -> Dict[str, List[Dict[str, Any]]]:
    """Synthesize diverse PDF documents and carve labeled fragments."""
    logger.info("Generating %d synthetic documents for fragment corpus...", sample_count)
    generator = SyntheticDocumentGenerator()
    doc_sizes = ["SMALL", "MEDIUM", "LARGE"]

    corpus: Dict[str, List[Dict[str, Any]]] = {}

    for i in range(sample_count):
        active_seed = seed + i * 37
        doc_size = doc_sizes[i % len(doc_sizes)]
        pages = 2 if doc_size == "SMALL" else (5 if doc_size == "MEDIUM" else 11)
        pdf_bytes = generator.generate(
            page_count=pages,
            seed=active_seed,
            doc_size=doc_size,
        )
        doc_id = f"doc_{doc_size}_{active_seed}"
        labeled_frags = build_labeled_fragments_from_document(
            pdf_bytes,
            doc_id=doc_id,
            block_sizes=block_sizes,
        )
        corpus[doc_id] = labeled_frags
        logger.info("  Synthesized %s: %d bytes, %d carved fragments", doc_id, len(pdf_bytes), len(labeled_frags))

    return corpus


def run_training_pipeline(
    dataset_path: Optional[str] = None,
    output_dir: str = "trace/ml/artifacts/fragment_classifier",
    n_estimators: int = 100,
    max_depth: Optional[int] = 16,
    abstention_threshold: float = 0.50,
    seed: int = 42,
    generate_if_missing: bool = True,
    sample_count: int = 12,
) -> Dict[str, Any]:
    """Execute complete training, baseline comparison, and artifact serialization."""
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1. Dataset Acquisition
    if dataset_path and Path(dataset_path).exists():
        logger.info("Loading existing dataset from %s", dataset_path)
        dataset = FragmentDataset.load_json(dataset_path)
    else:
        if not generate_if_missing:
            raise FileNotFoundError(f"Dataset path {dataset_path} does not exist and generate_if_missing=False")
        logger.info("Synthesizing fragment dataset from scratch (seed=%d)...", seed)
        corpus = generate_training_corpus(sample_count=sample_count, seed=seed)
        dataset = build_dataset_from_samples(
            samples_by_doc=corpus,
            train_ratio=0.60,
            val_ratio=0.20,
            test_ratio=0.20,
            seed=seed,
        )
        # Cache dataset JSON
        dataset_save_path = out_dir / "training_dataset.json"
        dataset.save_json(dataset_save_path)
        logger.info("Saved dataset JSON to %s", dataset_save_path)

    # 2. Strict Partition Validation (Zero split leakage)
    dataset.verify_no_document_leakage()
    summary = dataset.summary()
    logger.info("Dataset summary: %s", json.dumps(summary["splits"], indent=2))

    X_train, y_train = dataset.get_feature_matrix("train")
    X_val, y_val = dataset.get_feature_matrix("validation")
    X_test, y_test = dataset.get_feature_matrix("test")

    logger.info("Split sizes - Train: %d, Validation: %d, Test: %d", len(y_train), len(y_val), len(y_test))

    # 3. Fit ML Model
    logger.info("Training ForensicFragmentClassifier (n_estimators=%d, max_depth=%s)...", n_estimators, max_depth)
    model = ForensicFragmentClassifier(
        model_version="1.0.0",
        abstention_threshold=abstention_threshold,
        feature_names=dataset.feature_names,
        n_estimators=n_estimators,
        max_depth=max_depth,
        random_state=seed,
    )

    t0 = time.perf_counter()
    model.fit(X_train, y_train)
    fit_duration = time.perf_counter() - t0
    logger.info("Model fitted successfully in %.3f seconds", fit_duration)

    # 4. Fit Majority Baseline
    majority_baseline = MajorityClassBaselineClassifier()
    majority_baseline.fit(y_train)

    # 5. Rule-Based Baseline
    rule_baseline = RuleBasedBaselineClassifier()

    # 6. Evaluation on Validation & Test Sets
    reports: List[EvaluationReport] = []

    # Evaluate ML Model
    t_inf_start = time.perf_counter()
    ml_test_preds = [model.predict_features(x) for x in X_test]
    inf_duration = time.perf_counter() - t_inf_start
    ml_test_report = evaluate_predictions(
        y_true=y_test,
        predictions=ml_test_preds,
        model_name="ForensicFragmentClassifier",
        split_name="test",
        elapsed_time_sec=inf_duration,
    )
    reports.append(ml_test_report)

    # Evaluate Rule Baseline
    # Convert test samples back to bytes or extract using features
    test_samples = dataset.get_split("test").samples
    # Rule baseline predicts on synthetic bytes representation or raw features
    rule_preds = []
    t_rule_start = time.perf_counter()
    for s in test_samples:
        pred = rule_baseline.predict_bytes(s.features.get("starts_with_pdf_magic", 0.0) and b"%PDF" or b"obj")
        # Direct rule prediction based on feature flags for fair comparison
        if s.features.get("starts_with_pdf_magic", 0.0) > 0:
            lbl = "PDF_HEADER"
        elif s.features.get("token_count_xref", 0.0) > 0:
            lbl = "XREF"
        elif s.features.get("token_count_trailer", 0.0) > 0 or s.features.get("token_count_startxref", 0.0) > 0:
            lbl = "TRAILER"
        elif s.features.get("has_type_page", 0.0) > 0:
            lbl = "PAGE_OBJECT"
        elif s.features.get("has_type_font", 0.0) > 0:
            lbl = "FONT_OBJECT"
        elif s.features.get("has_subtype_image", 0.0) > 0:
            lbl = "IMAGE_STREAM"
        elif s.features.get("has_bt_et_text_ops", 0.0) > 0:
            lbl = "TEXT_STREAM"
        elif s.features.get("token_count_stream", 0.0) > 0 or s.features.get("is_compressed_candidate", 0.0) > 0:
            lbl = "PDF_STREAM"
        elif s.features.get("token_count_obj", 0.0) > 0:
            lbl = "PDF_OBJECT"
        else:
            lbl = "UNKNOWN"
        pred.predicted_label = lbl
        rule_preds.append(pred)
    rule_inf_duration = time.perf_counter() - t_rule_start

    rule_test_report = evaluate_predictions(
        y_true=y_test,
        predictions=rule_preds,
        model_name="RuleBasedBaseline",
        split_name="test",
        elapsed_time_sec=rule_inf_duration,
    )
    reports.append(rule_test_report)

    # Evaluate Majority Baseline
    majority_preds = majority_baseline.predict(len(y_test))
    majority_test_report = evaluate_predictions(
        y_true=y_test,
        predictions=majority_preds,
        model_name="MajorityClassBaseline",
        split_name="test",
    )
    reports.append(majority_test_report)

    # 7. Model Comparison
    comparison = compare_models(reports)
    logger.info("Model Comparison Summary:")
    for item in comparison["summary"]:
        logger.info(
            "  %-28s | Acc: %5.2f%% | Macro-F1: %5.2f%% | Weighted-F1: %5.2f%% | Abstain: %4.1f%% | Latency: %6.1f us",
            item["model"],
            item["accuracy"] * 100,
            item["macro_f1"] * 100,
            item["weighted_f1"] * 100,
            item["abstention_rate"] * 100,
            item["latency_us"],
        )

    # 8. Save Model & Evaluation Artifacts
    saved_artifacts = model.save_model(out_dir)
    report_file = out_dir / "evaluation_report.json"
    comparison_file = out_dir / "model_comparison.json"

    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(ml_test_report.to_dict(), f, indent=2)

    with open(comparison_file, "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2)

    logger.info("Trained model and artifacts saved to %s", out_dir)
    return {
        "out_dir": str(out_dir),
        "comparison": comparison,
        "ml_report": ml_test_report.to_dict(),
        "artifacts": {k: str(v) for k, v in saved_artifacts.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Train TRACE Forensic Fragment Classifier")
    parser.add_argument("--dataset-path", type=str, default=None, help="Path to prebuilt dataset JSON")
    parser.add_argument("--output-dir", type=str, default="trace/ml/artifacts/fragment_classifier", help="Artifacts directory")
    parser.add_argument("--n-estimators", type=int, default=100, help="Random forest estimators")
    parser.add_argument("--max-depth", type=int, default=16, help="Maximum tree depth")
    parser.add_argument("--abstention-threshold", type=float, default=0.50, help="Abstention confidence cutoff")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--sample-count", type=int, default=12, help="Synthetic document count if synthesizing")

    args = parser.parse_args()

    results = run_training_pipeline(
        dataset_path=args.dataset_path,
        output_dir=args.output_dir,
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        abstention_threshold=args.abstention_threshold,
        seed=args.seed,
        sample_count=args.sample_count,
    )
    print("\nTraining completed successfully!")
    print(json.dumps(results["comparison"], indent=2))


if __name__ == "__main__":
    main()
