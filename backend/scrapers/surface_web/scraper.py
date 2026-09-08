"""
Surface Web Scraper.

Fetches a page by whichever route actually returns readable content, and
refuses to file a record when none of them do.

Three things drove this design, all of them observed failures:

  * A site serving Brotli produced mojibake, because the stealth headers
    advertised "br" while the codec was not installed. Fixed by installing
    brotli/zstandard - the header must not claim more than the client can
    decode.

  * A JavaScript-only page (Reddit) produced a record containing a title and
    nothing else, and the source was marked as collecting successfully. An
    empty record is worse than a failure: it looks like evidence and hides
    that the source is unreachable.

  * Playwright was tried first and httpx only on *exception*, so a browser
    render that returned an empty shell was never retried over plain HTTP -
    even where plain HTTP would have worked.

Routes are therefore tried in order and judged on what they return, not on
whether they raised.
"""

from typing import Any, Dict, Optional, Tuple
import asyncio
import logging

from scrapers.base_scraper import BaseScraper
from scrapers.content_extraction import extract_readable_text
from scrapers.surface_web.anti_detection import (
    get_random_user_agent,
    get_random_viewport,
    get_stealth_headers,
    STEALTH_JS_INJECTION,
    detect_bot_challenge,
)
from proxy.pool import proxy_pool
from config import settings

logger = logging.getLogger("surface_scraper")

try:
    from playwright.async_api import async_playwright
except ImportError:
    async_playwright = None

try:
    import httpx
except ImportError:
    httpx = None

# Below this much readable text a page has not really been retrieved. A cookie
# wall, a JS shell or an error stub all clear a byte-count check but contain
# nothing to analyse.
MIN_USEFUL_TEXT_CHARS = 200


class FetchResult:
    """What one transport returned, before any decision is made about it."""

    __slots__ = ("route", "html", "status_code", "error", "text", "extracted",
                 "final_url")

    def __init__(self, route: str, html: str = "", status_code: Optional[int] = None,
                 error: Optional[str] = None, final_url: Optional[str] = None):
        self.route = route
        self.html = html or ""
        self.status_code = status_code
        self.error = error
        # Where the response actually came from, after redirects.
        self.final_url = final_url
        self.extracted = extract_readable_text(self.html) if self.html else None
        self.text = (self.extracted or {}).get("text", "")

    @property
    def usable(self) -> bool:
        return len(self.text.strip()) >= MIN_USEFUL_TEXT_CHARS

    def describe(self) -> str:
        if self.error:
            return f"{self.route}: {self.error}"
        return f"{self.route}: {len(self.text)} chars of readable text"


class SurfaceWebScraper(BaseScraper):
    """Scraper for clearnet forums, marketplaces and classifieds."""

    def __init__(self):
        super().__init__(name="SurfaceWebScraper", source_type="SURFACE_WEB")

    # ── Entry point ──────────────────────────────────────────────────

    async def scrape(self, target_url: str) -> Dict[str, Any]:
        await self.apply_jitter()
        proxy_url = await proxy_pool.get_next_proxy()

        attempts = []

        # Route 1: a real browser. Required for anything rendered client-side.
        if async_playwright is not None:
            result = await self._fetch_with_playwright(target_url, proxy_url)
            attempts.append(result)
            blocked = self._as_block(result, target_url, proxy_url)
            if blocked:
                return blocked
            if result.usable:
                return await self._store(target_url, result, proxy_url, attempts)

        # Route 2: plain HTTP. Faster, and succeeds on plenty of pages where a
        # headless browser is fingerprinted and served an empty shell.
        result = await self._fetch_with_httpx(target_url, proxy_url)
        attempts.append(result)
        blocked = self._as_block(result, target_url, proxy_url)
        if blocked:
            return blocked
        if result.usable:
            return await self._store(target_url, result, proxy_url, attempts)

        # Route 3: the proxy may be the problem rather than the site.
        if proxy_url:
            await proxy_pool.report_result(proxy_url, success=False)
            direct = await self._fetch_with_httpx(target_url, None)
            attempts.append(direct)
            blocked = self._as_block(direct, target_url, None)
            if blocked:
                return blocked
            if direct.usable:
                return await self._store(target_url, direct, None, attempts)

        # Nothing returned anything worth filing. Say so rather than storing an
        # empty record and reporting the collection as successful.
        summary = "; ".join(a.describe() for a in attempts) or "no transport available"
        logger.warning("No readable content from %s (%s)", target_url, summary)
        return {
            "status": "NO_CONTENT",
            "url": target_url,
            "error": (
                "No readable content retrieved. Tried "
                + ", ".join(a.route for a in attempts)
                + f". Detail - {summary}. The page is most likely rendered "
                  "entirely client-side, behind a login, or serving an empty "
                  "shell to automated clients."
            ),
            "attempts": [{"route": a.route, "chars": len(a.text), "error": a.error}
                         for a in attempts],
        }

    # ── Transports ───────────────────────────────────────────────────

    async def _fetch_with_playwright(self, url: str, proxy_url: Optional[str]) -> FetchResult:
        browser = None
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(
                    headless=True,
                    proxy={"server": proxy_url} if proxy_url else None,
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--no-sandbox",
                        "--disable-web-security",
                    ],
                )
                context = await browser.new_context(
                    viewport=get_random_viewport(),
                    user_agent=get_random_user_agent(),
                    locale="en-US",
                    timezone_id="Asia/Kolkata",
                )
                await context.add_init_script(STEALTH_JS_INJECTION)
                page = await context.new_page()

                # "networkidle" never settles on sites that poll in the
                # background - Reddit among them - so the load is anchored on
                # the DOM and then given a fixed grace period for hydration.
                response = await page.goto(
                    url, timeout=settings.SCRAPE_TIMEOUT * 1000,
                    wait_until="domcontentloaded",
                )
                await page.wait_for_timeout(2500)
                await page.evaluate("window.scrollBy(0, 600)")
                await page.wait_for_timeout(500)

                html = await page.content()
                status = response.status if response else 200
                return FetchResult("playwright", html, status, final_url=page.url)

        except Exception as e:
            return FetchResult("playwright", error=f"{type(e).__name__}: {str(e)[:160]}")
        finally:
            if browser is not None:
                try:
                    await browser.close()
                except Exception:
                    pass

    async def _fetch_with_httpx(self, url: str, proxy_url: Optional[str]) -> FetchResult:
        if httpx is None:
            return FetchResult("httpx", error="httpx not installed")

        kwargs: Dict[str, Any] = {
            "timeout": settings.SCRAPE_TIMEOUT,
            "headers": get_stealth_headers(),
            "follow_redirects": True,
        }
        if proxy_url:
            kwargs["proxy"] = proxy_url

        route = "httpx+proxy" if proxy_url else "httpx"
        try:
            async with httpx.AsyncClient(**kwargs) as client:
                resp = await client.get(url)
                return FetchResult(route, resp.text, resp.status_code,
                                   final_url=str(resp.url))
        except Exception as e:
            return FetchResult(route, error=f"{type(e).__name__}: {str(e)[:160]}")

    # ── Decisions ────────────────────────────────────────────────────

    def _as_block(self, result: FetchResult, url: str,
                  proxy_url: Optional[str]) -> Optional[Dict[str, Any]]:
        """Return a BLOCKED payload when the response is a challenge page."""
        if not result.html:
            return None
        challenge = detect_bot_challenge(result.html, result.status_code)
        if not challenge:
            return None

        logger.warning("Bot challenge on %s via %s: %s", url, result.route, challenge)
        if proxy_url:
            asyncio.create_task(proxy_pool.report_result(proxy_url, success=False))
        return {
            "status": "BLOCKED",
            "url": url,
            "status_code": result.status_code,
            "error": f"Bot challenge detected via {result.route}: {challenge}",
        }

    async def _store(self, url: str, result: FetchResult,
                     proxy_url: Optional[str], attempts) -> Dict[str, Any]:
        if proxy_url:
            await proxy_pool.report_result(proxy_url, success=True)

        extracted = result.extracted or {}
        title = extracted.get("title", "")
        logger.info("Collected %s via %s (%d chars)", url, result.route, len(result.text))

        return await self.save_evidence(
            url=url,
            raw_content=result.html,
            cleaned_text=(title + "\n\n" + result.text).strip(),
            metadata={
                "title": title,
                "status_code": result.status_code,
                "proxy": proxy_url,
                "transport": result.route,
                "extraction_strategy": extracted.get("strategy"),
                "boilerplate_removed_chars": extracted.get("removed_chars"),
                # Kept so a thin page can be told from one that needed several
                # attempts, which is useful when tuning a difficult source.
                "routes_tried": [a.route for a in attempts],
            },
        )

    async def crawl(self, seed_target: str, max_depth: int = 2):
        from scrapers.surface_web.crawler import SurfaceCrawler
        return await SurfaceCrawler(self).crawl(seed_target, max_depth)
