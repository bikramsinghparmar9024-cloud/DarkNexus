"""
Cryptocurrency Forensics & Wallet Tracking Endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from blockchain.bitcoin_tracker import bitcoin_tracker
from blockchain.ethereum_tracker import ethereum_tracker
from auth.rbac import require_investigator

router = APIRouter(
    prefix="/api/blockchain", tags=["Blockchain Forensics"],
    # Every endpoint on this router requires authentication.
    dependencies=[Depends(require_investigator)],
)


class WalletQueryRequest(BaseModel):
    address: str
    crypto_type: str = "BTC"  # BTC or ETH


@router.post("/lookup")
async def lookup_wallet(req: WalletQueryRequest):
    """Query balance and on-chain activity for a suspect cryptocurrency wallet."""
    crypto = req.crypto_type.upper()
    if crypto == "BTC":
        overview = await bitcoin_tracker.get_address_overview(req.address)
        txs = await bitcoin_tracker.get_recent_transactions(req.address, limit=5)
        return {
            "overview": overview,
            "recent_transactions": txs
        }
    elif crypto == "ETH":
        overview = await ethereum_tracker.get_address_overview(req.address)
        return {
            "overview": overview,
            "recent_transactions": []
        }
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported cryptocurrency type: {req.crypto_type}")
