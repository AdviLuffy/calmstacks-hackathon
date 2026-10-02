"""Dataset abstraction for forensic fragment classification.

Guarantees document-level partition isolation (zero split leakage),
tracks feature matrices, class labels, and metadata.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from trace.datasets.schemas.ground_truth import FragmentLabel
from trace.ml.features.fragment_features import FragmentFeatureExtractor, FEATURE_NAMES


@dataclass
class FragmentSample:
    """A single labeled evidence fragment."""
    sample_id: str
    doc_id: str
    fragment_id: str
    offset: int
    length: int
    label: str
    is_exact: bool
    features: Dict[str, float]
    provenance: str = "SYNTHETIC_LABELED_FRAGMENT"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FragmentSample":
        return cls(**data)


@dataclass
class DatasetSplit:
    """Group of samples assigned to a particular evaluation partition."""
    name: str
    doc_ids: List[str]
    samples: List[FragmentSample] = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.samples)

    @property
    def class_counts(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for s in self.samples:
            counts[s.label] = counts.get(s.label, 0) + 1
        return counts


class FragmentDataset:
    """Container managing train, validation, test, and hard-test splits."""

    def __init__(
        self,
        name: str = "trace_fragment_benchmark",
        version: str = "1.0",
        feature_names: Sequence[str] | None = None,
    ) -> None:
        self.name = name
        self.version = version
        self.feature_names = list(feature_names) if feature_names else list(FEATURE_NAMES)
        self.train_split = DatasetSplit(name="train", doc_ids=[])
        self.val_split = DatasetSplit(name="validation", doc_ids=[])
        self.test_split = DatasetSplit(name="test", doc_ids=[])
        self.hard_test_split = DatasetSplit(name="hard_test", doc_ids=[])

    def get_split(self, split_name: str) -> DatasetSplit:
        if split_name == "train":
            return self.train_split
        elif split_name in ("val", "validation"):
            return self.val_split
        elif split_name == "test":
            return self.test_split
        elif split_name == "hard_test":
            return self.hard_test_split
        else:
            raise ValueError(f"Unknown split name: {split_name}")

    def add_sample(self, split_name: str, sample: FragmentSample) -> None:
        split = self.get_split(split_name)
        if sample.doc_id not in split.doc_ids:
            split.doc_ids.append(sample.doc_id)
        split.samples.append(sample)

    def verify_no_document_leakage(self) -> bool:
        """Verifies that no doc_id exists in more than one partition."""
        seen: Dict[str, str] = {}
        for s in [self.train_split, self.val_split, self.test_split, self.hard_test_split]:
            for doc_id in s.doc_ids:
                if doc_id in seen:
                    raise ValueError(
                        f"Document leakage detected: doc_id '{doc_id}' is present in both '{seen[doc_id]}' and '{s.name}'"
                    )
                seen[doc_id] = s.name
        return True

    def get_feature_matrix(
        self, split_name: str
    ) -> Tuple[List[List[float]], List[str]]:
        """Extract ordered feature matrix X and label vector y for a split."""
        split = self.get_split(split_name)
        X: List[List[float]] = []
        y: List[str] = []
        for sample in split.samples:
            row = [sample.features.get(f_name, 0.0) for f_name in self.feature_names]
            X.append(row)
            y.append(sample.label)
        return X, y

    def summary(self) -> Dict[str, Any]:
        """Dataset composition telemetry."""
        return {
            "name": self.name,
            "version": self.version,
            "feature_count": len(self.feature_names),
            "splits": {
                "train": {
                    "docs": len(self.train_split.doc_ids),
                    "samples": len(self.train_split.samples),
                    "classes": self.train_split.class_counts,
                },
                "validation": {
                    "docs": len(self.val_split.doc_ids),
                    "samples": len(self.val_split.samples),
                    "classes": self.val_split.class_counts,
                },
                "test": {
                    "docs": len(self.test_split.doc_ids),
                    "samples": len(self.test_split.samples),
                    "classes": self.test_split.class_counts,
                },
                "hard_test": {
                    "docs": len(self.hard_test_split.doc_ids),
                    "samples": len(self.hard_test_split.samples),
                    "classes": self.hard_test_split.class_counts,
                },
            },
        }

    def save_json(self, output_path: str | Path) -> None:
        """Serialize dataset into JSON format."""
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "name": self.name,
            "version": self.version,
            "feature_names": self.feature_names,
            "train": [s.to_dict() for s in self.train_split.samples],
            "validation": [s.to_dict() for s in self.val_split.samples],
            "test": [s.to_dict() for s in self.test_split.samples],
            "hard_test": [s.to_dict() for s in self.hard_test_split.samples],
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    @classmethod
    def load_json(cls, input_path: str | Path) -> "FragmentDataset":
        """Load dataset from JSON format."""
        with open(input_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        dataset = cls(
            name=data.get("name", "trace_fragment_benchmark"),
            version=data.get("version", "1.0"),
            feature_names=data.get("feature_names", FEATURE_NAMES),
        )

        for split_key in ["train", "validation", "test", "hard_test"]:
            for item in data.get(split_key, []):
                sample = FragmentSample.from_dict(item)
                dataset.add_sample(split_key, sample)

        dataset.verify_no_document_leakage()
        return dataset


def build_dataset_from_samples(
    samples_by_doc: Dict[str, List[Dict[str, Any]]],
    train_ratio: float = 0.60,
    val_ratio: float = 0.20,
    test_ratio: float = 0.20,
    seed: int = 42,
    feature_extractor: Optional[FragmentFeatureExtractor] = None,
) -> FragmentDataset:
    """Partition documents into splits and construct a FragmentDataset."""
    fe = feature_extractor or FragmentFeatureExtractor()
    dataset = FragmentDataset(feature_names=fe.feature_names)

    doc_ids = sorted(list(samples_by_doc.keys()))
    rng = random.Random(seed)
    rng.shuffle(doc_ids)

    n_total = len(doc_ids)
    if n_total == 0:
        return dataset

    n_train = max(1, int(round(n_total * train_ratio)))
    n_val = max(1 if n_total >= 3 else 0, int(round(n_total * val_ratio)))
    
    train_docs = set(doc_ids[:n_train])
    val_docs = set(doc_ids[n_train : n_train + n_val])
    test_docs = set(doc_ids[n_train + n_val :])

    # If only 1 or 2 docs, handle gracefully
    if not test_docs and not val_docs:
        val_docs = set()
        test_docs = set()
    elif not test_docs and val_docs:
        # Move at least one to test if total >= 2
        if len(val_docs) > 1:
            moved = val_docs.pop()
            test_docs.add(moved)

    for doc_id, items in samples_by_doc.items():
        if doc_id in train_docs:
            split_name = "train"
        elif doc_id in val_docs:
            split_name = "validation"
        else:
            split_name = "test"

        for item in items:
            raw_bytes = item.get("bytes", b"")
            features = fe.extract_features(raw_bytes)
            sample = FragmentSample(
                sample_id=item["fragment_id"],
                doc_id=doc_id,
                fragment_id=item["fragment_id"],
                offset=item["offset"],
                length=item["length"],
                label=item["label"],
                is_exact=item.get("is_exact", True),
                features=features,
            )
            dataset.add_sample(split_name, sample)

    dataset.verify_no_document_leakage()
    return dataset
