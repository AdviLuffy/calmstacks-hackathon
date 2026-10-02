"""Forensic fragment classification models and baselines.

Provides:
- RuleBasedBaselineClassifier (transparent heuristic baseline)
- MajorityClassBaselineClassifier (zero-intelligence baseline)
- ForensicFragmentClassifier (CPU-friendly balanced ensemble ML model)
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from trace.datasets.schemas.ground_truth import FragmentLabel
from trace.ml.features.fragment_features import FragmentFeatureExtractor, FEATURE_NAMES

logger = logging.getLogger(__name__)


@dataclass
class FragmentPrediction:
    """Forensic classification output for a single fragment."""
    predicted_label: str
    confidence: float
    probabilities: Dict[str, float] = field(default_factory=dict)
    abstained: bool = False
    abstention_reason: Optional[str] = None
    provenance: str = "ML_DETECTED"
    model_version: str = "1.0.0"
    top_signals: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class RuleBasedBaselineClassifier:
    """Transparent heuristic baseline comparator."""

    def __init__(self) -> None:
        self.classes = [c.value for c in FragmentLabel]

    def predict_bytes(self, fragment: bytes) -> FragmentPrediction:
        """Rule-based decision tree using structural tokens."""
        raw = bytes(fragment)
        probs = {c: 0.0 for c in self.classes}

        if raw.startswith(b"%PDF") or b"%PDF-" in raw[:32]:
            label = FragmentLabel.PDF_HEADER.value
            conf = 0.95
        elif b"xref" in raw:
            label = FragmentLabel.XREF.value
            conf = 0.85
        elif b"trailer" in raw or b"startxref" in raw:
            label = FragmentLabel.TRAILER.value
            conf = 0.85
        elif b"/Subtype /Image" in raw or b"/DCTDecode" in raw:
            label = FragmentLabel.IMAGE_STREAM.value
            conf = 0.80
        elif (b"BT" in raw and b"ET" in raw) or (b"/Type /Page" in raw and b"/Contents" in raw):
            label = FragmentLabel.TEXT_STREAM.value
            conf = 0.75
        elif b"/Type /Page" in raw:
            label = FragmentLabel.PAGE_OBJECT.value
            conf = 0.80
        elif b"/Type /Font" in raw:
            label = FragmentLabel.FONT_OBJECT.value
            conf = 0.80
        elif b"/Type /Metadata" in raw or b"<x:xmpmeta" in raw:
            label = FragmentLabel.METADATA.value
            conf = 0.80
        elif b"stream" in raw and b"endstream" in raw:
            label = FragmentLabel.PDF_STREAM.value
            conf = 0.70
        elif b" obj" in raw:
            label = FragmentLabel.PDF_OBJECT.value
            conf = 0.65
        else:
            label = FragmentLabel.UNKNOWN.value
            conf = 0.50

        probs[label] = conf
        # Normalize other probabilities
        remaining = max(0.0, 1.0 - conf)
        other_classes = [c for c in self.classes if c != label]
        for c in other_classes:
            probs[c] = remaining / len(other_classes)

        return FragmentPrediction(
            predicted_label=label,
            confidence=conf,
            probabilities=probs,
            abstained=False,
            provenance="RULE_BASELINE",
            model_version="rule_baseline_v1",
        )

    def predict_batch(self, fragments: Sequence[bytes]) -> List[FragmentPrediction]:
        return [self.predict_bytes(f) for f in fragments]


class MajorityClassBaselineClassifier:
    """Majority-class baseline for empirical comparison."""

    def __init__(self, majority_label: str = FragmentLabel.UNKNOWN.value) -> None:
        self.majority_label = majority_label
        self.classes = [c.value for c in FragmentLabel]

    def fit(self, y: Sequence[str]) -> "MajorityClassBaselineClassifier":
        if not y:
            return self
        counts: Dict[str, int] = {}
        for label in y:
            counts[label] = counts.get(label, 0) + 1
        self.majority_label = max(counts.keys(), key=lambda k: counts[k])
        return self

    def predict(self, n_samples: int) -> List[FragmentPrediction]:
        probs = {c: (1.0 if c == self.majority_label else 0.0) for c in self.classes}
        return [
            FragmentPrediction(
                predicted_label=self.majority_label,
                confidence=1.0,
                probabilities=probs,
                provenance="MAJORITY_BASELINE",
                model_version="majority_v1",
            )
            for _ in range(n_samples)
        ]


class ForensicFragmentClassifier:
    """Supervised ML model for classifying forensic fragments."""

    def __init__(
        self,
        model_version: str = "1.0.0",
        abstention_threshold: float = 0.50,
        feature_names: Optional[Sequence[str]] = None,
        n_estimators: int = 100,
        max_depth: Optional[int] = 16,
        random_state: int = 42,
    ) -> None:
        self.model_version = model_version
        self.abstention_threshold = abstention_threshold
        self.feature_names = list(feature_names) if feature_names else list(FEATURE_NAMES)
        self.n_estimators = n_estimators
        self.max_depth = max_depth
        self.random_state = random_state

        self.classes_: List[str] = []
        self._model: Any = None
        self._feature_extractor = FragmentFeatureExtractor(self.feature_names)
        self._rule_fallback = RuleBasedBaselineClassifier()
        self.training_metadata: Dict[str, Any] = {}

    @property
    def is_trained(self) -> bool:
        return self._model is not None and len(self.classes_) > 0

    def fit(
        self,
        X: Sequence[Sequence[float]],
        y: Sequence[str],
        sample_weight: Optional[Sequence[float]] = None,
    ) -> "ForensicFragmentClassifier":
        """Train the ensemble tree model on extracted features."""
        try:
            from sklearn.ensemble import RandomForestClassifier
            import numpy as np
        except ImportError as e:
            logger.error("scikit-learn is required to train ForensicFragmentClassifier: %s", e)
            raise RuntimeError(f"scikit-learn required: {e}") from e

        X_arr = np.asarray(X, dtype=np.float32)
        y_arr = np.asarray(y, dtype=str)

        if len(X_arr) == 0:
            raise ValueError("Cannot train on empty feature matrix")

        # Record unique classes
        self.classes_ = sorted(list(set(y_arr)))

        # Handle edge case of single class in dataset
        if len(self.classes_) == 1:
            # Add synthetic dummy class to allow sklearn classifier to fit
            dummy_class = FragmentLabel.UNKNOWN.value if self.classes_[0] != FragmentLabel.UNKNOWN.value else FragmentLabel.PDF_OBJECT.value
            self.classes_.append(dummy_class)

        self._model = RandomForestClassifier(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            class_weight="balanced",
            random_state=self.random_state,
            n_jobs=-1,
        )

        self._model.fit(X_arr, y_arr, sample_weight=sample_weight)
        self.classes_ = list(self._model.classes_)

        # Calculate feature importances
        importances = self._model.feature_importances_
        feature_importance_map = {
            name: float(imp) for name, imp in zip(self.feature_names, importances)
        }
        # Sort by importance descending
        sorted_importance = dict(sorted(feature_importance_map.items(), key=lambda kv: kv[1], reverse=True))

        self.training_metadata = {
            "model_type": "RandomForestClassifier",
            "model_version": self.model_version,
            "classes": self.classes_,
            "n_samples": len(X_arr),
            "n_features": len(self.feature_names),
            "feature_importance": sorted_importance,
        }

        return self

    def predict_features(
        self, feature_vector: Sequence[float]
    ) -> FragmentPrediction:
        """Predict class given numerical feature vector."""
        if not self.is_trained:
            return FragmentPrediction(
                predicted_label=FragmentLabel.UNKNOWN.value,
                confidence=0.0,
                abstained=True,
                abstention_reason="model_not_trained",
                provenance="UNINITIALIZED_MODEL",
            )

        try:
            import numpy as np
            x_arr = np.asarray([feature_vector], dtype=np.float32)
            proba = self._model.predict_proba(x_arr)[0]
        except Exception as e:
            logger.warning("Inference execution failed, falling back: %s", e)
            return FragmentPrediction(
                predicted_label=FragmentLabel.UNKNOWN.value,
                confidence=0.0,
                abstained=True,
                abstention_reason=str(e),
                provenance="INFERENCE_ERROR",
            )

        prob_dict = {str(cls_name): float(p) for cls_name, p in zip(self.classes_, proba)}
        best_class = str(max(prob_dict.keys(), key=lambda k: prob_dict[k]))
        best_prob = prob_dict[best_class]

        # Extract top feature signals for explainability
        top_signals: Dict[str, float] = {}
        for name, val in zip(self.feature_names, feature_vector):
            if val > 0:
                top_signals[str(name)] = float(val)

        # Abstention check
        abstained = False
        abstention_reason = None
        predicted_label = best_class

        if best_prob < self.abstention_threshold:
            abstained = True
            abstention_reason = f"Confidence {best_prob:.3f} below abstention threshold {self.abstention_threshold:.3f}"
            predicted_label = FragmentLabel.UNKNOWN.value

        return FragmentPrediction(
            predicted_label=predicted_label,
            confidence=best_prob,
            probabilities=prob_dict,
            abstained=abstained,
            abstention_reason=abstention_reason,
            provenance="ML_DETECTED",
            model_version=self.model_version,
            top_signals=dict(list(top_signals.items())[:5]),
        )

    def predict_bytes(self, fragment: bytes) -> FragmentPrediction:
        """End-to-end inference directly from raw fragment bytes."""
        if not self.is_trained:
            # Fall back safely to rule-based baseline
            return self._rule_fallback.predict_bytes(fragment)

        feat_vector = self._feature_extractor.extract_vector(fragment)
        return self.predict_features(feat_vector)

    def save_model(self, export_dir: Union[str, Path]) -> Dict[str, Path]:
        """Serialize model, metadata, and feature config."""
        try:
            import joblib
        except ImportError as e:
            raise RuntimeError(f"joblib required to serialize model: {e}") from e

        out_path = Path(export_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        model_file = out_path / "model.joblib"
        meta_file = out_path / "metadata.json"
        config_file = out_path / "feature_config.json"

        # Save model binary
        joblib.dump(self._model, model_file)

        # Save metadata
        metadata = {
            "model_version": self.model_version,
            "classes": self.classes_,
            "abstention_threshold": self.abstention_threshold,
            "feature_names": self.feature_names,
            "n_estimators": self.n_estimators,
            "max_depth": self.max_depth,
            "random_state": self.random_state,
            "training_metadata": self.training_metadata,
        }
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        # Save feature config
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump({"feature_names": self.feature_names}, f, indent=2)

        return {
            "model_file": model_file,
            "metadata_file": meta_file,
            "config_file": config_file,
        }

    @classmethod
    def load_model(cls, export_dir: Union[str, Path]) -> "ForensicFragmentClassifier":
        """Load serialized model, metadata, and feature config."""
        try:
            import joblib
        except ImportError as e:
            raise RuntimeError(f"joblib required to load model: {e}") from e

        in_path = Path(export_dir)
        model_file = in_path / "model.joblib"
        meta_file = in_path / "metadata.json"

        if not model_file.exists() or not meta_file.exists():
            raise FileNotFoundError(f"Model artifacts missing in {export_dir}")

        with open(meta_file, "r", encoding="utf-8") as f:
            metadata = json.load(f)

        instance = cls(
            model_version=metadata.get("model_version", "1.0.0"),
            abstention_threshold=metadata.get("abstention_threshold", 0.50),
            feature_names=metadata.get("feature_names", FEATURE_NAMES),
            n_estimators=metadata.get("n_estimators", 100),
            max_depth=metadata.get("max_depth", 16),
            random_state=metadata.get("random_state", 42),
        )

        instance._model = joblib.load(model_file)
        instance.classes_ = metadata.get("classes", list(instance._model.classes_))
        instance.training_metadata = metadata.get("training_metadata", {})
        return instance
