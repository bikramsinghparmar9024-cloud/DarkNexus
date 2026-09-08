"""
Readable Content Extraction.

Scraped pages were being stored with the whole site around them. A Wikipedia
article arrived as:

    "Jump to content Main menu Main menu move to sidebar hide Navigation
     Main page Contents Current events Random article About Wikipedia..."

before a single word of the article. That has three costs. It pads the
evidence store with menus; it pollutes the vector index, so semantic search
matches on navigation furniture shared by every page from a site; and it feeds
the threat scorer text the page author never wrote.

This module keeps the part a reader would call the content. It is deliberately
conservative: when it cannot identify a main region it falls back to the whole
body, because losing evidence is worse than keeping some chrome.
"""

from typing import Any, Dict, Optional
import logging
import re

from bs4 import BeautifulSoup

logger = logging.getLogger("content_extraction")

# Structural elements that are never article content.
_STRUCTURAL_NOISE = [
    "script", "style", "noscript", "svg", "iframe", "form", "button",
    "input", "select", "textarea", "nav", "header", "footer", "aside",
    "menu", "dialog", "template",
]

# Class/id fragments that mark furniture on most sites. Matched as substrings
# against the element's class and id.
_NOISE_PATTERNS = [
    "nav", "menu", "sidebar", "side-bar", "footer", "header", "masthead",
    "breadcrumb", "cookie", "consent", "banner", "advert", "advertis",
    "promo", "newsletter", "subscribe", "social", "share", "toolbar",
    "pagination", "skip-link", "screen-reader", "visually-hidden",
    "related-posts", "comment-form", "site-info", "widget-area",
]

# Containers that usually hold the real content, in order of preference.
_CONTENT_SELECTORS = [
    "main",
    "article",
    '[role="main"]',
    "#mw-content-text",       # MediaWiki
    ".post-content",
    ".entry-content",
    "#content",
    ".content",
]

_WHITESPACE = re.compile(r"[ \t\xa0]+")
_BLANK_LINES = re.compile(r"\n{3,}")


# Elements that must never be removed no matter what they are named. Wikipedia
# puts "vector-feature-main-menu-pinned" on <html> itself, which matched the
# "menu" pattern and removed the entire document.
_NEVER_REMOVE = {"html", "body", "[document]"}

# An element holding this much of the page cannot be furniture, whatever its
# class says. Named wrappers routinely enclose the content they are named for.
_MAX_NOISE_TEXT_SHARE = 0.4


def _is_noise(tag, total_text_len: int = 0) -> bool:
    """True when an element's class or id marks it as site furniture."""
    # Removing a parent decomposes its children, so a tag captured earlier in
    # the sweep may already be gone by the time it is examined.
    if tag is None or getattr(tag, "attrs", None) is None:
        return False
    if tag.name in _NEVER_REMOVE:
        return False

    identifiers = " ".join(filter(None, [
        " ".join(tag.get("class") or []),
        tag.get("id") or "",
    ])).lower()
    if not identifiers:
        return False
    if not any(pattern in identifiers for pattern in _NOISE_PATTERNS):
        return False

    # A "nav"-classed wrapper containing most of the page is a layout
    # container, not navigation. Removing it would take the article too.
    if total_text_len:
        share = len(tag.get_text(strip=True)) / total_text_len
        if share > _MAX_NOISE_TEXT_SHARE:
            return False

    return True


def _clean_text(text: str) -> str:
    text = _WHITESPACE.sub(" ", text)
    lines = [line.strip() for line in text.split("\n")]
    text = "\n".join(line for line in lines if line)
    return _BLANK_LINES.sub("\n\n", text).strip()


# Share of unreadable characters above which a response is treated as a
# decode failure rather than as text.
MAX_UNDECODABLE_RATIO = 0.05


def undecodable_ratio(text: str) -> float:
    """Proportion of characters that no readable document would contain."""
    if not text:
        return 0.0
    bad = sum(1 for c in text
              if c == "�" or (ord(c) < 32 and c not in "\n\r\t"))
    return bad / len(text)


def is_decoded_text(text: str) -> bool:
    """
    Whether this looks like text at all.

    A page served in an encoding the client did not negotiate arrives as
    binary. Stored as evidence it is worse than useless: one such record put
    360 KB of compressed bytes into the corpus, and the identifier patterns
    duly mined it for a dozen UPI IDs and six Telegram handles that never
    existed. Everything downstream - embeddings, entities, actor dossiers -
    then treated that noise as intelligence.
    """
    return undecodable_ratio(text) <= MAX_UNDECODABLE_RATIO


def extract_readable_text(html: str, url: Optional[str] = None) -> Dict[str, Any]:
    """
    Pull the readable content out of a page.

    Returns the title, the cleaned text, and how much was removed - the last
    so an operator can tell aggressive stripping from an empty page.
    """
    if not html:
        return {"title": "", "text": "", "strategy": "empty",
                "original_chars": 0, "extracted_chars": 0, "removed_chars": 0}

    if not is_decoded_text(html):
        ratio = undecodable_ratio(html)
        logger.warning("Content for %s is %.0f%% undecodable; refusing to "
                       "treat it as text", url or "<unknown>", ratio * 100)
        return {"title": "", "text": "", "strategy": "undecodable",
                "original_chars": len(html), "extracted_chars": 0,
                "removed_chars": len(html),
                "undecodable_ratio": round(ratio, 4)}

    soup = BeautifulSoup(html, "html.parser")

    title = ""
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    full_text_len = len(_clean_text(soup.get_text(separator=" ", strip=True)))

    for tag in soup(_STRUCTURAL_NOISE):
        tag.decompose()

    # Snapshot the tree first: decomposing during iteration invalidates the
    # generator and leaves detached tags behind.
    raw_text_len = len(soup.get_text(strip=True))
    for tag in list(soup.find_all(True)):
        if _is_noise(tag, raw_text_len):
            tag.decompose()

    container = None
    strategy = "body"
    for selector in _CONTENT_SELECTORS:
        try:
            found = soup.select_one(selector)
        except Exception:
            continue
        if found and len(found.get_text(strip=True)) > 200:
            container, strategy = found, selector
            break

    if container is None:
        container = soup.body or soup

    text = _clean_text(container.get_text(separator="\n", strip=True))

    # A selector that returned almost nothing has misfired; the whole body is
    # a safer answer than a near-empty record.
    if len(text) < 100 and full_text_len > 400:
        text = _clean_text((soup.body or soup).get_text(separator="\n", strip=True))
        strategy = "body (fallback)"

    return {
        "title": title,
        "text": text,
        "strategy": strategy,
        "original_chars": full_text_len,
        "extracted_chars": len(text),
        "removed_chars": max(0, full_text_len - len(text)),
    }
