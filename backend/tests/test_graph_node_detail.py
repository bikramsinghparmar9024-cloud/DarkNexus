"""
Node labels and the evidence behind a node.

Two problems this covers. Nodes were labelled "Intercept #14", which tells a
reader nothing - identifying what a node was meant leaving the graph and
looking the id up elsewhere. And selecting a node showed its label and type
only, so an investigator could see that a substance was in the graph but not
where the word had actually been found.

The snippet must also be honest about itself: when the term cannot be located
in the stored text, the excerpt is the top of the document and has to say so,
because an arbitrary opening paragraph presented as "where this was found" is
a small fabrication.
"""

import pytest

from ai.enrichment import intercept_label_for
from core.identity import slugify_entity_key


class TestInterceptLabels:

    def test_the_page_title_is_used_when_one_was_captured(self):
        assert intercept_label_for(
            14, "Illegal drug trade in India - Wikipedia"
        ) == "Illegal drug trade in India - Wikipedia"

    def test_the_url_is_used_when_there_is_no_title(self):
        label = intercept_label_for(15, None, "https://en.wikipedia.org/wiki/Opium")
        assert "Opium" in label
        assert "en.wikipedia.org" in label

    def test_a_bare_host_is_better_than_a_number(self):
        assert intercept_label_for(16, None, "http://abc123.onion/") == "abc123.onion"

    def test_the_id_remains_the_last_resort(self):
        assert intercept_label_for(17) == "Intercept #17"
        assert intercept_label_for(17, "   ", None) == "Intercept #17"

    def test_a_long_title_is_truncated_visibly(self):
        label = intercept_label_for(18, "x" * 200)
        assert label.endswith("...")
        assert len(label) < 200


class TestNodeEvidence:

    async def _seed(self, db, text, url="https://example.test/page",
                    author="@vendor_one", title="Vendor listing"):
        from ai.enrichment import store_intelligence
        return await store_intelligence(
            source_type="TELEGRAM", source_url=url, raw_content=text,
            author=author, provenance={"title": title}, session=db)

    async def test_a_node_returns_the_records_behind_it(self, db):
        from database.graph_db import graph_manager

        saved = await self._seed(db, "Chitta available near Majitha, escrow only.")
        detail = await graph_manager.describe_node(
            slugify_entity_key("chitta", "drug"))

        assert detail["status"] == "FOUND"
        assert detail["evidence_count"] >= 1
        assert detail["evidence"][0]["record_id"] == saved["record_id"]
        assert detail["evidence"][0]["sha256"]

    async def test_the_snippet_surrounds_the_actual_match(self, db):
        """
        The passage has to be where the term appears, not the opening of the
        document - otherwise "found in" is showing an unrelated paragraph.
        """
        from database.graph_db import graph_manager

        filler = "Unrelated preamble about general policy. " * 30
        await self._seed(db, filler + " Chitta available, escrow only.")

        detail = await graph_manager.describe_node(
            slugify_entity_key("chitta", "drug"))
        evidence = detail["evidence"][0]

        assert evidence["is_excerpt_around_match"] is True
        assert evidence["found_at"] > 0
        assert "hitta" in evidence["snippet"]

    async def test_an_alias_is_located_even_though_the_node_is_canonical(self, db):
        """
        The node says "heroin"; the page said "smack". Searching only for the
        canonical name would never match and every snippet would silently
        fall back to the top of the document.
        """
        from database.graph_db import graph_manager

        filler = "Preamble. " * 40
        await self._seed(db, filler + " Smack available, wholesale rates.")

        detail = await graph_manager.describe_node(
            slugify_entity_key("heroin", "drug"))
        evidence = detail["evidence"][0]

        assert evidence["is_excerpt_around_match"] is True
        assert evidence["matched_term"] == "smack"

    async def test_a_fallback_excerpt_declares_itself(self, db):
        from database.graph_db import graph_manager

        saved = await self._seed(db, "Chitta available.")
        detail = await graph_manager.describe_node(
            slugify_entity_key(str(saved["record_id"]), "intercept"))
        evidence = detail["evidence"][0]

        # An intercept node's key is a number; it will not appear in the text,
        # so this must be reported as the start of the document, not as a hit.
        assert evidence["is_excerpt_around_match"] is False
        assert evidence["matched_term"] is None

    async def test_a_node_lists_its_connections(self, db):
        from database.graph_db import graph_manager

        saved = await self._seed(db, "Chitta available, escrow only.")
        detail = await graph_manager.describe_node(
            slugify_entity_key(str(saved["record_id"]), "intercept"))

        relations = {c["relation"] for c in detail["connections"]}
        assert "MENTIONS_NARCOTIC" in relations
        assert all(c["other_label"] for c in detail["connections"])

    async def test_an_unknown_node_is_reported_not_invented(self, db):
        from database.graph_db import graph_manager
        result = await graph_manager.describe_node("suspect_does_not_exist")
        assert result["status"] == "NOT_FOUND"

    async def test_the_node_carries_a_real_label(self, db):
        from database.graph_db import graph_manager

        saved = await self._seed(db, "Chitta available.", title="NCB seizes 2kg")
        detail = await graph_manager.describe_node(
            slugify_entity_key(str(saved["record_id"]), "intercept"))

        assert detail["node"]["label"] == "NCB seizes 2kg"
        assert "Intercept #" not in detail["node"]["label"]
