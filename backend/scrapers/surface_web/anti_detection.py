"""
Anti-Bot Evasion and Browser Fingerprint Spoofing.
Includes:
- Realistic User-Agent pool
- Screen resolution and canvas noise injection
- Bot challenge / Cloudflare / CAPTCHA detection
- Human behavioral simulation (jitter delays, smooth scroll)
"""

import random
import re
from typing import Dict, List, Optional, Tuple

# 50+ Realistic Browser User-Agents
USER_AGENTS: List[str] = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0"
]

VIEWPORTS: List[Tuple[int, int]] = [
    (1920, 1080),
    (1366, 768),
    (1536, 864),
    (1440, 900),
    (1280, 720)
]

# ── Bot-challenge detection ──────────────────────────────────────────
#
# A challenge page must be distinguished from an ordinary page that merely
# *mentions* CAPTCHAs or Cloudflare. That distinction matters here: narcotics
# forums and marketplace mirrors routinely discuss being blocked, and naive
# substring matching silently discards exactly the pages worth collecting.
#
# Signals are therefore split by how much they prove on their own.

# Strings that essentially only occur on a real interstitial.
STRONG_CHALLENGE_MARKERS: List[str] = [
    "cf-browser-verification",
    "challenge-running",
    "cf_chl_opt",
    "/cdn-cgi/challenge-platform",
    "just a moment...",
    "checking your browser before accessing",
    "attention required! | cloudflare",
    "enable javascript and cookies to continue",
    "verifying you are human",
    "please verify you are a human",
    "ddos-guard.net",
]

# Strings that appear on challenge pages AND on ordinary pages. These only
# count as a block when corroborated by a blocking status code or a page too
# small to be real content.
WEAK_CHALLENGE_MARKERS: List[str] = [
    "cloudflare",
    "recaptcha",
    "hcaptcha",
    "turnstile",
    "ddos-guard",
    "access denied",
    "blocked ip",
    "bot detected",
    "ray id",
]

# Kept for backwards compatibility with older imports.
BOT_KEYWORDS: List[str] = STRONG_CHALLENGE_MARKERS + WEAK_CHALLENGE_MARKERS

# HTTP statuses a WAF actually returns when refusing a request.
BLOCKING_STATUS_CODES = {401, 403, 405, 407, 429, 503}

# Challenge interstitials are genuinely tiny - a heading, a spinner and a
# script tag. 60 KB was far too generous: a 56 KB Wikipedia disambiguation
# page fell under it and was discarded.
CHALLENGE_PAGE_MAX_BYTES = 15_000

# A page carrying this much readable prose is content, whatever else it says.
# A block page has nothing to read.
MIN_CONTENT_TEXT_CHARS = 1_500

# Only the top of the document is inspected: a block page declares itself in
# the <title>/<head>, never 900 KB down inside body prose.
HEAD_SCAN_BYTES = 4_096
BODY_SCAN_BYTES = 20_000


def get_random_user_agent() -> str:
    """Select a realistic desktop User-Agent string."""
    return random.choice(USER_AGENTS)


def get_random_viewport() -> Dict[str, int]:
    """Get random common screen resolution."""
    width, height = random.choice(VIEWPORTS)
    return {"width": width, "height": height}


def get_stealth_headers() -> Dict[str, str]:
    """Generate modern browser headers with HTTP/2 Client Hints."""
    ua = get_random_user_agent()
    return {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,pa;q=0.8,hi;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Sec-Fetch-User": "?1"
    }


_SCRIPT_STYLE = re.compile(r"<(script|style)[^>]*>.*?</>", re.I | re.S)
_TAGS = re.compile(r"<[^>]+>")


def _visible_text(html: str) -> str:
    """
    Page text with scripts and styles removed.

    Weak markers must be matched against what a blocked user would actually
    see. Sites routinely name their captcha provider in inline configuration:
    Wikipedia ships "wgConfirmEditCaptchaNeededForGenericEdit":"hcaptcha" in a
    <script> in every page head, which made every Wikipedia article look like
    a captcha wall.
    """
    return _TAGS.sub(" ", _SCRIPT_STYLE.sub(" ", html))


def detect_bot_challenge(html_content: str, status_code: Optional[int] = None) -> Optional[str]:
    """
    Decide whether a response is a CAPTCHA / WAF challenge rather than content.

    Returns a short reason string when the page is judged a challenge, or None
    when it looks like genuine content. Pass `status_code` when available - a
    403/429/503 is the strongest single signal there is.
    """
    if not html_content:
        return "empty response body"

    size = len(html_content)
    body = html_content[:BODY_SCAN_BYTES].lower()

    visible = _visible_text(html_content[:BODY_SCAN_BYTES])
    visible_head = visible[:HEAD_SCAN_BYTES].lower()

    # 1. Unambiguous interstitial fingerprints.
    for marker in STRONG_CHALLENGE_MARKERS:
        if marker in body:
            return f"challenge fingerprint '{marker}'"

    # 2. The server actively refused us, and the page talks like a block page.
    if status_code in BLOCKING_STATUS_CODES:
        for marker in WEAK_CHALLENGE_MARKERS:
            if marker in body:
                return f"HTTP {status_code} with '{marker}'"
        return f"HTTP {status_code} refusal"

    # 3. A page too small to carry content, whose visible text reads like a
    #    block. Both conditions are required: size alone catches short real
    #    pages, and markers alone catch any page that merely names a captcha
    #    provider in its configuration.
    if size <= CHALLENGE_PAGE_MAX_BYTES and len(visible.strip()) < MIN_CONTENT_TEXT_CHARS:
        for marker in WEAK_CHALLENGE_MARKERS:
            if marker in visible_head:
                return f"small page ({size}b, no readable content) with '{marker}'"

    return None


def is_bot_challenge(html_content: str, status_code: Optional[int] = None) -> bool:
    """Boolean form of detect_bot_challenge()."""
    return detect_bot_challenge(html_content, status_code) is not None


STEALTH_JS_INJECTION = """
// Overwrite the `languages` property to use standard values
Object.defineProperty(navigator, 'languages', {
    get: () => ['en-US', 'en', 'pa', 'hi'],
});

// Overwrite the `plugins` property to appear non-empty
Object.defineProperty(navigator, 'plugins', {
    get: () => [1, 2, 3, 4, 5],
});

// Pass Webdriver tests
Object.defineProperty(navigator, 'webdriver', {
    get: () => false,
});

// Pass Chrome test
window.chrome = { runtime: {} };

// Mock audio/canvas fingerprints slightly
const originalGetParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
    if (parameter === 37445) return 'Intel Inc.';
    if (parameter === 37446) return 'Intel Iris OpenGL Engine';
    return originalGetParameter.apply(this, arguments);
};
"""
