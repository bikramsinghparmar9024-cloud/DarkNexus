"""
Surface Web Crawler & Link Discovery Engine.
Extracts links from scraped pages, filters relevant domains,
and feeds new notable URLs back into the targets queue (matching your architecture diagram).
"""

from typing import List, Set
from urllib.parse import urljoin, urlparse
import logging
from bs4 import BeautifulSoup

from ai.enrichment import fetch_raw_content
from database.postgres import AsyncSessionLocal, Target
from sqlalchemy import select

logger = logging.getLogger("surface_crawler")


class SurfaceCrawler:
    """Discovers internal and external links from intelligence targets."""

    def __init__(self, scraper_instance):
        self.scraper = scraper_instance

    async def crawl(self, seed_url: str, max_pages: int = 5) -> List[str]:
        """Perform recursive link discovery starting from a seed URL."""
        visited: Set[str] = set()
        queue: List[str] = [seed_url]
        discovered_targets: List[str] = []

        seed_domain = urlparse(seed_url).netloc

        while queue and len(visited) < max_pages:
            current_url = queue.pop(0)
            if current_url in visited:
                continue

            visited.add(current_url)
            logger.info(f"Crawling link: {current_url}")

            scrape_result = await self.scraper.scrape(current_url)
            if str(scrape_result.get("status", "")).upper() in ("FAILED", "BLOCKED"):
                continue

            # Read the page source back from the stored record. The previous
            # guard required a "raw_content" key that the save result has never
            # contained, so every page was skipped and the crawl found nothing.
            raw_html = await fetch_raw_content(scrape_result.get("record_id"))
            if not raw_html:
                continue
            soup = BeautifulSoup(raw_html, "html.parser")

            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                full_url = urljoin(current_url, href)
                parsed = urlparse(full_url)

                # Keep HTTP/HTTPS links
                if parsed.scheme in ("http", "https"):
                    # Check if internal domain or interesting subpath
                    if parsed.netloc == seed_domain and full_url not in visited:
                        queue.append(full_url)
                    elif parsed.netloc != seed_domain:
                        # Found external notable website - feed back to target database!
                        await self._register_new_target(full_url)
                        discovered_targets.append(full_url)

        return discovered_targets

    async def _register_new_target(self, url: str):
        """Save discovered notable website into targets DB if not already present."""
        async with AsyncSessionLocal() as session:
            stmt = select(Target).where(Target.identifier == url)
            existing = (await session.execute(stmt)).scalars().first()
            if not existing:
                new_target = Target(
                    identifier=url,
                    source_type="SURFACE_WEB",
                    label=f"Discovered by Crawler from {urlparse(url).netloc}",
                    priority=1,
                    status="ACTIVE",
                    discovered_by="CRAWLER"
                )
                session.add(new_target)
                await session.commit()
                logger.info(f"Registered newly discovered crawler target: {url}")
