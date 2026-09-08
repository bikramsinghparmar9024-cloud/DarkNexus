"""
Tests for collection-side behaviour: bot-challenge detection, media URL
discovery, and forensic metadata extraction.

The bot-challenge tests matter disproportionately. The original detector
searched the whole page for words like "hcaptcha", so a 1.5 MB Wikipedia
article that merely mentioned CAPTCHAs was discarded as a block page. For a
system whose targets are forums discussing how to evade blocks, that threw
away exactly the pages worth keeping.
"""

import pytest


# ── Bot-challenge detection ──────────────────────────────────────────

CF_JS_CHALLENGE = """<!DOCTYPE html><html><head><title>Just a moment...</title></head>
<body><div id="cf-wrapper"><h1>Checking your browser before accessing example.com</h1>
<script src="/cdn-cgi/challenge-platform/h/b/orchestrate/jsch/v1"></script></div></body></html>"""

CF_ACCESS_DENIED = """<!DOCTYPE html><html><head><title>Attention Required! | Cloudflare</title>
</head><body><h1>Access denied</h1><p>Ray ID: 8b2f4a</p></body></html>"""

RECAPTCHA_WALL = """<html><head><title>Verify</title></head><body>
<div class="g-recaptcha" data-sitekey="x"></div><p>Please verify you are a human</p></body></html>"""

PLAIN_403 = """<html><head><title>403 Forbidden</title></head><body><h1>Forbidden</h1>
<p>You do not have permission to access this resource.</p></body></html>"""

# A long article that mentions every blocking keyword without being a block.
ARTICLE_MENTIONING_BLOCKS = (
    "<html><head><title>Darknet market operations</title></head><body>"
    "<p>Vendors complain that Cloudflare and hCaptcha make mirrors unreachable. "
    "Some report access denied errors and a bot detected message.</p>"
    + ("<p>" + "Filler prose about narcotics trafficking routes. " * 40 + "</p>") * 60
    + "</body></html>"
)


class TestBotChallengeDetection:

    @pytest.mark.parametrize("html,status", [
        (CF_JS_CHALLENGE, 503),
        (CF_ACCESS_DENIED, 403),
        (RECAPTCHA_WALL, 200),
        (PLAIN_403, 403),
    ])
    def test_real_challenges_are_caught(self, html, status):
        from scrapers.surface_web.anti_detection import detect_bot_challenge
        assert detect_bot_challenge(html, status) is not None

    def test_article_mentioning_captchas_is_kept(self):
        """Regression: this exact case discarded live Wikipedia articles."""
        from scrapers.surface_web.anti_detection import detect_bot_challenge
        assert detect_bot_challenge(ARTICLE_MENTIONING_BLOCKS, 200) is None

    def test_rejection_explains_itself(self):
        """'Blocked' with no reason is undebuggable in the field."""
        from scrapers.surface_web.anti_detection import detect_bot_challenge
        reason = detect_bot_challenge(CF_JS_CHALLENGE, 503)
        assert "challenge-platform" in reason

    def test_empty_response_is_treated_as_a_block(self):
        from scrapers.surface_web.anti_detection import detect_bot_challenge
        assert detect_bot_challenge("", 200) is not None


# ── Media URL discovery ──────────────────────────────────────────────

TELEGRAM_HTML = """
<div class="tgme_widget_message">
  <a class="tgme_widget_message_photo_wrap"
     style="width:800px;background-image:url('https://cdn1.telesco.pe/file/abc.jpg')"></a>
  <video src="https://cdn1.telesco.pe/file/clip.mp4"></video>
</div>
"""

PAGE_HTML = """
<html><body>
  <img src="/images/listing.jpg">
  <img src="/assets/logo.png">
  <img src="/icons/avatar.png">
  <a href="https://example.com/evidence/photo.jpeg">download</a>
</body></html>
"""


class TestMediaDiscovery:

    def test_finds_telegram_photos_and_video(self):
        """
        Telegram carries photos as a CSS background-image on a wrapper, not an
        <img> tag, so a naive image scrape finds nothing.
        """
        from media.extractor import extract_media_urls
        found = extract_media_urls(TELEGRAM_HTML, "https://t.me/s/channel")
        urls = {f["url"] for f in found}

        assert "https://cdn1.telesco.pe/file/abc.jpg" in urls
        assert "https://cdn1.telesco.pe/file/clip.mp4" in urls
        assert any(f["media_type"] == "VIDEO" for f in found)

    def test_resolves_relative_urls_and_skips_chrome(self):
        from media.extractor import extract_media_urls
        found = extract_media_urls(PAGE_HTML, "https://example.com/page")
        urls = {f["url"] for f in found}

        assert "https://example.com/images/listing.jpg" in urls
        assert "https://example.com/evidence/photo.jpeg" in urls
        assert not any("logo" in u or "avatar" in u for u in urls)

    def test_respects_the_limit(self):
        from media.extractor import extract_media_urls
        html = "".join(f'<img src="/p{i}.jpg">' for i in range(50))
        assert len(extract_media_urls(html, "https://example.com", limit=4)) == 4

    def test_empty_html_is_safe(self):
        from media.extractor import extract_media_urls
        assert extract_media_urls("", "https://example.com") == []


# ── Forensic metadata ────────────────────────────────────────────────

class TestImageForensics:

    def test_extracts_gps_camera_and_capture_time(self, gps_photo):
        from media.metadata import extract_image_metadata
        meta = extract_image_metadata(gps_photo)

        assert meta["has_exif"] is True
        assert meta["exif"]["Make"] == "Xiaomi"
        assert meta["exif"]["Model"] == "Redmi Note 12"
        assert meta["exif"]["DateTimeOriginal"] == "2026:09:02 23:14:07"
        assert meta["gps"]["lat"] == pytest.approx(31.6026, abs=1e-3)
        assert meta["gps"]["lon"] == pytest.approx(74.6033, abs=1e-3)

    def test_gps_resolves_to_the_border_corridor(self, gps_photo):
        """The point of extracting GPS: turning a photo into a map reference."""
        from media.metadata import extract_image_metadata
        from ai.geo_resolver import resolve_coordinates

        gps = extract_image_metadata(gps_photo)["gps"]
        geo = resolve_coordinates(gps["lat"], gps["lon"])

        assert geo["nearest_known_location"] == "Attari"
        assert geo["in_critical_border_corridor"] is True
        assert geo["distance_to_border_km"] <= 15

    def test_image_without_exif_is_handled(self, tmp_root):
        from PIL import Image
        from media.metadata import extract_image_metadata

        path = tmp_root / "plain.png"
        Image.new("RGB", (10, 10)).save(str(path))
        meta = extract_image_metadata(str(path))

        assert meta["has_exif"] is False
        assert meta["gps"] is None
        assert meta["width"] == 10

    def test_unreadable_file_reports_an_error_rather_than_raising(self, tmp_root):
        from media.metadata import extract_image_metadata

        path = tmp_root / "corrupt.jpg"
        path.write_bytes(b"this is not an image")
        assert "error" in extract_image_metadata(str(path))

    def test_media_summary_counts_what_matters(self, gps_photo):
        from media.pipeline import summarize_media, media_text_blob
        from media.metadata import extract_image_metadata
        from ai.geo_resolver import resolve_coordinates

        meta = extract_image_metadata(gps_photo)
        geo = resolve_coordinates(meta["gps"]["lat"], meta["gps"]["lon"])
        item = {
            "media_type": "IMAGE", "gps": meta["gps"], "geo": geo,
            "has_exif": True, "in_border_corridor": True,
            "device_signature": "Xiaomi Redmi Note 12", "ocr_text": "",
            "url": "https://example.com/p.jpg",
        }

        summary = summarize_media([item])
        assert summary["with_gps"] == 1
        assert summary["in_border_corridor"] == 1
        assert summary["devices"] == ["Xiaomi Redmi Note 12"]

        # The location must reach the text analyser so it can influence scoring.
        assert "Attari" in media_text_blob([item])


class TestCaptchaProviderNamesAreNotBlocks:
    """
    Regression for a live false positive.

    Wikipedia ships "wgConfirmEditCaptchaNeededForGenericEdit":"hcaptcha" in an
    inline <script> in every page head - the name of the provider used on its
    *edit* form. A 56 KB disambiguation page carrying that string was discarded
    as a captcha wall, and the source it came from was recorded as failing.
    """

    WIKI_LIKE = (
        '<html><head><title>Drug dealer - Wikipedia</title>'
        '<script>RLCONF={"wgConfirmEditCaptchaNeededForGenericEdit":"hcaptcha",'
        '"wgConfirmEditHCaptchaSiteKey":"abc"};</script></head><body>'
        '<div id="mw-content-text"><p>'
        + ('A drug dealer sells illicit substances. ' * 120)
        + '</p></div></body></html>'
    )

    def test_captcha_named_in_page_script_is_not_a_block(self):
        from scrapers.surface_web.anti_detection import detect_bot_challenge
        assert detect_bot_challenge(self.WIKI_LIKE, 200) is None

    def test_short_page_with_real_content_is_not_a_block(self):
        """Size alone must not condemn a page; some real pages are short."""
        from scrapers.surface_web.anti_detection import detect_bot_challenge
        html = ('<html><head><title>Notice</title></head><body><p>'
                + ('Genuine short article about narcotics enforcement. ' * 40)
                + ' recaptcha is mentioned here.</p></body></html>')
        assert len(html) < 15_000
        assert detect_bot_challenge(html, 200) is None

    def test_bare_captcha_page_is_still_caught(self):
        """The narrowing must not let an actual wall through."""
        from scrapers.surface_web.anti_detection import detect_bot_challenge
        html = ('<html><head><title>Security check</title></head><body>'
                '<h2>hCaptcha</h2><p>Complete the challenge to continue.</p>'
                '</body></html>')
        assert detect_bot_challenge(html, 200) is not None
