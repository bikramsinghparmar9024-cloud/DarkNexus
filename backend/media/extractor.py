"""
Media URL Discovery.

Finds the images and videos referenced by a page so the pipeline can fetch
them. Telegram's public web preview needs its own handling: photos are carried
as CSS background-image URLs on a wrapper element rather than <img> tags.
"""

from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse
import re
import logging

from bs4 import BeautifulSoup

logger = logging.getLogger("media_extractor")

IMAGE_EXTENSIONS = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".heic")
VIDEO_EXTENSIONS = (".mp4", ".mov", ".webm", ".mkv", ".avi", ".m4v")

# Telegram serves photos as background-image on the wrapper anchor.
_CSS_URL = re.compile(r"url\(['\"]?([^'\")]+)['\"]?\)")

# Layout chrome that is never intelligence.
_SKIP_PATTERNS = (
    "sprite", "icon", "logo", "avatar", "emoji", "placeholder",
    "1x1", "pixel", "spacer", "blank.", "loading",
)


def classify_media_url(url: str) -> Optional[str]:
    """Return IMAGE, VIDEO, or None based on the URL path extension."""
    path = urlparse(url).path.lower()
    if path.endswith(IMAGE_EXTENSIONS):
        return "IMAGE"
    if path.endswith(VIDEO_EXTENSIONS):
        return "VIDEO"
    return None


def _should_skip(url: str) -> bool:
    low = url.lower()
    return any(p in low for p in _SKIP_PATTERNS)


def extract_media_urls(html: str, base_url: str, limit: int = 8) -> List[Dict[str, str]]:
    """
    Collect candidate media URLs from a page.

    Returns a list of {url, media_type, context} dicts, de-duplicated and
    capped at `limit`. `context` records where the reference was found, which
    is useful when explaining provenance to an investigator.
    """
    if not html:
        return []

    found: List[Dict[str, str]] = []
    seen = set()

    def add(raw: Optional[str], context: str, forced_type: Optional[str] = None):
        if not raw or len(found) >= limit:
            return
        raw = raw.strip()
        if raw.startswith("data:") or not raw:
            return
        absolute = urljoin(base_url, raw)
        if not absolute.startswith(("http://", "https://")):
            return
        if absolute in seen or _should_skip(absolute):
            return
        media_type = forced_type or classify_media_url(absolute)
        if not media_type:
            return
        seen.add(absolute)
        found.append({"url": absolute, "media_type": media_type, "context": context})

    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception as e:
        logger.warning("Could not parse HTML for media: %s", e)
        return []

    # 1. Telegram web-preview photos (CSS background-image on the wrapper).
    for node in soup.find_all(class_="tgme_widget_message_photo_wrap"):
        for match in _CSS_URL.findall(node.get("style", "")):
            add(match, "telegram_photo", "IMAGE")

    # 2. Telegram video thumbnails, which also carry a background image.
    for node in soup.find_all(class_="tgme_widget_message_video_thumb"):
        for match in _CSS_URL.findall(node.get("style", "")):
            add(match, "telegram_video_thumb", "IMAGE")

    # 3. Video elements (Telegram and ordinary pages alike).
    for node in soup.find_all("video"):
        add(node.get("src"), "video_tag", "VIDEO")
        for source in node.find_all("source"):
            add(source.get("src"), "video_source", "VIDEO")

    # 4. Ordinary images. srcset entries are preferred where present because
    #    they point at the full-resolution original rather than a thumbnail.
    for node in soup.find_all("img"):
        srcset = node.get("srcset")
        if srcset:
            candidates = [c.strip().split(" ")[0] for c in srcset.split(",") if c.strip()]
            if candidates:
                add(candidates[-1], "img_srcset")
        add(node.get("src") or node.get("data-src"), "img_tag")

    # 5. Social preview images: often the only full-size asset on a page.
    for prop in ("og:image", "twitter:image"):
        for node in soup.find_all("meta", attrs={"property": prop}):
            add(node.get("content"), "meta_%s" % prop.replace(":", "_"))
        for node in soup.find_all("meta", attrs={"name": prop}):
            add(node.get("content"), "meta_%s" % prop.replace(":", "_"))

    # 6. Direct links to media files.
    for node in soup.find_all("a"):
        add(node.get("href"), "anchor_link")

    return found[:limit]
