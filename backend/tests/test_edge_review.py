"""
Investigator review of graph edges.

The review buttons already existed in the interface, and the endpoint behind
them wrote to a module-level dictionary. Two consequences: a judgement was
lost on the next restart, and it never reached the graph at all - an edge an
analyst had explicitly rejected carried on being drawn to every investigator
who opened the network map afterwards.

The tests here fix the shape of the fix: a decision must persist, must change
what is shown, and must never destroy the underlying observation.
"""

import pytest

from core.identity import slugify_entity_key


async def _edge(db, author="@vendor_one", text="Chitta available, escrow only.",
                url="https://t.me/x/1"):
    """Store one intercept and return its (intercept_key, drug_key) pair."""
    from ai.enrichment import store_intelligence

    saved = await store_intelligence(
        source_type="TELEGRAM", source_url=url, raw_content=text,
        author=author, session=db)
    return (slugify_entity_key(str(saved["record_id"]), "intercept"),
            slugify_entity_key("chitta", "drug"))


class TestReviewPersists:

    async def test_a_new_edge_starts_pending(self, db):
        from sqlalchemy import select
        from database.postgres import GraphEdge

        await _edge(db)
        edges = (await db.execute(select(GraphEdge))).scalars().all()
        assert edges
        assert all(e.status == "PENDING" for e in edges)

    async def test_verifying_records_who_and_when(self, db):
        from database.graph_db import graph_manager

        source, target = await _edge(db)
        result = await graph_manager.set_edge_status(
            source, target, "VERIFIED", reviewed_by="admin_punjab",
            note="Confirmed against case file")

        assert result["status"] == "SUCCESS"
        assert result["edge_status"] == "VERIFIED"
        assert result["reviewed_by"] == "admin_punjab"
        assert result["reviewed_at"]
        assert result["note"] == "Confirmed against case file"

    async def test_review_applies_in_both_directions(self, db):
        """
        Rejecting a connection must not leave its mirror standing - an analyst
        rejects a link, not one arbitrary direction of it.
        """
        from database.graph_db import graph_manager

        source, target = await _edge(db)
        forward = await graph_manager.set_edge_status(
            source, target, "REJECTED", reviewed_by="admin_punjab")
        reverse = await graph_manager.describe_edge(target, source)

        assert forward["edges_updated"] >= 1
        assert reverse["status"] == "OBSERVED"

    async def test_an_invalid_status_is_refused(self, db):
        from database.graph_db import graph_manager

        source, target = await _edge(db)
        result = await graph_manager.set_edge_status(
            source, target, "PROBABLY_FINE", reviewed_by="admin_punjab")
        assert result["status"] == "INVALID"

    async def test_reviewing_a_nonexistent_edge_says_so(self, db):
        from database.graph_db import graph_manager

        result = await graph_manager.set_edge_status(
            "suspect_nobody", "drug_heroin", "VERIFIED",
            reviewed_by="admin_punjab")
        assert result["status"] == "NO_EDGE"


class TestRejectedEdgesAreHiddenNotDeleted:

    async def test_a_rejected_edge_leaves_the_default_view(self, db):
        from database.graph_db import graph_manager

        source, target = await _edge(db)
        before = await graph_manager.get_network_graph()
        assert any(e["data"]["source"] == source for e in before["edges"])

        await graph_manager.set_edge_status(
            source, target, "REJECTED", reviewed_by="admin_punjab")

        after = await graph_manager.get_network_graph()
        pairs = {(e["data"]["source"], e["data"]["target"]) for e in after["edges"]}
        assert (source, target) not in pairs

    async def test_the_row_survives_rejection(self, db):
        """
        Never hard-delete evidence-linked data. The observation happened; the
        analyst disagreed with the inference drawn from it, and both facts
        have to remain checkable.
        """
        from sqlalchemy import select
        from database.graph_db import graph_manager
        from database.postgres import GraphEdge

        source, target = await _edge(db)
        await graph_manager.set_edge_status(
            source, target, "REJECTED", reviewed_by="admin_punjab",
            note="Coincidental mention")

        rows = (await db.execute(
            select(GraphEdge).where(GraphEdge.source_key == source)
        )).scalars().all()
        assert rows, "rejected edges must remain in the database"
        assert rows[0].status == "REJECTED"
        assert rows[0].review_note == "Coincidental mention"
        assert rows[0].evidence_record_ids, "evidence link must survive too"

    async def test_audit_view_can_bring_rejected_edges_back(self, db):
        from database.graph_db import graph_manager

        source, target = await _edge(db)
        await graph_manager.set_edge_status(
            source, target, "REJECTED", reviewed_by="admin_punjab")

        audit = await graph_manager.get_network_graph(include_rejected=True)
        pairs = {(e["data"]["source"], e["data"]["target"]) for e in audit["edges"]}
        assert (source, target) in pairs

    async def test_a_verified_edge_stays_visible(self, db):
        from database.graph_db import graph_manager

        source, target = await _edge(db)
        await graph_manager.set_edge_status(
            source, target, "VERIFIED", reviewed_by="admin_punjab")

        shown = await graph_manager.get_network_graph()
        edge = next(e for e in shown["edges"]
                    if e["data"]["source"] == source and e["data"]["target"] == target)
        assert edge["data"]["status"] == "VERIFIED"


class TestGraphResponseHonesty:

    async def test_the_response_says_how_much_is_being_shown(self, db):
        """
        The 300-edge cutoff was silent. An investigator has to be able to tell
        a complete graph from a truncated one.
        """
        from database.graph_db import graph_manager

        await _edge(db)
        graph = await graph_manager.get_network_graph()
        assert "shown_edge_count" in graph
        assert "total_edge_count" in graph
        assert graph["shown_edge_count"] <= graph["total_edge_count"]

    async def test_edges_carry_their_observation_window(self, db):
        """A link last seen a year ago must not look like one seen this week."""
        from database.graph_db import graph_manager

        await _edge(db)
        graph = await graph_manager.get_network_graph()
        edge = graph["edges"][0]["data"]
        assert edge["first_observed"]
        assert edge["last_observed"]

    async def test_edges_carry_their_evidence_ids(self, db):
        from database.graph_db import graph_manager

        await _edge(db)
        graph = await graph_manager.get_network_graph()
        assert all(e["data"]["evidence_record_ids"] for e in graph["edges"])
