"""TRACE Dataset Schemas."""

from trace.datasets.schemas.corruption import (
    CorruptionSeverity,
    CorruptionType,
    CorruptionOperation,
    CorruptionManifest,
    Recoverability,
)
from trace.datasets.schemas.ground_truth import (
    FragmentLabel,
    RecoveryState,
    RelationshipLabel,
    GroundTruthInventory,
    GroundTruthRecord,
)

from trace.datasets.schemas.real_world import (
    ContentCharacteristic,
    ControlledCorruptionRecord,
    DocumentCategory,
    GenuinelyDamagedRecord,
    LicenseType,
    RealWorldCorpusRegistry,
    RealWorldDocumentRecord,
)

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
    "LicenseType",
    "ContentCharacteristic",
    "DocumentCategory",
    "RealWorldDocumentRecord",
    "ControlledCorruptionRecord",
    "GenuinelyDamagedRecord",
    "RealWorldCorpusRegistry",
]
