"""
Media Forensics API Routes.

Exposes the images and video recovered alongside scraped records, together with
the metadata lifted out of them - camera signatures, capture timestamps, and
EXIF GPS fixes resolved against the Indo-Pak border.
"""

import os
from typing import Optional

from fastapi import (APIRouter, Depends, File, Form, HTTPException,
                     UploadFile)
from fastapi.responses import FileResponse
from sqlalchemy import select, desc, func
from sqlalchemy.ext.asyncio import AsyncSession

from database.postgres import get_db, MediaArtifact, ScrapedData
from evidence.audit_log import record_audit_event
from auth.rbac import require_investigator
from auth.jwt_handler import get_current_user_payload

router = APIRouter(
    prefix="/api/media", tags=["Media Forensics"],
    # Every endpoint on this router requires authentication.
    dependencies=[Depends(require_investigator)],
)


def _serialize(m: MediaArtifact) -> dict:
    return {
        "id": m.id,
        "scraped_data_id": m.scraped_data_id,
        "source_url": m.source_url,
        "media_type": m.media_type,
        "mime_type": m.mime_type,
        "file_size": m.file_size,
        "sha256_hash": m.sha256_hash,
        "dimensions": {"width": m.width, "height": m.height},
        "duration_seconds": m.duration_seconds,
        "forensics": {
            "exif": m.exif_json or {},
            "capture_timestamp": m.capture_timestamp,
            "device_signature": m.device_signature,
            "has_gps": m.gps_lat is not None,
        },
        "geo": m.geo_json,
        "in_border_corridor": m.in_border_corridor,
        "ocr_text": m.ocr_text,
        "created_at": m.created_at.isoformat() + "Z" if m.created_at else None,
    }


@router.get("/record/{record_id}")
async def media_for_record(record_id: int, db: AsyncSession = Depends(get_db)):
    """All media artifacts recovered alongside one intelligence record."""
    stmt = select(MediaArtifact).where(MediaArtifact.scraped_data_id == record_id)
    items = (await db.execute(stmt)).scalars().all()
    return {
        "record_id": record_id,
        "count": len(items),
        "artifacts": [_serialize(m) for m in items],
    }


@router.get("/gps-fixes")
async def gps_fixes(border_only: bool = False, db: AsyncSession = Depends(get_db)):
    """
    Every photograph carrying a GPS fix, ready to plot on a map.

    Set border_only=true to return just those inside the 15 km critical
    corridor along the international border.
    """
    stmt = select(MediaArtifact).where(MediaArtifact.gps_lat.is_not(None))
    if border_only:
        stmt = stmt.where(MediaArtifact.in_border_corridor.is_(True))
    items = (await db.execute(stmt.order_by(desc(MediaArtifact.created_at)))).scalars().all()

    return {
        "count": len(items),
        "border_corridor_count": sum(1 for m in items if m.in_border_corridor),
        "fixes": [
            {
                "media_id": m.id,
                "record_id": m.scraped_data_id,
                "lat": m.gps_lat,
                "lon": m.gps_lon,
                "district": (m.geo_json or {}).get("nearest_known_location"),
                "distance_to_border_km": (m.geo_json or {}).get("distance_to_border_km"),
                "in_border_corridor": m.in_border_corridor,
                "device": m.device_signature,
                "captured_at": m.capture_timestamp,
                "source_url": m.source_url,
            }
            for m in items
        ],
    }


@router.get("/devices")
async def device_correlation(db: AsyncSession = Depends(get_db)):
    """
    Group artifacts by camera signature.

    A device seen across several records is a correlation lead: it suggests one
    physical phone behind otherwise unconnected posts.
    """
    stmt = (
        select(MediaArtifact.device_signature, func.count(MediaArtifact.id))
        .where(MediaArtifact.device_signature.is_not(None))
        .group_by(MediaArtifact.device_signature)
        .order_by(desc(func.count(MediaArtifact.id)))
    )
    rows = (await db.execute(stmt)).all()
    return {
        "devices": [
            {"device": device, "artifact_count": count, "is_correlation_lead": count > 1}
            for device, count in rows
        ]
    }


@router.get("/{media_id}")
async def get_media_artifact(media_id: int, db: AsyncSession = Depends(get_db)):
    """Full forensic detail for one artifact."""
    m = (await db.execute(
        select(MediaArtifact).where(MediaArtifact.id == media_id)
    )).scalars().first()
    if not m:
        raise HTTPException(status_code=404, detail=f"Media artifact {media_id} not found")

    await record_audit_event(
        action="ACCESS_MEDIA_ARTIFACT",
        resource=f"media_{media_id}",
        details=f"Media artifact {media_id} inspected",
    )
    return _serialize(m)


@router.get("/{media_id}/file")
async def download_media_file(media_id: int, db: AsyncSession = Depends(get_db)):
    """Serve the stored original file."""
    m = (await db.execute(
        select(MediaArtifact).where(MediaArtifact.id == media_id)
    )).scalars().first()
    if not m:
        raise HTTPException(status_code=404, detail=f"Media artifact {media_id} not found")
    if not m.local_path or not os.path.exists(m.local_path):
        raise HTTPException(status_code=404, detail="Stored file is missing from the media vault")

    await record_audit_event(
        action="DOWNLOAD_MEDIA_FILE",
        resource=f"media_{media_id}",
        details=f"Original media file {media_id} retrieved ({m.sha256_hash[:16]}...)",
    )
    return FileResponse(m.local_path, media_type=m.mime_type or "application/octet-stream")


# ── Manual submission ────────────────────────────────────────────────

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


@router.post("/upload")
async def upload_media(
    file: UploadFile = File(...),
    case_reference: Optional[str] = Form(None),
    note: Optional[str] = Form(None),
    token_payload: dict = Depends(get_current_user_payload),
):
    """
    Submit an image as evidence and extract what it carries.

    Photographs seized from a handset are often the only intelligence in a
    case that was never posted anywhere, so there has to be a way in for them
    that is not a crawler. The file goes through exactly the same forensic
    path as media recovered from a page - one pipeline, so a submitted
    photograph and a scraped one are analysed identically and neither gets a
    weaker chain of custody than the other.

    Extracted: SHA-256 over the original bytes, EXIF, camera signature,
    capture timestamp, GPS resolved to a district and a distance to the
    border, and OCR of any text in the frame.
    """
    from datetime import datetime

    from media.pipeline import analyze_media_file, _storage_path
    from ai.enrichment import store_intelligence
    from auth.hashing import generate_sha256

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(f"File is {len(contents) // (1024 * 1024)} MB; the limit is "
                    f"{MAX_UPLOAD_BYTES // (1024 * 1024)} MB."))

    mime = (file.content_type or "").lower()
    if not mime.startswith("image/"):
        raise HTTPException(
            status_code=415,
            detail=f"Expected an image; this file reports itself as {mime or 'unknown'}.")

    # Content-addressed, so submitting the same photograph twice does not
    # produce a second copy on disk.
    sha256 = generate_sha256(contents)
    path = _storage_path(sha256, mime, "IMAGE")
    if not os.path.exists(path):
        with open(path, "wb") as handle:
            handle.write(contents)

    analysed = analyze_media_file({
        "url": f"upload://{file.filename}",
        "path": path,
        "sha256": sha256,
        "mime_type": mime,
        "media_type": "IMAGE",
        "size": len(contents),
    })

    uploader = (token_payload.get("sub") or token_payload.get("username")
                or "unknown_investigator")

    # Text lifted out of the frame is analysed like any other intercept, so a
    # number visible only in a photograph still reaches scoring and the graph.
    ocr_text = analysed.get("ocr_text") or ""
    saved = await store_intelligence(
        source_type="FORENSIC",
        source_url=f"upload://{file.filename}",
        raw_content=ocr_text or f"[image submitted with no readable text: {file.filename}]",
        cleaned_text=ocr_text,
        ocr_text=ocr_text,
        media_items=[analysed],
        provenance={
            "acquisition_method": "MANUAL_SUBMISSION",
            "submitted_by": uploader,
            "original_filename": file.filename,
            "case_reference": case_reference,
            "note": note,
            "title": file.filename,
            "submitted_at": datetime.utcnow().isoformat() + "Z",
        },
    )

    await record_audit_event(
        action="UPLOAD_MEDIA_EVIDENCE",
        resource=f"record_{saved.get('record_id')}",
        details=(f"{uploader} submitted {file.filename} "
                 f"({len(contents)} bytes, sha256 {sha256[:16]}...)"
                 + (f" for case {case_reference}" if case_reference else "")),
    )

    geo = analysed.get("geo") or {}
    return {
        "status": saved.get("status"),
        "record_id": saved.get("record_id"),
        "filename": file.filename,
        "size_bytes": len(contents),
        "sha256": sha256,
        "submitted_by": uploader,
        "case_reference": case_reference,
        "forensics": {
            "has_exif": analysed.get("has_exif", False),
            "device_signature": analysed.get("device_signature"),
            "capture_timestamp": analysed.get("capture_timestamp"),
            "width": analysed.get("width"),
            "height": analysed.get("height"),
            "gps": analysed.get("gps"),
            "location": geo.get("nearest_location") or geo.get("location"),
            "distance_to_border_km": geo.get("distance_to_border_km"),
            "in_border_corridor": analysed.get("in_border_corridor", False),
            "ocr_text": ocr_text,
            "ocr_char_count": len(ocr_text),
            "ocr_available": _ocr_state()[0],
            "ocr_unavailable_reason": _ocr_state()[1],
            "metadata_error": analysed.get("metadata_error"),
        },
        # Said plainly rather than left for the reader to infer from empty
        # fields: a photograph stripped of EXIF is the normal case for
        # anything that has passed through a messaging app.
        "notes": _upload_notes(analysed),
        "threat_level": saved.get("threat_level"),
        "analysis": saved.get("analysis", {}).get("threat"),
    }


def _ocr_state():
    from media.pipeline import ocr_available
    return ocr_available()


def _upload_notes(analysed: dict) -> list:
    """Plain-language observations about what the file did and did not carry."""
    notes = []
    if not analysed.get("has_exif"):
        notes.append("No EXIF metadata. Messaging apps and social platforms "
                     "strip it on upload, so its absence is expected for an "
                     "image that has been forwarded rather than taken from "
                     "the handset.")
    if not analysed.get("gps"):
        notes.append("No GPS coordinates recorded in the file.")
    elif not analysed.get("in_border_corridor"):
        notes.append("GPS present and resolved outside the 15 km border corridor.")
    else:
        notes.append("GPS places this photograph inside the 15 km border corridor.")
    if not analysed.get("device_signature"):
        notes.append("No camera make or model recorded.")
    if not (analysed.get("ocr_text") or "").strip():
        from media.pipeline import ocr_available

        available, reason = ocr_available()
        # "No text found" and "OCR never ran" are different findings, and
        # only one of them is a statement about the photograph.
        notes.append("OCR found no readable text in the image." if available
                     else f"Text could not be read from this image. {reason}")
    if analysed.get("metadata_error"):
        notes.append(f"Metadata extraction reported: {analysed['metadata_error']}")
    return notes
