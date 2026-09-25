"""End-to-end P1 evidence processing and reconstruction pipeline.

Chains the P1 engine steps sequentially:
1. Carves fixed-size fragments from the raw evidence media (scanning).
2. Assembles the minimal Evidence Bundle conforming to the frozen schema (bundle).
3. Profiles structural DNA markers from carved blocks (dna).
4. Derives candidate ordering relationships (relationships).
5. Assembles authentic bytes and validates PDF structure (reconstruction).
6. Tracks complete byte provenance and validates integrity (integrity).
7. Optionally exports artifacts to disk (bundle, reconstructed PDF, integrity report).

Honesty invariants:
- Never fabricate, pad, or synthesize bytes.
- Open source media read-only; never modify evidence.
- Zero oracle pollution: production code reads only the input media, never manifests
  or ground truth.
- Candidate relationships remain candidates with byte_contiguity=False.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .bundle import build_bundle, new_run_id, write_bundle
from .constants import (
    BLOCK_SIZE,
    STATUS_STRUCTURALLY_VALID,
    STATUS_VERIFIED,
)
from .dna import FragmentProfile, profile_fragment
from .integrity import IntegrityReport, verify_integrity
from .reconstruction import ReconstructionResult, reconstruct
from .relationships import RelationshipAnalysis, derive_relationships
from .scanning import ScanResult, scan_media

__all__ = ["PipelineResult", "run_pipeline"]


@dataclass(frozen=True)
class PipelineResult:
    """Consolidated outcome of the end-to-end P1 engine pipeline."""

    run_id: str
    media_path: str
    scan: ScanResult
    bundle: dict
    profiles: tuple[FragmentProfile, ...]
    analysis: RelationshipAnalysis
    reconstruction: ReconstructionResult
    integrity_report: IntegrityReport
    output_files: dict[str, str]

    @property
    def is_complete(self) -> bool:
        """True if reconstruction is complete and structurally valid or verified."""
        return self.reconstruction.complete and self.integrity_report.status in (
            STATUS_STRUCTURALLY_VALID,
            STATUS_VERIFIED,
        )

    @property
    def recovery_state(self) -> str:
        """Forensic recovery evaluation state."""
        return self.integrity_report.recovery_state


def run_pipeline(
    media_path: str | Path,
    run_id: str | None = None,
    block_size: int = BLOCK_SIZE,
    out_dir: str | Path | None = None,
    original_bytes: bytes | None = None,
) -> PipelineResult:
    """Execute the end-to-end P1 evidence and reconstruction pipeline.

    Inputs are strictly the raw evidence media file and optional caller configurations.
    Zero ground truth or manifest data is read by this function.
    """
    path = Path(media_path)
    if not path.is_file():
        raise FileNotFoundError(f"evidence media file not found: {path}")

    active_run_id = run_id if run_id is not None else new_run_id()

    # Step 3: Scan media into fragments and build Evidence Bundle
    scan = scan_media(path, block_size=block_size)
    bundle = build_bundle(scan, run_id=active_run_id)

    # Read authentic blocks for profiling and reconstruction (never in memory all at once for large files)
    fragment_bytes: dict[str, bytes] = {}
    with open(path, "rb") as handle:
        for fragment in scan.fragments:
            handle.seek(fragment.start)
            block = handle.read(fragment.size_bytes)
            fragment_bytes[fragment.fragment_id] = block

    # Step 4: DNA profiling
    profiles = tuple(
        profile_fragment(frag, fragment_bytes[frag.fragment_id])
        for frag in scan.fragments
    )

    # Step 5: Candidate relationship derivation
    analysis = derive_relationships(profiles)

    # Step 6: Reconstruction and structural self-validation
    try:
        reconstruction_res = reconstruct(
            analysis=analysis,
            profiles=profiles,
            fragment_bytes=fragment_bytes,
            fragments=scan.fragments,
        )
    except FragmentCorruptionError as err:
        from .constants import STATUS_FAILED, RECOVERY_CORRUPTED
        from .reconstruction import StructureValidationResult
        val = StructureValidationResult(
            is_valid=False,
            status=STATUS_FAILED,
            errors=(str(err),),
        )
        reconstruction_res = ReconstructionResult(
            raw_bytes=b"",
            fragment_order=(),
            relationships_used=(),
            validation=val,
            status=STATUS_FAILED,
            warnings=(str(err),),
            unresolved=analysis.unresolved,
            unplaced_fragment_ids=analysis.unplaced_fragment_ids,
            missing_elements=getattr(analysis, "missing_elements", ()),
            corrupted_fragment_ids=(getattr(err, "fragment_id", None) or "unknown",),
            recovery_state=RECOVERY_CORRUPTED,
        )

    # Step 7: Byte provenance and integrity verification
    integrity_res = verify_integrity(
        reconstruction=reconstruction_res,
        fragments=scan.fragments,
        original_bytes=original_bytes,
    )

    # Export output files if requested
    output_files: dict[str, str] = {}
    if out_dir is not None:
        target_dir = Path(out_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        bundle_path = target_dir / "evidence_bundle.json"
        write_bundle(bundle_path, bundle)
        output_files["evidence_bundle"] = str(bundle_path)

        if reconstruction_res.raw_bytes:
            recon_path = target_dir / "reconstructed.pdf"
            recon_path.write_bytes(reconstruction_res.raw_bytes)
            output_files["reconstructed_pdf"] = str(recon_path)

        report_path = target_dir / "integrity_report.json"
        report_payload = json.dumps(integrity_res.to_dict(), indent=2, sort_keys=True) + "\n"
        report_path.write_text(report_payload, encoding="utf-8", newline="\n")
        output_files["integrity_report"] = str(report_path)

    return PipelineResult(
        run_id=active_run_id,
        media_path=str(path),
        scan=scan,
        bundle=bundle,
        profiles=profiles,
        analysis=analysis,
        reconstruction=reconstruction_res,
        integrity_report=integrity_res,
        output_files=output_files,
    )
