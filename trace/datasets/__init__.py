"""TRACE Forensic Corruption Laboratory and Synthetic Dataset Generator.

Provides deterministic multi-operator document corruption, ground-truth inventorying,
split export (train/val/test/hard_test), dataset validation, and granular recovery benchmarking.
"""

from trace.datasets.schemas import (
    CorruptionSeverity,
    CorruptionType,
    CorruptionOperation,
    CorruptionManifest,
    Recoverability,
    FragmentLabel,
    RecoveryState,
    RelationshipLabel,
    GroundTruthInventory,
    GroundTruthRecord,
)
from trace.datasets.corruption import (
    ForensicCorruptionEngine,
    byte_ops,
    structure_ops,
    stream_ops,
    text_ops,
    image_ops,
    font_ops,
    layout_ops,
)
from trace.datasets.generators import (
    SyntheticDocumentGenerator,
    default_document_generator,
)
from trace.datasets.exporters import DatasetExporter
from trace.datasets.validators import DatasetValidator
from trace.datasets.benchmark import RecoveryBenchmarkRunner

__all__ = [
    "CorruptionSeverity",
    "CorruptionType",
    "CorruptionOperation",
    "CorruptionManifest",
    "Recoverability",
    "FragmentLabel",
    "RecoveryState",
    "RelationshipLabel",
    "GroundTruthInventory",
    "GroundTruthRecord",
    "ForensicCorruptionEngine",
    "byte_ops",
    "structure_ops",
    "stream_ops",
    "text_ops",
    "image_ops",
    "font_ops",
    "layout_ops",
    "SyntheticDocumentGenerator",
    "default_document_generator",
    "DatasetExporter",
    "DatasetValidator",
    "RecoveryBenchmarkRunner",
]
