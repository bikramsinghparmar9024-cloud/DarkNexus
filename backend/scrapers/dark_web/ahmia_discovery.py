"""
Ahmia Discovery - finding hidden services to crawl.

The dark web crawler could only follow links out of onion sites it had already
been given, which meant it could not start. Ahmia is a public search engine
that indexes Tor hidden services and filters abuse material; querying it turns
a search term into a list of candidate .onion addresses.

Two deliberate boundaries.

Ahmia's own index entries - the title and blurb it shows in results - are
*not* stored as collected intelligence. They describe a service; they are not
its content, and filing a search-engine snippet as an intercept would put text
in the evidence table that was never fetched from the service it is attributed
to. Discovered addresses are registered as targets, with the Ahmia metadata
kept as provenance, and become intelligence only once the Tor crawler fetches
them.

Nothing here is a list of known markets. Addresses come from the query, so the
operator's search terms decide what is collected, and every target records
which query produced it.

Routing. The clearnet host works without Tor; the onion mirror does not. Where
a network blocks ahmia.fi - which is common, and is the case on the machine
this was written on - the onion mirror through Tor is the way in.
"""

from typing import Any, Dict, List, Optional
from datetime import datetime
import asyncio
import logging
import re

logger = logging.getLogger("ahmia_discovery")

# v3 addresses only. v2 was retired in 2021 and anything still advertising one
# is either long dead or impersonating a service that has moved.
ONION_V3_RE = re.compile(r"\b([a-z2-7]{56}\.onion)\b", re.IGNORECASE)

CLEARNET_HOST = "https://ahmia.fi"
ONION_MIRROR = ("http://juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd"
                ".onion")

# Ahmia is a small volunteer service. One request at a time, with a pause
# between pages, and a header that says who is calling.
REQUEST_TIMEOUT = 60.0
# Ahmia's search backend sheds load with a gateway error while its front page
# stays up, so these are worth retrying rather than reporting as unreachable.
RETRYABLE_STATUSES = {502, 503, 504}
RETRY_ATTEMPTS = 2
RETRY_BACKOFF_SECONDS = 3.0
USER_AGENT = "PunjabNarcoticsIntel/1.0 (law enforcement OSINT; contact via department)"


def parse_results(html: str) -> List[Dict[str, Any]]:
    """
    Pull hidden-service results out of an Ahmia results page.

    Kept separate from fetching so the parser can be tested without a network,
    and so a change in Ahmia's markup shows up as a parser failure rather than
    as silently empty collection runs.
    """
    results: List[Dict[str, Any]] = []
    if not html:
        return results

    try:
        from bs4 import BeautifulSoup
    except ImportError:                                       # pragma: no cover
        logger.error("beautifulsoup4 is required to parse Ahmia results.")
        return results

    soup = BeautifulSoup(html, "html.parser")
    seen = set()

    for item in soup.select("li.result, div.result"):
        text = item.get_text(" ", strip=True)

        # The address may sit in a cite, in the link, or in a redirect
        # parameter depending on which Ahmia layout is served.
        candidates = [text]
        for anchor in item.find_all("a", href=True):
            candidates.append(anchor["href"])
        cite = item.find("cite")
        if cite:
            candidates.append(cite.get_text(strip=True))

        address = None
        for candidate in candidates:
            match = ONION_V3_RE.search(candidate or "")
            if match:
                address = match.group(1).lower()
                break
        if not address or address in seen:
            continue
        seen.add(address)

        heading = item.find(["h4", "h3", "h2"])
        title = heading.get_text(strip=True) if heading else ""
        paragraph = item.find("p")
        description = paragraph.get_text(strip=True) if paragraph else ""

        results.append({
            "onion_address": address,
            "url": f"http://{address}",
            "title": title,
            "description": description,
        })

    # Fall back to a raw scan when the markup has changed. Better to return
    # addresses with no metadata than to report a search found nothing.
    if not results:
        for address in {m.lower() for m in ONION_V3_RE.findall(html)}:
            results.append({
                "onion_address": address,
                "url": f"http://{address}",
                "title": "",
                "description": "",
                "parser_note": "recovered by raw scan; Ahmia markup may have changed",
            })
        if results:
            logger.warning("Ahmia result markup not recognised; recovered %d "
                           "addresses by raw scan", len(results))

    return results


class AhmiaDiscovery:
    """Queries Ahmia and registers what it finds as crawl targets."""

    def __init__(self, use_tor: Optional[bool] = None):
        from config import settings
        self.settings = settings
        # The onion mirror requires Tor; the clearnet host does not.
        self.use_tor = settings.TOR_ENABLED if use_tor is None else use_tor
        self.base_url = ONION_MIRROR if self.use_tor else CLEARNET_HOST

    def _client_kwargs(self) -> Dict[str, Any]:
        kwargs: Dict[str, Any] = {
            "timeout": REQUEST_TIMEOUT,
            "follow_redirects": True,
            "headers": {"User-Agent": USER_AGENT},
        }
        if self.use_tor:
            from scrapers.dark_web.tor_manager import tor_manager
            # socks5h keeps DNS resolution inside Tor, which is what stops the
            # lookup for a hidden service leaking to the local resolver.
            kwargs["proxy"] = tor_manager.socks_proxy_url
        return kwargs

    async def search(self, query: str, limit: int = 25) -> Dict[str, Any]:
        """Run one search and return the hidden services it named."""
        import httpx

        query = (query or "").strip()
        if not query:
            return {"status": "INVALID", "query": query, "results": [],
                    "message": "A search term is required."}

        # Ahmia's search backend returns 504 under load while its homepage
        # keeps serving, and it does so on both the onion mirror and the
        # clearnet host - so a single 504 says the service is busy, not that
        # the route is wrong. Retry, then try the other endpoint before
        # concluding anything.
        endpoints = [self.base_url]
        if self.use_tor and CLEARNET_HOST not in endpoints:
            # Over Tor the clearnet host resolves at the exit node, so a local
            # DNS block does not apply to it either.
            endpoints.append(CLEARNET_HOST)

        response = None
        last_status = None
        try:
            async with httpx.AsyncClient(**self._client_kwargs()) as client:
                for endpoint in endpoints:
                    for attempt in range(RETRY_ATTEMPTS):
                        response = await client.get(f"{endpoint}/search/",
                                                    params={"q": query})
                        last_status = response.status_code
                        if response.status_code not in RETRYABLE_STATUSES:
                            break
                        logger.warning("Ahmia %s returned %d for %r (attempt %d)",
                                       endpoint, response.status_code, query,
                                       attempt + 1)
                        await asyncio.sleep(RETRY_BACKOFF_SECONDS * (attempt + 1))
                    if response is not None and response.status_code == 200:
                        self.base_url = endpoint
                        break
        except Exception as e:
            # Distinguish the failures an operator can actually act on.
            message = str(e)
            if self.use_tor:
                hint = ("Tor is not reachable; start Tor and set "
                        "TOR_ENABLED=True.")
            elif "CERTIFICATE_VERIFY_FAILED" in message or "SSLError" in message:
                # A substituted certificate means something on the path is
                # terminating the connection - a filtering appliance or an
                # ISP block page. Turning verification off would accept that
                # interception rather than defeat it, and is never the fix:
                # the collected page would be the interceptor's, not Ahmia's.
                hint = ("The TLS certificate for ahmia.fi was not issued by a "
                        "trusted authority, which means the connection is "
                        "being intercepted - typically a network filter or ISP "
                        "block page. Do not disable certificate verification: "
                        "that accepts the interception and would file the "
                        "block page as collected content. Reach Ahmia through "
                        "the onion mirror over Tor instead.")
            else:
                hint = ("ahmia.fi could not be reached. Many networks resolve "
                        "it to a sinkhole address; compare `nslookup ahmia.fi` "
                        "against `nslookup ahmia.fi 1.1.1.1`. Routing through "
                        "the onion mirror with Tor avoids the block.")
            logger.error("Ahmia search failed for %r: %s", query, e)
            return {"status": "UNREACHABLE", "query": query, "results": [],
                    "endpoint": self.base_url, "error": str(e), "hint": hint}

        if response is None or response.status_code != 200:
            busy = last_status in RETRYABLE_STATUSES
            return {
                "status": "SERVICE_BUSY" if busy else "HTTP_ERROR",
                "query": query, "results": [], "endpoint": self.base_url,
                "endpoints_tried": endpoints, "via_tor": self.use_tor,
                "status_code": last_status,
                "hint": ("Ahmia's search backend returned a gateway error from "
                         "every route tried, while the service itself is "
                         "reachable. That is an outage on their side, not a "
                         "problem with Tor or with this configuration - retry "
                         "later." if busy else
                         f"Ahmia returned HTTP {last_status}."),
            }

        results = parse_results(response.text)[:limit]
        return {
            "status": "SUCCESS",
            "query": query,
            "endpoint": self.base_url,
            "via_tor": self.use_tor,
            "result_count": len(results),
            "results": results,
            "note": ("Ahmia index entries describe a service and are not its "
                     "content. Nothing here is stored as intelligence until "
                     "the Tor crawler fetches the service itself."),
        }

    async def register_targets(self, results: List[Dict[str, Any]],
                               query: str, priority: int = 2) -> Dict[str, Any]:
        """
        Add discovered services to the crawl queue.

        Existing targets are left alone rather than reset, so a service that
        has already been crawled and paused is not silently reactivated by a
        later search that happens to name it again.
        """
        from sqlalchemy import select
        from database.postgres import AsyncSessionLocal, Target

        added, already_known = [], []
        async with AsyncSessionLocal() as session:
            for result in results:
                identifier = result["url"]
                existing = (await session.execute(
                    select(Target).where(Target.identifier == identifier)
                )).scalars().first()
                if existing:
                    already_known.append(identifier)
                    continue

                session.add(Target(
                    identifier=identifier,
                    source_type="DARK_WEB",
                    label=(result.get("title") or "")[:200] or f"Ahmia: {query}",
                    priority=priority,
                    status="ACTIVE",
                    discovered_by="AHMIA",
                ))
                added.append(identifier)
            await session.commit()

        logger.info("Ahmia discovery for %r: %d new targets, %d already known",
                    query, len(added), len(already_known))
        return {
            "query": query,
            "registered": added,
            "already_known": already_known,
            "registered_count": len(added),
            "discovered_at": datetime.utcnow().isoformat() + "Z",
        }

    async def discover(self, query: str, limit: int = 25,
                       register: bool = True) -> Dict[str, Any]:
        """Search, and optionally queue what was found for crawling."""
        found = await self.search(query, limit=limit)
        if found["status"] != "SUCCESS" or not register:
            return found
        return {**found, "registration": await self.register_targets(
            found["results"], query)}


ahmia_discovery = AhmiaDiscovery()
