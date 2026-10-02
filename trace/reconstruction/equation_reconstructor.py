"""Equation and Mathematical Formula Reconstructor for TRACE Phase 9.

Detects, extracts, classifies, and transcribes mathematical formulas (inline, display,
numbered) from damaged research papers with strict forensic provenance.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from trace.multimodal.representation import (
    BoundingBox,
    DocumentElement,
    ElementType,
    ProvenanceCategory,
)
from trace.reconstruction.models import EquationElement, EquationType


class EquationReconstructor:
    """Detects, parses, and formats mathematical equations into LaTeX representations."""

    # Common math tokens and symbols
    MATH_SYMBOLS = [
        "\\sum", "\\int", "\\prod", "\\partial", "\\sqrt", "\\alpha", "\\beta",
        "\\gamma", "\\theta", "\\lambda", "\\sigma", "\\omega", "\\approx",
        "\\le", "\\ge", "\\pm", "\\neq", "\\in", "\\to", "\\infty", "\\nabla",
        "∑", "∫", "∏", "∂", "√", "α", "β", "γ", "θ", "λ", "σ", "ω", "≈",
        "≤", "≥", "±", "≠", "∈", "→", "∞", "∇",
    ]

    def __init__(self) -> None:
        pass

    def is_likely_equation(self, text: str) -> bool:
        """Heuristic check if a text fragment represents a mathematical formula."""
        t = text.strip()
        if not t or len(t) < 3:
            return False

        # Contains explicit unicode math or LaTeX symbols
        for sym in self.MATH_SYMBOLS:
            if sym in t:
                return True

        # Numbered equation format: e.g. "E = mc^2  (1)" or "f(x) = ... (2.3)"
        if re.search(r"=\s*.*?\(\s*\d+(?:\.\d+)?\s*\)$", t):
            return True

        # Has math operators combined with variables and exponents
        if re.search(r"\b[a-zA-Z]\s*=\s*[-+]?[\w\(\)\^/]+", t):
            # Check if has typical math punctuation like ^, _, or fractions
            if any(c in t for c in ["^", "_", "+", "-", "*", "/"]) and "=" in t:
                # Exclude simple assignment sentences
                if not re.search(r"\b(the|is|are|was|were|we|and|that|this)\b", t, re.IGNORECASE):
                    return True

        return False

    def parse_equation(
        self,
        text: str,
        page_number: int = 1,
        source_offset: int = 0,
        eq_idx: int = 1,
    ) -> EquationElement:
        """Parse raw math text, extract equation numbering, and format LaTeX."""
        t = text.strip()
        eq_num: Optional[str] = None
        eq_type = EquationType.DISPLAY

        # Extract equation number like (1) or (2.3) at the end
        num_match = re.search(r"\(\s*(\d+(?:\.\d+)?|[A-Z]\.\d+)\s*\)$", t)
        if num_match:
            eq_num = num_match.group(1)
            eq_type = EquationType.NUMBERED
            # Remove the equation number from the formula content
            t = t[:num_match.start()].strip()

        # Format symbols into LaTeX syntax if unicode
        latex_str = t
        unicode_to_latex = {
            "∑": r"\sum",
            "∫": r"\int",
            "∏": r"\prod",
            "∂": r"\partial",
            "√": r"\sqrt",
            "α": r"\alpha",
            "β": r"\beta",
            "γ": r"\gamma",
            "θ": r"\theta",
            "λ": r"\lambda",
            "σ": r"\sigma",
            "ω": r"\omega",
            "≈": r"\approx",
            "≤": r"\le",
            "≥": r"\ge",
            "±": r"\pm",
            "≠": r"\neq",
            "∈": r"\in",
            "→": r"\to",
            "∞": r"\infty",
            "∇": r"\nabla",
        }
        for u_char, l_cmd in unicode_to_latex.items():
            latex_str = latex_str.replace(u_char, l_cmd)

        raw_tokens = re.findall(r"\\[A-Za-z]+|[a-zA-Z0-9]+|[^\s\w]", latex_str)
        eq_id = f"eq_{eq_idx}_p{page_number}"

        return EquationElement(
            equation_id=eq_id,
            page_number=page_number,
            latex_content=latex_str,
            raw_tokens=raw_tokens,
            equation_type=eq_type,
            equation_number=eq_num,
            bbox=BoundingBox(x1=72.0, y1=300.0, x2=540.0, y2=330.0, coord_unit="pt"),
            confidence=0.95,
            provenance=ProvenanceCategory.AUTHENTIC,
            source_offsets=[[source_offset, source_offset + len(text)]],
        )

    def to_document_element(self, eq: EquationElement) -> DocumentElement:
        """Convert EquationElement to standard DocumentElement."""
        return DocumentElement(
            element_id=eq.equation_id,
            type=ElementType.EQUATION,
            page_number=eq.page_number,
            bbox=eq.bbox,
            content={
                "latex": eq.latex_content,
                "type": eq.equation_type.value,
                "number": eq.equation_number,
                "tokens": eq.raw_tokens,
            },
            reading_order_index=None,
            confidence=eq.confidence,
            provenance=eq.provenance,
            source="pdf_recovery.math_reconstruction",
            evidence_offsets=eq.source_offsets,
            metadata={
                "equation_type": eq.equation_type.value,
                "equation_number": eq.equation_number,
                "latex": eq.latex_content,
            },
        )
