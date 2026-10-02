"""Forensic Artifact Packaging and Verification for TRACE Phase 9.

Manages saving and verifying the 5 separate forensic artifacts:
1. Original Evidence
2. Authentic Recovered Bytes (unmodified carved evidence)
3. Deterministically Repaired PDF (ISO 32000-1 compliant)
4. Multimodal Reconstructed PDF (high-fidelity synthesis)
5. Structured Reconstruction Report (JSON)
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from trace.reconstruction.models import (
    MultimodalReconstructionReport,
    ReconstructionArtifacts,
)

logger = logging.getLogger(__name__)


class ReconstructionArtifactManager:
    """Handles verification and export of the 5 separate forensic recovery artifacts."""

    def __init__(self) -> None:
        pass

    def compute_sha256(self, data: bytes) -> str:
        """Compute SHA256 cryptographic digest."""
        return hashlib.sha256(data).hexdigest()

    def export_artifacts(
        self,
        artifacts: ReconstructionArtifacts,
        output_dir: Union[str, Path],
        base_name: str = "evidence",
    ) -> Dict[str, str]:
        """Save the 5 separate artifacts to the target directory and return absolute paths."""
        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)

        # 1. Original evidence
        orig_file = out_path / f"{base_name}_original.bin"
        with open(orig_file, "wb") as f:
            f.write(artifacts.original_evidence)

        # 2. Authentic carved partial bytes
        auth_file = out_path / f"{base_name}_authentic_recovered.bin"
        with open(auth_file, "wb") as f:
            f.write(artifacts.authentic_recovered_bytes)

        # 3. Repaired PDF
        repaired_file = out_path / f"{base_name}_repaired.pdf"
        with open(repaired_file, "wb") as f:
            f.write(artifacts.repaired_pdf)

        # 4. Multimodal reconstructed PDF
        recon_file = out_path / f"{base_name}_multimodal_reconstructed.pdf"
        with open(recon_file, "wb") as f:
            f.write(artifacts.multimodal_reconstructed_pdf)

        # Update report with file locations and SHA256 hashes
        report_dict = artifacts.report.to_dict()
        report_dict["artifacts"] = {
            "original_evidence": {
                "path": str(orig_file),
                "bytes": len(artifacts.original_evidence),
                "sha256": self.compute_sha256(artifacts.original_evidence),
            },
            "authentic_recovered_bytes": {
                "path": str(auth_file),
                "bytes": len(artifacts.authentic_recovered_bytes),
                "sha256": self.compute_sha256(artifacts.authentic_recovered_bytes),
            },
            "repaired_pdf": {
                "path": str(repaired_file),
                "bytes": len(artifacts.repaired_pdf),
                "sha256": self.compute_sha256(artifacts.repaired_pdf),
            },
            "multimodal_reconstructed_pdf": {
                "path": str(recon_file),
                "bytes": len(artifacts.multimodal_reconstructed_pdf),
                "sha256": self.compute_sha256(artifacts.multimodal_reconstructed_pdf),
            },
        }

        # 5. Reconstruction report JSON
        report_file = out_path / f"{base_name}_reconstruction_report.json"
        with open(report_file, "w", encoding="utf-8") as f:
            json.dump(report_dict, f, indent=2)

        report_dict["artifacts"]["report"] = {
            "path": str(report_file),
            "bytes": report_file.stat().st_size,
            "sha256": self.compute_sha256(report_file.read_bytes()),
        }

        # Update in-memory report artifact map
        artifacts.report.artifacts = {
            "original_evidence": str(orig_file),
            "authentic_recovered_bytes": str(auth_file),
            "repaired_pdf": str(repaired_file),
            "multimodal_reconstructed_pdf": str(recon_file),
            "report": str(report_file),
        }

        return artifacts.report.artifacts
