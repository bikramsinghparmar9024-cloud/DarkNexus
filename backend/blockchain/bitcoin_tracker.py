"""
Bitcoin Wallet & Transaction Tracker.
Integrates with public Blockstream Esplora API (https://blockstream.info/api)
to trace BTC addresses harvested from illicit marketplace listings.
"""

from typing import Dict, Any, List, Optional
import httpx
import logging
from config import settings

logger = logging.getLogger("btc_tracker")


class BitcoinTracker:
    """Queries public blockchain data for suspect BTC wallet addresses."""

    def __init__(self):
        self.base_url = settings.BLOCKSTREAM_API_URL

    async def get_address_overview(self, btc_address: str) -> Dict[str, Any]:
        """Fetch balance, confirmed transaction counts, and total received sats."""
        url = f"{self.base_url}/address/{btc_address}"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    chain_stats = data.get("chain_stats", {})
                    funded = chain_stats.get("funded_txo_sum", 0) / 1e8
                    spent = chain_stats.get("spent_txo_sum", 0) / 1e8
                    balance = funded - spent

                    return {
                        "address": btc_address,
                        "valid": True,
                        "total_received_btc": round(funded, 6),
                        "current_balance_btc": round(balance, 6),
                        "total_tx_count": chain_stats.get("tx_count", 0),
                        "network": "Bitcoin Mainnet"
                    }
                else:
                    return {"address": btc_address, "valid": False, "error": f"API error {resp.status_code}"}
        except Exception as e:
            logger.error(f"Error checking Bitcoin address {btc_address}: {e}")
            return {"address": btc_address, "valid": False, "error": str(e)}

    async def get_recent_transactions(self, btc_address: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetch recent transaction hashes and timestamps for an address."""
        url = f"{self.base_url}/address/{btc_address}/txs"
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    txs = resp.json()
                    results = []
                    for tx in txs[:limit]:
                        results.append({
                            "txid": tx.get("txid"),
                            "confirmed": tx.get("status", {}).get("confirmed", False),
                            "block_time": tx.get("status", {}).get("block_time"),
                            "fee_sats": tx.get("fee", 0),
                            "vin_count": len(tx.get("vin", [])),
                            "vout_count": len(tx.get("vout", []))
                        })
                    return results
        except Exception as e:
            logger.error(f"Error fetching txs for {btc_address}: {e}")
        return []


bitcoin_tracker = BitcoinTracker()
