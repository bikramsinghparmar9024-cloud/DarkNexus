"""
Dashboard Aggregated Metrics & Pipeline Intelligence Endpoints.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Dict, Any

from database.postgres import get_db, ScrapedData, Target, ScrapeJob, CryptoWalletIntel
from database.graph_db import graph_manager
from proxy.pool import proxy_pool
from auth.rbac import require_any_authenticated

router = APIRouter(
    prefix="/api/dashboard", tags=["Dashboard"],
    # Every endpoint on this router requires authentication.
    dependencies=[Depends(require_any_authenticated)],
)


@router.get("/stats")
async def get_dashboard_stats(db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """Retrieve high-level summary statistics across all 3 ingestion pipelines."""
    # Total intelligence records
    total_records = (await db.execute(select(func.count(ScrapedData.id)))).scalar() or 0

    # Pipeline breakdown
    surface_count = (await db.execute(
        select(func.count(ScrapedData.id)).where(ScrapedData.source_type == "SURFACE_WEB")
    )).scalar() or 0

    dark_count = (await db.execute(
        select(func.count(ScrapedData.id)).where(ScrapedData.source_type == "DARK_WEB")
    )).scalar() or 0

    telegram_count = (await db.execute(
        select(func.count(ScrapedData.id)).where(ScrapedData.source_type == "TELEGRAM")
    )).scalar() or 0

    # High / Severe threat alerts
    alert_count = (await db.execute(
        select(func.count(ScrapedData.id)).where(ScrapedData.threat_level.in_(["HIGH", "SEVERE"]))
    )).scalar() or 0

    # Target count
    target_count = (await db.execute(select(func.count(Target.id)))).scalar() or 0

    # Crypto wallets tracked
    wallet_count = (await db.execute(select(func.count(CryptoWalletIntel.id)))).scalar() or 0

    # Proxy stats
    proxy_stats = proxy_pool.get_stats()

    return {
        "total_intelligence_records": total_records,
        "threat_alerts": alert_count,
        "active_targets": target_count,
        "crypto_wallets_tracked": wallet_count,
        "pipelines": {
            "surface_web": {
                "records": surface_count,
                "status": "OPERATIONAL",
                "label": "Surface Web (Playwright Stealth)"
            },
            "dark_web": {
                "records": dark_count,
                "status": "OPERATIONAL",
                "label": "Dark/Deep Web (.onion Tor)"
            },
            "encrypted_messaging": {
                "records": telegram_count,
                "status": "OPERATIONAL",
                "label": "Telegram (MTProto/Preview)"
            }
        },
        "proxies": proxy_stats
    }


@router.get("/network-graph")
async def get_network_graph(
    limit: int = 300,
    min_observations: int = 1,
    include_rejected: bool = False,
):
    """
    Nodes and edges formatted for Cytoscape.js.

    Edges an investigator has rejected are excluded by default and can be
    brought back with `include_rejected` for audit - they are hidden, never
    deleted. The response carries `shown_edge_count` and `total_edge_count`
    so the interface can say how much of the graph is on screen instead of
    silently stopping at the limit.
    """
    return await graph_manager.get_network_graph(
        limit=limit, min_observations=min_observations,
        include_rejected=include_rejected)


@router.get("/network-graph/node/{node_key:path}")
async def get_graph_node(node_key: str, snippet_chars: int = 400):
    """
    What a graph node is, and the passages of collected text behind it.

    Clicking a node showed only its label and type, so an investigator could
    see that a substance or a suspect was in the graph but not where it had
    been found. This returns every record that produced an edge touching the
    node, with the text around the actual match - and says explicitly when a
    passage is the top of the document rather than the point of the match.
    """
    from fastapi import HTTPException

    result = await graph_manager.describe_node(node_key, snippet_chars=snippet_chars)
    if result.get("status") == "NOT_FOUND":
        raise HTTPException(status_code=404, detail=result["message"])
    return result


@router.get("/activity")
async def get_recent_activity(db: AsyncSession = Depends(get_db)):
    """Fetch the latest 10 scraped intelligence records."""
    stmt = select(ScrapedData).order_by(ScrapedData.created_at.desc()).limit(10)
    records = (await db.execute(stmt)).scalars().all()

    return [
        {
            "id": r.id,
            "source_type": r.source_type,
            "url": r.source_url,
            "snippet": (r.cleaned_text or r.raw_content)[:120],
            "threat_level": r.threat_level,
            "sha256": r.sha256_hash[:16] + "...",
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else "Just now"
        }
        for r in records
    ]
