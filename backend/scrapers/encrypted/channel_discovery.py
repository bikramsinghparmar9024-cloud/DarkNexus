"""
Telegram Channel & Group Discovery Crawler.
Scans scraped message bodies for mentions of other Telegram channels/groups
(e.g., 't.me/joinchat/...', 't.me/username', '@username')
and registers newly found drug communities back into the targets list.
"""

import re
from typing import List, Set
import logging
from database.postgres import AsyncSessionLocal, Target
from sqlalchemy import select

logger = logging.getLogger("channel_discovery")

# Regex to catch Telegram links and handles
TG_LINK_REGEX = re.compile(r"(?:https?://)?(?:www\.)?t\.me/([a-zA-Z0-9_+]+)", re.IGNORECASE)
TG_HANDLE_REGEX = re.compile(r"@([a-zA-Z0-9_]{5,32})\b")


class ChannelDiscovery:
    """Discovers connected Telegram channels and groups from scraped chatter."""

    def __init__(self, scraper_instance):
        self.scraper = scraper_instance

    async def discover_from_channel(self, seed_channel: str) -> List[str]:
        """Scrape seed channel and extract all cross-promoted drug channels."""
        discovered: Set[str] = set()

        result = await self.scraper.scrape(seed_channel)
        text_content = result.get("cleaned_text", "")
        if not text_content:
            return []

        # 1. Match t.me/ links
        for match in TG_LINK_REGEX.findall(text_content):
            # Ignore common standard paths
            if match.lower() not in ("share", "joinchat", "s", "addstickers"):
                discovered.add(match)

        # 2. Match @handles
        for handle in TG_HANDLE_REGEX.findall(text_content):
            if handle.lower() not in (seed_channel.lower(), "telegram", "admin", "bot"):
                discovered.add(handle)

        # 3. Enqueue into targets database
        for channel in discovered:
            await self._register_channel_target(channel)

        logger.info(f"Discovered {len(discovered)} new Telegram communities from @{seed_channel}")
        return list(discovered)

    async def _register_channel_target(self, channel_identifier: str):
        """Save discovered Telegram community into Target table."""
        async with AsyncSessionLocal() as session:
            stmt = select(Target).where(Target.identifier == f"@{channel_identifier}")
            existing = (await session.execute(stmt)).scalars().first()
            if not existing:
                new_target = Target(
                    identifier=f"@{channel_identifier}",
                    source_type="TELEGRAM",
                    label=f"Cross-linked Telegram Community",
                    priority=2,
                    status="ACTIVE",
                    discovered_by="CRAWLER"
                )
                session.add(new_target)
                await session.commit()
                logger.info(f"Enqueued new Telegram target: @{channel_identifier}")
