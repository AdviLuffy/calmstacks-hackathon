"""Comprehensive evaluation metrics for multiclass fragment classification.

Calculates:
- Per-class precision, recall, F1, and support
- Macro F1, weighted F1, accuracy
- Confusion matrix
- Abstention rate
- Latency (microseconds/sample)
- Model comparison tables
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from trace.ml.models.fragment_classifier import FragmentPrediction


@dataclass
class ClassMetric:
    """Performance metrics for an individual class."""
    precision: float
    recall: float
    f1: float
    support: int


@dataclass
class EvaluationReport:
    """Holistic evaluation report for a classifier."""
    model_name: str
    split_name: str
    sample_count: int
    accuracy: float
    macro_f1: float
    weighted_f1: float
    abstention_rate: float
    mean_latency_us: float
    per_class: Dict[str, ClassMetric] = field(default_factory=dict)
    classes: List[str] = field(default_factory=list)
    confusion_matrix: List[List[int]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        return data

    def save_json(self, output_path: Union[str, Path]) -> None:
        p = Path(output_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)


def evaluate_predictions(
    y_true: Sequence[str],
    predictions: Sequence[FragmentPrediction],
    model_name: str = "model",
    split_name: str = "test",
    elapsed_time_sec: float = 0.0,
) -> EvaluationReport:
    """Evaluate multiclass predictions against ground-truth labels."""
    n_samples = len(y_true)
    if n_samples == 0:
        return EvaluationReport(
            model_name=model_name,
            split_name=split_name,
            sample_count=0,
            accuracy=0.0,
            macro_f1=0.0,
            weighted_f1=0.0,
            abstention_rate=0.0,
            mean_latency_us=0.0,
        )

    y_pred = [p.predicted_label for p in predictions]
    abstained_count = sum(1 for p in predictions if p.abstained)
    abstention_rate = abstained_count / n_samples

    mean_latency_us = (elapsed_time_sec * 1_000_000.0) / n_samples if n_samples > 0 else 0.0

    # Collect union of classes in true and pred
    all_classes = sorted(list(set(y_true).union(set(y_pred))))
    class_to_idx = {c: i for i, c in enumerate(all_classes)}
    n_classes = len(all_classes)

    # Build confusion matrix: rows=true, cols=pred
    cm = [[0] * n_classes for _ in range(n_classes)]
    for yt, yp in zip(y_true, y_pred):
        cm[class_to_idx[yt]][class_to_idx[yp]] += 1

    per_class_metrics: Dict[str, ClassMetric] = {}
    total_correct = 0

    f1_list: List[float] = []
    f1_weighted_sum = 0.0

    for i, cls_name in enumerate(all_classes):
        tp = cm[i][i]
        total_correct += tp
        support = sum(cm[i])
        pred_count = sum(cm[r][i] for r in range(n_classes))

        precision = tp / pred_count if pred_count > 0 else 0.0
        recall = tp / support if support > 0 else 0.0
        f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0

        per_class_metrics[cls_name] = ClassMetric(
            precision=round(precision, 4),
            recall=round(recall, 4),
            f1=round(f1, 4),
            support=support,
        )

        f1_list.append(f1)
        f1_weighted_sum += f1 * support

    accuracy = total_correct / n_samples
    macro_f1 = sum(f1_list) / n_classes if n_classes > 0 else 0.0
    weighted_f1 = f1_weighted_sum / n_samples if n_samples > 0 else 0.0

    return EvaluationReport(
        model_name=model_name,
        split_name=split_name,
        sample_count=n_samples,
        accuracy=round(accuracy, 4),
        macro_f1=round(macro_f1, 4),
        weighted_f1=round(weighted_f1, 4),
        abstention_rate=round(abstention_rate, 4),
        mean_latency_us=round(mean_latency_us, 2),
        per_class=per_class_metrics,
        classes=all_classes,
        confusion_matrix=cm,
    )


def compare_models(
    reports: Sequence[EvaluationReport],
) -> Dict[str, Any]:
    """Generates comparative analysis between ML models and baselines."""
    comparison: Dict[str, Any] = {
        "summary": [],
        "best_macro_f1": None,
        "best_accuracy": None,
    }

    best_macro = -1.0
    best_acc = -1.0
    best_macro_model = ""
    best_acc_model = ""

    for rep in reports:
        entry = {
            "model": rep.model_name,
            "split": rep.split_name,
            "samples": rep.sample_count,
            "accuracy": rep.accuracy,
            "macro_f1": rep.macro_f1,
            "weighted_f1": rep.weighted_f1,
            "abstention_rate": rep.abstention_rate,
            "latency_us": rep.mean_latency_us,
        }
        comparison["summary"].append(entry)

        if rep.macro_f1 > best_macro:
            best_macro = rep.macro_f1
            best_macro_model = rep.model_name

        if rep.accuracy > best_acc:
            best_acc = rep.accuracy
            best_acc_model = rep.model_name

    comparison["best_macro_f1"] = {"model": best_macro_model, "score": best_macro}
    comparison["best_accuracy"] = {"model": best_acc_model, "score": best_acc}

    return comparison
