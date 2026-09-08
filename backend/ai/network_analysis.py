"""
Network Analysis - who holds the network together.

The correlation graph was being drawn and never analysed. Nodes and edges were
written to the database and rendered in the interface, and nothing ever asked
the question the graph exists to answer: if we can act against one person,
which one costs the network the most?

That question has a precise answer in graph terms. A courier who is the only
route between a supply cluster and a distribution cluster sits on every path
between them; removing him splits the network in two. Volume does not identify
that person - the busiest handle is usually a retail seller, easily replaced.
Position does.

Three measures are computed:

  degree        how many others this actor is directly connected to
  betweenness   how often this actor lies on the shortest path between two
                others - the broker measure
  articulation  whether removing this actor disconnects the network outright

A caution that governs the whole module. Centrality describes the graph, and
the graph describes what has been *collected*, not what exists. An actor can
look central because he is genuinely a broker, or because he is the only part
of the network the crawler has seen. Findings therefore carry the size of the
graph they were computed on, and small graphs are refused rather than ranked.
"""

from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict
from datetime import datetime
import logging

logger = logging.getLogger("network_analysis")

# Below this, centrality is arithmetic on noise. In a graph of four nodes
# everyone is central, and a ranking would imply a precision that is not there.
MIN_NODES_FOR_CENTRALITY = 5
# Edges built from circumstantial leads are kept separate from those built on
# shared identifiers, so a ranking can be recomputed on hard evidence alone.
EDGE_KINDS = ("MESSAGED", "CORRELATION_LINK")


class NetworkAnalyzer:
    """Graph-theoretic targeting over the actor network."""

    async def _actor_graph(self, days: Optional[int], limit: int,
                           hard_evidence_only: bool):
        """
        Build an actor-to-actor graph.

        Actors, not records, are the nodes: a graph whose nodes are pages and
        substances puts "Heroin" at the centre of everything, which is true
        and useless.
        """
        import networkx as nx
        from ai.actor_dossier import dossier_builder
        from ai.semantic_correlation import semantic_correlator

        dossiers = await dossier_builder.build(days=days, limit=limit)
        actors = dossiers.get("actors", [])

        graph = nx.Graph()
        for actor in actors:
            graph.add_node(
                actor["actor_id"],
                role=actor["role"]["role"],
                threat=actor["highest_threat"],
                records=actor["record_count"],
                platforms=list(actor["platforms"]),
            )

        # Which actors appear in which records.
        actors_by_record: Dict[int, List[str]] = defaultdict(list)
        for actor in actors:
            for record_id in actor["record_ids"]:
                actors_by_record[record_id].append(actor["actor_id"])

        def connect(a: str, b: str, kind: str, evidence: Any) -> None:
            if a == b or not graph.has_node(a) or not graph.has_node(b):
                return
            if graph.has_edge(a, b):
                graph[a][b]["kinds"].add(kind)
                graph[a][b]["evidence"].append(evidence)
            else:
                graph.add_edge(a, b, kinds={kind}, evidence=[evidence])

        # Communication edges: who addressed whom. These come from the dossier
        # layer, which separates "this handle was mentioned by that author"
        # from "these identifiers are the same person" - the distinction the
        # graph depends on, since merging the two collapses a network into a
        # single node.
        for left, right, record_id in dossiers.get("interactions", []):
            connect(left, right, "MESSAGED", record_id)

        # Records the semantic layer tied together carry their actors with them.
        picture = await semantic_correlator.build(days=days, limit=limit)
        for link in picture.get("links", []):
            if hard_evidence_only and link["verdict"] != "LINK":
                continue
            left, right = link["record_ids"]
            for a in actors_by_record.get(left, []):
                for b in actors_by_record.get(right, []):
                    connect(a, b, "CORRELATION_LINK",
                            {"records": [left, right], "verdict": link["verdict"]})

        return graph, actors

    async def analyse(self, days: Optional[int] = None, limit: int = 1000,
                      hard_evidence_only: bool = False) -> Dict[str, Any]:
        try:
            import networkx as nx
        except ImportError:                                   # pragma: no cover
            return {"status": "UNAVAILABLE",
                    "message": "networkx is not installed."}

        graph, actors = await self._actor_graph(days, limit, hard_evidence_only)
        base = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "status": "SUCCESS",
            "nodes": graph.number_of_nodes(),
            "edges": graph.number_of_edges(),
            "hard_evidence_only": hard_evidence_only,
        }

        if graph.number_of_nodes() < MIN_NODES_FOR_CENTRALITY:
            return {
                **base,
                "status": "INSUFFICIENT_DATA",
                "message": (f"{graph.number_of_nodes()} actors in the network; "
                            f"centrality needs at least {MIN_NODES_FOR_CENTRALITY} "
                            f"before a ranking means anything. Every actor in a "
                            f"graph this small looks central."),
                "brokers": [], "articulation_points": [], "components": [],
            }

        betweenness = nx.betweenness_centrality(graph)
        degree = dict(graph.degree())
        cut_vertices = set(nx.articulation_points(graph))
        components = [sorted(c) for c in nx.connected_components(graph)]

        ranked = []
        for node in graph.nodes:
            attrs = graph.nodes[node]
            ranked.append({
                "actor_id": node,
                "role": attrs.get("role"),
                "threat": attrs.get("threat"),
                "records": attrs.get("records"),
                "platforms": attrs.get("platforms"),
                "degree": degree.get(node, 0),
                "betweenness": round(betweenness.get(node, 0.0), 4),
                "is_articulation_point": node in cut_vertices,
                # Stated in words because the number alone does not tell an
                # officer what it implies for an operation.
                "interpretation": self._interpret(
                    betweenness.get(node, 0.0), degree.get(node, 0),
                    node in cut_vertices),
            })

        ranked.sort(key=lambda r: (r["is_articulation_point"],
                                   r["betweenness"], r["degree"]), reverse=True)

        return {
            **base,
            "components": [{"size": len(c), "actors": c} for c in components],
            "component_count": len(components),
            "brokers": ranked[:20],
            "articulation_points": [r for r in ranked if r["is_articulation_point"]],
            "caveat": ("Centrality describes the collected graph, not the real "
                       "network. An actor can rank highly because he is a broker, "
                       "or because he is the only part of the network that has "
                       "been observed."),
        }

    @staticmethod
    def _interpret(betweenness: float, degree: int, is_cut: bool) -> str:
        if is_cut:
            return ("removing this actor splits the observed network into "
                    "separate pieces - the strongest disruption target present")
        if betweenness >= 0.2:
            return ("sits on many of the shortest paths between other actors; "
                    "consistent with a broker or courier role")
        if degree >= 5 and betweenness < 0.05:
            return ("well connected but not a bridge - contacts are already "
                    "connected to each other, which fits a retail seller inside "
                    "one cluster rather than a link between clusters")
        if degree <= 1:
            return "peripheral in what has been collected so far"
        return "ordinary position in the network"


network_analyzer = NetworkAnalyzer()
