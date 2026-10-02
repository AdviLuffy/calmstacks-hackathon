"""TRACE Multimodal Document Intelligence Layer.

Provides modular interfaces, a model registry, normalized document representation,
deterministic forensic extractors, and model adapters for multi-column documents,
tables, figures, equations, reading order, and OCR.
"""

from trace.multimodal.representation import (
    ProvenanceCategory,
    ElementType,
    BoundingBox,
    DocumentElement,
    DocumentPage,
    NormalizedDocument,
)
from trace.multimodal.interfaces import (
    IOcrEngine,
    IDocumentLayoutDetector,
    IReadingOrderDetector,
    ITableDetector,
    IFigureDetector,
    IEquationDetector,
    IDocumentClassifier,
    IVisualDocumentAnalyzer,
    IFragmentClassifier,
    IFragmentRelationshipScorer,
)
from trace.multimodal.registry import (
    ModelRegistry,
    ModelInfo,
    ExecutionMode,
    TaskType,
)
from trace.multimodal.deterministic import DeterministicDocumentIntelligence
from trace.multimodal.pipeline import build_normalized_document_from_recovery

__all__ = [
    "ProvenanceCategory",
    "ElementType",
    "BoundingBox",
    "DocumentElement",
    "DocumentPage",
    "NormalizedDocument",
    "IOcrEngine",
    "IDocumentLayoutDetector",
    "IReadingOrderDetector",
    "ITableDetector",
    "IFigureDetector",
    "IEquationDetector",
    "IDocumentClassifier",
    "IVisualDocumentAnalyzer",
    "IFragmentClassifier",
    "IFragmentRelationshipScorer",
    "ModelRegistry",
    "ModelInfo",
    "ExecutionMode",
    "TaskType",
    "DeterministicDocumentIntelligence",
    "build_normalized_document_from_recovery",
]
