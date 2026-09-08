"""
Intelligence Data Query, Filter, & Semantic Search Endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import Optional, List
from database.postgres import get_db, ScrapedData
from database.vector_store import vector_store
from auth.rbac import require_any_authenticated

router = APIRouter(
    prefix="/api/data", tags=["Intelligence Records"],
    # Every endpoint on this router requires authentication.
    dependencies=[Depends(require_any_authenticated)],
)


@router.get("")
async def list_intelligence(
    source_type: Optional[str] = Query(None, description="SURFACE_WEB, DARK_WEB, TELEGRAM"),
    threat_level: Optional[str] = Query(None, description="LOW, MEDIUM, HIGH, SEVERE"),
    search: Optional[str] = Query(None, description="Text keyword to filter"),
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """List scraped intelligence records with optional filters."""
    query = select(ScrapedData).order_by(desc(ScrapedData.created_at))

    if source_type:
        query = query.where(ScrapedData.source_type == source_type.upper())
    if threat_level:
        query = query.where(ScrapedData.threat_level == threat_level.upper())
    if search:
        query = query.where(ScrapedData.cleaned_text.ilike(f"%{search}%"))

    query = query.limit(limit).offset(offset)
    records = (await db.execute(query)).scalars().all()

    return [
        {
            "id": r.id,
            "source_type": r.source_type,
            "source_url": r.source_url,
            "cleaned_text": r.cleaned_text,
            "sha256_hash": r.sha256_hash,
            "threat_level": r.threat_level,
            "author": r.author_or_handle,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else None,
            # Surfaced as a first-class field so a record typed into the Live
            # Triage console is never mistaken for one a scraper collected.
            # Records predating provenance tracking report UNKNOWN rather than
            # being assumed to be collected.
            "acquisition_method": (
                (r.metadata_json or {}).get("provenance", {}).get("acquisition_method")
                or "UNKNOWN"
            ),
            "metadata": r.metadata_json
        }
        for r in records
    ]


@router.get("/semantic-search")
async def semantic_search(query: str = Query(..., description="Natural language slang search")):
    """Vector similarity search using ChromaDB embeddings."""
    results = vector_store.query_similar(query_text=query, n_results=10)
    return {
        "query": query,
        "matches": results
    }


@router.get("/{record_id}")
async def get_record_detail(record_id: int, db: AsyncSession = Depends(get_db)):
    """Fetch single evidence record with raw HTML/content and verification details."""
    stmt = select(ScrapedData).where(ScrapedData.id == record_id)
    record = (await db.execute(stmt)).scalars().first()
    if not record:
        raise HTTPException(status_code=404, detail="Intelligence record not found.")

    return {
        "id": record.id,
        "source_type": record.source_type,
        "source_url": record.source_url,
        "raw_content": record.raw_content,
        "cleaned_text": record.cleaned_text,
        "ocr_extracted_text": record.ocr_extracted_text,
        "sha256_hash": record.sha256_hash,
        "threat_level": record.threat_level,
        "author": record.author_or_handle,
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "metadata": record.metadata_json
    }
