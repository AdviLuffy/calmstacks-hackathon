"""Local-First Intelligence Provider for TRACE.

Operates completely offline on local CPU with zero external API calls, zero quota
consumption, and deterministic grounding.
"""

from __future__ import annotations

import math
import os
from pathlib import Path
import re
import time
from typing import Any, Dict, List, Optional, Tuple

from trace.ml.providers.base import (
    BaseAIProvider,
    ProviderTelemetry,
    ProviderType,
)
from trace.multimodal.deterministic import DeterministicDocumentIntelligence
from trace.multimodal.representation import (
    DocumentElement,
    DocumentPage,
    NormalizedDocument,
    ProvenanceCategory,
)


class LocalProvider(BaseAIProvider):
    """Local, offline, zero-network deterministic intelligence provider."""

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        deterministic_engine: Optional[DeterministicDocumentIntelligence] = None,
    ) -> None:
        self._cache_dir = Path(
            cache_dir
            or os.environ.get("TRACE_MODELS_CACHE_DIR")
            or Path.home() / ".cache" / "trace_models"
        )
        self._deterministic = deterministic_engine or DeterministicDocumentIntelligence()
        self._telemetry = ProviderTelemetry(
            provider="local",
            model="deterministic-forensic-engine",
            local_or_cloud="local",
            request_count=0,
            failure_reason=None,
            fallback_used=False,
            latency_ms=0.0,
        )

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.LOCAL

    @property
    def is_cloud(self) -> bool:
        return False

    @property
    def is_available(self) -> bool:
        return True

    @property
    def cache_directory(self) -> Path:
        """Local cache path where optional pre-downloaded weights can reside.
        
        TRACE never automatically downloads large models on startup.
        """
        return self._cache_dir

    def get_telemetry(self) -> ProviderTelemetry:
        return self._telemetry

    def _record_call(self, latency_ms: float) -> None:
        self._telemetry.request_count += 1
        self._telemetry.latency_ms += latency_ms

    def classify_fragment(
        self,
        fragment_id: str,
        data: bytes,
    ) -> Dict[str, Any]:
        """Classify a fragment using local Shannon entropy and signature scanning."""
        start = time.time()
        size = len(data)
        entropy = 0.0
        if size > 0:
            counts = [0] * 256
            for b in data:
                counts[b] += 1
            for count in counts:
                if count > 0:
                    p = count / size
                    entropy -= p * math.log2(p)
            entropy = round(entropy, 2)

        file_type = "unknown"
        role = "data"
        markers = []

        if data.startswith(b"%PDF"):
            file_type = "pdf"
            role = "header"
            markers.append("%PDF")
        elif b"%%EOF" in data:
            file_type = "pdf"
            role = "footer"
            markers.append("%%EOF")
        elif b"xref" in data or b"/Root" in data:
            file_type = "pdf"
            role = "catalog"
            markers.append("xref" if b"xref" in data else "/Root")
        elif b"stream" in data:
            file_type = "pdf"
            role = "stream"
            markers.append("stream")
        elif data.startswith(b"\x89PNG\r\n\x1a\n"):
            file_type = "png"
            role = "image"
            markers.append("PNG")
        elif data.startswith(b"\xff\xd8\xff"):
            file_type = "jpeg"
            role = "image"
            markers.append("JPEG")

        # Optional local ML fragment prediction enrichment (if trained weights exist)
        ml_enrichment = None
        try:
            from trace.ml.inference.fragment_predictor import get_default_fragment_predictor
            predictor = get_default_fragment_predictor()
            if predictor.is_ml_active:
                ml_pred = predictor.predict_fragment(data)
                ml_enrichment = {
                    "ml_label": ml_pred.predicted_label,
                    "ml_confidence": ml_pred.confidence,
                    "ml_abstained": ml_pred.abstained,
                    "ml_provenance": ml_pred.provenance,
                    "ml_probabilities": ml_pred.probabilities,
                    "ml_top_signals": ml_pred.top_signals,
                    "model_version": ml_pred.model_version,
                }
        except Exception:
            pass

        elapsed_ms = (time.time() - start) * 1000
        self._record_call(elapsed_ms)

        res: Dict[str, Any] = {
            "fragment_id": fragment_id,
            "likely_file_type": file_type,
            "structural_role": role,
            "confidence": 0.95 if markers else 0.50,
            "key_markers_found": markers,
            "reasoning": f"Local deterministic classification: {len(markers)} markers found, entropy={entropy}.",
            "source": "local_provider",
            "provenance": ProvenanceCategory.DETERMINISTIC.value,
            "inference": False,
        }
        if ml_enrichment:
            res["ml_enrichment"] = ml_enrichment

        return res

    def infer_relationship(
        self,
        frag_a_id: str,
        frag_a_data: bytes,
        frag_b_id: str,
        frag_b_data: bytes,
    ) -> Dict[str, Any]:
        """Infer affinity between two fragments using local syntax continuity and relationship scoring."""
        start = time.time()
        from trace.ml.relationships.features import FragmentInput
        from trace.ml.relationships.scorer import ForensicRelationshipScorer

        scorer = ForensicRelationshipScorer()
        cand = scorer.score_pair(
            FragmentInput(fragment_id=frag_a_id, data=frag_a_data),
            FragmentInput(fragment_id=frag_b_id, data=frag_b_data),
        )

        can_precede = cand.affinity_score >= 0.50 and cand.relationship_type.value != "DISJOINT"
        reasoning = (
            f"Forensic relationship scoring ({cand.relationship_type.value}): "
            + (", ".join(cand.evidence_observed + cand.inferred_compatibility) or "No strong continuity signals detected.")
        )

        elapsed_ms = (time.time() - start) * 1000
        self._record_call(elapsed_ms)

        return {
            "source_fragment_id": frag_a_id,
            "target_fragment_id": frag_b_id,
            "affinity_score": cand.affinity_score,
            "relationship_type": cand.relationship_type.value.lower(),
            "confidence_tier": cand.confidence_tier.value,
            "can_precede": can_precede,
            "component_scores": cand.component_scores,
            "evidence_observed": cand.evidence_observed,
            "inferred_compatibility": cand.inferred_compatibility,
            "negative_signals": cand.negative_signals,
            "uncertainty_limitations": cand.uncertainty_limitations,
            "reasoning": reasoning,
            "source": "local_provider",
            "provenance": ProvenanceCategory.DETERMINISTIC.value,
            "inference": False,
        }

    def generate_reconstruction_plan(
        self,
        case_id: str,
        features: Dict[str, Any],
        media_size: int,
        authentic_bytes: int,
        unplaced_count: int,
        session_metadata: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Any, str, str, bool, str]:
        """Generate deterministic semantic reconstruction plan with ZERO external calls."""
        start = time.time()
        from trace.ai.reconstruction import generate_fallback_plan

        plan = generate_fallback_plan(
            case_id=case_id,
            features=features,
            authentic_bytes=authentic_bytes,
            media_size=media_size,
            unplaced_count=unplaced_count,
        )

        elapsed_ms = (time.time() - start) * 1000
        self._record_call(elapsed_ms)

        return (
            plan,
            "deterministic-forensic-engine",
            "local",
            False,
            f"Deterministic local reconstruction grounded in {authentic_bytes} authentic recovered bytes.",
        )

    def detect_layout(
        self,
        page: DocumentPage,
        raw_evidence: Optional[bytes] = None,
    ) -> List[DocumentElement]:
        start = time.time()
        res = self._deterministic.detect_layout(page, raw_evidence)
        self._record_call((time.time() - start) * 1000)
        return res

    def detect_tables(
        self,
        page: DocumentPage,
        raw_evidence: Optional[bytes] = None,
    ) -> List[DocumentElement]:
        start = time.time()
        res = self._deterministic.detect_tables(page, raw_evidence)
        self._record_call((time.time() - start) * 1000)
        return res

    def classify_document(
        self,
        document: NormalizedDocument,
    ) -> Dict[str, Any]:
        start = time.time()
        res = self._deterministic.classify_document(document)
        self._record_call((time.time() - start) * 1000)
        return res
