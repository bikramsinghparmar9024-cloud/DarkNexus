"""
Tests for stored-content quality.

Two problems, both of which quietly degraded everything downstream. Scraped
pages were stored with the whole site around them - menus, footers, cookie
banners - which padded the evidence store, polluted the vector index with
furniture common to every page on a site, and fed the threat scorer text the
page author never wrote. And Telegram posts were all filed as undated.
"""

import pytest


WIKI_LIKE = """
<html class="client-nojs vector-feature-main-menu-pinned-clientpref-1">
<head><title>Darknet market - Wikipedia</title></head>
<body>
  <div id="mw-navigation"><nav><a>Jump to content</a><a>Main menu</a>
    <a>Main page</a><a>Random article</a><a>About Wikipedia</a></nav></div>
  <div class="vector-header-container"><span>Search</span></div>
  <main id="content">
    <div id="mw-content-text">
      <p>A darknet market is a commercial website on the dark web that operates
         via darknets such as Tor. They function primarily as black markets,
         selling or brokering transactions involving drugs and other illicit goods.</p>
    </div>
  </main>
  <footer class="footer"><span>Privacy policy</span><span>Cookie statement</span></footer>
</body></html>
"""


class TestReadableExtraction:

    def test_navigation_is_removed(self):
        from scrapers.content_extraction import extract_readable_text
        result = extract_readable_text(WIKI_LIKE, "https://example.org/x")

        assert "Jump to content" not in result["text"]
        assert "Random article" not in result["text"]
        assert "Cookie statement" not in result["text"]

    def test_article_text_survives(self):
        from scrapers.content_extraction import extract_readable_text
        result = extract_readable_text(WIKI_LIKE, "https://example.org/x")

        assert "darknet market is a commercial website" in result["text"]
        assert result["title"] == "Darknet market - Wikipedia"
        assert result["removed_chars"] > 0

    def test_a_wrapper_class_cannot_delete_the_page(self):
        """
        Regression: Wikipedia puts 'vector-feature-main-menu-pinned' on <html>
        itself. Matching 'menu' there removed the entire document and stored an
        empty record.
        """
        from scrapers.content_extraction import extract_readable_text
        result = extract_readable_text(WIKI_LIKE, "https://example.org/x")
        assert result["extracted_chars"] > 100

    def test_large_containers_are_never_treated_as_furniture(self):
        from scrapers.content_extraction import extract_readable_text

        html = ("<html><body><div class='content-nav-wrapper'><p>"
                + ("Substantive article text about narcotics trafficking. " * 60)
                + "</p></div></body></html>")
        result = extract_readable_text(html, "https://example.org/y")
        assert "Substantive article text" in result["text"]

    def test_empty_input_is_safe(self):
        from scrapers.content_extraction import extract_readable_text
        result = extract_readable_text("", None)
        assert result["text"] == ""
        assert result["strategy"] == "empty"

    def test_plain_page_is_left_alone(self):
        from scrapers.content_extraction import extract_readable_text
        html = "<html><body><p>chitta available, contact me</p></body></html>"
        assert "chitta available" in extract_readable_text(html, None)["text"]


TELEGRAM_LIKE = """
<div class="tgme_widget_message" data-post="somechannel/441">
  <a class="tgme_widget_message_date" href="https://t.me/somechannel/441">
    <time datetime="2026-05-14T16:08:31+00:00" class="time">16:08</time>
  </a>
  <div class="tgme_widget_message_text">Chitta ready aa, barcode bhejo</div>
</div>
<div class="tgme_widget_message" data-post="somechannel/442">
  <time class="message_video_duration js-message_video_duration">0:06</time>
  <a class="tgme_widget_message_date" href="https://t.me/somechannel/442">
    <time datetime="2026-05-15T09:30:00+00:00" class="time">09:30</time>
  </a>
  <div class="tgme_widget_message_text">Second post with video attached</div>
  <video src="https://cdn.telesco.pe/file/x.mp4"></video>
</div>
"""


class TestTelegramParsing:

    def _parse(self, html):
        """Mirror the scraper's per-message parsing."""
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        out = []
        for msg in soup.find_all("div", class_="tgme_widget_message"):
            text_div = msg.find("div", class_="tgme_widget_message_text")
            if not text_div:
                continue
            date_link = msg.find("a", class_="tgme_widget_message_date")
            time_el = date_link.find("time") if date_link else None
            if time_el is None:
                time_el = msg.find("time", attrs={"datetime": True})
            out.append({
                "text": text_div.get_text(strip=True),
                "date": time_el["datetime"] if time_el and time_el.has_attr("datetime") else None,
                "permalink": f"https://t.me/{msg.get('data-post')}" if msg.get("data-post") else None,
            })
        return out

    def test_video_duration_is_not_mistaken_for_a_timestamp(self):
        """
        The bug: find('time') returned the video duration element ('0:06'),
        which has no datetime attribute, so every post was filed as undated.
        """
        messages = self._parse(TELEGRAM_LIKE)
        assert len(messages) == 2
        assert all(m["date"] is not None for m in messages)
        assert messages[1]["date"] == "2026-05-15T09:30:00+00:00"

    def test_per_message_permalinks_are_captured(self):
        """
        Provenance: a record should cite the exact post, not just the channel.
        """
        messages = self._parse(TELEGRAM_LIKE)
        assert messages[0]["permalink"] == "https://t.me/somechannel/441"
        assert messages[1]["permalink"] == "https://t.me/somechannel/442"


class TestModuleNaming:

    def test_batch_analysis_is_importable_under_its_real_name(self):
        from ai.batch_analysis import batch_analyzer, BatchAnalyzer
        assert isinstance(batch_analyzer, BatchAnalyzer)

    def test_old_import_path_still_resolves(self):
        """Renaming must not break callers that have not been updated."""
        from ai.langgraph_workflow import langgraph_pipeline
        from ai.batch_analysis import batch_analyzer
        assert langgraph_pipeline is batch_analyzer

    def test_langgraph_is_still_not_a_dependency(self):
        """The name claimed a framework the code never used."""
        import ai.batch_analysis as module
        source = open(module.__file__, encoding="utf-8").read()
        assert "import langgraph" not in source
