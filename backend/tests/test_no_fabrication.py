"""
Guards against fabricated data re-entering the system.

Several parts of this codebase used to manufacture plausible-looking output
when they had nothing real to show: seeded evidence records, invented suspect
rosters, placeholder entity counts. In a system whose output can justify a
search warrant, that is worse than showing nothing, because an empty system
looked identical to a working one.

These tests are deliberately blunt. They assert that with an empty database,
every surface returns empty.
"""

import pytest


class TestSeedScriptCannotRun:

    def test_importing_the_seed_script_raises(self):
        """
        It wrote invented records, targets, wallets and a graph of fictional
        suspects into the operational database.
        """
        with pytest.raises(ImportError):
            import database.seed_data  # noqa: F401

    def test_purge_utility_identifies_only_seeded_records(self, db):
        """
        The marker must match the retired seed script's output and nothing
        else - deleting real evidence is far worse than leaving a fake one.
        """
        from scripts.purge_demo_data import _is_seeded
        from database.postgres import ScrapedData

        seeded = ScrapedData(
            source_type="DARK_WEB", source_url="http://fake...onion/x",
            raw_content="x", sha256_hash="0" * 64,
            metadata_json={"origin": "Majitha Bypass", "border_alert": True},
        )
        collected = ScrapedData(
            source_type="SURFACE_WEB", source_url="https://real.example/x",
            raw_content="x", sha256_hash="1" * 64,
            metadata_json={"analysis": {}, "provenance": {"acquisition_method": "AUTOMATED_COLLECTION"}},
        )
        simulated = ScrapedData(
            source_type="TELEGRAM", source_url="https://t.me/s/x/1",
            raw_content="x", sha256_hash="2" * 64,
            metadata_json={"analysis": {}, "provenance": {"acquisition_method": "MANUAL_IMPORT"}},
        )

        assert _is_seeded(seeded) is True
        assert _is_seeded(collected) is False
        assert _is_seeded(simulated) is False


class TestEmptySystemLooksEmpty:

    async def test_entity_summary_returns_no_placeholder_counts(self, db):
        """
        This endpoint used to substitute invented counts - Heroin 8,
        Amritsar 9, a fabricated wallet address - whenever the database
        returned nothing.
        """
        from routes.ai_routes import get_entities_summary

        result = await get_entities_summary(db)

        assert result["top_drugs"] == {}
        assert result["top_locations"] == {}
        assert result["suspect_handles"] == []
        assert result["crypto_wallets"] == []
        assert result["has_data"] is False
        assert result["note"], "an empty result must explain itself"

    async def test_entity_summary_reports_real_data_when_present(self, db):
        from ai.enrichment import store_intelligence
        from routes.ai_routes import get_entities_summary

        await store_intelligence(
            source_type="TELEGRAM", source_url="https://t.me/s/x/1",
            raw_content="Veere Attari chitta ready aa, crypto "
                        "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa te bhejo.",
            author="@actor", session=db,
        )
        result = await get_entities_summary(db)

        assert result["has_data"] is True
        assert "Heroin / Chitta" in result["top_drugs"]
        assert "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa" in result["crypto_wallets"]
        assert result["note"] is None

    async def test_no_fictional_names_survive_anywhere(self, db):
        """
        A sweep across every surface that previously carried the invented
        cast, with an empty database.
        """
        from ai.entity_resolver import entity_resolver
        from database.graph_db import graph_manager
        from ai.correlation import correlation_engine
        from ai.suspect_correlation import correlate_suspect
        from sqlalchemy import select
        from database.postgres import CTIProject

        await entity_resolver.refresh()
        graph = await graph_manager.get_network_graph()
        picture = await correlation_engine.build_intelligence_picture()
        suspect = await correlate_suspect("@Tariq_Lahori")
        projects = (await db.execute(select(CTIProject))).scalars().all()

        # The suspect result is excluded from the sweep: it echoes back the
        # handle that was queried, which is correct. What matters is that the
        # query returns no evidence, asserted separately below.
        combined = " ".join(str(x) for x in (
            entity_resolver.knowledge_base, graph, picture, projects)).lower()

        for ghost in ("tariq", "jagga_majitha", "gopi_fzr", "sunny_gill",
                      "punjabchem4vq", "afghansilkx6", "kasurnexus82"):
            assert ghost not in combined, f"'{ghost}' still reachable"

        # Querying a name that was formerly hardcoded must now find nothing.
        assert suspect["risk_score"] == 0
        assert suspect["found"] is False
        assert suspect["matched_sources"] == []
        assert projects == []
