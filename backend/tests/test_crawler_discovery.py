"""
Link-following discovery must actually follow links.

Both crawlers read the page source from `result["raw_content"]` - a key that
store_intelligence() has never returned. The dark web crawler therefore
returned an empty list on every run it had ever made, and the surface crawler
skipped every page it collected. Crawl mode reported success while discovering
nothing, on both pipelines.
"""

import pytest


class TestStoredContentIsReadable:

    async def test_stored_page_source_can_be_read_back(self, db):
        from ai.enrichment import store_intelligence, fetch_raw_content

        html = "<html><body><a href='http://x.example'>link</a></body></html>"
        saved = await store_intelligence(
            source_type="DARK_WEB", source_url="http://seed.onion",
            raw_content=html, session=db)

        assert await fetch_raw_content(saved["record_id"]) == html

    async def test_the_save_result_does_not_carry_the_page_source(self, db):
        """
        It deliberately does not - the same dict is serialised into API
        responses. That is why the content is read back by id instead.
        """
        from ai.enrichment import store_intelligence

        saved = await store_intelligence(
            source_type="DARK_WEB", source_url="http://seed.onion",
            raw_content="<html>x</html>", session=db)
        assert "raw_content" not in saved

    async def test_a_missing_record_returns_empty_not_an_error(self):
        from ai.enrichment import fetch_raw_content
        assert await fetch_raw_content(999999) == ""
        assert await fetch_raw_content(None) == ""


class TestDarkCrawlerFindsAddresses:

    async def test_onion_links_are_discovered_and_queued(self, db):
        from sqlalchemy import select
        from database.postgres import Target
        from scrapers.dark_web.crawler import DarkCrawler
        from ai.enrichment import store_intelligence

        found = "abcdefghijklmnopqrstuvwxyz234567abcdefghijklmnopqrstuvwx.onion"
        html = f"<html><body><a href='http://{found}'>market</a></body></html>"

        class FakeScraper:
            async def scrape(self, url):
                return await store_intelligence(
                    source_type="DARK_WEB", source_url=url, raw_content=html)

        discovered = await DarkCrawler(FakeScraper()).crawl("http://seed.onion")

        assert f"http://{found}" in discovered
        targets = (await db.execute(select(Target))).scalars().all()
        assert any(found in t.identifier for t in targets)

    async def test_a_failed_seed_yields_nothing(self, db):
        from scrapers.dark_web.crawler import DarkCrawler

        class FailingScraper:
            async def scrape(self, url):
                return {"status": "FAILED", "url": url, "error": "no tor"}

        assert await DarkCrawler(FailingScraper()).crawl("http://seed.onion") == []
