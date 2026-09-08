"""
Dark Web .onion Marketplace Scraper.
Routes HTTP traffic securely through Tor SOCKS5 proxy (socks5h://) to prevent DNS leaks.
Performs periodic circuit rotation and extracts illicit listing titles, pricing, and crypto wallets.
"""

from typing import Dict, Any, Optional
import httpx
import logging
from bs4 import BeautifulSoup

from scrapers.base_scraper import BaseScraper
from scrapers.content_extraction import extract_readable_text
from scrapers.dark_web.tor_manager import tor_manager
from config import settings

logger = logging.getLogger("dark_scraper")


class DarkWebScraper(BaseScraper):
    """Scrapes hidden services (.onion) across dark web drug markets."""

    def __init__(self):
        super().__init__(name="DarkWebScraper", source_type="DARK_WEB")

    async def scrape(self, onion_url: str) -> Dict[str, Any]:
        """Scrape hidden service content via Tor SOCKS5 proxy."""
        await self.apply_jitter()

        # Rotate Tor exit node circuit before heavy batch
        tor_manager.rotate_circuit()

        client_kwargs = {
            "proxy": tor_manager.socks_proxy_url,
            "timeout": 45.0,  # Hidden services are significantly slower
            "follow_redirects": True,
            "headers": {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/115.0", # Tor Browser UA
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Connection": "keep-alive"
            }
        }

        try:
            async with httpx.AsyncClient(**client_kwargs) as client:
                resp = await client.get(onion_url)
                html_content = resp.text

                extracted = extract_readable_text(html_content, onion_url)
                title = extracted["title"] or onion_url

                saved = await self.save_evidence(
                    url=onion_url,
                    raw_content=html_content,
                    cleaned_text=(title + '\n\n' + extracted["text"]).strip(),
                    metadata={
                        "title": title,
                        "status_code": resp.status_code,
                        "tor_routed": True,
                        "extraction_strategy": extracted["strategy"],
                        "boilerplate_removed_chars": extracted["removed_chars"],
                    },
                )
                return saved

        except Exception as e:
            logger.warning(f"Error scraping .onion service {onion_url}: {e}")
            return {
                "status": "FAILED",
                "url": onion_url,
                "error": str(e),
                "note": "Tor daemon must be active on socks port 9050"
            }

    async def crawl(self, seed_target: str, max_depth: int = 2):
        """Crawler implementation in crawler.py."""
        from scrapers.dark_web.crawler import DarkCrawler
        crawler = DarkCrawler(self)
        return await crawler.crawl(seed_target, max_depth)
