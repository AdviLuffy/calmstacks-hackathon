"""P1 Evidence & Reconstruction Engine implementation for P3 adapter integration.

Conforms to P3's engine adapter protocol (A10):
- Exposes `name`, `version`, and `run_id` (all non-empty strings).
- Exposes `analyse(request: StageRequest) -> Mapping[str, Any]`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from . import __version__
from .contract_bundle import build_contract_bundle
from .pipeline import run_pipeline

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class TraceEvidenceEngine:
    """Connected P1 Evidence & Reconstruction Engine."""

    name: str = "trace-evidence"
    version: str = __version__
    run_id: str = "RUN-0001"

    def __init__(self, run_id: str | None = None) -> None:
        if run_id:
            self.run_id = run_id
        self.engine_info = {
            "name": self.name,
            "version": self.version,
            "run_id": self.run_id,
        }

    def analyse(self, request: Any) -> Mapping[str, Any]:
        """Execute P1 recovery and reconstruction on the provided stage request.

        If media_path is provided in options or discovered in evidence metadata,
        executes the authentic P1 pipeline (scanning, DNA profiling, candidate
        relationships, structural reconstruction, and byte provenance), then builds
        a fully validated trace.evidence_bundle/1.0 bundle.
        """
        options = getattr(request, "options", {}) or {}
        evidence = getattr(request, "evidence", None)
        case_id = getattr(request, "case_id", None) or "CASE-01"

        # Determine media path
        media_path = None
        if "media_path" in options and options["media_path"]:
            candidate = Path(options["media_path"])
            if candidate.is_file():
                media_path = candidate

        if media_path is None and isinstance(evidence, Mapping):
            media_list = evidence.get("acquisition", {}).get("media", [])
            if media_list and isinstance(media_list, list):
                source_ref = media_list[0].get("source_ref")
                if source_ref:
                    # Check candidate locations
                    candidates = [
                        Path(source_ref),
                        PROJECT_ROOT / source_ref,
                        PROJECT_ROOT / "evidence" / source_ref,
                        PROJECT_ROOT / "evidence" / "datasets" / "evidence" / source_ref,
                        PROJECT_ROOT / "evidence" / "datasets" / "evidence" / Path(source_ref).name,
                    ]
                    for cand in candidates:
                        if cand.is_file():
                            media_path = cand
                            break

        if media_path is not None and media_path.is_file():
            # Run the authentic P1 pipeline
            pipeline_result = run_pipeline(
                media_path=media_path,
                run_id=self.run_id,
                original_bytes=options.get("original_bytes"),
            )
            # Assemble contract bundle
            bundle = build_contract_bundle(
                scan=pipeline_result.scan,
                reconstruction=pipeline_result.reconstruction,
                integrity_report=pipeline_result.integrity_report,
                media_path=media_path,
                case_id=case_id,
                title=options.get("case_title", "TRACE Evidence Recovery & Reconstruction"),
                investigator=options.get("investigator"),
                run_id=self.run_id,
                profiles=pipeline_result.profiles,
            )
            return bundle

        # If evidence was already supplied as an Evidence Bundle, return it
        if isinstance(evidence, Mapping) and evidence:
            return dict(evidence)

        # Fallback default empty contract bundle
        return {
            "schema_version": "trace.evidence_bundle/1.0",
            "bundle_id": "BND-P1-EMPTY",
            "generated_utc": "2026-09-25T12:00:00Z",
            "case": {"case_id": case_id, "title": "Empty Evidence"},
            "acquisition": {"media": []},
            "capabilities": {
                "byte_recovery": True,
                "carving_methods": ["fixed_block_dna_profile"],
                "hash_verification": True,
                "hash_sets": [],
                "filesystem_parsers": [],
                "timestamp_sources": [],
                "slack_space": False,
                "encrypted_containers": False,
                "limitations": ["empty_input"],
            },
            "artifacts": [],
            "engine": {
                "name": self.name,
                "version": self.version,
                "determinism": "reproducible",
                "run_id": self.run_id,
            },
            "fragments": [],
            "reconstruction_groups": [],
            "warnings": [],
        }
