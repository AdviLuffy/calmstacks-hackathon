"""Fragment relationship graph and deterministic traversal engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from trace.recovery.models import FragmentCandidate


@dataclass(frozen=True)
class GraphEdge:
    """Directed transition from source fragment to target fragment."""

    source_id: str
    target_id: str
    weight: float  # Higher weight = stronger structural affinity
    rule: str
    is_hard_constraint: bool = False


class FragmentGraph:
    """Directed graph representing candidate fragment sequences."""

    def __init__(self, fragments: Sequence[FragmentCandidate]) -> None:
        self.fragments: dict[str, FragmentCandidate] = {f.fragment_id: f for f in fragments}
        self.adj: dict[str, list[GraphEdge]] = {f.fragment_id: [] for f in fragments}
        self.in_edges: dict[str, list[GraphEdge]] = {f.fragment_id: [] for f in fragments}

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        weight: float,
        rule: str,
        is_hard_constraint: bool = False,
    ) -> None:
        """Add directed relationship between two fragments."""
        if source_id == target_id:
            return  # No self-loops
        if source_id not in self.fragments or target_id not in self.fragments:
            return

        edge = GraphEdge(source_id, target_id, weight, rule, is_hard_constraint)
        self.adj[source_id].append(edge)
        self.in_edges[target_id].append(edge)

    def find_best_chain(
        self, start_id: str | None = None, max_depth: int = 100
    ) -> tuple[list[str], float]:
        """Greedy walk on maximum weight edges with cycle avoidance."""
        if not self.fragments:
            return [], 0.0

        # Choose start node: explicitly specified or node with role="header" or min in-degree
        if not start_id or start_id not in self.fragments:
            header_nodes = [
                fid for fid, f in self.fragments.items() if f.is_header or f.structural_role == "header"
            ]
            if header_nodes:
                start_id = header_nodes[0]
            else:
                # Node with lowest in-degree
                start_id = min(self.in_edges.keys(), key=lambda k: len(self.in_edges[k]))

        chain: list[str] = [start_id]
        visited: set[str] = {start_id}
        total_weight = 0.0

        current = start_id
        while len(chain) < min(max_depth, len(self.fragments)):
            outgoing = [e for e in self.adj[current] if e.target_id not in visited]
            if not outgoing:
                break

            # Sort by weight descending
            best_edge = max(outgoing, key=lambda e: e.weight)
            chain.append(best_edge.target_id)
            visited.add(best_edge.target_id)
            total_weight += best_edge.weight
            current = best_edge.target_id

            # Stop if footer reached
            if self.fragments[current].is_footer or self.fragments[current].structural_role == "footer":
                break

        return chain, total_weight
