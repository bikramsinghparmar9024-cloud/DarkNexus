"""
Multi-engine hidden-service discovery.

Discovery previously ran through Ahmia alone, which made the whole capability
depend on one volunteer service - and when Ahmia's search backend started
answering 504 on every route, discovery stopped entirely while the rest of the
Tor pipeline was working fine.

There are many onion search engines. Querying several and pooling the results
removes the single point of failure, and gives a signal one engine cannot: an
address that several independent indexes return is an established service,
while one that appears in a single index is likely short-lived or obscure.

Engine list adapted from the open-source Robin project
(github.com/apurvsinghgautam/robin, MIT).

── A safety rule that shapes the design ─────────────────────────────

Ahmia filters child sexual abuse material from its index. Most of the other
engines do not filter anything.

This system stores whatever it fetches, and the surveillance scheduler
collects from ACTIVE targets unattended. Feeding unfiltered dark web search
results straight into that loop would eventually pull illegal imagery into an
evidence database, with no human ever having chosen to fetch it. For a police
system that is not a theoretical concern - it is a serious one, and it would
be discovered afterwards rather than prevented.

So addresses found through engines that do not filter are registered with
status PENDING_REVIEW. The scheduler only collects from ACTIVE targets, so
nothing is fetched until an investigator has looked at the address and
approved it. Results from filtering engines may be queued directly, and even
that is opt-in per call.
"""

from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
import asyncio
import logging
import random
import re

logger = logging.getLogger("onion_search")

ONION_V3_RE = re.compile(r"\b([a-z2-7]{56}\.onion)\b", re.IGNORECASE)

# name, URL template, filters_abuse
#
# `filters_abuse` records whether the engine states that it removes abuse
# material from its index. Only Ahmia does. The flag decides whether results
# may be queued for collection or must wait for review.
ENGINES: List[Dict[str, Any]] = [
    {"name": "Ahmia",
     "url": "http://juhanurmihxlp77nkq76byazcldy2hlmovfu2epvl5ankdibsot4csyd.onion/search/?q={query}",
     "filters_abuse": True},
    {"name": "OnionLand",
     "url": "http://3bbad7fauom4d6sgppalyqddsqbf5u5p56b5k5uk2zxsy3d6ey2jobad.onion/search?q={query}",
     "filters_abuse": False},
    {"name": "Torgle",
     "url": "http://iy3544gmoeclh5de6gez2256v6pjh4omhpqdh2wpeeppjtvqmjhkfwad.onion/torgle/?query={query}",
     "filters_abuse": False},
    {"name": "Amnesia",
     "url": "http://amnesia7u5odx5xbwtpnqk3edybgud5bmiagu75bnqx2crntw5kry7ad.onion/search?query={query}",
     "filters_abuse": False},
    {"name": "Kaizer",
     "url": "http://kaizerwfvp5gxu6cppibp7jhcqptavq3iqef66wbxenh6a2fklibdvid.onion/search?q={query}",
     "filters_abuse": False},
    {"name": "Anima",
     "url": "http://anima4ffe27xmakwnseih3ic2y7y3l6e7fucwk4oerdn4odf7k74tbid.onion/search?q={query}",
     "filters_abuse": False},
    {"name": "Tornado",
     "url": "http://tornadoxn3viscgz647shlysdy7ea5zqzwda7hierekeuokh5eh5b3qd.onion/search?q={query}",
     "filters_abuse": False},
    {"name": "TorNet",
     "url": "http://tornetupfu7gcgidt33ftnungxzyfq2pygui5qdoyss34xbgx2qruzid.onion/search?q={query}",
     "filters_abuse": False},
    {"name": "Torland",
     "url": "http://torlbmqwtudkorme6prgfpmsnile7ug2zm4u3ejpcncxuhpu4k2j4kyd.onion/index.php?a=search&q={query}",
     "filters_abuse": False},
    {"name": "FindTor",
     "url": "http://findtorroveq5wdnipkaojfpqulxnkhblymc7aramjzajcvpptd4rjqd.onion/search?q={query}",
     "filters_abuse": False},
    {"name": "Excavator",
     "url": "http://2fd6cemt4gmccflhm6imvdfvli3nf7zn6rfrwpsy7uhxrgbypvwf5fad.onion/search?query={query}",
     "filters_abuse": False},
    {"name": "Onionway",
     "url": "http://oniwayzz74cv2puhsgx4dpjwieww4wdphsydqvf5q7eyz4myjvyw26ad.onion/search.php?s={query}",
     "filters_abuse": False},
    {"name": "Tor66",
     "url": "http://tor66sewebgixwhcqfnp5inzp5x5uohhdy3kvtnyfxc2e5mxiuh34iid.onion/search?q={query}",
     "filters_abuse": False},
    {"name": "OSS",
     "url": "http://3fzh7yuupdfyjhwt3ugzqqof6ulbcl27ecev33knxe3u7goi3vfn2qqd.onion/oss/index.php?search={query}",
     "filters_abuse": False},
    {"name": "Torgol",
     "url": "http://torgolnpeouim56dykfob6jh5r2ps2j73enc42s2um4ufob3ny4fcdyd.onion/?q={query}",
     "filters_abuse": False},
    {"name": "DeepSearches",
     "url": "http://searchgf7gdtauh7bhnbyed4ivxqmuoat3nm6zfrg3ymkq6mtnpye3ad.onion/search?q={query}",
     "filters_abuse": False},
]

ENGINES_BY_NAME = {e["name"].lower(): e for e in ENGINES}

# Hidden services are slow and these are volunteer-run. Queries run with a
# small amount of concurrency and a pause between them rather than all at once.
PER_ENGINE_TIMEOUT = 45.0
MAX_CONCURRENT_ENGINES = 4
INTER_QUERY_DELAY = (0.5, 1.5)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; rv:115.0) Gecko/20100101 Firefox/115.0",
    "Mozilla/5.0 (Windows NT 10.0; rv:109.0) Gecko/20100101 Firefox/115.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:115.0) Gecko/20100101 Firefox/115.0",
]


def extract_onion_links(html: str, engine_host: Optional[str] = None) -> List[str]:
    """
    Pull hidden-service addresses out of a results page.

    Engines differ in markup, so rather than writing sixteen brittle parsers
    this takes every v3 address on the page and drops the engine's own. A
    parser tuned per engine would break silently one engine at a time; this
    degrades to "fewer results" instead of "no results and no error".
    """
    if not html:
        return []

    found: List[str] = []
    seen = set()

    candidates = list(ONION_V3_RE.findall(html))

    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        for anchor in soup.find_all("a", href=True):
            candidates.extend(ONION_V3_RE.findall(anchor["href"]))
    except ImportError:                                       # pragma: no cover
        logger.debug("beautifulsoup4 unavailable; using raw scan only")

    for address in candidates:
        address = address.lower()
        if address in seen:
            continue
        if engine_host and address == engine_host.lower():
            continue        # the engine linking to itself
        seen.add(address)
        found.append(address)

    return found


class OnionSearch:
    """Queries several onion search engines and pools what they return."""

    def __init__(self):
        from config import settings
        self.settings = settings

    def _client_kwargs(self) -> Dict[str, Any]:
        from scrapers.dark_web.tor_manager import tor_manager
        return {
            "timeout": PER_ENGINE_TIMEOUT,
            "follow_redirects": True,
            # socks5h resolves inside Tor; socks5 would leak the lookup.
            "proxy": tor_manager.socks_proxy_url,
            "headers": {"User-Agent": random.choice(USER_AGENTS)},
        }

    @staticmethod
    def _engine_host(engine: Dict[str, Any]) -> Optional[str]:
        match = ONION_V3_RE.search(engine["url"])
        return match.group(1) if match else None

    async def _query_one(self, client, engine: Dict[str, Any],
                         query: str) -> Dict[str, Any]:
        """Query a single engine. A failure here must not stop the others."""
        from urllib.parse import quote_plus

        url = engine["url"].format(query=quote_plus(query))
        try:
            response = await client.get(url)
        except Exception as e:
            logger.info("Engine %s unreachable: %s", engine["name"], e)
            return {"engine": engine["name"], "status": "UNREACHABLE",
                    "error": str(e)[:200], "addresses": []}

        if response.status_code != 200:
            return {"engine": engine["name"], "status": "HTTP_ERROR",
                    "status_code": response.status_code, "addresses": []}

        addresses = extract_onion_links(response.text, self._engine_host(engine))
        return {"engine": engine["name"], "status": "SUCCESS",
                "filters_abuse": engine["filters_abuse"],
                "addresses": addresses, "count": len(addresses)}

    async def search(self, query: str, engines: Optional[List[str]] = None,
                     limit: int = 50) -> Dict[str, Any]:
        """
        Query the engines and pool the addresses they return.

        Each address records which engines returned it, because agreement
        across independent indexes is the closest thing to corroboration
        available at the discovery stage.
        """
        import httpx

        query = (query or "").strip()
        if not query:
            return {"status": "INVALID", "results": [],
                    "message": "A search term is required."}

        if not self.settings.TOR_ENABLED:
            return {"status": "TOR_DISABLED", "results": [],
                    "message": ("Onion search engines are hidden services and "
                                "are only reachable over Tor. Start Tor and set "
                                "TOR_ENABLED=True.")}

        selected = ENGINES
        if engines:
            wanted = {name.lower() for name in engines}
            selected = [e for e in ENGINES if e["name"].lower() in wanted]
            if not selected:
                return {"status": "INVALID", "results": [],
                        "message": f"No known engines named {sorted(wanted)}. "
                                   f"Known: {[e['name'] for e in ENGINES]}"}

        semaphore = asyncio.Semaphore(MAX_CONCURRENT_ENGINES)
        engine_reports: List[Dict[str, Any]] = []

        async with httpx.AsyncClient(**self._client_kwargs()) as client:
            async def run(engine):
                async with semaphore:
                    await asyncio.sleep(random.uniform(*INTER_QUERY_DELAY))
                    return await self._query_one(client, engine, query)

            engine_reports = await asyncio.gather(
                *(run(engine) for engine in selected))

        # Pool: which engines returned each address.
        pooled: Dict[str, Dict[str, Any]] = {}
        for report in engine_reports:
            for address in report.get("addresses", []):
                entry = pooled.setdefault(address, {
                    "onion_address": address,
                    "url": f"http://{address}",
                    "engines": [],
                    "from_filtering_engine": False,
                })
                entry["engines"].append(report["engine"])
                if report.get("filters_abuse"):
                    entry["from_filtering_engine"] = True

        results = sorted(pooled.values(),
                         key=lambda r: (-len(r["engines"]), r["onion_address"]))
        for entry in results:
            entry["engine_count"] = len(entry["engines"])

        responded = [r for r in engine_reports if r["status"] == "SUCCESS"]
        return {
            "status": "SUCCESS" if responded else "ALL_ENGINES_FAILED",
            "query": query,
            "engines_queried": len(selected),
            "engines_responded": len(responded),
            "engine_reports": engine_reports,
            "result_count": len(results),
            "results": results[:limit],
            "note": ("An address returned by several independent indexes is "
                     "more established than one returned by a single engine. "
                     "Nothing here has been fetched; these are candidates."),
        }

    async def register_targets(self, results: List[Dict[str, Any]], query: str,
                               auto_activate_filtered: bool = False) -> Dict[str, Any]:
        """
        Queue discovered services, defaulting to review rather than collection.

        Most onion search engines apply no abuse filtering. Registering their
        output as ACTIVE would hand unattended collection a list of addresses
        nobody has looked at, and this system stores whatever it fetches.
        PENDING_REVIEW targets are invisible to the scheduler, which only
        selects ACTIVE ones.
        """
        from sqlalchemy import select
        from database.postgres import AsyncSessionLocal, Target

        queued, pending, already_known = [], [], []
        async with AsyncSessionLocal() as session:
            for result in results:
                identifier = result["url"]
                existing = (await session.execute(
                    select(Target).where(Target.identifier == identifier)
                )).scalars().first()
                if existing:
                    already_known.append(identifier)
                    continue

                activate = auto_activate_filtered and result.get("from_filtering_engine")
                status = "ACTIVE" if activate else "PENDING_REVIEW"

                session.add(Target(
                    identifier=identifier,
                    source_type="DARK_WEB",
                    label=f"Discovered via {', '.join(result['engines'][:3])}"[:200],
                    priority=2,
                    status=status,
                    discovered_by="ONION_SEARCH",
                ))
                (queued if activate else pending).append(identifier)
            await session.commit()

        return {
            "query": query,
            "activated": queued,
            "pending_review": pending,
            "already_known": already_known,
            "activated_count": len(queued),
            "pending_review_count": len(pending),
            "note": ("Targets held for review are not collected. Approve one "
                     "by setting its status to ACTIVE in Sources once you have "
                     "judged the address worth fetching."),
            "discovered_at": datetime.utcnow().isoformat() + "Z",
        }

    async def discover(self, query: str, engines: Optional[List[str]] = None,
                       limit: int = 50, queue_targets: bool = True,
                       auto_activate_filtered: bool = False) -> Dict[str, Any]:
        found = await self.search(query, engines=engines, limit=limit)
        if found["status"] != "SUCCESS" or not queue_targets:
            return found
        return {**found, "registration": await self.register_targets(
            found["results"], query, auto_activate_filtered)}


onion_search = OnionSearch()
