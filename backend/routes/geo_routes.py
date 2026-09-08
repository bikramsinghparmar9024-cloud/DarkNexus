"""
Geospatial Intelligence, Border Distance Matrix, & Section 65B Endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database.postgres import get_db, ScrapedData
from ai.geo_resolver import resolve_location, get_all_punjab_hotspots
from evidence.section_65b import generate_section_65b_certificate
from evidence.audit_log import record_audit_event
from auth.rbac import require_any_authenticated

router = APIRouter(
    prefix="/api/geo", tags=["Geospatial & Border Intelligence"],
    # Every endpoint on this router requires authentication.
    dependencies=[Depends(require_any_authenticated)],
)


class ResolveLocationRequest(BaseModel):
    location_name: str


class Section65BRequest(BaseModel):
    investigator_name: str
    investigator_badge: str
    department: Optional[str] = "Punjab State Narcotics Control Bureau"
    case_fir_number: str
    record_ids: List[int]


@router.get("/hotspots")
async def get_punjab_hotspots():
    """Retrieve all Punjab coordinates, border markers, and 15km danger zone flags."""
    return get_all_punjab_hotspots()


@router.post("/resolve")
async def resolve_place_name(req: ResolveLocationRequest):
    """Lookup GPS coordinates and border proximity for a Punjab place name."""
    result = resolve_location(req.location_name)
    if not result:
        raise HTTPException(status_code=404, detail=f"Location '{req.location_name}' not found in Punjab geospatial database.")
    return result


@router.get("/border-alerts")
async def get_border_corridor_alerts(db: AsyncSession = Depends(get_db)):
    """
    Records the analyser placed inside the border corridor.

    This endpoint used to substring-match the words "border", "attari" and so
    on against raw page text, which meant an encyclopedia article mentioning
    the word "border" once in 200 KB was returned as border transit chatter at
    MEDIUM threat. It bypassed every safeguard in the pipeline: no resolved
    distance, no narcotics gate, no speech-act check.

    It now reports only what the analyser resolved. A record appears if its
    geo markers place it within the corridor, and each entry carries its
    disposition, because a seizure report near Attari and an offer near Attari
    are not the same intelligence product and must not be listed as though
    they were.
    """
    from ai.enrichment import get_analysis
    from ai.geo_resolver import BORDER_PROXIMITY_THRESHOLD_KM

    stmt = select(ScrapedData).order_by(ScrapedData.created_at.desc()).limit(200)
    records = (await db.execute(stmt)).scalars().all()

    alerts = []
    for r in records:
        analysis = get_analysis(r)
        markers = [m for m in (analysis.get("geo_markers") or [])
                   if m.get("in_critical_border_corridor")]
        if not markers:
            continue

        threat = analysis.get("threat") or {}
        act = (analysis.get("speech_act") or {})
        has_narcotics = threat.get("narcotics_evidence", False)

        # Disposition, not a single undifferentiated "alert" stream.
        if not has_narcotics:
            disposition = "NON_NARCOTICS"
            note = ("located in the corridor, but no narcotics indicator was "
                    "found; retained for context only")
        elif act.get("act") == "REPORT":
            disposition = "REPORTING"
            note = ("third-party reporting of activity in the corridor - a "
                    "seizure, court record or news account, not live activity")
        elif act.get("act") in ("OFFER", "DEMAND"):
            disposition = "OPERATIONAL"
            note = f"reads as {act['act'].lower()} activity inside the corridor"
        else:
            disposition = "UNCLASSIFIED"
            note = "no speech-act markers found; disposition undetermined"

        nearest = min(markers, key=lambda m: m.get("distance_to_border_km", 9999))
        alerts.append({
            "id": r.id,
            "source_type": r.source_type,
            "source_url": r.source_url,
            "corridors": sorted({m["location"] for m in markers if m.get("location")}),
            "nearest_location": nearest.get("location"),
            "distance_to_border_km": nearest.get("distance_to_border_km"),
            "threat_level": threat.get("threat_level", r.threat_level),
            "risk_score": threat.get("risk_score", 0),
            "disposition": disposition,
            "disposition_note": note,
            "speech_act": act.get("act"),
            "narcotics_evidence": has_narcotics,
            "snippet": (r.cleaned_text or "")[:160],
            "sha256": (r.sha256_hash or "")[:16] + "...",
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else None,
        })

    alerts.sort(key=lambda a: (a["disposition"] != "OPERATIONAL", -a["risk_score"]))
    counts: dict = {}
    for a in alerts:
        counts[a["disposition"]] = counts.get(a["disposition"], 0) + 1

    return {
        "border_threshold_km": BORDER_PROXIMITY_THRESHOLD_KM,
        "records_examined": len(records),
        "total_in_corridor": len(alerts),
        "by_disposition": counts,
        "operational_count": counts.get("OPERATIONAL", 0),
        "method": ("resolved geo markers from the analysis pipeline; no "
                   "keyword matching against page text"),
        "alerts": alerts,
    }


@router.post("/generate-section-65b")
async def generate_65b_certificate(req: Section65BRequest, db: AsyncSession = Depends(get_db)):
    """Generate official Indian Evidence Act Section 65B legal court certificate."""
    stmt = select(ScrapedData).where(ScrapedData.id.in_(req.record_ids))
    records = (await db.execute(stmt)).scalars().all()

    if not records:
        raise HTTPException(status_code=400, detail="No records found for given IDs.")

    records_data = [
        {
            "source_type": r.source_type,
            "source_url": r.source_url,
            "sha256_hash": r.sha256_hash,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else None
        }
        for r in records
    ]

    html_content = generate_section_65b_certificate(
        investigator_name=req.investigator_name,
        investigator_badge=req.investigator_badge,
        department=req.department or "Punjab State Narcotics Control Bureau",
        case_fir_number=req.case_fir_number,
        evidence_records=records_data
    )

    await record_audit_event(
        action="EXPORT_SECTION_65B_CERTIFICATE",
        resource=req.case_fir_number,
        details=f"Generated Section 65B Certificate for {len(records)} evidence items"
    )

    return HTMLResponse(content=html_content, status_code=200)
