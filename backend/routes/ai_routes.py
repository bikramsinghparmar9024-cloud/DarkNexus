"""
AI & Intelligence Layer REST API Endpoints.
Exposes spaCy NER, Hugging Face threat classification, RAG querying, and LangGraph pipelines.
"""

from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from database.postgres import get_db, ScrapedData
from ai.entity_extractor import entity_extractor
from ai.threat_classifier import threat_classifier
from ai.rag_engine import rag_engine
from ai.batch_analysis import batch_analyzer
from ai.dossier_narrative import generate_ai_case_narrative
from ai.enrichment import reindex_vector_store
from ai.semantic_classifier import semantic_classifier
from auth.rbac import require_investigator

router = APIRouter(
    prefix="/api/ai", tags=["AI & Intelligence"],
    # Every endpoint on this router requires authentication.
    dependencies=[Depends(require_investigator)],
)


class AnalyzeTextRequest(BaseModel):
    text: str


class RAGQueryRequest(BaseModel):
    query: str
    top_k: Optional[int] = 5


class GenerateNarrativeRequest(BaseModel):
    investigator_badge: str
    record_ids: List[int]
    case_title: Optional[str] = "Narcotic Trafficking Network Analysis"


@router.post("/analyze-text")
async def analyze_raw_text(req: AnalyzeTextRequest):
    """Test spaCy NER and Hugging Face threat scoring on arbitrary text or drug slang."""
    entities = entity_extractor.extract(req.text)
    threat = threat_classifier.classify(req.text)
    return {
        "text": req.text,
        "entities": entities,
        "threat_assessment": threat
    }


@router.post("/run-pipeline")
async def run_langgraph_pipeline(background_tasks: BackgroundTasks):
    """Run LangGraph autonomous analysis over unreviewed scraped records."""
    result = await batch_analyzer.run_batch_analysis(limit=25)
    return result


@router.post("/reindex")
async def reindex_semantic_search():
    """Backfill the ChromaDB vector index from records already in the database."""
    return await reindex_vector_store()


@router.get("/model-status")
async def model_status():
    """Report which ML components are actually loaded, rather than merely configured."""
    from database.vector_store import vector_store
    return {
        "semantic_classifier": {
            "enabled": semantic_classifier.available or semantic_classifier.load(),
            "model": __import__("config").settings.SEMANTIC_CLASSIFIER_MODEL,
        },
        "vector_store": {
            "available": vector_store.collection is not None,
            "indexed_documents": vector_store.collection.count() if vector_store.collection else 0,
        },
    }


@router.post("/rag-query")
async def rag_query(req: RAGQueryRequest):
    """Query ChromaDB vector store and synthesize plain-English intelligence briefs."""
    return rag_engine.query(req.query, top_k=req.top_k or 5)


@router.get("/entities-summary")
async def get_entities_summary(db: AsyncSession = Depends(get_db)):
    """Aggregate top detected drugs, locations, and suspect handles across all records."""
    stmt = select(ScrapedData).where(ScrapedData.flagged_entities.is_not(None)).limit(50)
    records = (await db.execute(stmt)).scalars().all()

    drugs_count = {}
    locations_count = {}
    handles_set = set()
    wallets_set = set()

    for r in records:
        ents = r.flagged_entities or {}
        for d in ents.get("drugs", []):
            drugs_count[d] = drugs_count.get(d, 0) + 1
        for loc in ents.get("locations", []):
            locations_count[loc] = locations_count.get(loc, 0) + 1
        for h in ents.get("handles", []):
            handles_set.add(h)
        for btc in ents.get("crypto_wallets", {}).get("btc", []):
            wallets_set.add(btc)

    # No placeholder values. This endpoint previously substituted invented
    # counts when the database returned nothing, so a working query and a
    # failed one produced identical-looking output and an empty system
    # appeared to hold intelligence.
    return {
        "records_analysed": len(records),
        "has_data": bool(drugs_count or locations_count or handles_set or wallets_set),
        "top_drugs": drugs_count,
        "top_locations": locations_count,
        "suspect_handles": sorted(handles_set),
        "crypto_wallets": sorted(wallets_set),
        "note": (None if records else
                 "No analysed records yet. Collect intelligence, then run "
                 "POST /api/ai/run-pipeline to populate entity extraction."),
    }


@router.post("/generate-narrative")
async def create_ai_narrative(req: GenerateNarrativeRequest, db: AsyncSession = Depends(get_db)):
    """Synthesize full AI narrative for court dossiers."""
    stmt = select(ScrapedData).where(ScrapedData.id.in_(req.record_ids))
    records = (await db.execute(stmt)).scalars().all()

    evidence_items = [
        {
            "id": r.id,
            "source_type": r.source_type,
            "flagged_entities": r.flagged_entities or entity_extractor.extract(r.cleaned_text or r.raw_content),
            "threat_level": r.threat_level
        }
        for r in records
    ]

    narrative = generate_ai_case_narrative(
        evidence_items=evidence_items,
        investigator_badge=req.investigator_badge,
        case_title=req.case_title or "Inter-State Narcotic Trafficking Network Investigation"
    )
    return narrative
