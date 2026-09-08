"""
Tests for cross-record correlation.

The property that matters most here is restraint. Correlation output can drive
an arrest, so the engine must not promote thin evidence into a confident
finding - and it must say so plainly when it has too little to work with.
"""

import hashlib
from datetime import datetime, timedelta

import pytest

WALLET = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
PHONE = "9814098211"


async def _seed_network(db):
    """
    A small synthetic network: one wallet and one phone reused across three
    aliases and two platforms, with activity clustering on the border corridor.
    """
    from ai.enrichment import store_intelligence
    from ai.geo_resolver import resolve_coordinates
    from database.postgres import ScrapedData, MediaArtifact

    posts = [
        ("TELEGRAM", "@jagga_drops", f"Veere Attari border te chitta ready aa. Crypto {WALLET} te bhejo."),
        ("TELEGRAM", "@jagga_drops", f"Majitha bypass dead drop confirmed. Phone {PHONE} te call karo. Chitta ready."),
        ("DARK_WEB", "punjab_king", f"Grade-A heroin, Attari pickup available. Escrow to {WALLET}."),
        ("DARK_WEB", "punjab_king", f"Tramadol strips wholesale available, Ludhiana dispatch. Contact {PHONE}."),
        ("TELEGRAM", "@gopi_border", f"Attari side chitta maal ready. Same wallet {WALLET}."),
    ]

    ids = []
    for i, (source, author, text) in enumerate(posts):
        result = await store_intelligence(
            source_type=source, source_url=f"https://src/{i}",
            raw_content=text, author=author, session=db,
        )
        ids.append(result["record_id"])
        # Push timestamps into the small hours to exercise the temporal pass.
        record = await db.get(ScrapedData, result["record_id"])
        record.published_at = datetime.utcnow().replace(hour=2) - timedelta(days=i)
        db.add(record)
    await db.commit()

    # Two photographs from one phone, both GPS-tagged on the corridor.
    for n, (lat, lon) in enumerate([(31.6026, 74.6033), (31.7611, 74.9547)]):
        geo = resolve_coordinates(lat, lon)
        db.add(MediaArtifact(
            scraped_data_id=ids[n], source_url=f"https://src/photo{n}.jpg",
            media_type="IMAGE", mime_type="image/jpeg", file_size=1000,
            sha256_hash=hashlib.sha256(str(n).encode()).hexdigest(),
            device_signature="Xiaomi Redmi Note 12",
            gps_lat=lat, gps_lon=lon, geo_json=geo,
            in_border_corridor=geo["in_critical_border_corridor"],
        ))
    await db.commit()
    return ids


class TestHotspots:

    async def test_repeated_locations_become_hotspots(self, db):
        from ai.correlation import correlation_engine
        await _seed_network(db)

        picture = await correlation_engine.build_intelligence_picture()
        hotspots = {h["location"]: h for h in picture["hotspots"]["hotspots"]}

        assert "Attari" in hotspots
        assert hotspots["Attari"]["is_hotspot"] is True
        assert hotspots["Attari"]["in_border_corridor"] is True
        assert "Attari" in picture["hotspots"]["border_corridor_hotspots"]

    async def test_photo_gps_contributes_to_hotspots(self, db):
        """Coordinates from photographs feed the same map as text mentions."""
        from ai.correlation import correlation_engine
        await _seed_network(db)

        picture = await correlation_engine.build_intelligence_picture()
        attari = next(h for h in picture["hotspots"]["hotspots"]
                      if h["location"] == "Attari")
        assert attari["gps_fixes"] >= 1
        assert "MEDIA_GPS" in attari["independent_sources"]

    async def test_a_single_sighting_is_not_a_hotspot(self, db):
        """
        Restraint: one mention is a lead, not a pattern. Promoting it would
        put a location on a map on the strength of a single message.
        """
        from ai.enrichment import store_intelligence
        from ai.correlation import correlation_engine

        await store_intelligence(
            source_type="TELEGRAM", source_url="https://src/solo",
            raw_content="chitta available in Bathinda, contact me", author="@one",
            session=db,
        )
        picture = await correlation_engine.build_intelligence_picture()
        bathinda = [h for h in picture["hotspots"]["hotspots"]
                    if h["location"] == "Bathinda"]
        if bathinda:
            assert bathinda[0]["is_hotspot"] is False
            assert bathinda[0]["confidence"] == "INSUFFICIENT"


class TestIdentifierLinks:

    async def test_reused_wallet_links_separate_aliases(self, db):
        """The strongest cheap signal that one actor runs several accounts."""
        from ai.correlation import correlation_engine
        await _seed_network(db)

        picture = await correlation_engine.build_intelligence_picture()
        wallet_link = next(
            l for l in picture["identifier_links"]["links"] if l["value"] == WALLET
        )

        assert wallet_link["record_count"] >= 3
        assert set(wallet_link["source_types"]) == {"TELEGRAM", "DARK_WEB"}
        assert len(wallet_link["linked_authors"]) >= 2
        assert wallet_link["significance"] == "STRONG"

    async def test_identifier_seen_once_is_not_a_link(self, db):
        from ai.enrichment import store_intelligence
        from ai.correlation import correlation_engine

        await store_intelligence(
            source_type="TELEGRAM", source_url="https://src/lonely",
            raw_content="chitta ready, call 9876543210", author="@solo",
            session=db,
        )
        picture = await correlation_engine.build_intelligence_picture()
        assert not any(l["value"] == "9876543210"
                       for l in picture["identifier_links"]["links"])

    async def test_shared_camera_links_records(self, db):
        from ai.correlation import correlation_engine
        await _seed_network(db)

        picture = await correlation_engine.build_intelligence_picture()
        device = next(d for d in picture["device_links"]
                      if d["device"] == "Xiaomi Redmi Note 12")
        assert device["record_count"] == 2
        assert device["significance"] == "STRONG"


class TestJudgements:

    async def test_conclusions_carry_evidence_and_confidence(self, db):
        from ai.correlation import correlation_engine
        await _seed_network(db)

        picture = await correlation_engine.build_intelligence_picture()
        judgements = picture["key_judgements"]

        assert judgements
        for j in judgements:
            assert j["judgement"] and j["evidence"] and j["confidence"]

    async def test_thin_evidence_is_declared_provisional(self, db):
        """
        The engine must volunteer its own limits rather than presenting a
        confident picture built on a handful of records.
        """
        from ai.correlation import correlation_engine
        await _seed_network(db)

        picture = await correlation_engine.build_intelligence_picture()
        assert any("provisional" in j["judgement"].lower()
                   for j in picture["key_judgements"])

    async def test_no_data_is_reported_honestly(self, db):
        from ai.correlation import correlation_engine
        picture = await correlation_engine.build_intelligence_picture()
        assert picture["status"] == "NO_DATA"
        assert picture["record_count"] == 0


class TestTemporalPattern:

    async def test_night_concentration_is_detected(self, db):
        from ai.correlation import correlation_engine
        await _seed_network(db)

        temporal = (await correlation_engine.build_intelligence_picture())["temporal_pattern"]
        assert temporal["night_activity_share_pct"] > 50
        assert "night" in temporal["assessment"].lower()


class TestReCollectionDeduplication:
    """
    A scheduled crawler revisiting the same page must not manufacture evidence.

    The background scheduler re-scraped its targets every two minutes and
    stored each pass as a new row. Correlation counts sightings, so one
    Wikipedia page became a six-sighting "hotspot" backed by six independent
    records that were all the same document.
    """

    async def test_identical_content_folds_into_the_original(self, db):
        from ai.enrichment import store_intelligence
        from database.postgres import ScrapedData
        from sqlalchemy import select

        text = "Attari border te chitta ready aa. Escrow only."
        url = "https://example.onion/listing"

        first = await store_intelligence(
            source_type="DARK_WEB", source_url=url,
            raw_content=text, session=db)
        second = await store_intelligence(
            source_type="DARK_WEB", source_url=url,
            raw_content=text, session=db)

        assert first["status"] == "SAVED"
        assert second["status"] == "DUPLICATE"
        assert second["record_id"] == first["record_id"]

        rows = (await db.execute(
            select(ScrapedData).where(ScrapedData.source_url == url)
        )).scalars().all()
        assert len(rows) == 1

    async def test_re_collection_is_counted_not_discarded(self, db):
        """Knowing a listing is still up is intelligence; it just isn't a new record."""
        from ai.enrichment import store_intelligence
        from database.postgres import ScrapedData

        text = "Majitha dead drop confirmed."
        url = "https://example.onion/repeat"

        first = await store_intelligence(
            source_type="DARK_WEB", source_url=url, raw_content=text, session=db)
        for _ in range(3):
            await store_intelligence(
                source_type="DARK_WEB", source_url=url, raw_content=text, session=db)

        record = await db.get(ScrapedData, first["record_id"])
        provenance = (record.metadata_json or {}).get("provenance", {})
        assert provenance["times_collected"] == 4
        assert provenance["last_collected_at"]

    async def test_same_content_at_a_different_url_stays_separate(self, db):
        """
        A mirrored listing is a genuine finding, not a duplicate.

        Identical content under two URLs is how a vendor rotating domains
        shows up. Collapsing those would destroy the evidence of the rotation.
        """
        from ai.enrichment import store_intelligence

        text = "Grade-A chitta, escrow only, dead drop Majitha."
        first = await store_intelligence(
            source_type="DARK_WEB", source_url="https://market-a.onion/x",
            raw_content=text, session=db)
        second = await store_intelligence(
            source_type="DARK_WEB", source_url="https://market-b.onion/y",
            raw_content=text, session=db)

        assert second["status"] == "SAVED"
        assert second["record_id"] != first["record_id"]
        assert first["sha256_hash"] == second["sha256_hash"]
