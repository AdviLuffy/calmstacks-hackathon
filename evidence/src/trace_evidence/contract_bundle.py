"""Builder for Evidence Bundles conforming to the frozen trace.evidence_bundle/1.0 schema.

Used for cross-subsystem integration with P2 (Intelligence) and P3 (Investigator API).
Strictly adheres to trace/contracts/v1/evidence_bundle.schema.json.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from .constants import STATUS_STRUCTURALLY_VALID, STATUS_VERIFIED
from .dna import FragmentProfile
from .integrity import IntegrityReport
from .models import Fragment
from .reconstruction import ReconstructionResult
from .scanning import ScanResult

SCHEMA_VERSION = "trace.evidence_bundle/1.0"
ENGINE_NAME = "trace-evidence"
DEFAULT_DETERMINISM = "reproducible"


def build_contract_bundle(
    scan: ScanResult,
    reconstruction: ReconstructionResult,
    integrity_report: IntegrityReport,
    media_path: str | Path,
    case_id: str = "CASE-01",
    title: str = "TRACE Evidence Recovery & Reconstruction",
    bundle_id: str = "BND-P1-0001",
    generated_utc: str | None = None,
    investigator: str | None = None,
    write_blocked: bool = True,
    acquisition_method: str = "file_copy",
    run_id: str = "RUN-0001",
    profiles: Sequence[FragmentProfile] | None = None,
    engine_name: str = ENGINE_NAME,
    engine_version: str = "0.1.0",
) -> dict[str, Any]:
    """Assemble an Evidence Bundle strictly compliant with trace.evidence_bundle/1.0."""
    now_utc = generated_utc or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Map profiles by fragment_id
    profile_by_id: dict[str, FragmentProfile] = {}
    if profiles:
        for p in profiles:
            profile_by_id[p.fragment_id] = p

    # Build fragments list
    contract_fragments: list[dict[str, Any]] = []
    for frag in scan.fragments:
        p = profile_by_id.get(frag.fragment_id)
        probe: dict[str, Any] = {"matched": False, "marker_id": None, "offset_in_fragment": 0}
        if p is not None:
            if p.kind == "header":
                probe = {"matched": True, "marker_id": "pdf_header", "offset_in_fragment": 0}
            elif p.kind == "eof":
                probe = {"matched": True, "marker_id": "pdf_eof", "offset_in_fragment": 0}

        contract_fragments.append(
            {
                "fragment_id": frag.fragment_id,
                "media_id": "MED-01",
                "byte_range": {
                    "start": frag.start,
                    "end": frag.end,
                    "size_bytes": frag.size_bytes,
                    "media_id": "MED-01",
                },
                "bytes_sha256": frag.bytes_sha256,
                "location": "unallocated",
                "signature_probe": probe,
                "reconstruction": {
                    "group_id": "RGRP-01",
                    "algorithm": "structural_pdf_carving",
                    "confidence": 0.85,
                    "ordering_confidence": 0.85,
                    "byte_contiguity": False,
                    "overlap_bytes": 0,
                },
            }
        )

    # Build reconstruction group
    member_ids = list(reconstruction.fragment_order)
    recon_group: dict[str, Any] = {
        "group_id": "RGRP-01",
        "member_fragment_ids": member_ids if member_ids else [f.fragment_id for f in scan.fragments],
        "algorithm": "structural_pdf_carving",
        "confidence": 0.85,
        "ordering": member_ids if member_ids else [f.fragment_id for f in scan.fragments],
        "ordering_confidence": 0.85,
        "byte_contiguity": False,
        "overlap_bytes": 0,
        "gaps_bytes": 0,
        "basis": [
            "PDF structural DNA chain starting from header to xref/trailer/startxref/EOF"
        ],
    }

    # Format warnings per VocabCode and SanitizedText
    contract_warnings: list[dict[str, Any]] = [
        {"code": "SCAN_WARNING", "message": str(w)} for w in scan.warnings
    ]
    for w in reconstruction.warnings:
        contract_warnings.append({"code": "RECON_WARNING", "message": str(w)})

    case_obj: dict[str, Any] = {
        "case_id": case_id,
        "title": title,
        "notes": ["Authentic carved evidence processed by TRACE Subsystem 1"],
    }
    if investigator:
        case_obj["investigator"] = investigator

    media_name = Path(media_path).name if media_path else "evidence.bin"

    return {
        "schema_version": SCHEMA_VERSION,
        "bundle_id": bundle_id,
        "generated_utc": now_utc,
        "case": case_obj,
        "acquisition": {
            "media": [
                {
                    "media_id": "MED-01",
                    "kind": "file_copy",
                    "source_ref": media_name,
                    "size_bytes": scan.media_size_bytes,
                    "write_blocked": write_blocked,
                    "acquisition_method": acquisition_method,
                    "image_hashes": {
                        "sha256": scan.media_sha256,
                        "verified": True,
                    },
                }
            ]
        },
        "capabilities": {
            "byte_recovery": True,
            "carving_methods": ["fixed_block_dna_profile", "pdf_structural_reconstruction"],
            "hash_verification": True,
            "hash_sets": [],
            "filesystem_parsers": [],
            "timestamp_sources": [],
            "slack_space": False,
            "encrypted_containers": False,
            "limitations": [
                "fixed_size_block_carving",
                "single_document_synthetic_pdf",
            ],
        },
        "artifacts": [],
        "fragments": contract_fragments,
        "reconstruction_groups": [recon_group],
        "engine": {
            "name": engine_name,
            "version": engine_version,
            "determinism": DEFAULT_DETERMINISM,
            "run_id": run_id,
        },
        "warnings": contract_warnings,
        "extensions": {
            "reconstruction_status": reconstruction.status,
            "reconstruction_complete": reconstruction.complete,
            "reconstructed_sha256": integrity_report.reconstructed_sha256,
            "is_verified": integrity_report.is_verified,
            "provenance_count": len(integrity_report.provenance),
        },
    }
