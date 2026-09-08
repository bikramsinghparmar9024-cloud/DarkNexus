"""
Tests for entity resolution.

The resolver previously ran against a hardcoded cast of invented suspects with
fabricated PGP keys, so it produced confident, evidence-cited explanations of
links between people who did not exist. For a system whose output could
justify a search warrant, that is the most dangerous failure mode available.

These tests assert the opposite property: every entity and every link must be
traceable to a stored record.
"""

import pytest

from core.identity import slugify_entity_key


def key(handle: str) -> str:
    """Entity id as the system builds it - never a hardcoded prefix."""
    return slugify_entity_key(handle, "suspect")

PGP = "A4F2 8C91 D3E7 6B05 1234 ABCD EF01 2345 6789 FACE"
PGP_NORMALISED = "A4F28C91D3E76B051234ABCDEF0123456789FACE"
WALLET = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"


async def _seed(db, posts):
    from ai.enrichment import store_intelligence
    ids = []
    for i, (source, author, text) in enumerate(posts):
        result = await store_intelligence(
            source_type=source, source_url=f"https://src/{i}",
            raw_content=text, author=author, session=db,
        )
        ids.append(result["record_id"])
    return ids


class TestKnowledgeBaseIsReal:

    async def test_empty_database_yields_no_entities(self, db):
        """
        The decisive test. Previously this returned a roster of invented
        suspects regardless of what had been collected.
        """
        from ai.entity_resolver import entity_resolver
        await entity_resolver.refresh()

        assert entity_resolver.knowledge_base == {}
        assert entity_resolver.get_all_entities() == []

    async def test_entities_come_from_collected_records(self, db):
        from ai.entity_resolver import entity_resolver
        await _seed(db, [
            ("TELEGRAM", "@jagga_drops", f"Chitta ready aa. Crypto {WALLET} te bhejo."),
            ("DARK_WEB", "punjab_king", f"Grade-A heroin available. Escrow to {WALLET}."),
        ])
        await entity_resolver.refresh()

        names = {e["name"] for e in entity_resolver.get_all_entities()}
        assert names == {"@jagga_drops", "punjab_king"}

    async def test_no_fictional_suspects_survive(self, db):
        """The removed cast must not reappear from any code path."""
        from ai.entity_resolver import entity_resolver
        await _seed(db, [("TELEGRAM", "@real_actor", "chitta ready, contact me")])
        await entity_resolver.refresh()

        blob = str(entity_resolver.knowledge_base).lower()
        for ghost in ("tariq", "jagga_majitha", "gopi", "sunny_gill", "afghan_silk"):
            assert ghost not in blob

    async def test_every_entity_cites_its_sources(self, db):
        from ai.entity_resolver import entity_resolver
        await _seed(db, [("TELEGRAM", "@actor_one", "chitta available, contact me")])
        await entity_resolver.refresh()

        for entity in entity_resolver.knowledge_base.values():
            assert entity["sources"], "an entity with no source record is unfounded"
            for source in entity["sources"]:
                assert source["record_id"]
                assert source["url"]


class TestLinkResolution:

    async def test_shared_wallet_links_two_aliases(self, db):
        from ai.entity_resolver import entity_resolver
        await _seed(db, [
            ("TELEGRAM", "@jagga_drops", f"Chitta ready aa. Crypto {WALLET} te bhejo."),
            ("DARK_WEB", "punjab_king", f"Grade-A heroin available. Escrow to {WALLET}."),
        ])
        await entity_resolver.refresh()

        result = entity_resolver.explain_link(key("jagga_drops"), key("punjab_king"))
        assert result.get("status") != "NOT_FOUND"

        signals = {s["signal_type"]: s for s in result["signal_breakdown"]} \
            if isinstance(result.get("signal_breakdown"), list) else {}
        assert result["confidence"]["score"] > 0
        # The wallet is the reason; it must appear in the explanation somewhere.
        assert WALLET in str(result)

    async def test_pgp_match_produces_high_confidence(self, db):
        """
        A shared PGP fingerprint is the strongest signal in the model, and it
        only became functional once extraction was added.
        """
        from ai.entity_resolver import entity_resolver
        await _seed(db, [
            ("DARK_WEB", "vendor_alpha", f"Grade-A heroin available. PGP {PGP}"),
            ("TELEGRAM", "@vendor_beta", f"Chitta ready, verify me. PGP {PGP}"),
        ])
        await entity_resolver.refresh()

        alpha = entity_resolver.knowledge_base[key("vendor_alpha")]
        assert PGP_NORMALISED in alpha["identifiers"]["pgp_fingerprints"]

        result = entity_resolver.explain_link(key("vendor_alpha"), key("vendor_beta"))
        assert result["confidence"]["score"] >= 35

    async def test_unrelated_actors_are_not_linked(self, db):
        """Absence of shared identifiers must not become a relationship."""
        from ai.entity_resolver import entity_resolver
        await _seed(db, [
            ("TELEGRAM", "@actor_a", "chitta ready in Amritsar, contact me"),
            ("TELEGRAM", "@actor_b", "tramadol strips available in Ludhiana"),
        ])
        await entity_resolver.refresh()

        pairs = {(r["source_entity"], r["target_entity"])
                 for r in entity_resolver.relationships}
        assert (key("actor_a"), key("actor_b")) not in pairs

    async def test_confidence_never_exceeds_one_hundred(self, db):
        from ai.entity_resolver import entity_resolver
        await _seed(db, [
            ("SURFACE_WEB", "@twin", f"chitta available. PGP {PGP}. Wallet {WALLET}. Call 9814098211"),
            ("SURFACE_WEB", "@twin", f"chitta available. PGP {PGP}. Wallet {WALLET}. Call 9814098211"),
            ("DARK_WEB", "@twin_alt", f"chitta available. PGP {PGP}. Wallet {WALLET}. Call 9814098211"),
        ])
        await entity_resolver.refresh()

        for rel in entity_resolver.relationships:
            score, _ = entity_resolver.calculate_confidence(rel["signals"])
            assert 0 <= score <= 100

    async def test_missing_entity_is_reported_not_invented(self, db):
        from ai.entity_resolver import entity_resolver
        await entity_resolver.refresh()
        result = entity_resolver.explain_link(key("nobody"), key("nothing"))
        assert result["status"] == "NOT_FOUND"


class TestContradictions:

    async def test_conflicting_phones_are_surfaced(self, db):
        """
        An analyst shown only supporting evidence has been handed a
        conclusion, not an assessment.
        """
        from ai.entity_resolver import entity_resolver
        await _seed(db, [
            ("TELEGRAM", "@actor_x", f"chitta ready. Wallet {WALLET}. Call 9814098211"),
            ("DARK_WEB", "actor_y", f"heroin available. Escrow {WALLET}. Contact 9876543210"),
        ])
        await entity_resolver.refresh()

        rel = next(r for r in entity_resolver.relationships)
        kinds = {c["type"] for c in rel["contradictions"]}
        assert "IDENTIFIER_CONFLICT" in kinds

    async def test_differing_pgp_keys_argue_against_one_identity(self, db):
        from ai.entity_resolver import entity_resolver
        other_pgp = "B7D3 E4A1 C290 5F87 9876 DCBA 5432 1098 7654 BEEF"
        await _seed(db, [
            ("DARK_WEB", "vendor_one", f"chitta available. Wallet {WALLET}. PGP {PGP}"),
            ("DARK_WEB", "vendor_two", f"chitta available. Wallet {WALLET}. PGP {other_pgp}"),
        ])
        await entity_resolver.refresh()

        rel = next(r for r in entity_resolver.relationships)
        kinds = {c["type"] for c in rel["contradictions"]}
        assert "PGP_MISMATCH" in kinds
