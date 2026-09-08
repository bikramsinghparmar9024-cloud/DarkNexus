"""
Evidence Dossier Export & Audit Log Endpoints.
"""

import uuid
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from pydantic import BaseModel
from typing import List, Optional

from database.postgres import get_db, ScrapedData, AuditLog
from evidence.pdf_generator import pdf_generator
from evidence.audit_log import record_audit_event
from auth.rbac import require_investigator

router = APIRouter(
    prefix="/api/evidence", tags=["Evidence & Reports"],
    # Every endpoint on this router requires authentication.
    dependencies=[Depends(require_investigator)],
)


class GenerateDossierRequest(BaseModel):
    investigator_badge: str
    record_ids: List[int]
    case_notes: Optional[str] = None


@router.post("/generate-dossier")
async def generate_intelligence_dossier(
    req: GenerateDossierRequest,
    db: AsyncSession = Depends(get_db)
):
    """Generate a formal court-admissible PDF intelligence package."""
    # Fetch evidence records
    stmt = select(ScrapedData).where(ScrapedData.id.in_(req.record_ids))
    records = (await db.execute(stmt)).scalars().all()

    if not records:
        raise HTTPException(status_code=400, detail="No valid intelligence records found for given IDs.")

    records_data = [
        {
            "source_type": r.source_type,
            "source_url": r.source_url,
            "sha256_hash": r.sha256_hash,
            "cleaned_text": r.cleaned_text or r.raw_content,
            "created_at": r.created_at.strftime("%Y-%m-%d %H:%M:%S") if r.created_at else None
        }
        for r in records
    ]

    report_id = f"PB-INTEL-{uuid.uuid4().hex[:8].upper()}"
    file_path = pdf_generator.generate_dossier(
        report_id=report_id,
        investigator_badge=req.investigator_badge,
        evidence_records=records_data,
        notes=req.case_notes or ""
    )

    await record_audit_event(
        action="EXPORT_DOSSIER",
        resource=report_id,
        details=f"Generated dossier containing {len(records)} evidence items"
    )

    return {
        "report_id": report_id,
        "file_path": file_path,
        "evidence_count": len(records),
        "download_url": f"/api/evidence/download/{report_id}"
    }


@router.get("/download/{report_id}")
async def download_dossier(report_id: str):
    """Download generated PDF dossier."""
    import os
    from config import settings

    pdf_candidate = os.path.join(settings.REPORTS_DIR, f"dossier_{report_id}.pdf")
    html_candidate = os.path.join(settings.REPORTS_DIR, f"dossier_{report_id}.html")

    if os.path.exists(pdf_candidate):
        return FileResponse(pdf_candidate, media_type="application/pdf", filename=f"dossier_{report_id}.pdf")
    elif os.path.exists(html_candidate):
        return FileResponse(html_candidate, media_type="text/html", filename=f"dossier_{report_id}.html")
    else:
        raise HTTPException(status_code=404, detail="Requested dossier file was not found.")


@router.get("/audit-trail")
async def get_audit_trail(limit: int = 50, db: AsyncSession = Depends(get_db)):
    """Fetch recent chain of custody audit events."""
    stmt = select(AuditLog).order_by(desc(AuditLog.timestamp)).limit(limit)
    events = (await db.execute(stmt)).scalars().all()
    return events
