"""Pairwise relationship evaluation and defensibility analysis.

Evaluates deterministic relationship scorer against ground-truth document fragments
on held-out documents (grouped by document ID to prevent split leakage).
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from trace.datasets.generators import SyntheticDocumentGenerator
from trace.ml.relationships.features import FragmentInput, PairwiseFeatureExtractor
from trace.ml.relationships.scorer import CandidateRelationship, ForensicRelationshipScorer

logger = logging.getLogger(__name__)


@dataclass
class PairwiseEvaluationReport:
    """Empirical evaluation report for pairwise relationship prediction."""
    model_name: str
    total_pairs_evaluated: int
    positive_ground_truth_count: int
    negative_ground_truth_count: int
    predicted_link_count: int
    true_positives: int
    false_positives: int
    false_negatives: int
    true_negatives: int
    precision: float
    recall: float
    f1_score: float
    false_link_rate: float
    precision_at_k: Dict[str, float] = field(default_factory=dict)
    details: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def generate_pairwise_benchmark_corpus(
    doc_count: int = 6,
    seed: int = 100,
    block_size: int = 256,
) -> Dict[str, List[FragmentInput]]:
    """Generate independent documents carved into fragments with exact offsets."""
    generator = SyntheticDocumentGenerator()
    doc_sizes = ["SMALL", "MEDIUM", "LARGE"]
    corpus: Dict[str, List[FragmentInput]] = {}

    for i in range(doc_count):
        active_seed = seed + i * 29
        doc_size = doc_sizes[i % len(doc_sizes)]
        pages = 2 if doc_size == "SMALL" else (4 if doc_size == "MEDIUM" else 8)
        pdf_bytes = generator.generate(page_count=pages, seed=active_seed, doc_size=doc_size)
        doc_id = f"doc_{doc_size}_{active_seed}"

        fragments: List[FragmentInput] = []
        for offset in range(0, len(pdf_bytes), block_size):
            chunk = pdf_bytes[offset : offset + block_size]
            fid = f"{doc_id}_blk_{offset // block_size:04d}"
            # Add advisory predicted label from header/stream tokens
            pred_label = "UNKNOWN"
            if chunk.startswith(b"%PDF"):
                pred_label = "PDF_HEADER"
            elif b"xref" in chunk:
                pred_label = "XREF"
            elif b"trailer" in chunk:
                pred_label = "TRAILER"
            elif b"stream" in chunk:
                pred_label = "TEXT_STREAM"
            elif b"/Type /Page" in chunk:
                pred_label = "PAGE_OBJECT"

            fragments.append(FragmentInput(
                fragment_id=fid,
                data=chunk,
                length=len(chunk),
                offset=offset,
                source_id=doc_id,
                predicted_label=pred_label,
                label_confidence=0.85,
            ))

        corpus[doc_id] = fragments

    return corpus


def evaluate_relationship_scorer(
    held_out_docs: Dict[str, List[FragmentInput]],
    scorer: Optional[ForensicRelationshipScorer] = None,
    min_affinity_threshold: float = 0.50,
    top_k_values: Sequence[int] = (1, 3, 5),
) -> PairwiseEvaluationReport:
    """Evaluate pairwise affinity scorer on held-out documents.

    Ground Truth Definition:
    - Directed pair (frag_i, frag_{i+1}) from the same document is POSITIVE (true adjacent transition).
    - Any pair where frag_j != frag_{i+1} is NEGATIVE.
    - Pairs between different documents are strictly NEGATIVE.
    """
    sc = scorer or ForensicRelationshipScorer()

    total_pairs = 0
    positive_gt = 0
    negative_gt = 0

    tp = 0
    fp = 0
    fn = 0
    tn = 0

    k_hits = {k: 0 for k in top_k_values}
    k_totals = {k: 0 for k in top_k_values}

    # Evaluate within and across held-out documents
    doc_ids = sorted(list(held_out_docs.keys()))

    for d_idx, doc_id in enumerate(doc_ids):
        frags = held_out_docs[doc_id]
        n_frags = len(frags)
        if n_frags < 2:
            continue

        # Score all internal pairs
        all_candidates = sc.score_all_pairs(frags, min_threshold=0.0)
        candidates_by_source: Dict[str, List[CandidateRelationship]] = {}
        for c in all_candidates:
            candidates_by_source.setdefault(c.from_fragment_id, []).append(c)

        for i in range(n_frags):
            frag_a = frags[i]
            expected_next_id = frags[i + 1].fragment_id if i + 1 < n_frags else None

            # Check top-k ranking for this source fragment
            ordered_cands = candidates_by_source.get(frag_a.fragment_id, [])
            for k in top_k_values:
                top_k_ids = [c.to_fragment_id for c in ordered_cands[:k]]
                if expected_next_id is not None:
                    k_totals[k] += 1
                    if expected_next_id in top_k_ids:
                        k_hits[k] += 1

            for j in range(n_frags):
                if i == j:
                    continue
                total_pairs += 1
                frag_b = frags[j]
                is_true_next = (j == i + 1)

                cand = sc.score_pair(frag_a, frag_b)
                pred_link = cand.affinity_score >= min_affinity_threshold

                if is_true_next:
                    positive_gt += 1
                    if pred_link:
                        tp += 1
                    else:
                        fn += 1
                else:
                    negative_gt += 1
                    if pred_link:
                        fp += 1
                    else:
                        tn += 1

        # Also evaluate negative pairs across different documents
        if d_idx + 1 < len(doc_ids):
            other_doc_id = doc_ids[d_idx + 1]
            other_frags = held_out_docs[other_doc_id]
            # Sample cross-document pairs (strictly negative)
            for fa in frags[:3]:
                for fb in other_frags[:3]:
                    total_pairs += 1
                    negative_gt += 1
                    cand = sc.score_pair(fa, fb)
                    if cand.affinity_score >= min_affinity_threshold:
                        fp += 1
                    else:
                        tn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    false_link_rate = fp / negative_gt if negative_gt > 0 else 0.0

    p_at_k: Dict[str, float] = {}
    for k in top_k_values:
        p_at_k[f"recall@{k}"] = round(k_hits[k] / k_totals[k], 4) if k_totals[k] > 0 else 0.0

    return PairwiseEvaluationReport(
        model_name="DeterministicRelationshipScorer",
        total_pairs_evaluated=total_pairs,
        positive_ground_truth_count=positive_gt,
        negative_ground_truth_count=negative_gt,
        predicted_link_count=tp + fp,
        true_positives=tp,
        false_positives=fp,
        false_negatives=fn,
        true_negatives=tn,
        precision=round(precision, 4),
        recall=round(recall, 4),
        f1_score=round(f1, 4),
        false_link_rate=round(false_link_rate, 4),
        precision_at_k=p_at_k,
        details={
            "min_affinity_threshold": min_affinity_threshold,
            "held_out_documents_count": len(doc_ids),
        },
    )
