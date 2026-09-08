"""
Tests for storage and the unified ingest pipeline.

The system previously had two ingest paths that wrote incompatible records:
the scrapers set `flagged_entities`, the simulator wrote a differently-named
blob into `metadata_json`, and only one of them reached the search index. Code
that read one could not find the other. These tests exist so that cannot
return.
"""

import pytest

from tests.conftest import DEALER_OFFER, BENIGN_TEXT


class TestUnifiedIngest:

    async def test_both_paths_write_the_same_shape(self, db):
        """
        A scraped record and a manually injected one must be indistinguishable
        once stored, apart from their provenance.
        """
        from ai.enrichment import store_intelligence
        from scrapers.base_scraper import BaseScraper

        class _Probe(BaseScraper):
            async def scrape(self, target): ...
            async def crawl(self, target, max_depth=2): ...

        scraped = await _Probe("Probe", "SURFACE_WEB").save_evidence(
            url="https://example.test/listing",
            raw_content=DEALER_OFFER,
            cleaned_text=DEALER_OFFER,
            author="@vendor",
            fetch_media=False,
        )
        injected = await store_intelligence(
            source_type="TELEGRAM",
            source_url="https://t.me/s/x/1",
            raw_content=DEALER_OFFER,
            author="@vendor",
            provenance={"acquisition_method": "MANUAL_IMPORT"},
        )

        assert scraped["threat_level"] == injected["threat_level"]
        assert scraped["sha256_hash"] == injected["sha256_hash"]  # same content
        assert set(scraped["analysis"].keys()) == set(injected["analysis"].keys())

    async def test_record_columns_are_populated(self, db):
        from sqlalchemy import select
        from ai.enrichment import store_intelligence
        from database.postgres import ScrapedData

        result = await store_intelligence(
            source_type="TELEGRAM", source_url="https://t.me/s/x/2",
            raw_content=DEALER_OFFER, author="@vendor",
        )
        record = (await db.execute(
            select(ScrapedData).where(ScrapedData.id == result["record_id"])
        )).scalars().first()

        assert record.flagged_entities, "flagged_entities must always be set"
        assert record.threat_level != "UNREVIEWED"
        assert set(record.metadata_json.keys()) == {"analysis", "provenance"}
        assert len(record.sha256_hash) == 64

    async def test_wallets_are_recorded_and_deduplicated(self, db):
        """
        The crypto_wallets table was write-only dead code; the dashboard
        counter read from it and always showed the seeded value.
        """
        from sqlalchemy import select
        from ai.enrichment import store_intelligence
        from database.postgres import CryptoWalletIntel

        for i in range(2):
            await store_intelligence(
                source_type="TELEGRAM", source_url=f"https://t.me/s/x/{i}",
                raw_content=DEALER_OFFER, author="@vendor",
            )

        wallets = (await db.execute(select(CryptoWalletIntel))).scalars().all()
        addresses = [w.wallet_address for w in wallets]
        assert "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa" in addresses
        assert len(addresses) == len(set(addresses)), "wallets must not duplicate"

    async def test_legacy_records_still_read(self, db):
        """
        Records written before the pipelines were unified use the old key
        layout. get_analysis() must keep understanding them.
        """
        from ai.enrichment import get_analysis
        from database.postgres import ScrapedData

        legacy = ScrapedData(
            source_type="TELEGRAM", source_url="https://t.me/s/old/1",
            raw_content="veere chitta ready", cleaned_text="veere chitta ready",
            sha256_hash="0" * 64, threat_level="SEVERE",
            metadata_json={                      # pre-unification layout
                "extracted_entities": {"drugs": ["Heroin / Chitta"]},
                "threat_classifier": {"risk_score": 80, "intent": "RETAIL"},
                "geo_resolver": {"district": "Attari"},
                "border_alert": True,
            },
        )
        db.add(legacy)
        await db.commit()
        await db.refresh(legacy)

        analysis = get_analysis(legacy)
        assert analysis["schema_version"] == 1
        assert analysis["entities"]["drugs"] == ["Heroin / Chitta"]
        assert analysis["threat"]["threat_level"] == "SEVERE"
        assert analysis["border_alert"] is True


class TestMediaLinkage:

    async def test_border_gps_escalates_a_record_with_no_location_text(self, db):
        """
        The headline capability: a photograph's coordinates can raise a threat
        level even when the message text names no place at all.
        """
        import hashlib
        from ai.geo_resolver import resolve_coordinates
        from ai.enrichment import store_intelligence, analyze_text

        text = "Veere maal ready aa, 2 packet chitta. Rate daso."
        assert analyze_text(text)["geo"] is None, "text must contain no location"

        geo = resolve_coordinates(31.6026, 74.6033)  # Attari
        media = [{
            "url": "https://t.me/s/x/p.jpg", "media_type": "IMAGE",
            "mime_type": "image/jpeg", "sha256": hashlib.sha256(b"x").hexdigest(),
            "path": None, "size": 1000, "gps": {"lat": 31.6026, "lon": 74.6033},
            "geo": geo, "in_border_corridor": True, "has_exif": True,
            "device_signature": "Xiaomi Redmi Note 12", "ocr_text": "",
            "width": 640, "height": 480,
        }]

        result = await store_intelligence(
            source_type="TELEGRAM", source_url="https://t.me/s/x/9",
            raw_content=text, author="@actor", media_items=media,
        )
        analysis = result["analysis"]

        assert analysis["border_alert"] is True
        assert analysis["geo"]["district"] == "Attari"
        assert analysis["media"]["with_gps"] == 1
        assert analysis["media"]["devices"] == ["Xiaomi Redmi Note 12"]

    async def test_media_artifacts_are_linked_to_their_record(self, db):
        import hashlib
        from sqlalchemy import select
        from ai.geo_resolver import resolve_coordinates
        from ai.enrichment import store_intelligence
        from database.postgres import MediaArtifact

        geo = resolve_coordinates(31.6026, 74.6033)
        result = await store_intelligence(
            source_type="TELEGRAM", source_url="https://t.me/s/x/10",
            raw_content=DEALER_OFFER, author="@actor",
            media_items=[{
                "url": "https://t.me/s/x/q.jpg", "media_type": "IMAGE",
                "mime_type": "image/jpeg", "sha256": hashlib.sha256(b"q").hexdigest(),
                "path": None, "size": 2048, "gps": {"lat": 31.6026, "lon": 74.6033},
                "geo": geo, "in_border_corridor": True, "has_exif": True,
                "device_signature": "Xiaomi Redmi Note 12", "ocr_text": "",
                "width": 800, "height": 600,
            }],
        )

        artifact = (await db.execute(
            select(MediaArtifact).where(
                MediaArtifact.scraped_data_id == result["record_id"])
        )).scalars().first()

        assert artifact is not None
        assert artifact.in_border_corridor is True
        assert artifact.gps_lat == pytest.approx(31.6026)
        assert len(artifact.sha256_hash) == 64
