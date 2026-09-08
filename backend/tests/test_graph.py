"""
Tests for the correlation graph.

The graph previously lived in two Python lists seeded with invented suspects.
Anything an investigator built was lost on restart, and the fiction returned in
its place - so the graph could present fabricated links as findings. These
tests assert that it now holds only what was observed, and that it survives.
"""

import pytest

WALLET = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"


class TestGraphIsReal:

    async def test_empty_database_yields_an_empty_graph(self, db):
        """
        The decisive test: this used to return 15 fictional suspects and 15
        relationships between them, regardless of what had been collected.
        """
        from database.graph_db import graph_manager
        graph = await graph_manager.get_network_graph()

        assert graph["nodes"] == []
        assert graph["edges"] == []

    async def test_no_fictional_suspects_can_appear(self, db):
        from database.graph_db import graph_manager
        from ai.enrichment import store_intelligence

        await store_intelligence(
            source_type="TELEGRAM", source_url="https://t.me/s/x/1",
            raw_content=f"Chitta ready aa, crypto {WALLET} te bhejo.",
            author="@real_actor", session=db,
        )
        blob = str(await graph_manager.get_network_graph()).lower()
        for ghost in ("tariq", "jagga_majitha", "gopi", "sunny", "afghan_silk",
                      "punjabchem4vq"):
            assert ghost not in blob

    async def test_the_old_module_cannot_be_imported(self):
        """A stale import must fail loudly, not quietly restore fake data."""
        with pytest.raises(ImportError):
            import database.neo4j_db  # noqa: F401


class TestGraphPersistence:

    async def test_ingest_creates_nodes_and_edges(self, db):
        from database.graph_db import graph_manager
        from ai.enrichment import store_intelligence

        await store_intelligence(
            source_type="TELEGRAM", source_url="https://t.me/s/x/2",
            raw_content=f"Veere chitta ready aa. Crypto {WALLET} te bhejo.",
            author="@jagga_drops", session=db,
        )
        graph = await graph_manager.get_network_graph()

        labels = {n["data"]["label"] for n in graph["nodes"]}
        types = {n["data"]["type"] for n in graph["nodes"]}

        assert any("jagga_drops" in l for l in labels)
        assert "suspect" in types
        assert graph["edges"], "an ingested record must produce relationships"

    async def test_graph_survives_a_restart(self, db):
        """
        The whole point of the change: rebuild the manager from scratch and
        the graph must still be there.
        """
        from database.graph_db import GraphManager, graph_manager
        from ai.enrichment import store_intelligence

        await store_intelligence(
            source_type="DARK_WEB", source_url="https://onion/x",
            raw_content=f"Grade-A heroin available. Escrow {WALLET}.",
            author="punjab_king", session=db,
        )
        before = await graph_manager.get_network_graph()
        assert before["nodes"]

        fresh = GraphManager()          # simulates a process restart
        await fresh.connect()
        after = await fresh.get_network_graph()

        assert len(after["nodes"]) == len(before["nodes"])
        assert len(after["edges"]) == len(before["edges"])

    async def test_repeated_observations_increment_rather_than_duplicate(self, db):
        """
        A relationship seen twice is stronger evidence, not two relationships.
        Duplicating edges would inflate the graph and mislead centrality.
        """
        from database.graph_db import graph_manager

        for _ in range(3):
            await graph_manager.add_entity_link(
                "suspect_a", "Actor A", "suspect",
                "drug_chitta", "Chitta", "drug", "MENTIONS_NARCOTIC",
            )
        graph = await graph_manager.get_network_graph()
        edges = [e for e in graph["edges"] if e["data"]["label"] == "MENTIONS_NARCOTIC"]

        assert len(edges) == 1
        assert edges[0]["data"]["observations"] == 3

    async def test_one_off_links_can_be_filtered_out(self, db):
        """
        An analyst needs to separate established connections from single
        passing mentions.
        """
        from database.graph_db import graph_manager

        await graph_manager.add_entity_link(
            "suspect_solo", "Solo", "suspect",
            "drug_x", "X", "drug", "MENTIONS_NARCOTIC")
        for _ in range(2):
            await graph_manager.add_entity_link(
                "suspect_repeat", "Repeat", "suspect",
                "drug_y", "Y", "drug", "MENTIONS_NARCOTIC")

        filtered = await graph_manager.get_network_graph(min_observations=2)
        keys = {n["data"]["id"] for n in filtered["nodes"]}

        assert "suspect_repeat" in keys
        assert "suspect_solo" not in keys

    async def test_stats_report_what_is_stored(self, db):
        from database.graph_db import graph_manager

        await graph_manager.add_entity_link(
            "suspect_z", "Z", "suspect", "wallet_abc", "Wallet", "wallet", "USES_CRYPTO")
        stats = await graph_manager.get_stats()

        assert stats["backend"] == "database"
        assert stats["node_count"] == 2
        assert stats["edge_count"] == 1
        assert stats["nodes_by_type"]["suspect"] == 1
