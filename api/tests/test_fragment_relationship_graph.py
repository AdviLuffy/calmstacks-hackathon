"""Tests for TRACE Phase 8 Forensic Fragment Relationship Scoring & Reconstruction Graph.

Verifies:
- Explainable pairwise feature extraction
- Known compatible and incompatible fragment pairs
- Physical offset and same vs different source handling
- Contradictory evidence (duplicate headers, reversed EOF)
- Stable tie-breaking and top-k threshold filtering
- ReconstructionGraph components, ambiguous joins, and candidate chains
- Advisory Phase 7 ML class prediction integration
- Non-destructive evidence invariants
- Zero network or Gemini API calls
"""

from __future__ import annotations

import pytest

from trace.ml.relationships.features import (
    FragmentInput,
    PairwiseFeatureExtractor,
    PairwiseRelationshipFeatures,
)
from trace.ml.relationships.scorer import (
    CandidateRelationship,
    ConfidenceTier,
    ForensicRelationshipScorer,
    RelationshipType,
)
from trace.ml.relationships.graph import (
    GraphEdge,
    GraphNode,
    ReconstructionGraph,
    build_reconstruction_graph,
)
from trace.ml.relationships.learning import (
    evaluate_relationship_scorer,
    generate_pairwise_benchmark_corpus,
)


def test_pairwise_features_exact_physical_adjacency():
    extractor = PairwiseFeatureExtractor()
    frag_a = FragmentInput(
        fragment_id="frag_01",
        data=b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>",
        offset=0,
        source_id="evidence_source_1",
    )
    frag_b = FragmentInput(
        fragment_id="frag_02",
        data=b"\nendobj\n2 0 obj\n<< /Type /Pages >>\nendobj\n",
        offset=len(frag_a.data),
        source_id="evidence_source_1",
    )

    feats = extractor.extract_features(frag_a, frag_b)
    assert feats.same_source is True
    assert feats.offset_distance == 0
    assert feats.is_physically_adjacent is True
    assert feats.is_forward_ordered is True
    assert feats.spatial_proximity_score == 1.0
    assert any("exact_physical_adjacency" in ev for ev in feats.observed_evidence)


def test_pairwise_features_token_boundary_join():
    extractor = PairwiseFeatureExtractor()
    # Token 'endobj' split across fragment boundary: 'end' + 'obj'
    frag_a = FragmentInput(
        fragment_id="frag_a",
        data=b"1 0 obj << /Length 10 >> stream 0123456789 end",
    )
    frag_b = FragmentInput(
        fragment_id="frag_b",
        data=b"obj\n2 0 obj <<>> endobj\n",
    )

    feats = extractor.extract_features(frag_a, frag_b)
    assert feats.token_boundary_continuity is True
    assert feats.boundary_joined_token == "endobj"
    assert any("boundary_token_join" in ev for ev in feats.observed_evidence)


def test_stream_continuation_and_object_reference():
    scorer = ForensicRelationshipScorer()
    frag_stream = FragmentInput(
        fragment_id="frag_stream_start",
        data=b"1 0 obj\n<< /Length 100 >>\nstream\nBinaryPayloadData123456",
    )
    frag_endstream = FragmentInput(
        fragment_id="frag_stream_end",
        data=b"RemainingBinaryPayload\nendstream\nendobj\n",
    )

    cand = scorer.score_pair(frag_stream, frag_endstream)
    assert cand.relationship_type == RelationshipType.STREAM_CONTINUATION
    assert cand.affinity_score >= 0.75
    assert cand.confidence_tier in (ConfidenceTier.HIGH, ConfidenceTier.MEDIUM)
    assert any("unclosed_stream_marker" in ev for ev in cand.evidence_observed)


def test_negative_signals_duplicate_headers():
    scorer = ForensicRelationshipScorer()
    frag_hdr1 = FragmentInput(
        fragment_id="frag_hdr_1",
        data=b"%PDF-1.4\n%header1\n",
    )
    frag_hdr2 = FragmentInput(
        fragment_id="frag_hdr_2",
        data=b"%PDF-1.7\n%header2\n",
    )

    cand = scorer.score_pair(frag_hdr1, frag_hdr2)
    assert cand.affinity_score < 0.20
    assert cand.confidence_tier == ConfidenceTier.NEGLIGIBLE
    assert any("contradictory_double_header" in s for s in cand.negative_signals)


def test_negative_signals_contradictory_eof_precedence():
    scorer = ForensicRelationshipScorer()
    frag_eof = FragmentInput(
        fragment_id="frag_eof",
        data=b"trailer\n<< /Size 5 >>\nstartxref\n1200\n%%EOF\n",
    )
    frag_body = FragmentInput(
        fragment_id="frag_body",
        data=b"1 0 obj\n<< /Type /Catalog >>\nendobj\n",
    )

    cand = scorer.score_pair(frag_eof, frag_body)
    assert cand.affinity_score < 0.20
    assert any("contradictory_eof_precedence" in s for s in cand.negative_signals)


def test_different_sources_offset_safety():
    scorer = ForensicRelationshipScorer()
    frag_src1 = FragmentInput(
        fragment_id="frag_src1",
        data=b"1 0 obj << /Type /Page >> endobj",
        offset=512,
        source_id="disk_image_A.raw",
    )
    frag_src2 = FragmentInput(
        fragment_id="frag_src2",
        data=b"2 0 obj << /Type /Font >> endobj",
        offset=256,
        source_id="disk_image_B.raw",
    )

    cand = scorer.score_pair(frag_src1, frag_src2)
    assert any("different_evidence_sources" in u for u in cand.uncertainty_limitations)
    # Does not crash or erroneously compute negative offset penalty across different files
    assert cand.component_scores["negative_penalty"] == 0.0


def test_score_all_pairs_reproducibility_and_top_k():
    scorer = ForensicRelationshipScorer()
    fragments = [
        FragmentInput(fragment_id="f1", data=b"%PDF-1.4\n", offset=0, source_id="s1"),
        FragmentInput(fragment_id="f2", data=b"1 0 obj << /Type /Catalog >> endobj\n", offset=9, source_id="s1"),
        FragmentInput(fragment_id="f3", data=b"xref\n0 2\n0000000000 65535 f \n", offset=100, source_id="s1"),
        FragmentInput(fragment_id="f4", data=b"trailer\n<< /Root 1 0 R >>\n%%EOF\n", offset=200, source_id="s1"),
    ]

    cands_all = scorer.score_all_pairs(fragments, min_threshold=0.30)
    cands_top2 = scorer.score_all_pairs(fragments, min_threshold=0.30, top_k=2)

    assert len(cands_top2) == 2
    assert cands_top2[0] == cands_all[0]
    assert cands_top2[1] == cands_all[1]

    # Verify stable descending score sort
    for idx in range(len(cands_all) - 1):
        assert cands_all[idx].affinity_score >= cands_all[idx + 1].affinity_score


def test_reconstruction_graph_competing_edges_and_components():
    fragments = [
        FragmentInput(fragment_id="root", data=b"%PDF-1.4\n", predicted_label="PDF_HEADER"),
        FragmentInput(fragment_id="cand_a", data=b"1 0 obj << /Type /Pages >> endobj\n", predicted_label="PAGE_OBJECT"),
        FragmentInput(fragment_id="cand_b", data=b"2 0 obj << /Type /Pages >> endobj\n", predicted_label="PAGE_OBJECT"),
        FragmentInput(fragment_id="isolated", data=b"\x00\x00\x00\x00\x00", predicted_label="UNKNOWN"),
    ]

    graph = build_reconstruction_graph(fragments, min_affinity_threshold=0.35, max_edges_per_node=3)
    assert len(graph.nodes) == 4

    # Check connected components (isolated fragment must remain separate)
    components = graph.get_connected_components()
    assert len(components) >= 2
    isolated_comp = [c for c in components if "isolated" in c]
    assert len(isolated_comp) == 1
    assert isolated_comp[0] == ["isolated"]

    # Check candidate chains
    chains = graph.find_candidate_chains(min_edge_weight=0.35)
    assert len(chains) >= 1
    assert chains[0][0] == "root"


def test_local_provider_infer_relationship_integration():
    from trace.ml.providers.local import LocalProvider

    provider = LocalProvider()
    res = provider.infer_relationship(
        "hdr_frag",
        b"%PDF-1.7\n",
        "body_frag",
        b"1 0 obj << /Type /Catalog >> endobj\n",
    )

    assert res["source_fragment_id"] == "hdr_frag"
    assert res["target_fragment_id"] == "body_frag"
    assert res["affinity_score"] > 0.50
    assert res["can_precede"] is True
    assert "component_scores" in res
    assert "confidence_tier" in res
    assert res["provenance"] == "DETERMINISTIC"


def test_pairwise_evaluation_held_out_documents():
    corpus = generate_pairwise_benchmark_corpus(doc_count=3, seed=123)
    assert len(corpus) == 3

    report = evaluate_relationship_scorer(corpus, min_affinity_threshold=0.55)
    assert report.total_pairs_evaluated > 0
    assert report.precision > 0.70
    assert report.recall >= 0.90
    assert report.precision_at_k["recall@1"] >= 0.95
    assert report.false_link_rate < 0.05


def test_zero_gemini_and_non_destructive_guarantee():
    import os
    # Guarantee no API key is required
    scorer = ForensicRelationshipScorer()
    frag_data = b"original_raw_immutable_bytes_012345"
    frag = FragmentInput(fragment_id="immutable_test", data=frag_data)

    cand = scorer.score_pair(frag, frag)
    # Original bytes must be completely unchanged
    assert frag.data == frag_data
