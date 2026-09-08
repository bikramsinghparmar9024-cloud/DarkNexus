"""
Three-Level Intelligence State Machine Routes.
Manages LEAD → CORROBORATED → VERIFIED state transitions.
All transitions are audited for chain of custody.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from database.postgres import get_db, ScrapedData, AuditLog
from evidence.audit_log import record_audit_event
from auth.rbac import require_investigator
from auth.jwt_handler import get_current_user_payload

router = APIRouter(
    prefix="/api/verification", tags=["Intelligence Verification & State Machine"],
    # Every endpoint on this router requires authentication.
    dependencies=[Depends(require_investigator)],
)


class VerifyRequest(BaseModel):
    investigator_badge: str = Field(..., example="PB-CID-8821")
    notes: Optional[str] = None


class RejectRequest(BaseModel):
    investigator_badge: str = Field(..., example="PB-CID-8821")
    reason: str = Field(..., example="Insufficient corroboration — alias match only")


class RequestCorroborationRequest(BaseModel):
    investigator_badge: str = Field(..., example="PB-CID-8821")
    additional_signals_needed: Optional[str] = "Requires independent surface-web or forensic corroboration"


# ─── In-memory verification store for graph relationships ─────────
RELATIONSHIP_VERIFICATIONS = {}


@router.post("/verify/{record_id}")
async def verify_finding(record_id: int, req: VerifyRequest, db: AsyncSession = Depends(get_db)):
    """
    Mark a finding as VERIFIED by an authorized investigator.
    Only CORROBORATED or LEAD findings can be verified.
    Eligible for approved investigative outputs after verification.
    """
    stmt = select(ScrapedData).where(ScrapedData.id == record_id)
    record = (await db.execute(stmt)).scalars().first()

    if not record:
        raise HTTPException(status_code=404, detail=f"Record {record_id} not found")

    # Update metadata with verification info
    meta = record.metadata_json or {}
    meta["intelligence_state"] = "VERIFIED"
    meta["verified_by"] = req.investigator_badge
    meta["verified_at"] = datetime.utcnow().isoformat() + "Z"
    meta["verification_notes"] = req.notes or ""
    record.metadata_json = meta

    await db.commit()

    await record_audit_event(
        action="VERIFY_FINDING",
        resource=f"record_{record_id}",
        details=f"Investigator {req.investigator_badge} verified finding. Notes: {req.notes or 'N/A'}"
    )

    return {
        "status": "SUCCESS",
        "record_id": record_id,
        "new_state": "VERIFIED",
        "verified_by": req.investigator_badge,
        "verified_at": meta["verified_at"],
        "message": "Finding is now VERIFIED and eligible for approved investigative outputs."
    }


@router.post("/reject/{record_id}")
async def reject_finding(record_id: int, req: RejectRequest, db: AsyncSession = Depends(get_db)):
    """
    Reject a finding. Moves state to REJECTED with documented reason.
    """
    stmt = select(ScrapedData).where(ScrapedData.id == record_id)
    record = (await db.execute(stmt)).scalars().first()

    if not record:
        raise HTTPException(status_code=404, detail=f"Record {record_id} not found")

    meta = record.metadata_json or {}
    meta["intelligence_state"] = "REJECTED"
    meta["rejected_by"] = req.investigator_badge
    meta["rejected_at"] = datetime.utcnow().isoformat() + "Z"
    meta["rejection_reason"] = req.reason
    record.metadata_json = meta

    await db.commit()

    await record_audit_event(
        action="REJECT_FINDING",
        resource=f"record_{record_id}",
        details=f"Investigator {req.investigator_badge} rejected finding. Reason: {req.reason}"
    )

    return {
        "status": "SUCCESS",
        "record_id": record_id,
        "new_state": "REJECTED",
        "rejected_by": req.investigator_badge,
        "reason": req.reason,
    }


@router.post("/request-corroboration/{record_id}")
async def request_corroboration(record_id: int, req: RequestCorroborationRequest, db: AsyncSession = Depends(get_db)):
    """
    Request further corroboration for a finding. Sets state to LEAD with a note.
    """
    stmt = select(ScrapedData).where(ScrapedData.id == record_id)
    record = (await db.execute(stmt)).scalars().first()

    if not record:
        raise HTTPException(status_code=404, detail=f"Record {record_id} not found")

    meta = record.metadata_json or {}
    meta["intelligence_state"] = "LEAD"
    meta["corroboration_requested_by"] = req.investigator_badge
    meta["corroboration_requested_at"] = datetime.utcnow().isoformat() + "Z"
    meta["additional_signals_needed"] = req.additional_signals_needed
    record.metadata_json = meta

    await db.commit()

    await record_audit_event(
        action="REQUEST_CORROBORATION",
        resource=f"record_{record_id}",
        details=f"Investigator {req.investigator_badge} requested further corroboration: {req.additional_signals_needed}"
    )

    return {
        "status": "SUCCESS",
        "record_id": record_id,
        "new_state": "LEAD",
        "message": "Corroboration requested. Finding returned to LEAD state pending further evidence."
    }


@router.get("/findings")
async def list_findings_by_state(
    state: Optional[str] = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db)
):
    """
    List findings filtered by intelligence state: LEAD, CORROBORATED, VERIFIED, REJECTED.
    """
    stmt = select(ScrapedData).order_by(ScrapedData.created_at.desc()).limit(limit)
    records = (await db.execute(stmt)).scalars().all()

    results = []
    for r in records:
        meta = r.metadata_json or {}
        record_state = meta.get("intelligence_state", "LEAD")

        if state and record_state != state.upper():
            continue

        results.append({
            "id": r.id,
            "source_type": r.source_type,
            "source_url": r.source_url,
            "author": r.author_or_handle,
            "threat_level": r.threat_level,
            "intelligence_state": record_state,
            "sha256_hash": r.sha256_hash,
            "snippet": (r.cleaned_text or r.raw_content or "")[:150],
            "verified_by": meta.get("verified_by"),
            "verified_at": meta.get("verified_at"),
            "created_at": r.created_at.isoformat() if r.created_at else None,
        })

    return {
        "status": "SUCCESS",
        "filter": state or "ALL",
        "count": len(results),
        "findings": results,
    }


# ─── Relationship verification (for graph edges) ─────────────────

class VerifyRelationshipRequest(BaseModel):
    source_entity_id: str
    target_entity_id: str
    action: str = Field(..., example="VERIFY")  # VERIFY | REJECT | REQUEST_MORE
    notes: Optional[str] = None
    # investigator_badge was accepted here and recorded as the reviewer. It is
    # now taken from the authenticated token instead: who performed a review
    # is not something the caller should be able to assert.
    investigator_badge: Optional[str] = None


@router.post("/verify-relationship")
async def verify_relationship(
    req: VerifyRelationshipRequest,
    token_payload: dict = Depends(get_current_user_payload),
):
    """
    Record an investigator's judgement on a link in the correlation graph.

    This used to write only to a module-level dictionary, so a verification
    survived until the next restart and never reached the graph: an edge an
    analyst had explicitly rejected carried on being drawn. The decision is
    now written onto the edge itself, and rejected edges drop out of the
    default graph view while remaining in the database for audit.

    The reviewer is taken from the authenticated token, not from the request
    body. A client-supplied badge number is an unverified claim about who
    performed a review, which is precisely the field that must not be.
    """
    from database.graph_db import graph_manager

    key = f"{req.source_entity_id}::{req.target_entity_id}"
    reverse_key = f"{req.target_entity_id}::{req.source_entity_id}"

    now = datetime.utcnow().isoformat() + "Z"
    reviewer = (token_payload.get("sub") or token_payload.get("username")
                or "unknown_investigator")

    verification = {
        "source_entity_id": req.source_entity_id,
        "target_entity_id": req.target_entity_id,
        "action": req.action.upper(),
        "reviewed_by": reviewer,
        "notes": req.notes,
        "timestamp": now,
    }

    if req.action.upper() == "VERIFY":
        verification["state"] = "VERIFIED"
        verification["message"] = "Relationship verified by investigator. Eligible for dossier inclusion."
    elif req.action.upper() == "REJECT":
        verification["state"] = "REJECTED"
        verification["message"] = "Relationship rejected. Excluded from approved outputs."
    else:
        verification["state"] = "PENDING_CORROBORATION"
        verification["message"] = "Additional corroboration requested before verification."

    RELATIONSHIP_VERIFICATIONS[key] = verification
    RELATIONSHIP_VERIFICATIONS[reverse_key] = verification

    # Persist onto the graph edge so the decision outlives this process and
    # actually changes what the investigator is shown.
    edge_status = {"VERIFY": "VERIFIED", "REJECT": "REJECTED"}.get(
        req.action.upper(), "PENDING")
    persisted = await graph_manager.set_edge_status(
        req.source_entity_id, req.target_entity_id,
        status=edge_status, reviewed_by=reviewer, note=req.notes)
    verification["persisted"] = persisted

    await record_audit_event(
        action=f"RELATIONSHIP_{req.action.upper()}",
        resource=key,
        details=(f"Investigator {reviewer}: {req.action} relationship. "
                 f"Notes: {req.notes or 'N/A'}")
    )

    return {"status": "SUCCESS", "verification": verification}


@router.get("/relationship-status/{source_id}/{target_id}")
async def get_relationship_status(source_id: str, target_id: str):
    """Check the verification status of a specific relationship."""
    key = f"{source_id}::{target_id}"
    reverse_key = f"{target_id}::{source_id}"

    verification = RELATIONSHIP_VERIFICATIONS.get(key) or RELATIONSHIP_VERIFICATIONS.get(reverse_key)

    if not verification:
        return {
            "status": "SUCCESS",
            "state": "PENDING",
            "message": "Relationship has not been reviewed by an investigator yet."
        }

    return {"status": "SUCCESS", "verification": verification}
