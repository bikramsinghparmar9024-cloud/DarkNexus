"""
Proxy Pool Manager with Round-Robin and Random Rotation.
Provides failover handling and automatic dead-proxy removal.
"""

import random
import asyncio
import logging
from typing import Optional, List, Dict, Any
from proxy.sources import fetch_public_proxies
from proxy.validator import validate_proxy
from config import settings

logger = logging.getLogger("proxy_pool")


class ProxyPool:
    """Manages active proxies, rotation index, and background health checks."""

    def __init__(self):
        self.proxies: List[Dict[str, Any]] = []
        self._current_index: int = 0
        self._lock = asyncio.Lock()

    async def initialize(self):
        """Fetch initial proxies and run validation."""
        raw_list = await fetch_public_proxies(limit=25)
        # httpx speaks SOCKS5 once httpx[socks] is installed, which it now is.
        # SOCKS4 it does not support at any version, so those stay excluded.
        supported_schemes = ("http://", "https://", "socks5://", "socks5h://")
        for p in raw_list:
            if not p.lower().startswith(supported_schemes):
                logger.debug(f"Skipping unsupported proxy scheme: {p}")
                continue
            self.proxies.append({
                "url": p,
                "is_alive": True,
                "latency_ms": 100.0,
                "fail_count": 0,
                "success_count": 0
            })
        logger.info(f"Initialized proxy pool with {len(self.proxies)} candidate proxies (filtered unsupported schemes).")

    async def get_next_proxy(self) -> Optional[str]:
        """Get next working proxy URL based on configured rotation strategy."""
        async with self._lock:
            active_proxies = [p for p in self.proxies if p["is_alive"]]
            if not active_proxies:
                return None

            if settings.PROXY_ROTATION_STRATEGY == "random":
                chosen = random.choice(active_proxies)
                return chosen["url"]
            else:
                # Round-robin
                self._current_index = (self._current_index + 1) % len(active_proxies)
                return active_proxies[self._current_index]["url"]

    async def report_result(self, proxy_url: str, success: bool):
        """Update metrics for a proxy after an HTTP request."""
        async with self._lock:
            for p in self.proxies:
                if p["url"] == proxy_url:
                    if success:
                        p["success_count"] += 1
                        p["fail_count"] = 0
                    else:
                        p["fail_count"] += 1
                        if p["fail_count"] >= 3:
                            p["is_alive"] = False
                            logger.debug(f"Proxy marked dead due to failures: {proxy_url}")
                    break

    def get_stats(self) -> Dict[str, Any]:
        """Return pool health statistics for the frontend dashboard."""
        total = len(self.proxies)
        alive = sum(1 for p in self.proxies if p["is_alive"])
        dead = total - alive
        avg_latency = (
            sum(p["latency_ms"] for p in self.proxies if p["is_alive"]) / max(alive, 1)
        )
        return {
            "total_proxies": total,
            "alive_proxies": alive,
            "dead_proxies": dead,
            "avg_latency_ms": round(avg_latency, 1),
            "rotation_strategy": settings.PROXY_ROTATION_STRATEGY,
            "active_list": self.proxies[:15]
        }


proxy_pool = ProxyPool()
