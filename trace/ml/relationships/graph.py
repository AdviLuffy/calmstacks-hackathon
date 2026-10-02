"""Forensic Reconstruction Graph for candidate fragment assembly.

Models fragments as nodes and candidate relationships as weighted, typed directed edges.
Supports disconnected components, competing/ambiguous joins, and explicit provenance tracking.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

from trace.ml.relationships.features import FragmentInput
from trace.ml.relationships.scorer import CandidateRelationship, ForensicRelationshipScorer


@dataclass
class GraphNode:
    """A node representing a carved evidence fragment."""
    fragment_id: str
    length: int
    offset: Optional[int] = None
    source_id: Optional[str] = None
    predicted_label: Optional[str] = None
    label_confidence: float = 0.0
    provenance: str = "CARVED_FRAGMENT"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GraphEdge:
    """A directed candidate link between two fragment nodes."""
    source_id: str
    target_id: str
    weight: float
    relationship_type: str
    confidence_tier: str
    evidence: List[str] = field(default_factory=list)
    inferred_reasons: List[str] = field(default_factory=list)
    uncertainties: List[str] = field(default_factory=list)
    provenance: str = "HEURISTIC_AFFINITY"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ReconstructionGraph:
    """Graph structure managing candidate relationships and ambiguities between fragments."""

    def __init__(self, name: str = "reconstruction_graph_v1") -> None:
        self.name = name
        self.nodes: Dict[str, GraphNode] = {}
        self.edges: List[GraphEdge] = []
        self._adj_out: Dict[str, List[GraphEdge]] = defaultdict(list)
        self._adj_in: Dict[str, List[GraphEdge]] = defaultdict(list)

    def add_node(self, node: GraphNode) -> None:
        self.nodes[node.fragment_id] = node

    def add_edge(self, edge: GraphEdge) -> None:
        if edge.source_id not in self.nodes or edge.target_id not in self.nodes:
            raise KeyError(
                f"Both source '{edge.source_id}' and target '{edge.target_id}' must exist in graph nodes."
            )
        self.edges.append(edge)
        self._adj_out[edge.source_id].append(edge)
        self._adj_in[edge.target_id].append(edge)

    def get_outgoing_edges(self, node_id: str) -> List[GraphEdge]:
        return list(self._adj_out.get(node_id, []))

    def get_incoming_edges(self, node_id: str) -> List[GraphEdge]:
        return list(self._adj_in.get(node_id, []))

    def get_connected_components(self) -> List[List[str]]:
        """Return weakly connected components. Disconnected fragments form singletons."""
        visited: Set[str] = set()
        components: List[List[str]] = []

        undirected: Dict[str, Set[str]] = defaultdict(set)
        for n in self.nodes:
            undirected[n] = set()
        for e in self.edges:
            undirected[e.source_id].add(e.target_id)
            undirected[e.target_id].add(e.source_id)

        for node_id in sorted(self.nodes.keys()):
            if node_id not in visited:
                comp: List[str] = []
                queue = deque([node_id])
                visited.add(node_id)
                while queue:
                    curr = queue.popleft()
                    comp.append(curr)
                    for neighbor in sorted(undirected[curr]):
                        if neighbor not in visited:
                            visited.add(neighbor)
                            queue.append(neighbor)
                components.append(sorted(comp))

        return components

    def get_competing_edges(self, node_id: str) -> Dict[str, Any]:
        """Detect ambiguous competing predecessor or successor joins for a node."""
        out_edges = self._adj_out.get(node_id, [])
        in_edges = self._adj_in.get(node_id, [])

        competing_successors = [e for e in out_edges if e.weight >= 0.50]
        competing_predecessors = [e for e in in_edges if e.weight >= 0.50]

        is_ambiguous_out = len(competing_successors) > 1
        is_ambiguous_in = len(competing_predecessors) > 1

        return {
            "node_id": node_id,
            "has_ambiguity": is_ambiguous_out or is_ambiguous_in,
            "ambiguous_successors": is_ambiguous_out,
            "competing_successor_count": len(competing_successors),
            "successor_candidates": [e.to_dict() for e in competing_successors],
            "ambiguous_predecessors": is_ambiguous_in,
            "competing_predecessor_count": len(competing_predecessors),
            "predecessor_candidates": [e.to_dict() for e in competing_predecessors],
        }

    def find_candidate_chains(
        self,
        min_edge_weight: float = 0.50,
        max_chain_length: int = 100,
    ) -> List[List[str]]:
        """Find greedy candidate linear paths starting from nodes with in-degree 0."""
        # Find start nodes: nodes with no incoming edges >= min_edge_weight
        # or nodes predicted as PDF_HEADER
        start_nodes: List[str] = []
        for n_id, node in self.nodes.items():
            valid_ins = [e for e in self._adj_in.get(n_id, []) if e.weight >= min_edge_weight]
            if not valid_ins or node.predicted_label == "PDF_HEADER":
                start_nodes.append(n_id)

        if not start_nodes and self.nodes:
            start_nodes = sorted(list(self.nodes.keys()))

        chains: List[List[str]] = []
        for start in start_nodes:
            chain = [start]
            visited = {start}
            curr = start

            while len(chain) < max_chain_length:
                outs = [
                    e for e in self._adj_out.get(curr, [])
                    if e.weight >= min_edge_weight and e.target_id not in visited
                ]
                if not outs:
                    break
                # Select best candidate
                best_edge = max(outs, key=lambda e: e.weight)
                curr = best_edge.target_id
                chain.append(curr)
                visited.add(curr)

            if len(chain) > 1:
                chains.append(chain)

        return chains

    def to_dict(self) -> Dict[str, Any]:
        """Serialize graph to forensic inspection dictionary."""
        components = self.get_connected_components()
        ambiguities = [
            self.get_competing_edges(n_id)
            for n_id in self.nodes
            if self.get_competing_edges(n_id)["has_ambiguity"]
        ]

        return {
            "name": self.name,
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "connected_component_count": len(components),
            "components": components,
            "ambiguous_nodes_count": len(ambiguities),
            "ambiguities": ambiguities,
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "edges": [e.to_dict() for e in self.edges],
        }

    def to_cytoscape(self) -> List[Dict[str, Any]]:
        """Export Cytoscape.js format for interactive forensic UI rendering."""
        elements: List[Dict[str, Any]] = []
        for node in self.nodes.values():
            elements.append({
                "data": {
                    "id": node.fragment_id,
                    "label": f"{node.fragment_id}\n({node.predicted_label or 'UNKNOWN'})",
                    "length": node.length,
                    "predicted_label": node.predicted_label or "UNKNOWN",
                    "provenance": node.provenance,
                }
            })
        for idx, edge in enumerate(self.edges):
            elements.append({
                "data": {
                    "id": f"edge_{idx}_{edge.source_id}_{edge.target_id}",
                    "source": edge.source_id,
                    "target": edge.target_id,
                    "weight": edge.weight,
                    "type": edge.relationship_type,
                    "confidence": edge.confidence_tier,
                    "provenance": edge.provenance,
                }
            })
        return elements


def build_reconstruction_graph(
    fragments: Sequence[FragmentInput],
    scorer: Optional[ForensicRelationshipScorer] = None,
    min_affinity_threshold: float = 0.40,
    max_edges_per_node: int = 3,
) -> ReconstructionGraph:
    """Construct a ReconstructionGraph from raw fragment inputs using relationship scoring."""
    graph = ReconstructionGraph()
    sc = scorer or ForensicRelationshipScorer()

    # 1. Add all fragments as nodes
    for frag in fragments:
        node = GraphNode(
            fragment_id=frag.fragment_id,
            length=frag.length,
            offset=frag.offset,
            source_id=frag.source_id,
            predicted_label=frag.predicted_label,
            label_confidence=frag.label_confidence,
            provenance="CARVED_FRAGMENT",
            metadata=frag.metadata,
        )
        graph.add_node(node)

    # 2. Score candidate relationships
    candidates = sc.score_all_pairs(fragments, min_threshold=min_affinity_threshold)

    # 3. Add top edges per source node to avoid noisy complete graphs
    edges_by_source: Dict[str, int] = defaultdict(int)
    for cand in candidates:
        if edges_by_source[cand.from_fragment_id] < max_edges_per_node:
            edge = GraphEdge(
                source_id=cand.from_fragment_id,
                target_id=cand.to_fragment_id,
                weight=cand.affinity_score,
                relationship_type=cand.relationship_type.value,
                confidence_tier=cand.confidence_tier.value,
                evidence=cand.evidence_observed,
                inferred_reasons=cand.inferred_compatibility,
                uncertainties=cand.uncertainty_limitations,
                provenance=cand.provenance,
            )
            graph.add_edge(edge)
            edges_by_source[cand.from_fragment_id] += 1

    return graph
