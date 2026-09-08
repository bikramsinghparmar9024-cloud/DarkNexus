"""
Correlation graph identity, evidence traceability and merge rules.

Three defects are covered here, all of which produced confident wrong output
rather than visible errors:

  * the graph and the entity resolver built different keys for the same
    person, so "Why This Link?" returned 404 for suspects present in both
  * wallet keys were the first twelve characters of an address, so two
    different wallets could merge into one node and the graph would assert a
    shared payment account that did not exist
  * the node label merge kept whichever label was longest, which has no
    relationship to being correct
"""

import pathlib
import re

import pytest

from core.identity import (
    slugify_entity_key, canonical_drug_name, reload_drug_aliases,
)
from ai.entity_store import _slug


class TestOneKeyPerEntity:
    """The root cause of the 404s: two key builders for one entity."""

    @pytest.mark.parametrize("handle", [
        "@Jagga_Drops", "jagga_drops", "@@jagga drops", "Jagga Drops",
        "  @JAGGA_DROPS  ",
    ])
    def test_graph_key_and_resolver_key_are_byte_identical(self, handle):
        assert slugify_entity_key(handle, "suspect") == _slug(handle)

    def test_spelling_variants_collapse_to_one_suspect(self):
        keys = {slugify_entity_key(h, "suspect") for h in
                ["@Jagga_Drops", "jagga drops", "JAGGA_DROPS", "@jagga_drops"]}
        assert len(keys) == 1


class TestWalletKeysCannotCollide:
    """
    Truncating to twelve characters merged distinct wallets into one node -
    the graph would report two vendors sharing a payment account.
    """

    def test_two_wallets_sharing_a_prefix_stay_separate(self):
        a = "bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh"
        b = "bc1qxy2kgdygABCDEFGHIJKLMNOPQRSTUVWXYZ01234"
        assert a[:12] == b[:12], "fixture must share a prefix to be meaningful"
        assert slugify_entity_key(a, "wallet") != slugify_entity_key(b, "wallet")

    def test_wallet_case_is_preserved(self):
        """Address case is meaningful; folding it could merge two wallets."""
        assert (slugify_entity_key("bc1QXY2KGDYG", "wallet")
                != slugify_entity_key("bc1qxy2kgdyg", "wallet"))

    def test_a_long_identifier_is_hashed_not_truncated(self):
        """A prefix can collide; a digest of the whole value effectively cannot."""
        base = "a" * 300
        key_a = slugify_entity_key(base + "1", "pgp")
        key_b = slugify_entity_key(base + "2", "pgp")
        assert key_a != key_b
        assert len(key_a) < 300


class TestDrugAliasNormalization:

    @pytest.mark.parametrize("alias", ["chitta", "Chitta", "Heroin / Chitta",
                                       "smack", "brown sugar"])
    def test_known_aliases_collapse_to_one_node(self, alias):
        assert slugify_entity_key(alias, "drug") == "drug_heroin"

    @pytest.mark.parametrize("alias", ["bhukki", "afeem", "poppy straw",
                                       "Opium / Bhukki"])
    def test_opium_aliases_collapse(self, alias):
        assert slugify_entity_key(alias, "drug") == "drug_opium"

    @pytest.mark.parametrize("alias", ["ice", "crystal", "meth", "shabu"])
    def test_meth_aliases_collapse(self, alias):
        assert slugify_entity_key(alias, "drug") == "drug_methamphetamine"

    def test_an_unknown_substance_is_kept_rather_than_dropped(self):
        assert canonical_drug_name("novelcompound-7") == "novelcompound-7"

    def test_the_alias_table_is_editable_without_a_code_change(self):
        """Shipped as JSON precisely so new slang can be added mid-operation."""
        table = reload_drug_aliases()
        assert table["chitta"] == "heroin"
        assert len(table) > 30

    def test_punctuation_and_case_do_not_split_a_substance(self):
        assert (slugify_entity_key("Heroin / Chitta", "drug")
                == slugify_entity_key("heroin-chitta", "drug")
                == slugify_entity_key("HEROIN   CHITTA", "drug"))


class TestNoManualKeyConstruction:
    """A fourth divergent copy is how this bug arrived. Grep for one."""

    def test_no_module_builds_entity_keys_by_hand(self):
        root = pathlib.Path(__file__).resolve().parent.parent
        pattern = re.compile(r'f"(suspect|actor|drug|wallet|intercept|vendor)_\{')

        offenders = []
        for path in root.rglob("*.py"):
            parts = set(path.parts)
            if parts & {"tests", "scripts", "__pycache__"}:
                continue
            if pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
                offenders.append(str(path.relative_to(root)))

        assert offenders == [], (
            f"manual entity-key construction still present in: {offenders}")


class TestEvidenceTraceability:

    async def test_every_edge_records_the_record_that_made_it(self, db):
        from sqlalchemy import select
        from ai.enrichment import store_intelligence
        from database.postgres import GraphEdge

        saved = await store_intelligence(
            source_type="TELEGRAM", source_url="https://t.me/x/1",
            raw_content="Chitta available, escrow only.",
            author="@vendor_one", session=db)

        edges = (await db.execute(select(GraphEdge))).scalars().all()
        assert edges, "storing an intercept must produce edges"
        for edge in edges:
            assert edge.evidence_record_ids, (
                f"edge {edge.edge_key} has no traceable source record")
            assert saved["record_id"] in edge.evidence_record_ids

    async def test_an_edge_can_be_described_with_its_evidence(self, db):
        from ai.enrichment import store_intelligence
        from database.graph_db import graph_manager

        saved = await store_intelligence(
            source_type="TELEGRAM", source_url="https://t.me/x/2",
            raw_content="Chitta available near Majitha.",
            author="@vendor_two", session=db)

        described = await graph_manager.describe_edge(
            slugify_entity_key(str(saved["record_id"]), "intercept"),
            slugify_entity_key("chitta", "drug"))

        assert described["status"] == "OBSERVED"
        assert described["relations"][0]["relation"] == "MENTIONS_NARCOTIC"
        assert described["evidence_count"] >= 1
        assert described["relations"][0]["first_observed"]
        assert described["relations"][0]["last_observed"]

    async def test_an_unknown_pair_says_so_rather_than_inventing_a_link(self, db):
        from database.graph_db import graph_manager
        result = await graph_manager.describe_edge("suspect_nobody", "drug_heroin")
        assert result["status"] == "NO_EDGE"

    async def test_no_confidence_score_is_invented_for_a_co_occurrence(self, db):
        """
        A mention is not an identity claim. Attaching a confidence number to
        one would be a fabricated measurement.
        """
        from ai.enrichment import store_intelligence
        from database.graph_db import graph_manager

        saved = await store_intelligence(
            source_type="TELEGRAM", source_url="https://t.me/x/3",
            raw_content="Chitta available.", author="@vendor_three", session=db)

        described = await graph_manager.describe_edge(
            slugify_entity_key(str(saved["record_id"]), "intercept"),
            slugify_entity_key("chitta", "drug"))

        assert "confidence_score" not in described
        assert "co-occurrence" in described["basis"]


class TestLabelMergeRule:
    """
    String length has no relationship to correctness, and must never be a
    tiebreaker again. A verified label outranks everything; otherwise the most
    recent observation wins.
    """

    async def test_a_later_label_replaces_an_earlier_one(self, db):
        from sqlalchemy import select
        from database.graph_db import graph_manager
        from database.postgres import GraphNode

        await graph_manager.add_entity_link(
            "suspect_x", "A Very Long Descriptive Scraped Title", "suspect",
            "drug_heroin", "heroin", "drug", "MENTIONS_NARCOTIC", session=db)
        await graph_manager.add_entity_link(
            "suspect_x", "Short", "suspect",
            "drug_heroin", "heroin", "drug", "MENTIONS_NARCOTIC", session=db)

        node = (await db.execute(
            select(GraphNode).where(GraphNode.node_key == "suspect_x")
        )).scalars().first()
        assert node.label == "Short", "most recent label must win, not longest"

    async def test_a_verified_label_is_never_overwritten(self, db):
        from sqlalchemy import select
        from database.graph_db import graph_manager
        from database.postgres import GraphNode

        await graph_manager.add_entity_link(
            "suspect_y", "Analyst Confirmed Name", "suspect",
            "drug_heroin", "heroin", "drug", "MENTIONS_NARCOTIC", session=db)
        node = (await db.execute(
            select(GraphNode).where(GraphNode.node_key == "suspect_y")
        )).scalars().first()
        node.label_verified = True
        await db.commit()

        await graph_manager.add_entity_link(
            "suspect_y", "Scraped Rubbish Title", "suspect",
            "drug_heroin", "heroin", "drug", "MENTIONS_NARCOTIC", session=db)

        node = (await db.execute(
            select(GraphNode).where(GraphNode.node_key == "suspect_y")
        )).scalars().first()
        assert node.label == "Analyst Confirmed Name"
