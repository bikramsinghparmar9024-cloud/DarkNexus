"""
Telegram channel collection.

The scraper stored an entire channel as one record: twenty messages
concatenated, authored by the channel, sourced to the channel page. Three
consequences, all of which defeat the analysis built on top of it.

A wallet posted by one member was attributed to the channel rather than to
whoever posted it, so no per-sender profile could be built and the graph drew
one node for a whole conversation. An entity found in the twelfth message
cited the channel page instead of the post it came from. And because the page
changes whenever anyone posts, every revisit stored a fresh copy of the
nineteen messages already held.

Parsing is tested against fixture HTML, so the suite never depends on a live
channel and a network failure cannot read as a code failure.
"""

import pytest

PREVIEW_HTML = """
<html><body>
  <div class="tgme_widget_message" data-post="punjabtest/101">
    <a class="tgme_widget_message_date" href="https://t.me/punjabtest/101">
      <time datetime="2026-09-01T10:00:00+00:00">Sep 1</time></a>
    <span class="tgme_widget_message_from_author">Jagga Drops</span>
    <div class="tgme_widget_message_text">
      Chitta available 50g. Escrow to bc1qxy2kgdygjrsqtzq2n0yrf2493p83kkfjhx0wlh
    </div>
    <span class="tgme_widget_message_views">1.2K</span>
  </div>
  <div class="tgme_widget_message" data-post="punjabtest/102">
    <a class="tgme_widget_message_date" href="https://t.me/punjabtest/102">
      <time datetime="2026-09-02T11:30:00+00:00">Sep 2</time></a>
    <span class="tgme_widget_message_from_author">Gopi Border</span>
    <div class="tgme_widget_message_text">
      Looking for bhukki near Majitha. Call 9814098211
    </div>
    <span class="tgme_widget_message_views">840</span>
  </div>
</body></html>
"""

# The same page a moment later: identical posts, higher view counts. This is
# what made hashing the rendered markup useless for deduplication.
PREVIEW_HTML_LATER = PREVIEW_HTML.replace("1.2K", "1.4K").replace("840", "902")


class _Response:
    status_code = 200

    def __init__(self, text):
        self.text = text


def _fake_client(pages):
    """An httpx.AsyncClient stand-in serving the given pages in order."""
    calls = {"n": 0}

    class Client:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url, **kw):
            page = pages[min(calls["n"], len(pages) - 1)]
            calls["n"] += 1
            return _Response(page)

    return Client


@pytest.fixture
def scraper(monkeypatch):
    import httpx
    from scrapers.encrypted.telegram_scraper import TelegramScraper

    monkeypatch.setattr(httpx, "AsyncClient", _fake_client([PREVIEW_HTML]))
    return TelegramScraper()


class TestOneRecordPerMessage:

    async def test_each_message_becomes_its_own_record(self, db, scraper):
        from sqlalchemy import select
        from database.postgres import ScrapedData

        result = await scraper.scrape("punjabtest")

        assert result["status"] == "SAVED"
        assert result["messages_found"] == 2
        assert result["stored"] == 2

        records = (await db.execute(select(ScrapedData))).scalars().all()
        assert len(records) == 2, "a channel is not one record"

    async def test_each_record_cites_its_own_post(self, db, scraper):
        """
        An entity found in one message must cite that post, not the channel
        page - otherwise the content and the source URL disagree.
        """
        from sqlalchemy import select
        from database.postgres import ScrapedData

        await scraper.scrape("punjabtest")
        urls = {r.source_url for r in
                (await db.execute(select(ScrapedData))).scalars().all()}

        assert urls == {"https://t.me/punjabtest/101",
                        "https://t.me/punjabtest/102"}

    async def test_the_sender_is_the_author_not_the_channel(self, db, scraper):
        """
        Attributing every post to the channel made per-sender profiling
        impossible: one wallet, one phone, all credited to @punjabtest.
        """
        from sqlalchemy import select
        from database.postgres import ScrapedData

        await scraper.scrape("punjabtest")
        authors = {r.author_or_handle for r in
                   (await db.execute(select(ScrapedData))).scalars().all()}

        assert authors == {"Jagga Drops", "Gopi Border"}

    async def test_message_text_is_stored_not_a_concatenated_blob(self, db, scraper):
        from sqlalchemy import select
        from database.postgres import ScrapedData

        await scraper.scrape("punjabtest")
        records = (await db.execute(
            select(ScrapedData).order_by(ScrapedData.source_url))).scalars().all()

        assert "Chitta available" in records[0].cleaned_text
        assert "bhukki" not in records[0].cleaned_text.lower(), (
            "messages must not be merged into one record")


class TestDeduplicationAcrossVisits:

    async def test_revisiting_stores_nothing_new(self, db, monkeypatch):
        import httpx
        from scrapers.encrypted.telegram_scraper import TelegramScraper
        from sqlalchemy import select
        from database.postgres import ScrapedData

        monkeypatch.setattr(httpx, "AsyncClient",
                            _fake_client([PREVIEW_HTML, PREVIEW_HTML_LATER]))
        scraper = TelegramScraper()

        first = await scraper.scrape("punjabtest")
        second = await scraper.scrape("punjabtest")

        assert first["stored"] == 2
        assert second["stored"] == 0
        assert second["duplicates"] == 2
        assert second["status"] == "DUPLICATE", (
            "a revisit finding only known posts is a check, not a collection")

        records = (await db.execute(select(ScrapedData))).scalars().all()
        assert len(records) == 2

    async def test_a_rising_view_count_is_not_new_evidence(self, db, monkeypatch):
        """
        The regression that made deduplication impossible: the preview markup
        carries a view counter, so hashing the rendered page produced a fresh
        digest on every visit and the same posts were stored again each time.
        """
        import httpx
        from scrapers.encrypted.telegram_scraper import TelegramScraper
        from sqlalchemy import select
        from database.postgres import ScrapedData

        monkeypatch.setattr(httpx, "AsyncClient",
                            _fake_client([PREVIEW_HTML, PREVIEW_HTML_LATER]))
        scraper = TelegramScraper()
        await scraper.scrape("punjabtest")
        hashes_before = {r.sha256_hash for r in
                         (await db.execute(select(ScrapedData))).scalars().all()}

        await scraper.scrape("punjabtest")
        hashes_after = {r.sha256_hash for r in
                        (await db.execute(select(ScrapedData))).scalars().all()}

        assert hashes_before == hashes_after


class TestGraphOutput:

    async def test_each_message_becomes_a_graph_node(self, db, scraper):
        from sqlalchemy import select
        from database.postgres import GraphNode

        await scraper.scrape("punjabtest")
        nodes = (await db.execute(select(GraphNode))).scalars().all()
        by_type = {}
        for n in nodes:
            by_type.setdefault(n.node_type, []).append(n.node_key)

        assert len(by_type.get("channel", [])) == 2, "one node per message"
        assert len(by_type.get("suspect", [])) == 2, "one node per sender"

    async def test_a_posted_wallet_attaches_to_its_sender(self, db, scraper):
        """The whole point: the wallet belongs to whoever posted it."""
        from sqlalchemy import select
        from database.postgres import GraphEdge
        from core.identity import slugify_entity_key

        await scraper.scrape("punjabtest")
        edges = (await db.execute(
            select(GraphEdge).where(GraphEdge.relation == "USES_CRYPTO")
        )).scalars().all()

        assert edges, "a wallet in a message must produce an edge"
        assert edges[0].source_key == slugify_entity_key("Jagga Drops", "suspect")


class TestFailureReporting:

    async def test_an_empty_channel_is_a_failure_not_a_silent_success(self, db, monkeypatch):
        import httpx
        from scrapers.encrypted.telegram_scraper import TelegramScraper

        monkeypatch.setattr(httpx, "AsyncClient",
                            _fake_client(["<html><body></body></html>"]))
        result = await TelegramScraper().scrape("emptychannel")

        assert result["status"] == "FAILED"
        assert result["messages_found"] == 0
        assert result["error"]

    async def test_the_job_counter_reports_messages_not_one(self):
        """
        A channel visit collecting twenty messages was logged as one item,
        because the count was hardcoded rather than read from the scraper.
        """
        from routes.scraper_routes import _interpret_result

        status, items, _ = _interpret_result(
            {"status": "SAVED", "stored": 20, "messages_found": 20}, "scrape")
        assert (status, items) == ("COMPLETED", 20)

    async def test_a_duplicate_visit_counts_as_zero_collected(self):
        from routes.scraper_routes import _interpret_result

        status, items, _ = _interpret_result(
            {"status": "DUPLICATE", "stored": 0, "duplicates": 20}, "scrape")
        assert (status, items) == ("COMPLETED", 0)
