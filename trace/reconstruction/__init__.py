"""TRACE Phase 9: Advanced Multimodal Document Reconstruction Engine.

Provides complete recovery and reconstruction of damaged PDF documents, research papers,
text, typography, images/figures, tables, mathematical equations, and page layouts
with strict forensic provenance guarantees and separate artifact management.
"""

from trace.reconstruction.artifacts import ReconstructionArtifactManager
from trace.reconstruction.engine import (
    AdvancedMultimodalReconstructionEngine,
    ReconstructionResult,
)
from trace.reconstruction.equation_reconstructor import EquationReconstructor
from trace.reconstruction.layout_engine import DocumentLayoutEngine
from trace.reconstruction.media_reconstructor import MediaReconstructor
from trace.reconstruction.models import (
    EquationElement,
    EquationType,
    ImageElement,
    ImageFormat,
    MultimodalReconstructionReport,
    PageLayoutData,
    ProvenanceBreakdown,
    ReconstructionArtifacts,
    TableCell,
    TableRow,
    TableStructure,
    TextBlockData,
)
from trace.reconstruction.pdf_builder import MultimodalPdfBuilder
from trace.reconstruction.table_reconstructor import TableReconstructor
from trace.reconstruction.text_reconstructor import TextReconstructor

__all__ = [
    "AdvancedMultimodalReconstructionEngine",
    "ReconstructionResult",
    "ReconstructionArtifactManager",
    "ReconstructionArtifacts",
    "MultimodalReconstructionReport",
    "ProvenanceBreakdown",
    "TextReconstructor",
    "MediaReconstructor",
    "TableReconstructor",
    "EquationReconstructor",
    "DocumentLayoutEngine",
    "MultimodalPdfBuilder",
    "TextBlockData",
    "TableStructure",
    "TableCell",
    "TableRow",
    "ImageElement",
    "ImageFormat",
    "EquationElement",
    "EquationType",
    "PageLayoutData",
]
