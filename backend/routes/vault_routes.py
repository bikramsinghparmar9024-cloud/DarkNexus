"""
Evidence Vault API Routes — Read-Only Evidence Repository.
Provides access to original evidence artifacts with integrity verification.
AI operates on a separate metadata-analysis layer; originals are never modified.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime

from database.postgres import get_db, ScrapedData
from auth.hashing import generate_sha256
from evidence.audit_log import record_audit_event
from ai.enrichment import get_analysis
from auth.rbac import require_investigator

router = APIRouter(
    prefix="/api/vault",
    tags=["Evidence Vault (Read-Only Repository)"],
    # Every endpoint on this router requires authentication.
    dependencies=[Depends(require_investigator)],
)


@router.get("/{record_id}")
async def get_vault_record(record_id: int, db: AsyncSession = Depends(get_db)):
    """
    Retrieve original evidence artifact from the read-only vault.
    Returns the original content, SHA-256 hash, provenance metadata,
    and integrity verification status.
    """
    stmt = select(ScrapedData).where(ScrapedData.id == record_id)
    record = (await db.execute(stmt)).scalars().first()

    if not record:
        raise HTTPException(status_code=404, detail=f"Evidence record {record_id} not found in vault")

    meta = record.metadata_json or {}
    prov = meta.get("provenance", {})
    analysis = get_analysis(record)

    await record_audit_event(
        action="ACCESS_VAULT_RECORD",
        resource=f"record_{record_id}",
        details=f"Vault record {record_id} accessed for review"
    )

    return {
        "status": "SUCCESS",
        "vault_record": {
            "id": record.id,
            "is_original": True,
            "immutable": True,

            # Original artifact
            "original_content": record.raw_content,
            "cleaned_content": record.cleaned_text,

            # Provenance metadata
            "provenance": {
                "source_type": record.source_type,
                "source_url": record.source_url,
                "author_or_handle": record.author_or_handle,
                "acquisition_timestamp": record.created_at.isoformat() + "Z" if record.created_at else None,
                "acquisition_method": prov.get("acquisition_method", "UNKNOWN"),
                "collector_identity": prov.get("collector")
                                      or prov.get("investigator_badge", "SYSTEM"),
            },

            # Integrity
            "integrity": {
                "sha256_hash": record.sha256_hash,
                "hash_algorithm": "SHA-256",
                "hash_computed_at": record.created_at.isoformat() + "Z" if record.created_at else None,
            },

            # Intelligence state
            "intelligence_state": meta.get("intelligence_state", "LEAD"),
            "threat_level": record.threat_level,
            "verified_by": meta.get("verified_by"),
            "verified_at": meta.get("verified_at"),

            # AI analysis layer (separate from original)
            "ai_analysis_layer": {
                "note": "AI-generated metadata below is derived analysis, NOT original evidence",
                "schema_version": analysis.get("schema_version"),
                "extracted_entities": analysis.get("entities"),
                "threat_classification": analysis.get("threat"),
                "geo_resolution": analysis.get("geo"),
                "border_alert": analysis.get("border_alert"),
                "normalized_text": analysis.get("normalized_text"),
                "detected_slang": analysis.get("detected_slang"),
            },
        }
    }


@router.get("/{record_id}/verify-integrity")
async def verify_vault_integrity(record_id: int, db: AsyncSession = Depends(get_db)):
    """
    Recompute SHA-256 hash of the stored artifact and compare with the
    recorded hash to verify that the evidence has not been tampered with.
    """
    stmt = select(ScrapedData).where(ScrapedData.id == record_id)
    record = (await db.execute(stmt)).scalars().first()

    if not record:
        raise HTTPException(status_code=404, detail=f"Evidence record {record_id} not found")

    # Recompute hash from stored content
    source_url = record.source_url or ""
    recomputed_hash = generate_sha256(record.raw_content + source_url)

    integrity_match = (recomputed_hash == record.sha256_hash)

    await record_audit_event(
        action="VERIFY_INTEGRITY",
        resource=f"record_{record_id}",
        details=f"Integrity check: {'PASS' if integrity_match else 'FAIL'} — stored={record.sha256_hash[:16]}... recomputed={recomputed_hash[:16]}..."
    )

    return {
        "status": "SUCCESS",
        "record_id": record_id,
        "integrity_verified": integrity_match,
        "stored_hash": record.sha256_hash,
        "recomputed_hash": recomputed_hash,
        "hash_algorithm": "SHA-256",
        "verification_timestamp": datetime.utcnow().isoformat() + "Z",
        "verdict": "INTEGRITY CONFIRMED — Evidence artifact is unaltered" if integrity_match
                   else "⚠ INTEGRITY FAILURE — Hash mismatch detected. Evidence may have been tampered with.",
    }


@router.get("/browse/all")
async def browse_vault(limit: int = 50, db: AsyncSession = Depends(get_db)):
    """
    Browse all evidence artifacts in the vault with provenance summaries.
    """
    stmt = select(ScrapedData).order_by(ScrapedData.created_at.desc()).limit(limit)
    records = (await db.execute(stmt)).scalars().all()

    items = []
    for r in records:
        meta = r.metadata_json or {}
        items.append({
            "id": r.id,
            "source_type": r.source_type,
            "source_url": r.source_url,
            "author": r.author_or_handle,
            "sha256_hash": r.sha256_hash,
            "threat_level": r.threat_level,
            "intelligence_state": meta.get("intelligence_state", "LEAD"),
            "snippet": (r.cleaned_text or r.raw_content or "")[:120],
            "acquisition_timestamp": r.created_at.isoformat() if r.created_at else None,
        })

    return {
        "status": "SUCCESS",
        "vault_name": "DarkNexus Evidence Vault",
        "description": "Read-only repository of original evidentiary artifacts. AI analysis operates on a separate layer.",
        "total_records": len(items),
        "records": items,
    }
