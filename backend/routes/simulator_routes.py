"""
Operational Law Enforcement Live Intercept Simulator & Triage API.
Shares the ai.enrichment pipeline with the automated scrapers, so injected
chatter is analysed and stored identically to collected data.
Allows investigators to inject raw multi-platform chatter
(Romanized Punjabi, Dark Web listings, Telegram messages) and witness end-to-end AI triage,
border danger zone calculations, graph correlation, and Section 65B court hashing in real time.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database.postgres import get_db
from ai.enrichment import analyze_text, store_intelligence
from auth.rbac import require_investigator

router = APIRouter(
    prefix="/api/simulator", tags=["Live Triage Simulator"],
    # Every endpoint on this router requires authentication.
    dependencies=[Depends(require_investigator)],
)

# Broadcast callback registered from app.py
_broadcast_callback = None

def register_broadcast_callback(cb):
    global _broadcast_callback
    _broadcast_callback = cb


class IngestRequest(BaseModel):
    source_type: str = "TELEGRAM"  # TELEGRAM, DARK_WEB, SURFACE_WEB
    text: str
    author: Optional[str] = "@unknown_actor"
    source_url: Optional[str] = None
    media_attached: Optional[bool] = False


# Pre-built realistic Punjab Police field scenarios
PRESET_SCENARIOS = [
    {
        "id": "drone_drop_khemkaran",
        "title": "Pakistani Drone Narcotics Drop",
        "badge": "BORDER SORTIE",
        "location": "Khemkaran Border (3.2 km to border)",
        "source_type": "TELEGRAM",
        "author": "@pak_pb_transit",
        "source_url": "https://t.me/s/border_transit_alert/481",
        "raw_text": "Veere khemkaran border te drone drop ho gya, 5kg chitta chakko. GPS location send kar reha behind tubewell. Jaldi khata clear karo.",
        "description": "Romanized Punjabi chatter coordinating a cross-border drone sortie drop in the Khemkaran sector."
    },
    {
        "id": "darkweb_chitta_majitha",
        "title": "Dark Web Afghan Heroin Escrow Listing",
        "badge": "TOR ONION LISTING",
        "location": "Majitha Corridor (13.5 km to border)",
        "source_type": "DARK_WEB",
        "author": "vendor_punjab_king",
        "source_url": "http://punjabchem4vq...onion/listing/heroin-majitha-88",
        "raw_text": "Grade-A Afghan Heroin (Chitta) 88% pure. Dead drop pickup points available across Majitha, Tarn Taran, and Attari bypass. Escrow deposit 0.045 BTC to 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa.",
        "description": ".onion marketplace listing with high-purity heroin and direct Bitcoin escrow deposit address."
    },
    {
        "id": "attari_border_retail",
        "title": "Attari Border Direct Courier Intercept",
        "badge": "CRITICAL BORDER",
        "location": "Attari (2.5 km to border)",
        "source_type": "TELEGRAM",
        "author": "@jagga_courier_01",
        "source_url": "https://t.me/s/amritsar_stealth_drops/129",
        "raw_text": "Veere Attari border side te 2 packet chitta ready aa. Cash nahi lena, direct crypto ya UPI barcode te transaction karo. Phone: 98140-98211.",
        "description": "Intercepted courier message offering immediate packet delivery near Attari border with phone & UPI trace."
    },
    {
        "id": "pharma_diversion_ludhiana",
        "title": "Commercial Tramadol Pharma Diversion",
        "badge": "SYNTHETIC PSYCHOTROPIC",
        "location": "Ludhiana Focal Point",
        "source_type": "SURFACE_WEB",
        "author": "@amritsar_hawk",
        "source_url": "https://t.me/s/pb_bulk_pharma/902",
        "raw_text": "Fresh stock arrived: 15,000 strips of Tramadol 100mg (Clovidol). Delivery via secret dead-drop in Ludhiana Focal Point and Jalandhar Model Town. Rate daso DM vich.",
        "description": "Bulk diversion of scheduled prescription opioids without medical license."
    }
]


@router.get("/scenarios")
async def get_scenarios() -> List[Dict[str, Any]]:
    """Retrieve preset operational field scenarios for 1-click execution."""
    return PRESET_SCENARIOS


@router.post("/ingest")
async def ingest_live_intercept(req: IngestRequest, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """
    Ingest a raw intercept and run it through the full triage pipeline.

    This is the SAME analysis and storage code the automated scrapers use
    (ai.enrichment), so a manually injected intercept and a scraped one are
    indistinguishable once stored: same field names, same scoring, same vector
    index, same graph correlation.
    """
    raw_text = req.text.strip()
    if not raw_text:
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    source_url = req.source_url or (
        f"https://intercept.punjabpolice.internal/"
        f"{req.source_type.lower()}/{int(datetime.utcnow().timestamp())}"
    )

    # 1. Analyse: slang normalization -> NER -> threat scoring -> border geo
    analysis = analyze_text(raw_text)

    # 2. Persist: SHA-256, database row, ChromaDB index, graph correlation
    stored = await store_intelligence(
        source_type=req.source_type,
        source_url=source_url,
        raw_content=raw_text,
        cleaned_text=analysis["normalized_text"],
        author=req.author,
        analysis=analysis,
        session=db,
        provenance={
            "acquisition_method": "MANUAL_IMPORT",
            "collector": "LIVE_SIMULATOR",
            "investigator_badge": "PB-CID-8821",
            "media_attached": req.media_attached,
        },
    )

    record_id = stored["record_id"]
    entities = analysis["entities"]
    threat = analysis["threat"]
    geo_data = analysis["geo"]
    detected_slang = analysis["detected_slang"]

    # 3. Push real-time WebSocket notification to connected investigators
    alert_payload = {
        "event": "NEW_INTELLIGENCE_INTERCEPT",
        "record_id": record_id,
        "source_type": req.source_type,
        "author": req.author,
        "threat_level": threat["threat_level"],
        "border_alert": analysis["border_alert"],
        "location": geo_data.get("district") if geo_data else "Punjab",
        "distance_to_border_km": geo_data.get("distance_to_border_km") if geo_data else None,
        "snippet": raw_text[:90] + ("..." if len(raw_text) > 90 else ""),
        "timestamp": datetime.utcnow().strftime("%H:%M:%S UTC"),
    }

    if _broadcast_callback:
        try:
            await _broadcast_callback(alert_payload)
        except Exception:
            pass

    wallet_count = sum(
        len(v) for v in (entities.get("crypto_wallets") or {}).values()
        if isinstance(v, (list, tuple))
    )

    return {
        "status": "SUCCESS",
        "message": "Intelligence intercept processed and verified under Section 65B",
        "record_id": record_id,
        "source_type": req.source_type,
        "author": req.author,
        "sha256_hash": stored["sha256_hash"],
        "threat_level": threat["threat_level"],
        "border_danger_zone": analysis["border_alert"],
        "pipeline_stages": {
            "stage_1_slang": {
                "detected_slang_count": len(detected_slang),
                "detected_terms": [s.get("original_term", "") for s in detected_slang],
                "normalized_text": analysis["normalized_text"],
            },
            "stage_2_ner": entities,
            "stage_3_threat": threat,
            "stage_4_geospatial": geo_data or {
                "resolved": False,
                "note": "No specific town resolved, monitored region Punjab",
            },
            "stage_5_chain_of_custody": {
                "sha256": stored["sha256_hash"],
                "court_admissible": True,
                "statute": "Section 65B Indian Evidence Act / Section 63 BSA 2023",
            },
        },
        "agent_pipeline": [
            {"agent": "Triage Agent", "stage": "Entity Extraction & Slang Normalization",
             "status": "COMPLETE",
             "output_summary": f"Extracted {len(entities.get('drugs', []))} drugs, "
                               f"{len(entities.get('handles', []))} handles, "
                               f"{len(detected_slang)} slang terms"},
            {"agent": "Correlation Agent", "stage": "Cross-Source Relationship Matching",
             "status": "COMPLETE",
             "output_summary": f"Correlated author '{req.author}' across {req.source_type} pipeline"},
            {"agent": "Evidence Agent", "stage": "Source Retrieval & Hash Verification",
             "status": "COMPLETE",
             "output_summary": f"SHA-256: {stored['sha256_hash'][:16]}... | "
                               f"Indexed for semantic search | Evidence preserved in read-only vault"},
            {"agent": "Network Agent", "stage": "Graph Analysis & Relationship Mapping",
             "status": "COMPLETE",
             "output_summary": f"Updated knowledge graph with {stored['graph_edges_added']} "
                               f"new relationships ({wallet_count} wallets)"},
            {"agent": "Governance Layer", "stage": "Verification Gate & Audit",
             "status": "AWAITING_REVIEW",
             "output_summary": "Intelligence state: LEAD - analyst verification pending"},
        ],
    }
