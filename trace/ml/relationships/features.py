"""Explainable pairwise feature extraction for forensic fragment relationships.

Extracts deterministic structural, offset, delimiter, boundary, and advisory ML features
between two fragments without data leakage.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

_OBJ_DEF_RE = re.compile(rb"\b(\d+)\s+(\d+)\s+obj\b")
_OBJ_REF_RE = re.compile(rb"\b(\d+)\s+(\d+)\s+R\b")
_KNOWN_SPLIT_TOKENS = [
    (b"end", b"obj", b"endobj"),
    (b"str", b"eam", b"stream"),
    (b"stre", b"am", b"stream"),
    (b"ends", b"tream", b"endstream"),
    (b"endst", b"ream", b"endstream"),
    (b"start", b"xref", b"startxref"),
    (b"%%E", b"OF", b"%%EOF"),
    (b"/Len", b"gth", b"/Length"),
    (b"/Ty", b"pe", b"/Type"),
    (b"/Pa", b"ge", b"/Page"),
    (b"/Fo", b"nt", b"/Font"),
    (b"<<", b">>", b"<<>>"),
]


@dataclass
class FragmentInput:
    """Standardized representation of a candidate fragment for relationship analysis."""
    fragment_id: str
    data: bytes
    length: int = 0
    offset: Optional[int] = None
    source_id: Optional[str] = None
    predicted_label: Optional[str] = None
    label_confidence: float = 0.0
    label_abstained: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.length <= 0 and self.data:
            self.length = len(self.data)


@dataclass
class PairwiseRelationshipFeatures:
    """Extracted pairwise features and categorized evidence between Fragment A and Fragment B."""
    from_fragment_id: str
    to_fragment_id: str

    # Spatial / Offset Features
    same_source: bool = False
    offset_distance: Optional[int] = None
    is_physically_adjacent: bool = False
    is_forward_ordered: bool = False
    spatial_proximity_score: float = 0.0

    # Object ID & Reference Continuity
    objs_defined_in_a: List[Tuple[int, int]] = field(default_factory=list)
    objs_defined_in_b: List[Tuple[int, int]] = field(default_factory=list)
    objs_referenced_in_a: List[Tuple[int, int]] = field(default_factory=list)
    objs_referenced_in_b: List[Tuple[int, int]] = field(default_factory=list)
    a_references_b: bool = False
    b_references_a: bool = False
    has_ascending_object_id: bool = False

    # Stream & Delimiter Boundary Continuity
    stream_opened_in_a: bool = False
    endstream_in_b: bool = False
    stream_continuation_signal: bool = False
    stream_conflict_signal: bool = False
    dict_opened_in_a: bool = False
    dict_closed_in_b: bool = False
    dict_continuation_signal: bool = False
    text_opened_in_a: bool = False
    text_closed_in_b: bool = False
    text_continuation_signal: bool = False

    # Byte Boundary Concatenation
    token_boundary_continuity: bool = False
    boundary_joined_token: Optional[str] = None
    ascii_boundary_continuity: bool = False

    # Structural Transitions
    is_header_to_body: bool = False
    is_body_to_xref: bool = False
    is_xref_to_trailer: bool = False
    is_trailer_to_eof: bool = False

    # Contradictions / Negative Compatibility
    is_contradictory_header_pair: bool = False
    is_contradictory_eof_pair: bool = False
    is_contradictory_direction: bool = False

    # ML Advisory Signals
    ml_advisory_compatibility: float = 0.0
    ml_pair_label: Optional[str] = None

    # Categorized Evidence Trails
    observed_evidence: List[str] = field(default_factory=list)
    inferred_compatibility: List[str] = field(default_factory=list)
    negative_signals: List[str] = field(default_factory=list)
    uncertainty_factors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_fragment_id": self.from_fragment_id,
            "to_fragment_id": self.to_fragment_id,
            "same_source": self.same_source,
            "offset_distance": self.offset_distance,
            "is_physically_adjacent": self.is_physically_adjacent,
            "is_forward_ordered": self.is_forward_ordered,
            "spatial_proximity_score": round(self.spatial_proximity_score, 4),
            "a_references_b": self.a_references_b,
            "b_references_a": self.b_references_a,
            "has_ascending_object_id": self.has_ascending_object_id,
            "stream_continuation_signal": self.stream_continuation_signal,
            "dict_continuation_signal": self.dict_continuation_signal,
            "text_continuation_signal": self.text_continuation_signal,
            "token_boundary_continuity": self.token_boundary_continuity,
            "boundary_joined_token": self.boundary_joined_token,
            "is_contradictory_header_pair": self.is_contradictory_header_pair,
            "is_contradictory_eof_pair": self.is_contradictory_eof_pair,
            "observed_evidence": self.observed_evidence,
            "inferred_compatibility": self.inferred_compatibility,
            "negative_signals": self.negative_signals,
            "uncertainty_factors": self.uncertainty_factors,
        }


class PairwiseFeatureExtractor:
    """Computes explainable pairwise relationships between two forensic fragments."""

    def extract_features(
        self,
        frag_a: FragmentInput,
        frag_b: FragmentInput,
    ) -> PairwiseRelationshipFeatures:
        """Extract all physical, structural, and semantic features between A and B."""
        data_a = bytes(frag_a.data)
        data_b = bytes(frag_b.data)
        len_a = len(data_a)
        len_b = len(data_b)

        features = PairwiseRelationshipFeatures(
            from_fragment_id=frag_a.fragment_id,
            to_fragment_id=frag_b.fragment_id,
        )

        # ---------------------------------------------------------
        # 1. Spatial & Offset Distance (Observed only if same source)
        # ---------------------------------------------------------
        same_src = (
            frag_a.source_id is not None
            and frag_b.source_id is not None
            and frag_a.source_id == frag_b.source_id
        )
        features.same_source = same_src

        if same_src and frag_a.offset is not None and frag_b.offset is not None:
            gap = frag_b.offset - (frag_a.offset + len_a)
            features.offset_distance = gap

            if gap == 0:
                features.is_physically_adjacent = True
                features.is_forward_ordered = True
                features.spatial_proximity_score = 1.0
                features.observed_evidence.append(
                    f"exact_physical_adjacency(offset_a={frag_a.offset}, len_a={len_a}, offset_b={frag_b.offset})"
                )
            elif gap > 0:
                features.is_forward_ordered = True
                features.spatial_proximity_score = 1.0 / (1.0 + math.log1p(gap))
                features.observed_evidence.append(
                    f"forward_offset_gap(gap={gap} bytes, offset_a={frag_a.offset}, offset_b={frag_b.offset})"
                )
                if gap > 4096:
                    features.uncertainty_factors.append(f"large_spatial_gap({gap}_bytes)")
            else:
                features.is_forward_ordered = False
                features.spatial_proximity_score = 0.0
                features.negative_signals.append(
                    f"reverse_offset_ordering(frag_b offset {frag_b.offset} precedes frag_a end {frag_a.offset + len_a})"
                )
        else:
            if frag_a.source_id is not None and frag_b.source_id is not None and frag_a.source_id != frag_b.source_id:
                features.uncertainty_factors.append("different_evidence_sources")
            features.uncertainty_factors.append("unknown_or_disparate_evidence_sources")

        # ---------------------------------------------------------
        # 2. Object Identification & Numerical References
        # ---------------------------------------------------------
        defs_a = [(int(m.group(1)), int(m.group(2))) for m in _OBJ_DEF_RE.finditer(data_a)]
        defs_b = [(int(m.group(1)), int(m.group(2))) for m in _OBJ_DEF_RE.finditer(data_b)]
        refs_a = [(int(m.group(1)), int(m.group(2))) for m in _OBJ_REF_RE.finditer(data_a)]
        refs_b = [(int(m.group(1)), int(m.group(2))) for m in _OBJ_REF_RE.finditer(data_b)]

        features.objs_defined_in_a = defs_a
        features.objs_defined_in_b = defs_b
        features.objs_referenced_in_a = refs_a
        features.objs_referenced_in_b = refs_b

        # Matching references
        set_defs_b = set(defs_b)
        set_defs_a = set(defs_a)

        matching_a_refs = [r for r in refs_a if r in set_defs_b]
        matching_b_refs = [r for r in refs_b if r in set_defs_a]

        if matching_a_refs:
            features.a_references_b = True
            ref_str = ", ".join(f"{num} {gen} R" for num, gen in matching_a_refs)
            features.observed_evidence.append(f"fragment_a_references_fragment_b_objects({ref_str})")
            features.inferred_compatibility.append("parent_child_object_reference")

        if matching_b_refs:
            features.b_references_a = True
            ref_str = ", ".join(f"{num} {gen} R" for num, gen in matching_b_refs)
            features.observed_evidence.append(f"fragment_b_references_fragment_a_objects({ref_str})")
            features.inferred_compatibility.append("backward_object_reference")

        # Ascending Object Number heuristic (consecutive or near-consecutive)
        if defs_a and defs_b:
            max_a = max(num for num, _ in defs_a)
            min_b = min(num for num, _ in defs_b)
            if min_b > max_a and (min_b - max_a <= 2):
                features.has_ascending_object_id = True
                features.observed_evidence.append(f"ascending_object_id_sequence({max_a}->{min_b})")
                features.inferred_compatibility.append("sequential_object_order")
            elif min_b < max_a:
                features.negative_signals.append(f"descending_object_id_sequence({max_a}->{min_b})")

        # ---------------------------------------------------------
        # 3. Stream & Boundary Syntax Continuity
        # ---------------------------------------------------------
        stream_in_a = data_a.count(b"stream")
        endstream_in_a = data_a.count(b"endstream")
        stream_in_b = data_b.count(b"stream")
        endstream_in_b = data_b.count(b"endstream")

        if stream_in_a > endstream_in_a:
            features.stream_opened_in_a = True
            features.observed_evidence.append("unclosed_stream_marker_in_fragment_a")
            # If B provides endstream or non-object stream content
            if endstream_in_b > 0 or (stream_in_b == 0 and not defs_b):
                features.stream_continuation_signal = True
                features.inferred_compatibility.append("stream_payload_or_endstream_continuation")

        if endstream_in_a > 0 and endstream_in_b > 0 and stream_in_b == 0 and not defs_b:
            features.stream_conflict_signal = True
            features.negative_signals.append("redundant_endstream_without_new_stream")

        # Dictionary delimiter continuity
        dict_open_a = data_a.count(b"<<")
        dict_close_a = data_a.count(b">>")
        dict_close_b = data_b.count(b">>")
        if dict_open_a > dict_close_a:
            features.dict_opened_in_a = True
            features.observed_evidence.append("unclosed_dictionary_delimiter_in_fragment_a")
            if dict_close_b > 0:
                features.dict_closed_in_b = True
                features.dict_continuation_signal = True
                features.inferred_compatibility.append("dictionary_closing_delimiter_continuation")

        # Text block continuity
        bt_a = data_a.count(b"BT")
        et_a = data_a.count(b"ET")
        et_b = data_b.count(b"ET")
        if bt_a > et_a:
            features.text_opened_in_a = True
            features.observed_evidence.append("unclosed_text_object_bt_in_fragment_a")
            if et_b > 0 or b"Tj" in data_b or b"TJ" in data_b:
                features.text_closed_in_b = True
                features.text_continuation_signal = True
                features.inferred_compatibility.append("text_operator_or_et_continuation")

        # ---------------------------------------------------------
        # 4. Token Boundary Concatenation Continuity
        # ---------------------------------------------------------
        tail_a = data_a[-24:] if len_a >= 24 else data_a
        head_b = data_b[:24] if len_b >= 24 else data_b

        for sfx, pfx, full in _KNOWN_SPLIT_TOKENS:
            if tail_a.endswith(sfx) and head_b.startswith(pfx):
                features.token_boundary_continuity = True
                features.boundary_joined_token = full.decode("latin1", errors="replace")
                features.observed_evidence.append(
                    f"boundary_token_join({sfx.decode('latin1')}+{pfx.decode('latin1')} -> {features.boundary_joined_token})"
                )
                features.inferred_compatibility.append("seamless_token_splice")
                break

        # Suffix / Prefix ASCII character continuity
        if tail_a and head_b:
            last_byte = tail_a[-1]
            first_byte = head_b[0]
            # Alphanumeric continuation without space
            if (48 <= last_byte <= 57 or 65 <= last_byte <= 90 or 97 <= last_byte <= 122) and (
                48 <= first_byte <= 57 or 65 <= first_byte <= 90 or 97 <= first_byte <= 122
            ):
                features.ascii_boundary_continuity = True

        # ---------------------------------------------------------
        # 5. Structural Transitions & Macro Ordering
        # ---------------------------------------------------------
        has_header_a = data_a.startswith(b"%PDF") or b"%PDF-" in data_a[:32]
        has_header_b = data_b.startswith(b"%PDF") or b"%PDF-" in data_b[:32]
        has_eof_a = b"%%EOF" in data_a
        has_eof_b = b"%%EOF" in data_b
        has_xref_a = b"xref" in data_a
        has_xref_b = b"xref" in data_b
        has_trailer_a = b"trailer" in data_a or b"startxref" in data_a
        has_trailer_b = b"trailer" in data_b or b"startxref" in data_b

        # Check if B contains actual PDF body structure (not null noise)
        has_body_b = bool(
            defs_b
            or b"obj" in data_b
            or b"<<" in data_b
            or b"/Type" in data_b
            or b"/Pages" in data_b
            or b"/Catalog" in data_b
            or (frag_b.predicted_label in ("PAGE_OBJECT", "PDF_OBJECT"))
        ) and not all(b == 0 for b in data_b)

        is_near_head = (frag_b.offset is None or frag_b.offset <= 1024 or features.is_physically_adjacent)

        if has_header_a and not has_header_b and has_body_b and is_near_head:
            features.is_header_to_body = True
            features.inferred_compatibility.append("header_to_document_body_transition")

        if not has_xref_a and has_xref_b and (features.is_physically_adjacent or features.is_forward_ordered or frag_a.offset is None):
            features.is_body_to_xref = True
            features.inferred_compatibility.append("body_to_xref_transition")

        if has_xref_a and has_trailer_b and (features.is_physically_adjacent or features.is_forward_ordered or frag_a.offset is None):
            features.is_xref_to_trailer = True
            features.inferred_compatibility.append("xref_to_trailer_transition")

        if has_trailer_a and has_eof_b and (features.is_physically_adjacent or features.is_forward_ordered or frag_a.offset is None):
            features.is_trailer_to_eof = True
            features.inferred_compatibility.append("trailer_to_eof_transition")

        # ---------------------------------------------------------
        # 6. Negative Signals / Hard Incompatibilities
        # ---------------------------------------------------------
        if has_header_a and has_header_b:
            features.is_contradictory_header_pair = True
            features.negative_signals.append("contradictory_double_header(both fragments contain %PDF)")

        if has_eof_a and not has_eof_b and not has_header_b:
            # EOF cannot precede non-EOF body elements in normal document flow
            features.is_contradictory_eof_pair = True
            features.negative_signals.append("contradictory_eof_precedence(fragment_a contains %%EOF termination)")

        # ---------------------------------------------------------
        # 7. Optional Advisory Phase 7 ML Predictions
        # ---------------------------------------------------------
        label_a = frag_a.predicted_label
        label_b = frag_b.predicted_label

        if label_a and label_b and not frag_a.label_abstained and not frag_b.label_abstained:
            features.ml_pair_label = f"{label_a}->{label_b}"
            conf = min(frag_a.label_confidence, frag_b.label_confidence)

            # Compatible structural sequences based on Phase 7 categories
            valid_transitions = {
                ("PDF_HEADER", "PAGE_OBJECT"): 0.85,
                ("PDF_HEADER", "PDF_OBJECT"): 0.80,
                ("PAGE_OBJECT", "TEXT_STREAM"): 0.90,
                ("PAGE_OBJECT", "FONT_OBJECT"): 0.80,
                ("PAGE_OBJECT", "IMAGE_STREAM"): 0.80,
                ("PAGE_OBJECT", "PAGE_OBJECT"): 0.75,
                ("TEXT_STREAM", "PAGE_OBJECT"): 0.75,
                ("TEXT_STREAM", "FONT_OBJECT"): 0.70,
                ("TEXT_STREAM", "XREF"): 0.80,
                ("PDF_OBJECT", "XREF"): 0.80,
                ("XREF", "TRAILER"): 0.95,
                ("TRAILER", "TRAILER"): 0.60,
            }

            base_compat = valid_transitions.get((label_a, label_b), 0.30)
            features.ml_advisory_compatibility = round(base_compat * conf, 3)
            features.inferred_compatibility.append(
                f"ml_advisory_transition({features.ml_pair_label}, score={features.ml_advisory_compatibility})"
            )

        return features
