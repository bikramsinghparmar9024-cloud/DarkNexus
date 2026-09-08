"""
Correlation Graph Storage.

Connects suspects, channels, onion services, substances and wallets so an
investigator can see a network rather than a list of records.

Two backends, one interface:

  * Neo4j, when NEO4J_ENABLED is set and a server is reachable
  * SQLite/PostgreSQL tables otherwise - the default

The fallback used to be two Python lists seeded with invented suspects. Real
correlations vanished on restart while the fictional ones returned, which is
worse than having no graph: it presented fabricated links as findings. The
tables below persist what was actually observed and nothing else.

Repeated observations increment a counter rather than duplicating an edge, so
an established connection is distinguishable from a single passing mention.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime

from core.identity import slugify_entity_key, canonical_drug_name

# Cap on evidence ids retained per edge. A heavily reobserved link does
# not need ten thousand ids to be traceable; the most recent are kept.
MAX_EVIDENCE_IDS = 50
import logging

from config import settings

logger = logging.getLogger("graph_db")

try:
    from neo4j import AsyncGraphDatabase
except ImportError:
    AsyncGraphDatabase = None


class GraphManager:
    """Persistent correlation graph with an optional Neo4j backend."""

    def __init__(self):
        self.driver: Optional[Any] = None
        self.enabled = settings.NEO4J_ENABLED

    # ── Lifecycle ────────────────────────────────────────────────────

    async def connect(self):
        """Attach to Neo4j when configured; otherwise use the database tables."""
        if not self.enabled:
            logger.info("Neo4j disabled; correlation graph persists to the "
                        "relational database.")
            return

        if AsyncGraphDatabase is None:
            logger.warning("neo4j package not installed; using database tables.")
            return

        try:
            self.driver = AsyncGraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
            )
            await self.driver.verify_connectivity()
            logger.info("Connected to Neo4j at %s.", settings.NEO4J_URI)
        except Exception as e:
            logger.warning("Neo4j unreachable at %s (%s); using database tables.",
                           settings.NEO4J_URI, e)
            self.driver = None

    async def close(self):
        if self.driver:
            await self.driver.close()
            self.driver = None

    # ── Writing ──────────────────────────────────────────────────────

    async def add_entity_link(self, source_id: str, source_label: str, source_type: str,
                              target_id: str, target_label: str, target_type: str,
                              relation: str, threat_level: str = "UNREVIEWED",
                              evidence_record_id: Optional[int] = None,
                              session=None) -> bool:
        """
        Record that two entities are connected.

        Idempotent: seeing the same relationship again bumps its observation
        count and last_seen rather than creating a duplicate edge.

        `evidence_record_id` records which collected record produced the link,
        so an investigator can be shown the actual message or listing behind
        any edge. An edge that cannot name its source is not evidence.
        """
        if self.driver:
            return await self._add_link_neo4j(
                source_id, source_label, source_type,
                target_id, target_label, target_type, relation)

        from sqlalchemy import select
        from database.postgres import AsyncSessionLocal, GraphNode, GraphEdge

        async def _write(db) -> bool:
            now = datetime.utcnow()

            for key, label, node_type in (
                (source_id, source_label, source_type),
                (target_id, target_label, target_type),
            ):
                node = (await db.execute(
                    select(GraphNode).where(GraphNode.node_key == key)
                )).scalars().first()
                if node:
                    node.last_seen = now
                    node.mention_count = (node.mention_count or 0) + 1
                    # Label precedence: an analyst-confirmed label is never
                    # overwritten; otherwise the most recent observation wins.
                    #
                    # This used to keep whichever label was LONGEST, which has
                    # no relationship to being correct - a verbose scraped
                    # title would permanently displace an analyst's own
                    # shorter, accurate one.
                    if label and not getattr(node, "label_verified", False):
                        node.label = label
                else:
                    db.add(GraphNode(
                        node_key=key, label=label or key, node_type=node_type,
                        threat_level=threat_level, first_seen=now, last_seen=now,
                        mention_count=1,
                    ))

            edge_key = f"{source_id}|{relation}|{target_id}"
            edge = (await db.execute(
                select(GraphEdge).where(GraphEdge.edge_key == edge_key)
            )).scalars().first()
            if edge:
                edge.observation_count = (edge.observation_count or 0) + 1
                edge.last_seen = now
                if evidence_record_id is not None:
                    # Reassigned rather than appended in place: SQLAlchemy does
                    # not notice mutation of a JSON list.
                    existing = list(edge.evidence_record_ids or [])
                    if evidence_record_id not in existing:
                        edge.evidence_record_ids = (
                            existing + [evidence_record_id])[-MAX_EVIDENCE_IDS:]
            else:
                db.add(GraphEdge(
                    edge_key=edge_key, source_key=source_id, target_key=target_id,
                    relation=relation, observation_count=1,
                    first_seen=now, last_seen=now,
                    evidence_record_ids=([evidence_record_id]
                                         if evidence_record_id is not None else []),
                ))

            await db.flush()
            return True

        try:
            if session is not None:
                return await _write(session)
            async with AsyncSessionLocal() as db:
                result = await _write(db)
                await db.commit()
                return result
        except Exception as e:
            logger.warning("Graph write failed (%s -> %s): %s", source_id, target_id, e)
            return False

    async def _add_link_neo4j(self, source_id, source_label, source_type,
                              target_id, target_label, target_type, relation) -> bool:
        cypher = """
        MERGE (s:Entity {key: $source_id})
          ON CREATE SET s.label = $source_label, s.type = $source_type
        MERGE (t:Entity {key: $target_id})
          ON CREATE SET t.label = $target_label, t.type = $target_type
        MERGE (s)-[r:RELATED {relation: $relation}]->(t)
          ON CREATE SET r.observation_count = 1
          ON MATCH SET r.observation_count = r.observation_count + 1
        """
        try:
            async with self.driver.session() as session:
                await session.run(
                    cypher, source_id=source_id, source_label=source_label,
                    source_type=source_type, target_id=target_id,
                    target_label=target_label, target_type=target_type,
                    relation=relation)
            return True
        except Exception as e:
            logger.warning("Neo4j write failed: %s", e)
            return False

    async def create_drug_listing_node(self, listing_id: str, title: str, drug_name: str,
                                       price: Optional[str] = None,
                                       source_type: str = "DARK_WEB",
                                       seller_handle: Optional[str] = None,
                                       crypto_address: Optional[str] = None):
        """Link a listing to its seller, its substance, and its payment address."""
        listing_label = (title or listing_id)[:60]
        node_type = "channel" if source_type == "TELEGRAM" else "onion"

        if seller_handle:
            await self.add_entity_link(
                slugify_entity_key(seller_handle, "suspect"),
                f"Seller: {seller_handle}",
                "suspect", listing_id, listing_label, node_type, "POSTED_LISTING")
        if drug_name:
            await self.add_entity_link(
                listing_id, listing_label, node_type,
                slugify_entity_key(drug_name, "drug"),
                canonical_drug_name(drug_name), "drug", "OFFERS_DRUG")
        if crypto_address:
            await self.add_entity_link(
                listing_id, listing_label, node_type,
                slugify_entity_key(crypto_address, "wallet"),
                f"Wallet: {crypto_address[:10]}...",
                "wallet", "ACCEPTS_CRYPTO")
        return {"status": "OK"}

    # ── Reading ──────────────────────────────────────────────────────

    async def get_network_graph(self, limit: int = 300,
                                min_observations: int = 1,
                                include_rejected: bool = False) -> Dict[str, Any]:
        """
        Return the graph in the shape Cytoscape.js expects.

        `min_observations` filters out one-off links, which is how an analyst
        separates an established connection from a single passing mention.

        Edges an investigator has rejected are hidden by default but remain in
        the database - `include_rejected` brings them back for audit. A view
        that quietly deletes what a reviewer disagreed with cannot be checked
        afterwards, which is the opposite of what a review is for.
        """
        if self.driver:
            return await self._read_neo4j(limit)

        from sqlalchemy import select, desc
        from database.postgres import AsyncSessionLocal, GraphNode, GraphEdge

        try:
            async with AsyncSessionLocal() as db:
                stmt = (select(GraphEdge)
                        .where(GraphEdge.observation_count >= min_observations))
                if not include_rejected:
                    stmt = stmt.where(GraphEdge.status != "REJECTED")
                edges = (await db.execute(
                    stmt.order_by(desc(GraphEdge.observation_count)).limit(limit)
                )).scalars().all()

                total_matching = len((await db.execute(
                    select(GraphEdge.id)
                    .where(GraphEdge.observation_count >= min_observations)
                )).scalars().all())

                referenced = {e.source_key for e in edges} | {e.target_key for e in edges}
                nodes = (await db.execute(
                    select(GraphNode).where(GraphNode.node_key.in_(referenced))
                )).scalars().all() if referenced else []

            return {
                "nodes": [
                    {"data": {
                        "id": n.node_key,
                        "label": n.label,
                        "type": n.node_type,
                        "threat": n.threat_level,
                        "mentions": n.mention_count,
                    }}
                    for n in nodes
                ],
                "edges": [
                    {"data": {
                        "id": f"e{e.id}",
                        "source": e.source_key,
                        "target": e.target_key,
                        "label": e.relation,
                        "observations": e.observation_count,
                        "status": e.status or "PENDING",
                        # Surfaced so the interface can de-emphasise a link
                        # last seen months ago rather than showing it as
                        # indistinguishable from one seen this week.
                        "first_observed": e.first_seen.isoformat() + "Z" if e.first_seen else None,
                        "last_observed": e.last_seen.isoformat() + "Z" if e.last_seen else None,
                        "evidence_record_ids": e.evidence_record_ids or [],
                    }}
                    for e in edges
                ],
                "backend": "database",
                "truncated": len(edges) >= limit,
                "shown_edge_count": len(edges),
                "total_edge_count": total_matching,
            }
        except Exception as e:
            logger.error("Graph read failed: %s", e)
            return {"nodes": [], "edges": [], "backend": "database", "error": str(e)}

    async def _read_neo4j(self, limit: int) -> Dict[str, Any]:
        cypher = "MATCH (n)-[r]->(m) RETURN n, r, m LIMIT $limit"
        nodes_map: Dict[str, Any] = {}
        edges: List[Dict[str, Any]] = []

        async with self.driver.session() as session:
            result = await session.run(cypher, limit=limit)
            async for record in result:
                for node in (record["n"], record["m"]):
                    key = node.get("key") or str(node.element_id)
                    nodes_map.setdefault(key, {"data": {
                        "id": key,
                        "label": node.get("label") or key,
                        "type": node.get("type") or "entity",
                    }})
                rel = record["r"]
                edges.append({"data": {
                    "id": str(rel.element_id),
                    "source": record["n"].get("key") or str(record["n"].element_id),
                    "target": record["m"].get("key") or str(record["m"].element_id),
                    "label": rel.get("relation") or rel.type,
                    "observations": rel.get("observation_count", 1),
                }})

        return {"nodes": list(nodes_map.values()), "edges": edges, "backend": "neo4j"}

    async def get_stats(self) -> Dict[str, Any]:
        """Summary counts for the dashboard."""
        from sqlalchemy import select, func
        from database.postgres import AsyncSessionLocal, GraphNode, GraphEdge

        if self.driver:
            return {"backend": "neo4j"}

        async with AsyncSessionLocal() as db:
            node_count = (await db.execute(select(func.count(GraphNode.id)))).scalar() or 0
            edge_count = (await db.execute(select(func.count(GraphEdge.id)))).scalar() or 0
            by_type = dict((await db.execute(
                select(GraphNode.node_type, func.count(GraphNode.id))
                .group_by(GraphNode.node_type)
            )).all())

        return {
            "backend": "database",
            "node_count": node_count,
            "edge_count": edge_count,
            "nodes_by_type": by_type,
        }

    async def describe_node(self, node_key: str, snippet_chars: int = 400
                            ) -> Dict[str, Any]:
        """
        What a node is, and the passages of collected text behind it.

        Clicking a node showed its label and type and nothing else, so an
        investigator could see that "heroin" was in the graph but not where
        the word had actually been found. This returns the records that
        produced every edge touching the node, with the surrounding text, so
        a claim on the graph can be read back to its source in one step.
        """
        from sqlalchemy import select, or_
        from database.postgres import (AsyncSessionLocal, GraphNode, GraphEdge,
                                       ScrapedData)

        async with AsyncSessionLocal() as db:
            node = (await db.execute(
                select(GraphNode).where(GraphNode.node_key == node_key)
            )).scalars().first()
            if not node:
                return {"status": "NOT_FOUND", "node_key": node_key,
                        "message": "No such node in the correlation graph."}

            edges = (await db.execute(
                select(GraphEdge).where(or_(
                    GraphEdge.source_key == node_key,
                    GraphEdge.target_key == node_key))
            )).scalars().all()

            record_ids = sorted({
                rid for e in edges for rid in (e.evidence_record_ids or [])})
            records = (await db.execute(
                select(ScrapedData).where(ScrapedData.id.in_(record_ids))
            )).scalars().all() if record_ids else []

            neighbour_keys = {
                (e.target_key if e.source_key == node_key else e.source_key)
                for e in edges}
            neighbours = {
                n.node_key: n for n in (await db.execute(
                    select(GraphNode).where(GraphNode.node_key.in_(neighbour_keys)))
                ).scalars().all()
            } if neighbour_keys else {}

        # Search terms used to locate the passage inside a record. For a
        # substance node the canonical name will not appear verbatim - the
        # page said "chitta", the node says "heroin" - so the aliases are
        # tried too, otherwise the snippet would silently fall back to the
        # opening of the document and look like an arbitrary excerpt.
        terms = [node.label.split(":", 1)[-1].strip(), node_key.split("_", 1)[-1]]
        if node.node_type == "drug":
            from core.identity import _load_drug_aliases
            canonical = node_key.split("_", 1)[-1].replace("_", " ")
            terms += [alias for alias, target in _load_drug_aliases().items()
                      if target.replace(" ", "_") == node_key.split("_", 1)[-1]
                      or target == canonical]

        def locate(text: str) -> Dict[str, Any]:
            """Return the passage around the first term that actually occurs."""
            lowered = (text or "").lower()
            for term in terms:
                term = (term or "").strip().lower().replace("_", " ")
                if len(term) < 3:
                    continue
                position = lowered.find(term)
                if position >= 0:
                    start = max(0, position - snippet_chars // 3)
                    return {
                        "snippet": text[start:start + snippet_chars],
                        "matched_term": term,
                        "found_at": position,
                        "is_excerpt_around_match": True,
                    }
            return {
                "snippet": (text or "")[:snippet_chars],
                "matched_term": None,
                "found_at": None,
                # Said plainly: this is the top of the document, not the place
                # the entity was seen.
                "is_excerpt_around_match": False,
            }

        return {
            "status": "FOUND",
            "node": {
                "key": node.node_key,
                "label": node.label,
                "type": node.node_type,
                "threat_level": node.threat_level,
                "mention_count": node.mention_count,
                "label_verified": bool(node.label_verified),
                "first_seen": node.first_seen.isoformat() + "Z" if node.first_seen else None,
                "last_seen": node.last_seen.isoformat() + "Z" if node.last_seen else None,
            },
            "connections": [{
                "other_key": (e.target_key if e.source_key == node_key else e.source_key),
                "other_label": (neighbours.get(
                    e.target_key if e.source_key == node_key else e.source_key).label
                    if neighbours.get(
                        e.target_key if e.source_key == node_key else e.source_key)
                    else None),
                "relation": e.relation,
                "direction": "outgoing" if e.source_key == node_key else "incoming",
                "observation_count": e.observation_count,
                "status": e.status or "PENDING",
            } for e in edges],
            "evidence": [{
                "record_id": r.id,
                "source_type": r.source_type,
                "source_url": r.source_url,
                "sha256": r.sha256_hash,
                "threat_level": r.threat_level,
                "collected_at": r.created_at.isoformat() + "Z" if r.created_at else None,
                **locate(r.cleaned_text or ""),
            } for r in records],
            "evidence_count": len(records),
        }

    async def set_edge_status(self, source_key: str, target_key: str,
                              status: str, reviewed_by: str,
                              note: Optional[str] = None) -> Dict[str, Any]:
        """
        Record an investigator's judgement on a link.

        Applies to every edge between the two nodes, in either direction, so
        a reviewer rejecting a connection does not leave its mirror standing.
        Nothing is deleted: a rejected edge stops being shown but stays
        queryable, because the observation genuinely happened and the review
        itself has to remain auditable.
        """
        from sqlalchemy import select, or_, and_
        from database.postgres import AsyncSessionLocal, GraphEdge

        status = (status or "").upper()
        if status not in ("PENDING", "VERIFIED", "REJECTED"):
            return {"status": "INVALID",
                    "message": "status must be PENDING, VERIFIED or REJECTED"}

        async with AsyncSessionLocal() as db:
            edges = (await db.execute(
                select(GraphEdge).where(or_(
                    and_(GraphEdge.source_key == source_key,
                         GraphEdge.target_key == target_key),
                    and_(GraphEdge.source_key == target_key,
                         GraphEdge.target_key == source_key),
                ))
            )).scalars().all()

            if not edges:
                return {"status": "NO_EDGE", "source_key": source_key,
                        "target_key": target_key,
                        "message": "No stored edge between these nodes to review."}

            now = datetime.utcnow()
            for edge in edges:
                edge.status = status
                edge.reviewed_by = reviewed_by
                edge.reviewed_at = now
                edge.review_note = note
            await db.commit()

            return {
                "status": "SUCCESS",
                "edge_status": status,
                "edges_updated": len(edges),
                "relations": [e.relation for e in edges],
                "reviewed_by": reviewed_by,
                "reviewed_at": now.isoformat() + "Z",
                "note": note,
                "hidden_from_default_view": status == "REJECTED",
            }

    async def describe_edge(self, source_key: str, target_key: str) -> Dict[str, Any]:
        """
        Everything real that is known about the link between two nodes.

        The "Why This Link?" panel answered 404 whenever the pair had no
        entity-resolution relationship - which is most edges, since drug and
        wallet co-occurrences are observations rather than identity claims.
        A judge clicking three edges and getting two dead ends has no reason
        to trust anything else on the screen.

        This returns the observation history instead: how often the link was
        seen, when it was first and last observed, and which collected records
        produced it. No confidence score is invented for a relationship type
        that has no signals to base one on.
        """
        from sqlalchemy import select, or_, and_
        from database.postgres import (AsyncSessionLocal, GraphNode, GraphEdge,
                                       ScrapedData)

        async with AsyncSessionLocal() as db:
            edges = (await db.execute(
                select(GraphEdge).where(or_(
                    and_(GraphEdge.source_key == source_key,
                         GraphEdge.target_key == target_key),
                    and_(GraphEdge.source_key == target_key,
                         GraphEdge.target_key == source_key),
                ))
            )).scalars().all()

            if not edges:
                return {"status": "NO_EDGE", "source_key": source_key,
                        "target_key": target_key,
                        "message": "No stored connection between these nodes."}

            nodes = {
                n.node_key: n for n in (await db.execute(
                    select(GraphNode).where(
                        GraphNode.node_key.in_([source_key, target_key]))
                )).scalars().all()
            }

            record_ids = sorted({
                rid for edge in edges for rid in (edge.evidence_record_ids or [])
            })
            records = (await db.execute(
                select(ScrapedData).where(ScrapedData.id.in_(record_ids))
            )).scalars().all() if record_ids else []

        def describe(key):
            node = nodes.get(key)
            return {"key": key,
                    "label": node.label if node else key,
                    "type": node.node_type if node else "unknown",
                    "threat_level": node.threat_level if node else None}

        return {
            "status": "OBSERVED",
            "source": describe(source_key),
            "target": describe(target_key),
            "relations": [{
                "relation": e.relation,
                "observation_count": e.observation_count,
                "first_observed": e.first_seen.isoformat() + "Z" if e.first_seen else None,
                "last_observed": e.last_seen.isoformat() + "Z" if e.last_seen else None,
                "evidence_record_ids": e.evidence_record_ids or [],
            } for e in edges],
            "evidence": [{
                "record_id": r.id,
                "source_type": r.source_type,
                "source_url": r.source_url,
                "sha256": r.sha256_hash,
                "threat_level": r.threat_level,
                "collected_at": r.created_at.isoformat() + "Z" if r.created_at else None,
                "snippet": (r.cleaned_text or "")[:240],
            } for r in records],
            "evidence_count": len(records),
            "basis": ("observed co-occurrence, not an identity claim - this "
                      "link records that the entities appeared together in the "
                      "collected records listed, and carries no confidence "
                      "score because a co-occurrence has no identity signals "
                      "to score"),
        }



graph_manager = GraphManager()



# The former name, kept so existing imports continue to resolve.
neo4j_manager = graph_manager
