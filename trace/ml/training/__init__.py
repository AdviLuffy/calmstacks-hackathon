"""Training and evaluation routines for TRACE ML models."""

from trace.ml.training.evaluation import (
    ClassMetric,
    EvaluationReport,
    evaluate_predictions,
    compare_models,
)

__all__ = [
    "ClassMetric",
    "EvaluationReport",
    "evaluate_predictions",
    "compare_models",
]
