"""
Surveillance Target Management.

A target is a source kept under continuous observation - a website, a .onion
address, or a Telegram channel. The background scheduler revisits each one on
its own interval and files whatever it finds as new intelligence records.

Until now targets could only be created by seeding the database directly;
these endpoints are what the investigator UI needs to run surveillance.
"""

from datetime import datetime, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.postgres import get_db, Target, ScrapedData
from evidence.audit_log import record_audit_event
from auth.rbac import require_investigator

router = APIRouter(
    prefix="/api/targets", tags=["Surveillance Targets"],
    # Every endpoint on this router requires authentication.
    dependencies=[Depends(require_investigator)],
)

VALID_PIPELINES = {"SURFACE_WEB", "DARK_WEB", "TELEGRAM"}
MIN_INTERVAL_MINUTES = 5


class CreateTargetRequest(BaseModel):
    identifier: str = Field(..., example="t.me/some_channel")
    source_type: str = Field(..., example="TELEGRAM")
    label: Optional[str] = None
    priority: int = Field(1, ge=1, le=3, description="1 normal, 2 high, 3 critical")
    scan_interval_minutes: int = Field(60, ge=MIN_INTERVAL_MINUTES, le=10080)


class UpdateTargetRequest(BaseModel):
    label: Optional[str] = None
    priority: Optional[int] = Field(None, ge=1, le=3)
    scan_interval_minutes: Optional[int] = Field(None, ge=MIN_INTERVAL_MINUTES, le=10080)
    status: Optional[str] = Field(None, description="ACTIVE or PAUSED")


def _serialize(t: Target, record_count: Optional[int] = None) -> dict:
    return {
        "id": t.id,
        "identifier": t.identifier,
        "source_type": t.source_type,
        "label": t.label,
        "priority": t.priority,
        "status": t.status,
        "discovered_by": t.discovered_by,
        "scan_interval_minutes": t.scan_interval_minutes,
        "last_scraped_at": t.last_scraped_at.isoformat() + "Z" if t.last_scraped_at else None,
        "next_scan_at": t.next_scan_at.isoformat() + "Z" if t.next_scan_at else None,
        "consecutive_failures": t.consecutive_failures or 0,
        "last_error": t.last_error,
        "total_records_collected": t.total_records_collected or 0,
        "records_in_db": record_count,
        "created_at": t.created_at.isoformat() + "Z" if t.created_at else None,
    }


@router.get("")
async def list_targets(
    source_type: Optional[str] = None,
    status: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    """List every source under surveillance, with its collection history."""
    stmt = select(Target).order_by(desc(Target.priority), Target.id)
    if source_type:
        stmt = stmt.where(Target.source_type == source_type.upper())
    if status:
        stmt = stmt.where(Target.status == status.upper())

    targets = (await db.execute(stmt)).scalars().all()

    counts = dict((await db.execute(
        select(ScrapedData.target_id, func.count(ScrapedData.id))
        .where(ScrapedData.target_id.is_not(None))
        .group_by(ScrapedData.target_id)
    )).all())

    items = [_serialize(t, counts.get(t.id, 0)) for t in targets]
    return {
        "count": len(items),
        "active": sum(1 for t in targets if t.status == "ACTIVE"),
        "paused": sum(1 for t in targets if t.status == "PAUSED"),
        "targets": items,
    }


@router.post("")
async def create_target(req: CreateTargetRequest, db: AsyncSession = Depends(get_db)):
    """Register a new source for continuous observation."""
    pipeline = req.source_type.upper()
    if pipeline not in VALID_PIPELINES:
        raise HTTPException(
            status_code=400,
            detail=f"source_type must be one of {sorted(VALID_PIPELINES)}",
        )

    identifier = req.identifier.strip()
    if not identifier:
        raise HTTPException(status_code=400, detail="identifier cannot be empty")

    existing = (await db.execute(
        select(Target).where(Target.identifier == identifier)
    )).scalars().first()
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"Target already under surveillance (id {existing.id})",
        )

    target = Target(
        identifier=identifier,
        source_type=pipeline,
        label=req.label or identifier,
        priority=req.priority,
        status="ACTIVE",
        discovered_by="MANUAL",
        scan_interval_minutes=req.scan_interval_minutes,
        next_scan_at=datetime.utcnow(),   # eligible on the next scheduler tick
    )
    db.add(target)
    await db.commit()
    await db.refresh(target)

    await record_audit_event(
        action="CREATE_SURVEILLANCE_TARGET",
        resource=f"target_{target.id}",
        details=f"{pipeline} target '{identifier}' added, scanning every "
                f"{req.scan_interval_minutes} min",
    )
    return {"status": "SUCCESS", "target": _serialize(target, 0)}


@router.patch("/{target_id}")
async def update_target(target_id: int, req: UpdateTargetRequest,
                        db: AsyncSession = Depends(get_db)):
    """Pause, resume, or retune a target."""
    target = (await db.execute(
        select(Target).where(Target.id == target_id)
    )).scalars().first()
    if not target:
        raise HTTPException(status_code=404, detail=f"Target {target_id} not found")

    if req.label is not None:
        target.label = req.label
    if req.priority is not None:
        target.priority = req.priority
    if req.scan_interval_minutes is not None:
        target.scan_interval_minutes = req.scan_interval_minutes
    if req.status is not None:
        status = req.status.upper()
        if status not in ("ACTIVE", "PAUSED"):
            raise HTTPException(status_code=400, detail="status must be ACTIVE or PAUSED")
        target.status = status
        if status == "ACTIVE":
            # Resuming clears the failure backoff and makes it due immediately.
            target.consecutive_failures = 0
            target.last_error = None
            target.next_scan_at = datetime.utcnow()

    await db.commit()
    await db.refresh(target)

    await record_audit_event(
        action="UPDATE_SURVEILLANCE_TARGET",
        resource=f"target_{target_id}",
        details=f"Target {target_id} updated: status={target.status}, "
                f"interval={target.scan_interval_minutes}min",
    )
    return {"status": "SUCCESS", "target": _serialize(target)}


@router.delete("/{target_id}")
async def delete_target(target_id: int, db: AsyncSession = Depends(get_db)):
    """
    Remove a target from surveillance.

    Intelligence already collected from it is retained - evidence is never
    deleted by removing the source that produced it.
    """
    target = (await db.execute(
        select(Target).where(Target.id == target_id)
    )).scalars().first()
    if not target:
        raise HTTPException(status_code=404, detail=f"Target {target_id} not found")

    identifier = target.identifier
    await db.delete(target)
    await db.commit()

    await record_audit_event(
        action="DELETE_SURVEILLANCE_TARGET",
        resource=f"target_{target_id}",
        details=f"Target '{identifier}' removed from surveillance; "
                f"collected records retained",
    )
    return {
        "status": "SUCCESS",
        "message": f"Target '{identifier}' removed. Collected records were kept.",
    }


@router.get("/surveillance-status")
async def surveillance_status(db: AsyncSession = Depends(get_db)):
    """Overall health of continuous collection."""
    from scheduler import intel_scheduler

    targets = (await db.execute(select(Target))).scalars().all()
    now = datetime.utcnow()
    due = [t for t in targets
           if t.status == "ACTIVE" and (t.next_scan_at is None or t.next_scan_at <= now)]

    return {
        "scheduler_running": intel_scheduler.is_running,
        "jobs": intel_scheduler.job_summary(),
        "targets_total": len(targets),
        "targets_active": sum(1 for t in targets if t.status == "ACTIVE"),
        "targets_paused": sum(1 for t in targets if t.status == "PAUSED"),
        "targets_failing": sum(1 for t in targets if (t.consecutive_failures or 0) > 0),
        "targets_due_now": len(due),
        "next_due": min(
            (t.next_scan_at.isoformat() + "Z" for t in targets
             if t.status == "ACTIVE" and t.next_scan_at),
            default=None,
        ),
    }


@router.post("/run-surveillance-now")
async def run_surveillance_now():
    """Force one surveillance cycle immediately instead of waiting for the tick."""
    from scheduler import intel_scheduler
    result = await intel_scheduler.run_now()
    await record_audit_event(
        action="MANUAL_SURVEILLANCE_RUN",
        resource="scheduler",
        details=f"Manual surveillance cycle: {result}",
    )
    return result
