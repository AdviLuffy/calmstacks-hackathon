"""Model Registry and Governance for TRACE Multimodal Document Intelligence.

Documents available models, providers, tasks, licenses, model sizes, hardware requirements,
execution modes, and commercial deployment compliance.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TaskType(str, Enum):
    OCR = "ocr"
    LAYOUT = "layout"
    READING_ORDER = "reading_order"
    TABLE = "table"
    FIGURE = "figure"
    EQUATION = "equation"
    CLASSIFICATION = "classification"
    VDU = "visual_document_understanding"
    FRAGMENT_CLASSIFICATION = "fragment_classification"
    RELATIONSHIP_SCORING = "relationship_scoring"


class ExecutionMode(str, Enum):
    LOCAL_CPU = "local_cpu"
    LOCAL_GPU = "local_gpu"
    REMOTE_API = "remote_api"
    WORKER_BACKGROUND = "worker_background"


class ModelInfo(BaseModel):
    """Cataloged specification and compliance record for an intelligence model."""
    model_id: str
    model_name: str
    provider: str
    task: TaskType
    license: str
    commercial_use_permitted: bool
    model_size_mb: float = 0.0
    execution_mode: ExecutionMode
    cpu_compatible: bool = True
    gpu_recommended: bool = False
    estimated_latency_ms: int = 100
    input_type: str
    output_type: str
    description: str = ""
    notes: str = ""


class ModelRegistry:
    """Central registry and compliance auditor for document intelligence models."""

    def __init__(self) -> None:
        self._registry: Dict[str, ModelInfo] = {}
        self._register_default_models()

    def register(self, model: ModelInfo) -> None:
        """Register a new model specification."""
        self._registry[model.model_id] = model

    def get(self, model_id: str) -> Optional[ModelInfo]:
        """Retrieve model metadata by ID."""
        return self._registry.get(model_id)

    def list_models(
        self,
        task: Optional[TaskType] = None,
        commercial_only: bool = False,
        cpu_only: bool = False,
    ) -> List[ModelInfo]:
        """List cataloged models matching filters."""
        matches = list(self._registry.values())
        if task:
            matches = [m for m in matches if m.task == task]
        if commercial_only:
            matches = [m for m in matches if m.commercial_use_permitted]
        if cpu_only:
            matches = [m for m in matches if m.cpu_compatible]
        return matches

    def check_compliance(self, model_id: str) -> Dict[str, Any]:
        """Verify whether a model meets TRACE operational and licensing guidelines."""
        model = self.get(model_id)
        if not model:
            return {"valid": False, "reason": f"Model '{model_id}' is not registered."}

        issues: List[str] = []
        if not model.commercial_use_permitted:
            issues.append(f"Model {model_id} has license '{model.license}' which may restrict commercial deployment.")
        if not model.cpu_compatible and model.execution_mode == ExecutionMode.LOCAL_CPU:
            issues.append(f"Model {model_id} requires GPU and cannot run on LOCAL_CPU.")
        if model.model_size_mb > 500 and model.execution_mode != ExecutionMode.WORKER_BACKGROUND:
            issues.append(f"Model size {model.model_size_mb}MB exceeds lightweight serverless threshold (>500MB).")

        return {
            "valid": len(issues) == 0,
            "model_id": model_id,
            "license": model.license,
            "commercial_ok": model.commercial_use_permitted,
            "cpu_ok": model.cpu_compatible,
            "issues": issues,
        }

    def _register_default_models(self) -> None:
        """Populate registry with standard documented model configurations."""
        defaults = [
            ModelInfo(
                model_id="deterministic-forensic-extractor",
                model_name="TRACE Deterministic Geometry & Object Extractor",
                provider="TRACE Forensic Core",
                task=TaskType.LAYOUT,
                license="Apache-2.0",
                commercial_use_permitted=True,
                model_size_mb=0.0,
                execution_mode=ExecutionMode.LOCAL_CPU,
                cpu_compatible=True,
                gpu_recommended=False,
                estimated_latency_ms=10,
                input_type="PDF Objects / Decompressed Page Streams / Binary Evidence",
                output_type="Normalized Document Elements",
                description="Zero-dependency deterministic structural parser harvesting layout, text blocks, and objects without neural models.",
            ),
            ModelInfo(
                model_id="gemini-2.5-flash",
                model_name="Gemini 2.5 Flash Multimodal Document",
                provider="Google",
                task=TaskType.VDU,
                license="Google API Terms / Client SDK Apache-2.0",
                commercial_use_permitted=True,
                model_size_mb=0.0,
                execution_mode=ExecutionMode.REMOTE_API,
                cpu_compatible=True,
                gpu_recommended=False,
                estimated_latency_ms=650,
                input_type="Document Images / Structured Evidence Manifest",
                output_type="Structured JSON Schema with reading order, tables, and visual reasoning",
                description="Fast remote multimodal LLM for complex layout reasoning, visual QA, and damaged text restoration.",
            ),
            ModelInfo(
                model_id="tesseract-ocr-lite",
                model_name="Tesseract OCR Engine",
                provider="Open Source / Google",
                task=TaskType.OCR,
                license="Apache-2.0",
                commercial_use_permitted=True,
                model_size_mb=15.0,
                execution_mode=ExecutionMode.LOCAL_CPU,
                cpu_compatible=True,
                gpu_recommended=False,
                estimated_latency_ms=150,
                input_type="Cropped image or page raster (PNG/JPEG)",
                output_type="Bounding boxes, text characters, word confidence",
                description="Lightweight CPU-based OCR engine for scanned and degraded document segments.",
            ),
            ModelInfo(
                model_id="microsoft-table-transformer",
                model_name="Table Transformer (TATR)",
                provider="Microsoft Research",
                task=TaskType.TABLE,
                license="MIT",
                commercial_use_permitted=True,
                model_size_mb=115.0,
                execution_mode=ExecutionMode.WORKER_BACKGROUND,
                cpu_compatible=True,
                gpu_recommended=True,
                estimated_latency_ms=400,
                input_type="Page raster image",
                output_type="Table bounding boxes and cell coordinate grid",
                description="Transformer-based table detection and structure recognition model.",
            ),
            ModelInfo(
                model_id="nougat-latex-small",
                model_name="Nougat Visual Equation Reader",
                provider="Meta AI",
                task=TaskType.EQUATION,
                license="MIT",
                commercial_use_permitted=True,
                model_size_mb=350.0,
                execution_mode=ExecutionMode.WORKER_BACKGROUND,
                cpu_compatible=True,
                gpu_recommended=True,
                estimated_latency_ms=1200,
                input_type="Cropped math formula image",
                output_type="LaTeX equation string",
                description="Vision transformer specialized in transcribing academic math formulas to LaTeX.",
            ),
            ModelInfo(
                model_id="fasttext-doc-classifier",
                model_name="FastText Forensic Document Classifier",
                provider="Meta / Community",
                task=TaskType.CLASSIFICATION,
                license="MIT",
                commercial_use_permitted=True,
                model_size_mb=4.5,
                execution_mode=ExecutionMode.LOCAL_CPU,
                cpu_compatible=True,
                gpu_recommended=False,
                estimated_latency_ms=5,
                input_type="Harvested text tokens and dictionary frequencies",
                output_type="Predicted document genre and probability distribution",
                description="Ultra-fast CPU classifier for document type categorizations (research paper, invoice, legal, financial).",
            ),
        ]
        for m in defaults:
            self.register(m)


# Global default singleton registry instance
default_model_registry = ModelRegistry()
