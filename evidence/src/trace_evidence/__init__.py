"""TRACE evidence & reconstruction engine (subsystem 1)."""

__version__ = "0.1.0"

from .pipeline import PipelineResult, run_pipeline  # noqa: E402

__all__ = ["__version__", "PipelineResult", "run_pipeline"]
