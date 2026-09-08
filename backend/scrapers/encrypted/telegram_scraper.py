"""
Telegram Intelligence Scraper.
Features dual operation modes:
1. Primary: Telethon MTProto Client (Full channel history, media attachments, user metadata).
2. Resilient Fallback: Telegram Web Preview Scraper (https://t.me/s/{channel_name})
   Allows scraping public channel posts without needing API ID / Hash!
"""

from typing import Dict, Any, List, Optional
import httpx
import logging
from bs4 import BeautifulSoup
from datetime import datetime

from scrapers.base_scraper import BaseScraper
from config import settings

logger = logging.getLogger("telegram_scraper")

try:
    from telethon import TelegramClient
    from telethon.tl.types import MessageMediaPhoto
except ImportError:
    TelegramClient = None
    MessageMediaPhoto = None


class TelegramScraper(BaseScraper):
    """Scrapes public channels, drug chatter groups, and bot storefronts on Telegram."""

    def __init__(self):
        super().__init__(name="TelegramScraper", source_type="TELEGRAM")
        self.client: Optional[Any] = None

    async def init_client(self):
        """Initialize Telethon async client if credentials exist."""
        if (
            TelegramClient
            and settings.TELEGRAM_API_ID
            and settings.TELEGRAM_API_HASH
        ):
            try:
                self.client = TelegramClient(
                    settings.TELEGRAM_SESSION_NAME,
                    settings.TELEGRAM_API_ID,
                    settings.TELEGRAM_API_HASH
                )
                await self.client.connect()
                logger.info("Telethon client connected successfully.")
            except Exception as e:
                logger.warning(f"Failed to connect Telethon client: {e}. Falling back to Web Preview scraper.")
                self.client = None

    async def scrape(self, target_channel: str) -> Dict[str, Any]:
        """Scrape messages from target channel (e.g. '@channel_name' or 'channel_name')."""
        await self.apply_jitter()

        clean_handle = target_channel.lstrip("@").split("/")[-1]

        # 1. Use Telethon if connected
        if self.client and await self.client.is_user_authorized():
            return await self._scrape_with_telethon(clean_handle)

        # 2. Fallback: Telegram Public Web Preview (t.me/s/...)
        return await self._scrape_with_web_preview(clean_handle)

    async def _scrape_with_web_preview(self, channel_name: str) -> Dict[str, Any]:
        """Scrapes the public web preview endpoint without requiring API credentials."""
        url = f"https://t.me/s/{channel_name}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        }

        try:
            async with httpx.AsyncClient(timeout=20.0, headers=headers) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return {
                        "status": "FAILED",
                        "channel": channel_name,
                        "error": f"HTTP status {resp.status_code}"
                    }

                soup = BeautifulSoup(resp.text, "html.parser")
                messages = []

                # Extract post elements
                for msg_div in soup.find_all("div", class_="tgme_widget_message"):
                    text_div = msg_div.find("div", class_="tgme_widget_message_text")
                    msg_text = text_div.get_text(separator=" ", strip=True) if text_div else ""
                    if not msg_text:
                        continue

                    # The first <time> in a message is the video duration
                    # ('0:06') on posts with media, and carries no datetime
                    # attribute - which is why every post was filed as
                    # [None]. The post timestamp lives inside the date link.
                    msg_date = None
                    date_link = msg_div.find("a", class_="tgme_widget_message_date")
                    time_el = date_link.find("time") if date_link else None
                    if time_el is None:
                        time_el = msg_div.find("time", attrs={"datetime": True})
                    if time_el is not None and time_el.has_attr("datetime"):
                        msg_date = time_el["datetime"]

                    # data-post gives a stable per-message permalink, so a
                    # record cites the exact post rather than the channel.
                    post_id = msg_div.get("data-post")
                    permalink = f"https://t.me/{post_id}" if post_id else None

                    author_el = msg_div.find("span", class_="tgme_widget_message_from_author")
                    msg_author = author_el.get_text(strip=True) if author_el else None

                    messages.append({
                        "text": msg_text,
                        "date": msg_date,
                        "permalink": permalink,
                        "author": msg_author,
                        # Kept for the media pass; not used for hashing,
                        # because it carries a volatile view counter.
                        "html": str(msg_div),
                        "has_media": bool(msg_div.find(class_="tgme_widget_message_photo_wrap")
                                          or msg_div.find("video")),
                    })

                # One record per message, not one per channel.
                #
                # The whole page used to be stored as a single record: twenty
                # messages concatenated, authored by the channel, with the
                # channel URL as the source. Three things went wrong with
                # that. A wallet posted by one member was attributed to the
                # channel rather than to whoever posted it, so no per-sender
                # profile could ever be built. An entity found in the twelfth
                # message cited the channel page instead of the post it came
                # from. And because the page changes whenever anyone posts,
                # every revisit stored a fresh copy of the nineteen messages
                # already held - the content hash never matched, so
                # deduplication could not fire.
                #
                # Storing each post separately fixes all three: the permalink
                # is the source, the sender is the author, and re-collecting a
                # channel only saves what is genuinely new.
                stored, duplicates, failures = [], [], []
                for message in messages:
                    permalink = message.get("permalink") or url
                    author = message.get("author") or f"@{channel_name}"
                    try:
                        # The message text is the artifact, not the page
                        # markup around it. The preview HTML carries a view
                        # counter that ticks up between visits, so hashing it
                        # produced a different digest every time and the same
                        # post was stored again on every revisit - twenty
                        # fresh records per check. A Telegram post is immutable
                        # once sent; its text plus its permalink identify it.
                        saved = await self.save_evidence(
                            url=permalink,
                            raw_content=message["text"],
                            cleaned_text=message["text"],
                            author=author,
                            metadata={
                                "channel": channel_name,
                                "posted_at": message.get("date"),
                                "has_media": message.get("has_media"),
                                "permalink": permalink,
                                "title": f"@{channel_name}: {message['text'][:60]}",
                                "scraped_via": "web_preview",
                            },
                        )
                    except Exception as e:                       # pragma: no cover
                        logger.warning("Storing %s failed: %s", permalink, e)
                        failures.append({"permalink": permalink, "error": str(e)})
                        continue

                    if saved.get("status") == "DUPLICATE":
                        duplicates.append(saved.get("record_id"))
                    else:
                        stored.append(saved.get("record_id"))

                if not stored and not duplicates:
                    return {
                        "status": "FAILED", "channel": channel_name, "url": url,
                        "error": ("no messages could be stored from this channel"
                                  if messages else
                                  "channel preview contained no readable posts"),
                        "messages_found": len(messages),
                    }

                dated = [m for m in messages if m.get("date")]
                return {
                    # A revisit that finds only posts already held is a
                    # successful check, not a collection - reported as
                    # DUPLICATE so the job log does not claim new evidence.
                    "status": "SAVED" if stored else "DUPLICATE",
                    "channel": channel_name,
                    "url": url,
                    "messages_found": len(messages),
                    "stored": len(stored),
                    "duplicates": len(duplicates),
                    "failures": len(failures),
                    "record_ids": stored,
                    "record_id": stored[0] if stored else (
                        duplicates[0] if duplicates else None),
                    "newest_post": dated[-1]["date"] if dated else None,
                    "oldest_post": dated[0]["date"] if dated else None,
                    "posts_with_media": sum(1 for m in messages if m.get("has_media")),
                    "scraped_via": "web_preview",
                }

        except Exception as e:
            logger.error(f"Error scraping Telegram channel @{channel_name}: {e}")
            return {"status": "FAILED", "channel": channel_name, "error": str(e)}

    async def _scrape_with_telethon(self, channel_name: str, limit: int = 50) -> Dict[str, Any]:
        """
        Scrape messages over MTProto, storing one record per message.

        Same reasoning as the web preview path: a channel dump concatenated
        into a single record loses which member posted what, and attributes
        every wallet and number in it to the channel itself.
        """
        try:
            stored, duplicates = [], []
            count = 0

            async for message in self.client.iter_messages(channel_name, limit=limit):
                if not message.text:
                    continue
                count += 1

                # Prefer the individual sender; fall back to the channel for
                # broadcast posts, which genuinely have no separate author.
                author = f"@{channel_name}"
                try:
                    sender = await message.get_sender()
                    handle = getattr(sender, "username", None)
                    if handle:
                        author = f"@{handle}"
                except Exception:                                # pragma: no cover
                    pass

                permalink = f"https://t.me/{channel_name}/{message.id}"
                saved = await self.save_evidence(
                    url=permalink,
                    raw_content=message.text,
                    cleaned_text=message.text,
                    author=author,
                    metadata={
                        "channel": channel_name,
                        "message_id": message.id,
                        "posted_at": str(message.date) if message.date else None,
                        "sender_id": message.sender_id,
                        "has_media": bool(message.media),
                        "permalink": permalink,
                        "title": f"@{channel_name}: {message.text[:60]}",
                        "scraped_via": "telethon",
                    },
                )
                (duplicates if saved.get("status") == "DUPLICATE" else stored).append(
                    saved.get("record_id"))

            if not stored and not duplicates:
                return {"status": "FAILED", "channel": channel_name,
                        "error": "no text messages returned by the API",
                        "messages_found": count}

            return {
                "status": "SAVED" if stored else "DUPLICATE",
                "channel": channel_name,
                "messages_found": count,
                "stored": len(stored),
                "duplicates": len(duplicates),
                "record_ids": stored,
                "record_id": stored[0] if stored else duplicates[0],
                "scraped_via": "telethon",
            }
        except Exception as e:
            logger.error(f"Telethon error: {e}")
            return {"status": "FAILED", "channel": channel_name, "error": str(e)}

    async def crawl(self, seed_channel: str, max_depth: int = 2):
        """Channel discovery in channel_discovery.py."""
        from scrapers.encrypted.channel_discovery import ChannelDiscovery
        discovery = ChannelDiscovery(self)
        return await discovery.discover_from_channel(seed_channel)
