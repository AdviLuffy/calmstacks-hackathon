"""Inference engine for forensic fragment classification."""

from trace.ml.inference.fragment_predictor import (
    FragmentPredictor,
    get_default_fragment_predictor,
)

__all__ = [
    "FragmentPredictor",
    "get_default_fragment_predictor",
]
