"""
Proxy Health Validator.
Tests connectivity and measures response latency using public test endpoints.
"""

import time
import httpx
import logging
from typing import Tuple, Optional

logger = logging.getLogger("proxy_validator")

TEST_ENDPOINT = "http://httpbin.org/ip"
TEST_TIMEOUT = 5.0  # seconds


async def validate_proxy(proxy_url: str) -> Tuple[bool, float, Optional[str]]:
    """
    Test proxy functionality and measure round-trip latency.
    Returns: (is_alive, latency_ms, public_ip_or_error)
    """
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(proxy=proxy_url, timeout=TEST_TIMEOUT) as client:
            resp = await client.get(TEST_ENDPOINT)
            latency_ms = (time.perf_counter() - start) * 1000.0
            if resp.status_code == 200:
                data = resp.json()
                return True, round(latency_ms, 2), data.get("origin")
            else:
                return False, round(latency_ms, 2), f"Status {resp.status_code}"
    except Exception as e:
        latency_ms = (time.perf_counter() - start) * 1000.0
        return False, round(latency_ms, 2), str(e)
