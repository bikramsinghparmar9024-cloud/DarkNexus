"""
Free and Residential Proxy Fetcher.
Retrieves working HTTP/SOCKS proxies from multiple public proxy APIs.
"""

import httpx
import logging
from typing import List

logger = logging.getLogger("proxy_sources")

# Each source is paired with the scheme its entries actually use. The lists
# publish bare "ip:port" lines carrying no protocol, and every one of them was
# previously assumed to be HTTP - so an entire file of SOCKS5 proxies was
# imported labelled "http://". Those entries cannot work: the client speaks
# HTTP proxy protocol to a SOCKS listener and the connection fails, or hangs.
PUBLIC_PROXIES_URLS = [
    # This endpoint is asked for protocol://ip:port, so it labels its own.
    ("https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies"
     "&proxy_format=protocolipport&format=text", None),
    ("https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/socks5.txt",
     "socks5"),
    ("https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
     "http"),
]


async def fetch_public_proxies(limit: int = 50) -> List[str]:
    """Fetch raw proxy list from public repository endpoints."""
    proxies = set()
    async with httpx.AsyncClient(timeout=10.0) as client:
        for url, scheme in PUBLIC_PROXIES_URLS:
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    lines = resp.text.strip().splitlines()
                    for line in lines:
                        clean_line = line.strip()
                        if not clean_line or clean_line.startswith("#"):
                            continue
                        if "://" not in clean_line:
                            if not scheme:
                                # An unlabelled entry from a source that was
                                # supposed to label its own is not safe to
                                # guess at; guessing is what caused this bug.
                                continue
                            clean_line = f"{scheme}://{clean_line}"
                        proxies.add(clean_line)
                        if len(proxies) >= limit:
                            break
            except Exception as e:
                logger.debug(f"Failed fetching proxies from {url}: {e}")
            if len(proxies) >= limit:
                break

    return list(proxies)
