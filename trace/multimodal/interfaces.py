"""Interfaces and Abstract Base Classes for TRACE Multimodal Document Intelligence.

Defines decoupled contracts for:
1. OCR (IOcrEngine)
2. Document Layout Detection (IDocumentLayoutDetector)
3. Reading-Order Detection (IReadingOrderDetector)
4. Table Detection (ITableDetector)
5. Figure/Image Detection (IFigureDetector)
6. Equation Detection (IEquationDetector)
7. Document Classification (IDocumentClassifier)
8. Visual Document Understanding (IVisualDocumentAnalyzer)
9. Fragment Classification (IFragmentClassifier)
10. Fragment Relationship Scoring (IFragmentRelationshipScorer)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
from trace.multimodal.representation import (
    BoundingBox,
    DocumentElement,
    DocumentPage,
    NormalizedDocument,
    ProvenanceCategory,
)


class IOcrEngine(ABC):
    """Interface for optical character recognition engines."""

    @abstractmethod
    def extract_text(
        self,
        image_bytes: bytes,
        language: str = "eng",
    ) -> List[DocumentElement]:
        """Extract text blocks with bounding boxes and confidence from page image bytes."""
        raise NotImplementedError


class IDocumentLayoutDetector(ABC):
    """Interface for document layout analysis and element segmentation."""

    @abstractmethod
    def detect_layout(
        self,
        page: DocumentPage,
        raw_evidence: Optional[bytes] = None,
    ) -> List[DocumentElement]:
        """Identify headers, footers, paragraphs, sidebars, and structural zones."""
        raise NotImplementedError


class IReadingOrderDetector(ABC):
    """Interface for reading order determination in complex or multi-column layouts."""

    @abstractmethod
    def determine_reading_order(
        self,
        page: DocumentPage,
    ) -> List[str]:
        """Return element IDs ordered sequentially according to human reading flow."""
        raise NotImplementedError


class ITableDetector(ABC):
    """Interface for detecting tabular data, rows, columns, and cell structures."""

    @abstractmethod
    def detect_tables(
        self,
        page: DocumentPage,
        raw_evidence: Optional[bytes] = None,
    ) -> List[DocumentElement]:
        """Detect and structure tables into structured DocumentElement representations."""
        raise NotImplementedError


class IFigureDetector(ABC):
    """Interface for detecting figures, diagrams, charts, and embedded images."""

    @abstractmethod
    def detect_figures(
        self,
        page: DocumentPage,
        raw_evidence: Optional[bytes] = None,
    ) -> List[DocumentElement]:
        """Locate figures/images, assigning bounding boxes and metadata."""
        raise NotImplementedError


class IEquationDetector(ABC):
    """Interface for detecting mathematical formulas and equations (inline and display)."""

    @abstractmethod
    def detect_equations(
        self,
        page: DocumentPage,
        raw_evidence: Optional[bytes] = None,
    ) -> List[DocumentElement]:
        """Locate and transcribe math equations (e.g. LaTeX or MathML if available)."""
        raise NotImplementedError


class IDocumentClassifier(ABC):
    """Interface for document type and genre classification."""

    @abstractmethod
    def classify_document(
        self,
        document: NormalizedDocument,
    ) -> Dict[str, Any]:
        """Classify document (e.g. 'research_paper', 'financial_report', 'legal_contract', 'invoice').
        
        Returns dict with keys: 'primary_category', 'confidence', 'attributes', 'provenance'.
        """
        raise NotImplementedError


class IVisualDocumentAnalyzer(ABC):
    """Interface for multimodal visual document understanding (VDU / VLM)."""

    @abstractmethod
    def analyze_page(
        self,
        page: DocumentPage,
        rendered_image: Optional[bytes] = None,
        context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Perform multimodal reasoning across visual layout and textual content."""
        raise NotImplementedError


class IFragmentClassifier(ABC):
    """Interface for classifying individual carved binary fragments."""

    @abstractmethod
    def classify_fragment(
        self,
        fragment_id: str,
        data: bytes,
    ) -> Dict[str, Any]:
        """Determine likely file type, structural role, and confidence for a fragment."""
        raise NotImplementedError


class IFragmentRelationshipScorer(ABC):
    """Interface for scoring semantic and structural affinity between two fragments."""

    @abstractmethod
    def score_relationship(
        self,
        fragment_a_id: str,
        fragment_a_data: bytes,
        fragment_b_id: str,
        fragment_b_data: bytes,
    ) -> Dict[str, Any]:
        """Calculate continuity or affinity score between fragment A and fragment B."""
        raise NotImplementedError
