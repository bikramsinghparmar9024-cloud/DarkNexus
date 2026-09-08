"""
Ethereum wallet forensics.

This module previously answered every query with zeros when no RPC endpoint
was configured:

    {"balance_eth": 0.0, "nonce_or_tx_count": 0, ...}

Nothing had been asked of any blockchain. An investigator reading that
concludes the wallet is empty and drops the line of enquiry, when in fact the
address may hold a substantial balance nobody looked for. "Not checked" and
"checked, holds nothing" are opposite findings, and a system that renders them
identically is worse than one that refuses to answer.

It now queries a real node over JSON-RPC and, when it cannot, says so and
returns no figures at all.

Talking to the node over plain JSON-RPC rather than through web3.py is
deliberate: web3's calls are synchronous, and awaiting them inside an async
request handler blocks the event loop for the whole application while a
remote node thinks about it.
"""

from typing import Any, Dict, Optional
import logging
import re

import httpx

from config import settings

logger = logging.getLogger("eth_tracker")

# Public endpoints that need no API key, so wallet lookups work out of the
# box. Tried in order: a single default is a single point of failure, and
# these come and go - cloudflare-eth.com was the obvious choice until
# Cloudflare retired it, and it now answers every request with an internal
# error. Configure ETH_PROVIDER_URL with an Infura or Alchemy endpoint for
# higher rate limits and archive queries.
PUBLIC_FALLBACK_RPCS = [
    "https://ethereum-rpc.publicnode.com",
    "https://eth.llamarpc.com",
    "https://rpc.ankr.com/eth",
]

ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")
WEI_PER_ETH = 10 ** 18
RPC_TIMEOUT = 20.0


class EthereumTracker:
    """Queries Ethereum state for a suspect address."""

    def __init__(self):
        configured = settings.ETH_PROVIDER_URL
        self.endpoints = [configured] if configured else list(PUBLIC_FALLBACK_RPCS)
        self.using_fallback = not configured

    @staticmethod
    def is_valid_address(address: str) -> bool:
        """Shape only. A well-formed address need not exist on chain."""
        return bool(ADDRESS_RE.match((address or "").strip()))

    async def _rpc(self, client: httpx.AsyncClient, endpoint: str,
                   method: str, params: list) -> Any:
        response = await client.post(
            endpoint,
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        )
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            raise RuntimeError(payload["error"].get("message", "RPC error"))
        return payload.get("result")

    async def get_address_overview(self, eth_address: str) -> Dict[str, Any]:
        """
        Balance and transaction count for an address.

        On any failure the numeric fields are omitted entirely rather than
        defaulted to zero, and `checked` is False with the reason attached.
        A caller cannot then mistake an unanswered query for an empty wallet.
        """
        address = (eth_address or "").strip()

        if not self.is_valid_address(address):
            return {
                "address": address,
                "valid": False,
                "checked": False,
                "network": "Ethereum Mainnet",
                "error": ("Not a well-formed Ethereum address: expected 0x "
                          "followed by 40 hexadecimal characters."),
            }

        failures = []
        async with httpx.AsyncClient(timeout=RPC_TIMEOUT) as client:
            for endpoint in self.endpoints:
                try:
                    balance_hex = await self._rpc(
                        client, endpoint, "eth_getBalance", [address, "latest"])
                    tx_count_hex = await self._rpc(
                        client, endpoint, "eth_getTransactionCount",
                        [address, "latest"])
                    break
                except Exception as e:
                    logger.info("Ethereum node %s unusable: %s", endpoint, e)
                    failures.append(f"{endpoint}: {e}")
            else:
                logger.warning("No Ethereum node answered for %s", address)
                return {
                    "address": address,
                    # The address is well-formed; what failed was reaching a
                    # node. No balance is reported, because none was read.
                    "valid": True,
                    "checked": False,
                    "network": "Ethereum Mainnet",
                    "error": "Could not reach any Ethereum node.",
                    "attempts": failures,
                    "remedy": ("Set ETH_PROVIDER_URL to an Infura or Alchemy "
                               "endpoint in backend/.env, or check outbound "
                               "network access."
                               if self.using_fallback else
                               "Check that ETH_PROVIDER_URL is reachable and "
                               "its rate limit has not been exceeded."),
                }

        try:
            balance_wei = int(balance_hex, 16)
            tx_count = int(tx_count_hex, 16)

            return {
                "address": address,
                "valid": True,
                "checked": True,
                "balance_wei": balance_wei,
                "balance_eth": balance_wei / WEI_PER_ETH,
                "nonce_or_tx_count": tx_count,
                # An address with no outgoing transactions has never spent.
                # Worth stating, because it distinguishes a receiving-only
                # deposit address from an actively used wallet.
                "has_outgoing_activity": tx_count > 0,
                "network": "Ethereum Mainnet",
                "provider": (endpoint if self.using_fallback
                             else "configured provider"),
            }

        except (TypeError, ValueError) as e:
            logger.warning("Malformed Ethereum response for %s: %s", address, e)
            return {
                "address": address,
                "valid": True,
                "checked": False,
                "network": "Ethereum Mainnet",
                "error": f"The node returned something unreadable: {e}",
            }


ethereum_tracker = EthereumTracker()
