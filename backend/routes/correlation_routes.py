"""
Correlation & Pattern Analysis API.

Surfaces network-level findings that no single intercept contains: hotspots,
identifier reuse across platforms, device linkage, operating hours, and
emerging trends.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from ai.correlation import correlation_engine
from ai.semantic_correlation import semantic_correlator
from ai.actor_dossier import dossier_builder
from ai.network_analysis import network_analyzer
from evidence.audit_log import record_audit_event
from auth.rbac import require_investigator

router = APIRouter(
    prefix="/api/correlation", tags=["Correlation & Pattern Analysis"],
    # Every endpoint on this router requires authentication.
    dependencies=[Depends(require_investigator)],
)


@router.get("/intelligence-picture")
async def intelligence_picture(
    days: Optional[int] = Query(None, description="Restrict to the last N days"),
    limit: int = Query(2000, ge=1, le=10000),
):
    """Full correlation pass across collected intelligence."""
    result = await correlation_engine.build_intelligence_picture(days=days, limit=limit)
    await record_audit_event(
        action="RUN_CORRELATION_ANALYSIS",
        resource="correlation",
        details=f"Correlation over {result.get('scope', {}).get('record_count', 0)} records",
    )
    return result


@router.get("/hotspots")
async def hotspots(days: Optional[int] = None, limit: int = 2000):
    """Ranked geographic concentrations, from text mentions and photograph GPS."""
    picture = await correlation_engine.build_intelligence_picture(days=days, limit=limit)
    if picture.get("status") != "SUCCESS":
        return picture
    return {"scope": picture["scope"], **picture["hotspots"]}


@router.get("/identifier-links")
async def identifier_links(days: Optional[int] = None, limit: int = 2000):
    """Wallets, phones, handles and UPI IDs that tie separate records together."""
    picture = await correlation_engine.build_intelligence_picture(days=days, limit=limit)
    if picture.get("status") != "SUCCESS":
        return picture
    return {"scope": picture["scope"], **picture["identifier_links"]}


@router.get("/key-judgements")
async def key_judgements(days: Optional[int] = None, limit: int = 2000):
    """Plain-language conclusions, each with its supporting evidence."""
    picture = await correlation_engine.build_intelligence_picture(days=days, limit=limit)
    if picture.get("status") != "SUCCESS":
        return picture
    return {
        "generated_at": picture["generated_at"],
        "scope": picture["scope"],
        "key_judgements": picture["key_judgements"],
    }


@router.get("/semantic")
async def semantic_picture(
    days: Optional[int] = Query(None, description="Restrict to the last N days"),
    limit: int = Query(500, ge=2, le=2000),
):
    """
    Vector-space pattern detection: mirrors, clusters and scored links.

    Complements /intelligence-picture, which matches identifiers literally.
    This pass finds records that describe the same activity in different
    words. Runs entirely on the local embedding model - no evidence text is
    sent to any external service.
    """
    result = await semantic_correlator.build(days=days, limit=limit)
    await record_audit_event(
        action="RUN_SEMANTIC_CORRELATION",
        resource="correlation",
        details=(f"Semantic pass over {result.get('records_embedded', 0)} "
                 f"embedded records"),
    )
    return result


@router.get("/clusters")
async def clusters(days: Optional[int] = None, limit: int = 500):
    """Groups of records describing the same activity, by embedding distance."""
    picture = await semantic_correlator.build(days=days, limit=limit)
    return {
        "generated_at": picture["generated_at"],
        "records_embedded": picture["records_embedded"],
        **picture.get("clusters", {}),
    }


@router.get("/links")
async def semantic_links(days: Optional[int] = None, limit: int = 500):
    """
    Pairwise connections between records, strongest first.

    A LINK rests on a shared identifier, device or wallet. A LEAD rests on
    wording alone and is a line of enquiry, not an established connection.
    """
    picture = await semantic_correlator.build(days=days, limit=limit)
    return {
        "generated_at": picture["generated_at"],
        "records_embedded": picture["records_embedded"],
        "links": picture.get("links", []),
        "summary": picture.get("summary", {}),
    }


@router.get("/actors")
async def actors(
    days: Optional[int] = Query(None, description="Restrict to the last N days"),
    limit: int = Query(1000, ge=1, le=5000),
    min_records: int = Query(1, ge=1, description="Hide actors seen fewer times"),
):
    """
    Intelligence organised by person rather than by page.

    Each actor merges the identifiers that keep appearing together - handles,
    phones, wallets, PGP keys, camera signatures - into one profile carrying
    substances, districts, platforms, activity window and an inferred role.
    `identity_confidence` says how well evidenced the merge is; a join resting
    on a single record is reported as WEAK.
    """
    result = await dossier_builder.build(days=days, limit=limit,
                                         min_records=min_records)
    await record_audit_event(
        action="BUILD_ACTOR_DOSSIERS",
        resource="correlation",
        details=f"Profiled {len(result.get('actors', []))} actors",
    )
    return result


@router.get("/actors/{actor_id:path}")
async def actor_detail(actor_id: str, days: Optional[int] = None,
                       limit: int = 1000):
    """One actor's dossier, by actor id (e.g. `wallet:bc1q...`)."""
    result = await dossier_builder.build(days=days, limit=limit)
    for actor in result.get("actors", []):
        if actor["actor_id"] == actor_id:
            return actor
    return {"status": "NOT_FOUND", "actor_id": actor_id,
            "message": "No actor with that identifier in the current window."}


@router.get("/network")
async def network(
    days: Optional[int] = Query(None),
    limit: int = Query(1000, ge=1, le=5000),
    hard_evidence_only: bool = Query(
        False, description="Build edges only from shared identifiers, "
                           "excluding circumstantial leads"),
):
    """
    Who holds the network together.

    Ranks actors by betweenness centrality and flags articulation points -
    those whose removal splits the observed network into disconnected pieces.
    Position, not volume: the busiest handle is usually a replaceable retail
    seller, while the broker between two clusters is not.
    """
    result = await network_analyzer.analyse(
        days=days, limit=limit, hard_evidence_only=hard_evidence_only)
    await record_audit_event(
        action="RUN_NETWORK_ANALYSIS",
        resource="correlation",
        details=(f"Centrality over {result.get('nodes', 0)} actors, "
                 f"{result.get('edges', 0)} edges"),
    )
    return result
