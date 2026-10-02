"""Gemini Multimodal Document Intelligence Adapter.

Provides an adapter connecting Google Gemini models (Gemini 2.5 Flash / Flash-Lite)
to the TRACE multimodal interfaces with strict forensic provenance tagging (ML_DETECTED / AI_INFERRED).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from trace.ai.client import ResilientGeminiClient
from trace.multimodal.interfaces import (
    IDocumentClassifier,
    IDocumentLayoutDetector,
    IFragmentClassifier,
    IFragmentRelationshipScorer,
    ITableDetector,
    IVisualDocumentAnalyzer,
)
from trace.multimodal.representation import (
    BoundingBox,
    DocumentElement,
    DocumentPage,
    ElementType,
    NormalizedDocument,
    ProvenanceCategory,
)


class GeminiMultimodalAdapter(
    IDocumentLayoutDetector,
    ITableDetector,
    IVisualDocumentAnalyzer,
    IDocumentClassifier,
    IFragmentClassifier,
    IFragmentRelationshipScorer,
):
    """Adapter wrapping Gemini for multimodal document layout, VDU, tables, and fragment scoring."""

    def __init__(
        self,
        gemini_client: Optional[ResilientGeminiClient] = None,
        model_name: str = "gemini-2.5-flash",
    ) -> None:
        self.client = gemini_client or ResilientGeminiClient()
        self.model_name = model_name

    def _build_ml_provenance(
        self,
        confidence: float,
        evidence_offsets: Optional[List[List[int]]] = None,
    ) -> Dict[str, Any]:
        """Construct standard mandatory ML provenance metadata record."""
        return {
            "source": "ml",
            "model": self.model_name,
            "confidence": round(confidence, 2),
            "evidence_offsets": evidence_offsets or [],
            "inference": True,
        }

    # --- IDocumentLayoutDetector ---
    def detect_layout(
        self,
        page: DocumentPage,
        raw_evidence: Optional[bytes] = None,
    ) -> List[DocumentElement]:
        """Detect document layout elements using Gemini reasoning when enabled, or fallback."""
        detected_elements: List[DocumentElement] = []

        # If client is disabled or unconfigured, return existing elements with ML provenance or empty
        if not self.client.settings.enabled or not self.client.settings.api_key:
            return detected_elements

        prompt = (
            f"Analyze the layout of Page {page.page_number}. Page dimensions: {page.width}x{page.height} pt.\n"
            f"Existing text elements: {[el.content for el in page.elements]}\n"
            "Identify headers, footers, sidebars, multi-column divisions, and paragraphs.\n"
            "Respond in JSON format with an array of objects: [{'type': 'header'|'footer'|'text_block', 'bbox': [x1, y1, x2, y2], 'content': str, 'confidence': float}]."
        )

        resp = self.client.generate_content(prompt)
        if resp.success and resp.raw_text:
            try:
                # Strip markdown fences if present
                clean_text = resp.raw_text.strip()
                if clean_text.startswith("```"):
                    clean_text = clean_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                data = json.loads(clean_text)
                items = data if isinstance(data, list) else data.get("elements", [])

                for idx, item in enumerate(items):
                    etype = ElementType(item.get("type", "text_block"))
                    conf = float(item.get("confidence", 0.90))
                    bbox_coords = item.get("bbox", [0, 0, page.width, 20])
                    bbox = BoundingBox(x1=bbox_coords[0], y1=bbox_coords[1], x2=bbox_coords[2], y2=bbox_coords[3])

                    detected_elements.append(
                        DocumentElement(
                            element_id=f"ml_layout_p{page.page_number}_{idx}",
                            type=etype,
                            page_number=page.page_number,
                            bbox=bbox,
                            content=item.get("content", ""),
                            confidence=conf,
                            provenance=ProvenanceCategory.ML_DETECTED,
                            source=self.model_name,
                            model_provenance=self._build_ml_provenance(conf),
                            metadata={"detector": "gemini_multimodal_layout"},
                        )
                    )
            except Exception:
                pass

        return detected_elements

    # --- ITableDetector ---
    def detect_tables(
        self,
        page: DocumentPage,
        raw_evidence: Optional[bytes] = None,
    ) -> List[DocumentElement]:
        """Detect and structure complex tables via Gemini."""
        detected_tables: List[DocumentElement] = []
        if not self.client.settings.enabled or not self.client.settings.api_key:
            return detected_tables

        prompt = (
            f"Examine Page {page.page_number} elements for tabular structures: {[el.content for el in page.elements]}\n"
            "Return JSON: [{'table_id': str, 'rows': [[str, ...]], 'bbox': [x1, y1, x2, y2], 'confidence': float}]"
        )
        resp = self.client.generate_content(prompt)
        if resp.success and resp.raw_text:
            try:
                clean_text = resp.raw_text.strip()
                if clean_text.startswith("```"):
                    clean_text = clean_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                data = json.loads(clean_text)
                tables = data if isinstance(data, list) else data.get("tables", [])
                for idx, tbl in enumerate(tables):
                    conf = float(tbl.get("confidence", 0.92))
                    bbox_coords = tbl.get("bbox", [50, 100, page.width - 50, 300])
                    bbox = BoundingBox(x1=bbox_coords[0], y1=bbox_coords[1], x2=bbox_coords[2], y2=bbox_coords[3])
                    rows = tbl.get("rows", [])
                    detected_tables.append(
                        DocumentElement(
                            element_id=f"ml_table_p{page.page_number}_{idx}",
                            type=ElementType.TABLE,
                            page_number=page.page_number,
                            bbox=bbox,
                            content={"rows": rows, "row_count": len(rows)},
                            confidence=conf,
                            provenance=ProvenanceCategory.ML_DETECTED,
                            source=self.model_name,
                            model_provenance=self._build_ml_provenance(conf),
                            metadata={"detector": "gemini_multimodal_table"},
                        )
                    )
            except Exception:
                pass
        return detected_tables

    # --- IVisualDocumentAnalyzer ---
    def analyze_page(
        self,
        page: DocumentPage,
        rendered_image: Optional[bytes] = None,
        context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Perform visual document understanding on page layout and structure."""
        if not self.client.settings.enabled or not self.client.settings.api_key:
            return {
                "source": "ml",
                "model": self.model_name,
                "confidence": 0.0,
                "status": "client_disabled_or_no_key",
                "analysis": "Deterministic fallback active. No remote API called.",
                "provenance": ProvenanceCategory.ML_DETECTED.value,
                "inference": True,
            }

        prompt = (
            f"Perform visual document analysis on Page {page.page_number}. Context: {context or 'None'}\n"
            f"Number of elements: {len(page.elements)}. Text snippet: {[str(el.content)[:50] for el in page.elements[:5]]}"
        )
        resp = self.client.generate_content(prompt)
        return {
            "source": "ml",
            "model": self.model_name,
            "confidence": 0.90 if resp.success else 0.0,
            "status": "success" if resp.success else "failed",
            "analysis": resp.raw_text,
            "provenance": ProvenanceCategory.ML_DETECTED.value,
            "inference": True,
        }

    # --- IDocumentClassifier ---
    def classify_document(
        self,
        document: NormalizedDocument,
    ) -> Dict[str, Any]:
        """Classify document category using Gemini."""
        if not self.client.settings.enabled or not self.client.settings.api_key:
            # Deterministic fallback classification
            from trace.multimodal.deterministic import DeterministicDocumentIntelligence
            return DeterministicDocumentIntelligence().classify_document(document)

        sample_text = " ".join(
            str(el.content)[:100]
            for page in document.pages
            for el in page.elements[:3]
        )[:1000]

        prompt = (
            f"Classify document type based on content sample:\n{sample_text}\n"
            "Return JSON: {'primary_category': str, 'confidence': float, 'reasoning': str}"
        )
        resp = self.client.generate_content(prompt)
        if resp.success and resp.raw_text:
            try:
                clean_text = resp.raw_text.strip()
                if clean_text.startswith("```"):
                    clean_text = clean_text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                data = json.loads(clean_text)
                return {
                    "primary_category": data.get("primary_category", "general_document"),
                    "confidence": float(data.get("confidence", 0.85)),
                    "reasoning": data.get("reasoning", ""),
                    "source": "ml",
                    "model": self.model_name,
                    "provenance": ProvenanceCategory.ML_DETECTED.value,
                    "inference": True,
                }
            except Exception:
                pass

        return {
            "primary_category": "general_document",
            "confidence": 0.50,
            "source": "ml",
            "model": self.model_name,
            "provenance": ProvenanceCategory.ML_DETECTED.value,
            "inference": True,
        }

    # --- IFragmentClassifier ---
    def classify_fragment(
        self,
        fragment_id: str,
        data: bytes,
    ) -> Dict[str, Any]:
        """Classify binary fragment using Gemini schema service."""
        from trace.ai.service import AIService
        service = AIService(client=self.client)
        result = service.classify_fragment(fragment_id, data)
        if result and result.data:
            return {
                "fragment_id": fragment_id,
                "likely_file_type": result.data.likely_file_type,
                "structural_role": result.data.structural_role,
                "confidence": result.data.confidence,
                "key_markers_found": result.data.key_markers_found,
                "reasoning": result.data.reasoning,
                "source": "ml",
                "model": self.model_name,
                "provenance": ProvenanceCategory.ML_DETECTED.value,
                "inference": True,
            }
        return {
            "fragment_id": fragment_id,
            "likely_file_type": "unknown",
            "structural_role": "unknown",
            "confidence": 0.0,
            "source": "ml",
            "model": self.model_name,
            "provenance": ProvenanceCategory.ML_DETECTED.value,
            "inference": True,
        }

    # --- IFragmentRelationshipScorer ---
    def score_relationship(
        self,
        fragment_a_id: str,
        fragment_a_data: bytes,
        fragment_b_id: str,
        fragment_b_data: bytes,
    ) -> Dict[str, Any]:
        """Score fragment relationship using Gemini schema service."""
        from trace.ai.service import AIService
        service = AIService(client=self.client)
        result = service.infer_relationship(
            fragment_a_id, fragment_a_data,
            fragment_b_id, fragment_b_data,
        )
        if result and result.data:
            return {
                "source_fragment_id": fragment_a_id,
                "target_fragment_id": fragment_b_id,
                "affinity_score": result.data.affinity_score,
                "relationship_type": result.data.relationship_type,
                "can_precede": result.data.can_precede,
                "reasoning": result.data.reasoning,
                "source": "ml",
                "model": self.model_name,
                "provenance": ProvenanceCategory.ML_DETECTED.value,
                "inference": True,
            }
        return {
            "source_fragment_id": fragment_a_id,
            "target_fragment_id": fragment_b_id,
            "affinity_score": 0.0,
            "relationship_type": "disjoint",
            "can_precede": False,
            "reasoning": "Relationship scoring unavailable or inconclusive.",
            "source": "ml",
            "model": self.model_name,
            "provenance": ProvenanceCategory.ML_DETECTED.value,
            "inference": True,
        }
