"""Runtime inference service for classifying forensic fragments.

Provides:
- Graceful degradation to deterministic rule fallback if model is absent
- Abstention threshold enforcement
- Full provenance metadata tracking
- Batch and single fragment prediction APIs
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from trace.datasets.schemas.ground_truth import FragmentLabel
from trace.ml.models.fragment_classifier import (
    ForensicFragmentClassifier,
    FragmentPrediction,
    RuleBasedBaselineClassifier,
)

logger = logging.getLogger(__name__)

DEFAULT_MODEL_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "fragment_classifier"


class FragmentPredictor:
    """Runtime predictor with safe fallback and telemetry."""

    def __init__(
        self,
        model_dir: Optional[Union[str, Path]] = None,
        abstention_threshold: float = 0.50,
        enable_fallback: bool = True,
    ) -> None:
        self.model_dir = Path(model_dir) if model_dir else DEFAULT_MODEL_DIR
        self.abstention_threshold = abstention_threshold
        self.enable_fallback = enable_fallback

        self._ml_model: Optional[ForensicFragmentClassifier] = None
        self._rule_fallback = RuleBasedBaselineClassifier()
        self._load_status: str = "uninitialized"

        self._try_load_model()

    def _try_load_model(self) -> None:
        """Attempt to load trained weights if present on disk."""
        if not self.model_dir.exists():
            self._load_status = f"model_dir_not_found: {self.model_dir}"
            logger.info("ML model directory not found at %s. Using rule fallback.", self.model_dir)
            return

        model_file = self.model_dir / "model.joblib"
        meta_file = self.model_dir / "metadata.json"

        if not model_file.exists() or not meta_file.exists():
            self._load_status = "model_artifacts_missing"
            logger.info("Model artifacts missing in %s. Using rule fallback.", self.model_dir)
            return

        try:
            self._ml_model = ForensicFragmentClassifier.load_model(self.model_dir)
            self._ml_model.abstention_threshold = self.abstention_threshold
            self._load_status = "loaded"
            logger.info("Successfully loaded ML fragment classifier (version %s)", self._ml_model.model_version)
        except Exception as e:
            self._load_status = f"load_error: {e}"
            logger.warning("Failed to load ML model from %s: %s. Using fallback.", self.model_dir, e)

    @property
    def is_ml_active(self) -> bool:
        return self._ml_model is not None and self._ml_model.is_trained

    def predict_fragment(self, fragment_bytes: bytes) -> FragmentPrediction:
        """Classify a single fragment with provenance and abstention."""
        if self.is_ml_active and self._ml_model is not None:
            try:
                pred = self._ml_model.predict_bytes(fragment_bytes)
                return pred
            except Exception as e:
                logger.warning("ML inference failed on fragment (%s). Using fallback.", e)
                if not self.enable_fallback:
                    raise

        # Rule-based fallback
        pred = self._rule_fallback.predict_bytes(fragment_bytes)
        pred.provenance = "FALLBACK_RULE"
        return pred

    def predict_batch(self, fragments: Sequence[bytes]) -> List[FragmentPrediction]:
        """Classify a sequence of fragments."""
        return [self.predict_fragment(f) for f in fragments]

    def get_telemetry(self) -> Dict[str, Any]:
        """Telemetry on predictor state."""
        return {
            "is_ml_active": self.is_ml_active,
            "load_status": self._load_status,
            "model_dir": str(self.model_dir),
            "abstention_threshold": self.abstention_threshold,
            "classes": self._ml_model.classes_ if self.is_ml_active and self._ml_model is not None else self._rule_fallback.classes,
        }


_GLOBAL_PREDICTOR: Optional[FragmentPredictor] = None


def get_default_fragment_predictor() -> FragmentPredictor:
    """Singleton getter for application-wide fragment predictor."""
    global _GLOBAL_PREDICTOR
    if _GLOBAL_PREDICTOR is None:
        _GLOBAL_PREDICTOR = FragmentPredictor()
    return _GLOBAL_PREDICTOR
