"""
Base Abstract Scraper Class.
Enforces common patterns:
- Rate limit backoff & random jitter
- Retry logic with exponential delay
- Delegates hashing, analysis and persistence to ai.enrichment
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
import asyncio
import random
import logging
from datetime import datetime

from config import settings

logger = logging.getLogger("base_scraper")


class BaseScraper(ABC):
    """Abstract parent class for intelligence collectors."""

    def __init__(self, name: str, source_type: str):
        self.name = name
        self.source_type = source_type
        self.is_running = False
        # Set by the surveillance scheduler so collected records link back to
        # the target that produced them.
        self.active_target_id = None

    async def apply_jitter(self):
        """Random delay between requests to defeat behavioural timing analysis."""
        delay = random.uniform(settings.SCRAPE_DELAY_MIN, settings.SCRAPE_DELAY_MAX)
        await asyncio.sleep(delay)

    async def save_evidence(
        self,
        url: str,
        raw_content: str,
        cleaned_text: Optional[str] = None,
        author: Optional[str] = None,
        target_id: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
        ocr_text: Optional[str] = None,
        fetch_media: bool = True
    ) -> Dict[str, Any]:
        """
        Persist a scraped artifact through the unified enrichment layer.

        Analysis, SHA-256 hashing, database write, vector indexing and graph
        correlation all happen in ai.enrichment.store_intelligence(), which is
        the same code path used by manual ingest and batch re-analysis.
        """
        from ai.enrichment import store_intelligence
        from media.pipeline import process_media_for_page

        # Fetch and forensically analyse any images or video the page carries.
        # Failures here must never lose the page itself.
        target_id = target_id if target_id is not None else self.active_target_id

        media_items = []
        if fetch_media:
            try:
                media_items = await process_media_for_page(raw_content, url)
                if media_items:
                    logger.info("Recovered %d media artifact(s) from %s",
                                len(media_items), url)
            except Exception as e:
                logger.warning("Media pass failed for %s: %s", url, e)

        return await store_intelligence(
            source_type=self.source_type,
            source_url=url,
            raw_content=raw_content,
            cleaned_text=cleaned_text,
            author=author,
            target_id=target_id,
            ocr_text=ocr_text,
            media_items=media_items,
            provenance={
                "acquisition_method": "AUTOMATED_COLLECTION",
                "collector": self.name,
                **(metadata or {}),
            },
        )

    @abstractmethod
    async def scrape(self, target: str) -> Dict[str, Any]:
        """Execute a scrape against a specific target."""
        pass

    @abstractmethod
    async def crawl(self, seed_target: str, max_depth: int = 2) -> List[str]:
        """Discover connected target links."""
        pass
