"""
Dark Web .onion Crawler & Link Extractor.
Extracts v3 56-character .onion domains from crawled onion indices/market forums
and feeds newly discovered hidden services into the database target list.
"""

import re
from typing import List, Set
from bs4 import BeautifulSoup
import logging
from database.postgres import AsyncSessionLocal, Target
from sqlalchemy import select

logger = logging.getLogger("dark_crawler")

# Regex for Tor v3 hidden services: [a-z2-7]{56}.onion
ONION_V3_REGEX = re.compile(r"\b([a-z2-7]{56}\.onion)\b", re.IGNORECASE)


class DarkCrawler:
    """Discovers new .onion websites from directories, market listings, and forums."""

    def __init__(self, scraper_instance):
        self.scraper = scraper_instance

    async def crawl(self, seed_onion_url: str, max_depth: int = 3) -> List[str]:
        """Scrape seed page and extract all referenced .onion links."""
        discovered: Set[str] = set()

        from ai.enrichment import fetch_raw_content

        result = await self.scraper.scrape(seed_onion_url)
        if str(result.get("status", "")).upper() in ("FAILED", "BLOCKED"):
            logger.warning("Seed %s could not be collected: %s",
                           seed_onion_url, result.get("error"))
            return []

        # The page source is read back from the stored record. It is not in the
        # save result, and asking for a key that was never there is why this
        # crawler returned an empty list on every run it had ever made.
        raw_html = await fetch_raw_content(result.get("record_id"))
        if not raw_html:
            logger.warning("No stored content for seed %s; nothing to follow",
                           seed_onion_url)
            return []

        # 1. Regex search for all v3 onion addresses in raw text/HTML
        matches = ONION_V3_REGEX.findall(raw_html)
        for m in matches:
            onion_url = f"http://{m.lower()}"
            discovered.add(onion_url)

        # 2. Parse <a> hrefs
        soup = BeautifulSoup(raw_html, "html.parser")
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if ".onion" in href:
                if not href.startswith("http"):
                    href = f"http://{href.lstrip('/')}"
                discovered.add(href)

        # 3. Register new targets into DB
        for onion_site in discovered:
            await self._register_onion_target(onion_site)

        logger.info(f"Discovered {len(discovered)} .onion addresses from {seed_onion_url}")
        return list(discovered)

    async def _register_onion_target(self, onion_url: str):
        """Save discovered .onion domain into Target database table."""
        async with AsyncSessionLocal() as session:
            stmt = select(Target).where(Target.identifier == onion_url)
            existing = (await session.execute(stmt)).scalars().first()
            if not existing:
                new_target = Target(
                    identifier=onion_url,
                    source_type="DARK_WEB",
                    label=f"Discovered by Dark Web Crawler",
                    priority=2, # Higher priority for hidden services
                    status="ACTIVE",
                    discovered_by="CRAWLER"
                )
                session.add(new_target)
                await session.commit()
                logger.info(f"Enqueued new dark web target: {onion_url}")
