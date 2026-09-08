"""
CTI Project Hub.

An investigation workspace: a topic, the sources watched under it, and the
suspect accounts tracked within it. Adding a source also registers it as a
surveillance target, so a project actually drives collection rather than
merely listing intentions.

Everything here is stored in the database. The previous implementation kept
projects in a module-level list seeded with invented operations and suspects,
so nothing an investigator created survived a restart, and suspect risk scores
were derived from whether the handle contained certain substrings.

Also hosts dataset compression and AES-256-GCM encryption, which were already
functional and are unchanged.
"""

import base64
import json
import logging
import os
import zlib
from datetime import datetime
from typing import Any, Dict, List, Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from database.postgres import (
    get_db, CTIProject, CTIProjectSource, CTIProjectSuspect, Target,
)
from ai.suspect_correlation import correlate_suspect
from evidence.audit_log import record_audit_event
from auth.rbac import require_investigator

logger = logging.getLogger("cti_routes")
router = APIRouter(
    prefix="/api/cti", tags=["CTI Projects & Threat Intelligence"],
    # Every endpoint on this router requires authentication.
    dependencies=[Depends(require_investigator)],
)

VALID_SOURCE_TYPES = {"TELEGRAM", "DARK_WEB", "SURFACE_WEB"}


# ─────────────────────────────────────────────────────────────
# Request models
# ─────────────────────────────────────────────────────────────

class CreateProjectRequest(BaseModel):
    name: str = Field(..., example="Operation Border Clean")
    topic: Optional[str] = Field("Drug Trafficking", example="Drug Trafficking")
    description: Optional[str] = None


class AddSourceRequest(BaseModel):
    identifier: str = Field(..., example="t.me/some_channel")
    source_type: str = Field(..., example="TELEGRAM")
    label: Optional[str] = None
    scan_interval_minutes: int = Field(60, ge=5, le=10080)


class AddSuspectRequest(BaseModel):
    username: str = Field(..., example="@some_handle")
    alias: Optional[str] = None
    platform: Optional[str] = None
    role: Optional[str] = None
    notes: Optional[str] = None


class CompressEncryptRequest(BaseModel):
    data_payload: str = Field(..., description="Raw text or JSON dump of intercepted data")
    passphrase: str = Field(..., min_length=8,
                            description="Encryption passphrase; no default is supplied")


class DecryptDecompressRequest(BaseModel):
    encrypted_payload_b64: str
    nonce_b64: str
    passphrase: str = Field(..., min_length=8)


# ─────────────────────────────────────────────────────────────
# Serialisation
# ─────────────────────────────────────────────────────────────

def _serialize_source(s: CTIProjectSource) -> Dict[str, Any]:
    return {
        "id": s.id,
        "identifier": s.identifier,
        "source_type": s.source_type,
        "label": s.label,
        "status": s.status,
        "target_id": s.target_id,
        "under_surveillance": s.target_id is not None,
        "created_at": s.created_at.isoformat() + "Z" if s.created_at else None,
    }


def _serialize_suspect(s: CTIProjectSuspect) -> Dict[str, Any]:
    return {
        "id": s.id,
        "username": s.username,
        "alias": s.alias,
        "platform": s.platform,
        "role": s.role,
        "notes": s.notes,
        "risk_score": s.risk_score or 0,
        "matched_sources": s.matched_sources or [],
        "evidence_record_ids": s.evidence_record_ids or [],
        "correlation_count": s.correlation_count or 0,
        "correlation_summary": s.correlation_summary,
        "last_correlated_at": (s.last_correlated_at.isoformat() + "Z"
                               if s.last_correlated_at else None),
        "last_active": s.last_active.isoformat() + "Z" if s.last_active else None,
        "has_evidence": bool(s.evidence_record_ids),
    }


async def _serialize_project(db: AsyncSession, p: CTIProject) -> Dict[str, Any]:
    sources = (await db.execute(
        select(CTIProjectSource).where(CTIProjectSource.project_id == p.id)
    )).scalars().all()
    suspects = (await db.execute(
        select(CTIProjectSuspect)
        .where(CTIProjectSuspect.project_id == p.id)
        .order_by(desc(CTIProjectSuspect.risk_score))
    )).scalars().all()

    return {
        "id": p.id,
        "name": p.name,
        "topic": p.topic,
        "topic_key": p.topic_key,
        "description": p.description,
        "is_observing": p.is_observing,
        "created_at": p.created_at.isoformat() + "Z" if p.created_at else None,
        "sources": [_serialize_source(s) for s in sources],
        "suspects": [_serialize_suspect(s) for s in suspects],
    }


async def _get_project(db: AsyncSession, project_id: int) -> CTIProject:
    project = (await db.execute(
        select(CTIProject).where(CTIProject.id == project_id)
    )).scalars().first()
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return project


# ─────────────────────────────────────────────────────────────
# Projects
# ─────────────────────────────────────────────────────────────

@router.get("/projects")
async def list_projects(db: AsyncSession = Depends(get_db)):
    """
    All investigation projects.

    Returns an empty list when none have been created - there is no seeded
    roster of operations.
    """
    projects = (await db.execute(
        select(CTIProject).order_by(desc(CTIProject.created_at))
    )).scalars().all()
    return [await _serialize_project(db, p) for p in projects]


@router.post("/projects")
async def create_project(req: CreateProjectRequest, db: AsyncSession = Depends(get_db)):
    """Create an investigation project."""
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Project name cannot be empty")

    project = CTIProject(
        name=name,
        topic=req.topic,
        topic_key=(req.topic or "general").lower().replace(" ", "_"),
        description=req.description,
        is_observing=True,
    )
    db.add(project)
    await db.commit()
    await db.refresh(project)

    await record_audit_event(
        action="CREATE_CTI_PROJECT", resource=f"cti_project_{project.id}",
        details=f"Project '{name}' created",
    )
    return {"status": "SUCCESS", "project": await _serialize_project(db, project)}


@router.post("/projects/{project_id}/toggle-observing")
async def toggle_observing(project_id: int, db: AsyncSession = Depends(get_db)):
    """Pause or resume collection for every source under a project."""
    project = await _get_project(db, project_id)
    project.is_observing = not project.is_observing

    # Mirror the state onto the underlying surveillance targets, so pausing a
    # project actually stops its collection rather than only relabelling it.
    sources = (await db.execute(
        select(CTIProjectSource).where(CTIProjectSource.project_id == project_id)
    )).scalars().all()
    new_status = "ACTIVE" if project.is_observing else "PAUSED"
    updated = 0
    for source in sources:
        if source.target_id:
            target = (await db.execute(
                select(Target).where(Target.id == source.target_id)
            )).scalars().first()
            if target:
                target.status = new_status
                if project.is_observing:
                    target.next_scan_at = datetime.utcnow()
                updated += 1

    await db.commit()
    return {
        "status": "SUCCESS",
        "project_id": project_id,
        "is_observing": project.is_observing,
        "targets_updated": updated,
    }


@router.delete("/projects/{project_id}")
async def delete_project(project_id: int, db: AsyncSession = Depends(get_db)):
    """
    Delete a project and its source and suspect entries.

    Collected intelligence is retained: evidence does not disappear because
    the workspace referencing it was closed.
    """
    project = await _get_project(db, project_id)
    name = project.name

    for model in (CTIProjectSource, CTIProjectSuspect):
        rows = (await db.execute(
            select(model).where(model.project_id == project_id)
        )).scalars().all()
        for row in rows:
            await db.delete(row)
    await db.delete(project)
    await db.commit()

    await record_audit_event(
        action="DELETE_CTI_PROJECT", resource=f"cti_project_{project_id}",
        details=f"Project '{name}' deleted; collected records retained",
    )
    return {"status": "SUCCESS", "message": f"Project '{name}' deleted. Records retained."}


# ─────────────────────────────────────────────────────────────
# Sources
# ─────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/sources")
async def add_source(project_id: int, req: AddSourceRequest,
                     db: AsyncSession = Depends(get_db)):
    """
    Watch a source under this project.

    Also registers it as a surveillance target, so the scheduler begins
    collecting from it.
    """
    project = await _get_project(db, project_id)

    source_type = req.source_type.upper()
    if source_type not in VALID_SOURCE_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"source_type must be one of {sorted(VALID_SOURCE_TYPES)}")

    identifier = req.identifier.strip()
    if not identifier:
        raise HTTPException(status_code=400, detail="identifier cannot be empty")

    existing = (await db.execute(
        select(CTIProjectSource)
        .where(CTIProjectSource.project_id == project_id)
        .where(CTIProjectSource.identifier == identifier)
    )).scalars().first()
    if existing:
        raise HTTPException(status_code=409,
                            detail="Source already watched under this project")

    # Reuse an existing target where one exists, otherwise create it.
    target = (await db.execute(
        select(Target).where(Target.identifier == identifier)
    )).scalars().first()
    if not target:
        target = Target(
            identifier=identifier, source_type=source_type,
            label=req.label or identifier, priority=1,
            status="ACTIVE" if project.is_observing else "PAUSED",
            discovered_by="CTI_PROJECT",
            scan_interval_minutes=req.scan_interval_minutes,
            next_scan_at=datetime.utcnow(),
        )
        db.add(target)
        await db.flush()

    source = CTIProjectSource(
        project_id=project_id, target_id=target.id, identifier=identifier,
        source_type=source_type, label=req.label or identifier, status="ACTIVE",
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)

    await record_audit_event(
        action="ADD_CTI_SOURCE", resource=f"cti_project_{project_id}",
        details=f"Source '{identifier}' ({source_type}) added and placed under surveillance",
    )
    return {"status": "SUCCESS", "source": _serialize_source(source)}


@router.delete("/projects/{project_id}/sources/{source_id}")
async def remove_source(project_id: int, source_id: int,
                        db: AsyncSession = Depends(get_db)):
    """
    Stop watching a source under this project.

    The surveillance target is left in place: it may be shared with another
    project, and records already collected keep their provenance.
    """
    source = (await db.execute(
        select(CTIProjectSource)
        .where(CTIProjectSource.id == source_id)
        .where(CTIProjectSource.project_id == project_id)
    )).scalars().first()
    if not source:
        raise HTTPException(status_code=404,
                            detail=f"Source {source_id} not found in project {project_id}")

    identifier = source.identifier
    await db.delete(source)
    await db.commit()

    remaining = (await db.execute(
        select(func.count(CTIProjectSource.id))
        .where(CTIProjectSource.project_id == project_id)
    )).scalar() or 0

    return {
        "status": "SUCCESS",
        "message": f"Source '{identifier}' removed from project",
        "remaining_count": remaining,
    }


# ─────────────────────────────────────────────────────────────
# Suspects
# ─────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/suspects")
async def get_suspects(project_id: int, db: AsyncSession = Depends(get_db)):
    """Accounts tracked under this project, highest risk first."""
    await _get_project(db, project_id)
    suspects = (await db.execute(
        select(CTIProjectSuspect)
        .where(CTIProjectSuspect.project_id == project_id)
        .order_by(desc(CTIProjectSuspect.risk_score))
    )).scalars().all()
    return {"status": "SUCCESS", "suspects": [_serialize_suspect(s) for s in suspects]}


@router.post("/projects/{project_id}/suspects")
async def add_suspect(project_id: int, req: AddSuspectRequest,
                      db: AsyncSession = Depends(get_db)):
    """
    Track an account and correlate it against collected intelligence.

    The risk score is computed from records the account actually appears in.
    An account with no footprint scores zero, and the response says so rather
    than presenting a placeholder as an assessment.
    """
    await _get_project(db, project_id)

    username = req.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="username cannot be empty")

    correlation = await correlate_suspect(username)
    last_active = None
    if correlation.get("last_active"):
        try:
            last_active = datetime.fromisoformat(correlation["last_active"].rstrip("Z"))
        except ValueError:
            last_active = None

    suspect = CTIProjectSuspect(
        project_id=project_id,
        username=username,
        alias=req.alias or username,
        platform=req.platform or (" & ".join(correlation["platforms"]) or None),
        role=req.role,
        notes=req.notes,
        risk_score=correlation["risk_score"],
        matched_sources=correlation["matched_sources"],
        evidence_record_ids=correlation["evidence_record_ids"],
        correlation_count=correlation["correlation_count"],
        correlation_summary=correlation["correlation_summary"],
        last_correlated_at=datetime.utcnow(),
        last_active=last_active,
    )
    db.add(suspect)
    await db.commit()
    await db.refresh(suspect)

    await record_audit_event(
        action="ADD_CTI_SUSPECT", resource=f"cti_project_{project_id}",
        details=f"Suspect '{username}' tracked; risk {correlation['risk_score']} "
                f"from {correlation['correlation_count']} record(s)",
    )
    return {
        "status": "SUCCESS",
        "suspect": _serialize_suspect(suspect),
        "evidence_found": correlation["found"],
        "score_breakdown": correlation["score_breakdown"],
        "linked_actors": correlation["linked_actors"],
        "correlation_summary": correlation["correlation_summary"],
    }


@router.post("/projects/{project_id}/suspects/{suspect_id}/recorrelate")
async def recorrelate_suspect(project_id: int, suspect_id: int,
                              db: AsyncSession = Depends(get_db)):
    """
    Re-run correlation against everything collected since the account was added.

    Scores go stale as collection continues; this is how they are refreshed.
    """
    suspect = (await db.execute(
        select(CTIProjectSuspect)
        .where(CTIProjectSuspect.id == suspect_id)
        .where(CTIProjectSuspect.project_id == project_id)
    )).scalars().first()
    if not suspect:
        raise HTTPException(status_code=404, detail=f"Suspect {suspect_id} not found")

    previous = suspect.risk_score or 0
    correlation = await correlate_suspect(suspect.username)

    suspect.risk_score = correlation["risk_score"]
    suspect.matched_sources = correlation["matched_sources"]
    suspect.evidence_record_ids = correlation["evidence_record_ids"]
    suspect.correlation_count = correlation["correlation_count"]
    suspect.correlation_summary = correlation["correlation_summary"]
    suspect.last_correlated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(suspect)

    return {
        "status": "SUCCESS",
        "suspect": _serialize_suspect(suspect),
        "previous_risk_score": previous,
        "score_delta": correlation["risk_score"] - previous,
        "score_breakdown": correlation["score_breakdown"],
    }


# ─────────────────────────────────────────────────────────────
# Dataset compression & AES-256-GCM encryption
# ─────────────────────────────────────────────────────────────

def _derive_aes_key(passphrase: str) -> bytes:
    """
    Derive a 256-bit key from a passphrase.

    PBKDF2 with a fixed salt, rather than a bare SHA-256 digest: a single hash
    of a passphrase is cheap to brute-force. A per-payload random salt would be
    better still, but would change the stored payload format.
    """
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(), length=32,
        salt=b"drug-intel-vault-v1", iterations=200_000,
    )
    return kdf.derive(passphrase.encode("utf-8"))


@router.post("/compress-encrypt")
async def compress_and_encrypt(req: CompressEncryptRequest):
    """Compress a dataset with zlib and encrypt it with AES-256-GCM."""
    raw = req.data_payload.encode("utf-8")
    compressed = zlib.compress(raw, level=9)

    key = _derive_aes_key(req.passphrase)
    nonce = os.urandom(12)
    ciphertext = AESGCM(key).encrypt(nonce, compressed, None)

    ratio = round((1 - len(compressed) / len(raw)) * 100, 2) if raw else 0.0
    return {
        "status": "SUCCESS",
        "original_size_bytes": len(raw),
        "compressed_size_bytes": len(compressed),
        "compression_ratio_pct": ratio,
        "encrypted_size_bytes": len(ciphertext),
        "encrypted_payload_b64": base64.b64encode(ciphertext).decode(),
        "nonce_b64": base64.b64encode(nonce).decode(),
        "algorithm": "AES-256-GCM",
        "key_derivation": "PBKDF2-HMAC-SHA256, 200000 iterations",
    }


@router.post("/decrypt-decompress")
async def decrypt_and_decompress(req: DecryptDecompressRequest):
    """Reverse compress-encrypt. A wrong passphrase fails authentication."""
    try:
        key = _derive_aes_key(req.passphrase)
        nonce = base64.b64decode(req.nonce_b64)
        ciphertext = base64.b64decode(req.encrypted_payload_b64)
        compressed = AESGCM(key).decrypt(nonce, ciphertext, None)
        plaintext = zlib.decompress(compressed).decode("utf-8")
    except Exception:
        # Deliberately non-specific: distinguishing "wrong key" from "corrupt
        # payload" tells an attacker which half they got right.
        raise HTTPException(
            status_code=400,
            detail="Decryption failed: wrong passphrase or corrupted payload")

    return {
        "status": "SUCCESS",
        "decrypted_size_bytes": len(plaintext),
        "data_payload": plaintext,
    }
