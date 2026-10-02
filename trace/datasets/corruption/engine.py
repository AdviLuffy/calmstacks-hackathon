"""Forensic Corruption Laboratory Engine.

Applies controlled, reproducible corruption operators to document bitstreams while
generating exhaustive manifests and ground-truth recovery specifications.
"""

from __future__ import annotations

import hashlib
import random
import re
from typing import Any, Dict, List, Optional, Tuple

from trace.datasets.corruption import (
    byte_ops,
    font_ops,
    image_ops,
    layout_ops,
    stream_ops,
    structure_ops,
    text_ops,
)
from trace.datasets.schemas.corruption import (
    CorruptionManifest,
    CorruptionOperation,
    CorruptionSeverity,
    CorruptionType,
    Recoverability,
)
from trace.datasets.schemas.ground_truth import (
    FragmentLabel,
    GroundTruthInventory,
    GroundTruthRecord,
    RecoveryState,
    RelationshipLabel,
)


class ForensicCorruptionEngine:
    """Deterministic laboratory engine for corrupting documents and generating ground-truth."""

    def __init__(self, seed: int = 12345) -> None:
        self.seed = seed
        self.rng = random.Random(seed)

    @staticmethod
    def sha256(data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def inspect_inventory(self, data: bytes) -> GroundTruthInventory:
        """Inspect structural elements in a PDF bitstream."""
        objects = sorted(set(int(m.group(1)) for m in re.finditer(rb"(?:^|[\r\n\s])(\d+)\s+0\s+obj", data)))
        streams_count = len(re.findall(rb"\bstream\b", data))
        pages_count = max(1, len(re.findall(rb"/Type\s*/Page\b", data)))
        fonts_count = len(re.findall(rb"/Type\s*/Font\b", data))
        images_count = len(re.findall(rb"/Subtype\s*/Image\b", data))
        tables_count = len(re.findall(rb"\b(?:Table|Col\s*1)\b", data))
        figures_count = len(re.findall(rb"\b(?:Figure|Fig\.)\b", data))
        equations_count = len(re.findall(rb"\b(?:\\int|\\sum|dx/dt|E=mc)\b", data))
        text_matches = re.findall(rb"\(([^\)\r\n]{4,})\)", data)
        total_text_len = sum(len(t) for t in text_matches)

        return GroundTruthInventory(
            total_objects=len(objects),
            object_numbers=objects,
            streams_count=streams_count,
            pages_count=pages_count,
            fonts_count=fonts_count,
            images_count=images_count,
            tables_count=tables_count,
            figures_count=figures_count,
            equations_count=equations_count,
            total_text_length=total_text_len,
        )

    def extract_text_strings(self, data: bytes) -> List[str]:
        """Extract surviving plain text string literals."""
        strings: List[str] = []
        for m in re.finditer(rb"\(([^\)\r\n]{4,120})\)", data):
            try:
                decoded = m.group(1).decode("ascii", errors="ignore").strip()
                if decoded and not any(k in decoded for k in ["obj", "endobj", "stream"]):
                    strings.append(decoded)
            except Exception:
                pass
        return strings

    def corrupt(
        self,
        source_pdf: bytes,
        sample_id: str,
        severity: CorruptionSeverity = CorruptionSeverity.LEVEL_2,
        seed: Optional[int] = None,
    ) -> Tuple[bytes, CorruptionManifest, GroundTruthRecord]:
        """Corrupt a copy of source_pdf according to severity and produce manifest + ground truth.
        
        CRITICAL SAFETY: The input source_pdf bytes are NEVER modified.
        """
        active_seed = seed if seed is not None else self.seed
        rng = random.Random(active_seed)

        # Work on an isolated copy
        current_data = bytes(source_pdf)
        orig_sha = self.sha256(source_pdf)
        orig_len = len(source_pdf)
        orig_inventory = self.inspect_inventory(source_pdf)
        orig_strings = self.extract_text_strings(source_pdf)

        operations: List[CorruptionOperation] = []

        if severity == CorruptionSeverity.LEVEL_0:
            # Level 0: Clean pass-through
            pass
        elif severity == CorruptionSeverity.LEVEL_1:
            # Level 1: Single light operation
            choice = rng.choice(["zero_bytes", "remove_text_op", "damage_length"])
            if choice == "zero_bytes":
                pos = rng.randint(0, max(0, len(current_data) - 32))
                current_data, op = byte_ops.zero_bytes(current_data, pos, 16)
                operations.append(op)
            elif choice == "remove_text_op":
                current_data, op = text_ops.remove_text_operators(current_data, max_count=1)
                if op:
                    operations.append(op)
            elif choice == "damage_length":
                current_data, op = structure_ops.damage_length(current_data)
                if op:
                    operations.append(op)
        elif severity == CorruptionSeverity.LEVEL_2:
            # Level 2: Moderate (stream payload corruption + damage length)
            current_data, op1 = stream_ops.damage_stream_payload_only(current_data, rng=rng)
            if op1:
                operations.append(op1)
            current_data, op2 = structure_ops.damage_length(current_data)
            if op2:
                operations.append(op2)
        elif severity == CorruptionSeverity.LEVEL_3:
            # Level 3: Heavy (xref damage + trailer damage + stream truncation)
            current_data, op1 = structure_ops.damage_xref(current_data, rng=rng)
            if op1:
                operations.append(op1)
            current_data, op2 = structure_ops.damage_trailer(current_data, rng=rng)
            if op2:
                operations.append(op2)
            current_data, op3 = stream_ops.truncate_stream(current_data, keep_ratio=0.5)
            if op3:
                operations.append(op3)
            # Remove an object if multiple exist
            if len(orig_inventory.object_numbers) > 3:
                target_obj = rng.choice(orig_inventory.object_numbers[2:])
                current_data, op4 = structure_ops.remove_indirect_object(current_data, target_obj)
                if op4:
                    operations.append(op4)
        elif severity == CorruptionSeverity.LEVEL_4:
            # Level 4: Severe multi-region destruction
            current_data, op1 = layout_ops.damage_page_tree(current_data)
            if op1:
                operations.append(op1)
            current_data, op2 = structure_ops.damage_xref(current_data, rng=rng)
            if op2:
                operations.append(op2)
            current_data, op3 = stream_ops.corrupt_stream_bytes(current_data, rng=rng)
            if op3:
                operations.append(op3)
            if len(orig_inventory.object_numbers) > 2:
                for obj_num in orig_inventory.object_numbers[1:3]:
                    current_data, op_rem = structure_ops.remove_indirect_object(current_data, obj_num)
                    if op_rem:
                        operations.append(op_rem)
            # Truncate final 10%
            new_target = int(len(current_data) * 0.90)
            current_data, op_trunc = byte_ops.truncate_bytes(current_data, new_target)
            operations.append(op_trunc)

        corrupted_sha = self.sha256(current_data)
        corrupted_inventory = self.inspect_inventory(current_data)

        # Delta analysis
        removed_objs = [o for o in orig_inventory.object_numbers if o not in corrupted_inventory.object_numbers]
        surviving_objs = [o for o in orig_inventory.object_numbers if o in corrupted_inventory.object_numbers]
        damaged_objs = [
            op.object_id for op in operations if op.object_id and op.type != CorruptionType.REMOVE_OBJECT
        ]

        # Manifest
        manifest = CorruptionManifest(
            dataset_version="1.0",
            sample_id=sample_id,
            source_sha256=orig_sha,
            corrupted_sha256=corrupted_sha,
            source_length=orig_len,
            corrupted_length=len(current_data),
            seed=active_seed,
            source_format="pdf",
            severity_level=severity,
            operations=operations,
            provenance="SYNTHETIC_GROUND_TRUTH",
            metadata={"operation_count": len(operations)},
        )

        # Generate future ML training labels for fragments (256-byte blocks)
        ml_fragment_labels: Dict[str, str] = {}
        ml_recovery_states: Dict[str, str] = {}
        block_size = 256
        for block_idx in range(0, len(current_data), block_size):
            chunk = current_data[block_idx : block_idx + block_size]
            fid = f"blk_{block_idx // block_size:04d}"
            if chunk.startswith(b"%PDF"):
                ml_fragment_labels[fid] = FragmentLabel.PDF_HEADER.value
            elif b"xref" in chunk:
                ml_fragment_labels[fid] = FragmentLabel.XREF.value
            elif b"trailer" in chunk:
                ml_fragment_labels[fid] = FragmentLabel.TRAILER.value
            elif b"stream" in chunk:
                ml_fragment_labels[fid] = FragmentLabel.PDF_STREAM.value
            elif b"obj" in chunk:
                ml_fragment_labels[fid] = FragmentLabel.PDF_OBJECT.value
            else:
                ml_fragment_labels[fid] = FragmentLabel.UNKNOWN.value

        for o in orig_inventory.object_numbers:
            if o in removed_objs:
                ml_recovery_states[str(o)] = RecoveryState.MISSING.value
            elif any(str(o) in str(d) for d in damaged_objs):
                ml_recovery_states[str(o)] = RecoveryState.PARTIALLY_DAMAGED.value
            else:
                ml_recovery_states[str(o)] = RecoveryState.INTACT.value

        ground_truth = GroundTruthRecord(
            sample_id=sample_id,
            seed=active_seed,
            provenance="SYNTHETIC_GROUND_TRUTH",
            original_sha256=orig_sha,
            corrupted_sha256=corrupted_sha,
            original_size_bytes=orig_len,
            corrupted_size_bytes=len(current_data),
            original_inventory=orig_inventory,
            corrupted_inventory=corrupted_inventory,
            original_text=orig_strings,
            original_images=[],
            original_tables=[],
            original_figures=[],
            original_equations=[],
            original_metadata={"Title": "Synthetic Ground Truth Document"},
            removed_objects=removed_objs,
            surviving_objects=surviving_objs,
            damaged_objects=[int(re.search(r"\d+", str(d)).group(0)) for d in damaged_objs if re.search(r"\d+", str(d))],
            corrupted_byte_regions=[[op.offset_start, op.offset_end] for op in operations],
            expected_recoverable_content={
                "surviving_objects_count": len(surviving_objs),
                "expected_surviving_bytes": len(current_data),
            },
            expected_unrecoverable_content={
                "removed_objects_count": len(removed_objs),
            },
            ml_fragment_labels=ml_fragment_labels,
            ml_recovery_states=ml_recovery_states,
            ml_pairwise_relationships=[],
        )

        return current_data, manifest, ground_truth
