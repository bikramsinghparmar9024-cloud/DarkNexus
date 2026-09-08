"""
Tor SOCKS5 & Control Circuit Manager.
Uses `stem` to signal Tor daemon (Signal.NEWNYM) to rotate exit nodes and obtain fresh circuits.
Provides socks5h:// proxy strings for DNS-leak-safe .onion routing.
"""

import logging
from typing import Optional, Dict, Any
import httpx
from config import settings

logger = logging.getLogger("tor_manager")

try:
    from stem import Signal
    from stem.control import Controller
except ImportError:
    Signal = None
    Controller = None


class TorManager:
    """Manages Tor daemon status and circuit rotation."""

    def __init__(self):
        self.socks_port = settings.TOR_SOCKS_PORT
        self.control_port = settings.TOR_CONTROL_PORT
        self.control_password = settings.TOR_CONTROL_PASSWORD
        self.host = settings.TOR_HOST
        # socks5h keeps the .onion lookup inside Tor; socks5 would resolve it
        # locally and leak which hidden service is being visited.
        self.socks_proxy_url = f"socks5h://{self.host}:{self.socks_port}"

    def rotate_circuit(self) -> bool:
        """Signal Tor controller to establish a brand new circuit and exit IP."""
        if not Controller or not Signal:
            logger.warning("stem library not available. Skipping circuit rotation.")
            return False

        try:
            with Controller.from_port(address=self.host,
                                     port=self.control_port) as controller:
                if self.control_password:
                    controller.authenticate(password=self.control_password)
                else:
                    controller.authenticate()  # Uses cookie authentication by default
                controller.signal(Signal.NEWNYM)
                logger.info("Tor circuit rotated successfully (Signal.NEWNYM). Fresh exit node acquired.")
                return True
        except Exception as e:
            logger.warning(f"Failed to signal Tor circuit rotation on port {self.control_port}: {e}")
            return False

    async def check_connection(self) -> Dict[str, Any]:
        """Test whether Tor SOCKS proxy is reachable by checking Tor Project check endpoint."""
        test_url = "https://check.torproject.org/api/ip"
        try:
            async with httpx.AsyncClient(proxy=self.socks_proxy_url, timeout=15.0) as client:
                resp = await client.get(test_url)
                if resp.status_code == 200:
                    data = resp.json()
                    is_tor = data.get("IsTor", False)
                    ip = data.get("IP", "")
                    return {
                        "connected": True,
                        "is_tor": is_tor,
                        "ip": ip,
                        "message": "Connected through Tor network" if is_tor else "Connected via proxy, but not recognized as Tor"
                    }
        except Exception as e:
            return {
                "connected": False,
                "is_tor": False,
                "ip": None,
                "message": f"Tor connection failed: {e}. Ensure Tor daemon or Tor Browser is running on port {self.socks_port}."
            }


tor_manager = TorManager()
