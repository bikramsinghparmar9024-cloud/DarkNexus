"""
Media Acquisition Pipeline.

For each media reference discovered on a page:

  1. Download it, with a size ceiling and content-type validation
  2. Hash the bytes (SHA-256) so the artifact is independently verifiable
  3. Store it under a content-addressed filename
  4. Extract forensic metadata - EXIF, GPS, camera, video properties
  5. Resolve any GPS fix against the Punjab border geography
  6. OCR images so text inside screenshots reaches the analysis layer

Returns both the persisted rows and a text blob that ai.enrichment folds into
the record's threat analysis, so a phone number visible only inside a
screenshot is still extracted and scored.
"""

from typing import Any, Dict, List, Optional, Tuple
import os
import hashlib
import logging

import httpx

from config import settings
from ai.geo_resolver import resolve_coordinates
from media.metadata import extract_metadata

logger = logging.getLogger("media_pipeline")

ALLOWED_IMAGE_MIME = ("image/jpeg", "image/png", "image/gif", "image/webp",
                      "image/bmp", "image/tiff", "image/heic")
ALLOWED_VIDEO_MIME = ("video/mp4", "video/quicktime", "video/webm",
                      "video/x-matroska", "application/octet-stream")

_EXT_BY_MIME = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
    "image/webp": ".webp", "image/bmp": ".bmp", "image/tiff": ".tiff",
    "video/mp4": ".mp4", "video/quicktime": ".mov", "video/webm": ".webm",
}


def _storage_path(sha256: str, mime: str, media_type: str) -> str:
    """Content-addressed path: identical files are stored once."""
    ext = _EXT_BY_MIME.get(mime) or (".mp4" if media_type == "VIDEO" else ".jpg")
    shard = os.path.join(settings.MEDIA_DIR, sha256[:2])
    os.makedirs(shard, exist_ok=True)
    return os.path.join(shard, sha256 + ext)


async def download_media(url: str, media_type: str,
                         client: Optional[httpx.AsyncClient] = None) -> Optional[Dict[str, Any]]:
    """
    Fetch one media file. Returns None when it is missing, too large, or not
    actually the media type it claimed to be.
    """
    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(
            timeout=settings.MEDIA_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        )

    try:
        # Stream so an oversized file is abandoned rather than buffered whole.
        async with client.stream("GET", url) as response:
            if response.status_code != 200:
                logger.info("Media fetch %s returned HTTP %s", url, response.status_code)
                return None

            mime = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
            allowed = ALLOWED_IMAGE_MIME if media_type == "IMAGE" else ALLOWED_VIDEO_MIME
            if mime and mime not in allowed:
                logger.info("Media %s has unexpected content-type %s", url, mime)
                return None

            declared = response.headers.get("content-length")
            if declared and int(declared) > settings.MEDIA_MAX_BYTES:
                logger.info("Media %s too large (%s bytes)", url, declared)
                return None

            chunks = bytearray()
            async for chunk in response.aiter_bytes():
                chunks.extend(chunk)
                if len(chunks) > settings.MEDIA_MAX_BYTES:
                    logger.info("Media %s exceeded size ceiling mid-download", url)
                    return None

        data = bytes(chunks)
        if not data:
            return None

        sha256 = hashlib.sha256(data).hexdigest()
        path = _storage_path(sha256, mime, media_type)
        if not os.path.exists(path):
            with open(path, "wb") as f:
                f.write(data)

        return {
            "url": url, "media_type": media_type, "mime_type": mime or None,
            "sha256": sha256, "path": path, "size": len(data),
        }

    except Exception as e:
        logger.warning("Media download failed for %s: %s: %s", url, type(e).__name__, e)
        return None
    finally:
        if owns_client:
            await client.aclose()


def ocr_available() -> Tuple[bool, Optional[str]]:
    """
    Whether OCR can actually run, and why not when it cannot.

    pytesseract is a wrapper: the package installs cleanly while the tesseract
    binary it drives may be absent, in which case every image returns empty
    text. Reported as "no readable text found", that is indistinguishable from
    a photograph that genuinely contains none - so a broken installation looks
    like a completed analysis, and a number visible in a seized photograph is
    silently never extracted.
    """
    if not settings.MEDIA_OCR_ENABLED:
        return False, "OCR is disabled by configuration (MEDIA_OCR_ENABLED)."
    try:
        # Ask the project's own locator, not pytesseract directly. The Windows
        # installer does not add itself to PATH, so a perfectly working engine
        # at "C:/Program Files/Tesseract-OCR" looks missing to a bare
        # get_tesseract_version() call - which is exactly what happened here:
        # the engine was installed and this check still reported it absent.
        from ocr.processor import ocr_processor

        if not ocr_processor.available:
            return False, (
                "The tesseract engine was not found. Install it "
                "(winget install UB-Mannheim.TesseractOCR), or set "
                "TESSERACT_CMD in backend/.env to the full path of "
                "tesseract.exe, then restart the backend.")

        import pytesseract
        pytesseract.get_tesseract_version()
        return True, None
    except Exception as e:
        return False, (
            "The tesseract engine is installed but could not be run: "
            f"{type(e).__name__}: {e}")


def _ocr(path: str) -> str:
    """Run OCR over a stored image, if OCR is available and enabled."""
    available, _ = ocr_available()
    if not available:
        return ""
    try:
        from ocr.processor import ocr_processor
        with open(path, "rb") as f:
            return ocr_processor.extract_text_from_bytes(f.read()) or ""
    except Exception as e:
        logger.debug("OCR skipped for %s: %s", path, e)
        return ""


def analyze_media_file(downloaded: Dict[str, Any]) -> Dict[str, Any]:
    """Extract metadata, resolve GPS, and OCR one downloaded file."""
    path = downloaded["path"]
    media_type = downloaded["media_type"]

    meta = extract_metadata(path, media_type)

    device = None
    make = (meta.get("exif") or {}).get("Make")
    model = (meta.get("exif") or {}).get("Model")
    if make or model:
        device = " ".join(str(x) for x in (make, model) if x).strip()

    capture = (
        (meta.get("exif") or {}).get("DateTimeOriginal")
        or (meta.get("exif") or {}).get("DateTime")
        or meta.get("creation_time")
    )

    gps = meta.get("gps")
    geo = resolve_coordinates(gps["lat"], gps["lon"]) if gps else None

    ocr_text = _ocr(path) if media_type == "IMAGE" else ""

    return {
        **downloaded,
        "width": meta.get("width"),
        "height": meta.get("height"),
        "duration_seconds": meta.get("duration_seconds"),
        "exif": meta.get("exif") or {},
        "has_exif": meta.get("has_exif", False),
        "capture_timestamp": capture,
        "device_signature": device,
        "gps": gps,
        "geo": geo,
        "in_border_corridor": bool(geo and geo.get("in_critical_border_corridor")),
        "ocr_text": ocr_text,
        "metadata_error": meta.get("error"),
    }


async def process_media_for_page(html: str, base_url: str,
                                 limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Discover, download and analyse every media file referenced by a page.

    Returns one analysed dict per successfully retrieved file.
    """
    if not settings.MEDIA_ENABLED or not html:
        return []

    from media.extractor import extract_media_urls

    limit = limit or settings.MEDIA_MAX_PER_RECORD
    candidates = extract_media_urls(html, base_url, limit=limit)
    if not candidates:
        return []

    results: List[Dict[str, Any]] = []
    async with httpx.AsyncClient(
        timeout=settings.MEDIA_TIMEOUT,
        follow_redirects=True,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    ) as client:
        for candidate in candidates:
            downloaded = await download_media(candidate["url"], candidate["media_type"], client)
            if not downloaded:
                continue
            analysed = analyze_media_file(downloaded)
            analysed["context"] = candidate.get("context")
            results.append(analysed)

    return results


def media_text_blob(media_items: List[Dict[str, Any]]) -> str:
    """
    Flatten media findings into text for the threat analyser.

    OCR output and resolved GPS districts are folded in, so a location that
    only ever appeared as coordinates on a photograph still contributes to the
    record's threat score and border alerting.
    """
    parts: List[str] = []
    for item in media_items:
        if item.get("ocr_text"):
            parts.append(item["ocr_text"])
        geo = item.get("geo")
        if geo and geo.get("nearest_known_location"):
            parts.append(geo["nearest_known_location"])
            if geo.get("in_critical_border_corridor"):
                parts.append("border")
    return " ".join(parts).strip()


def summarize_media(media_items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Compact summary for the record's analysis block."""
    with_gps = [m for m in media_items if m.get("gps")]
    return {
        "count": len(media_items),
        "images": sum(1 for m in media_items if m["media_type"] == "IMAGE"),
        "videos": sum(1 for m in media_items if m["media_type"] == "VIDEO"),
        "with_gps": len(with_gps),
        "with_exif": sum(1 for m in media_items if m.get("has_exif")),
        "in_border_corridor": sum(1 for m in media_items if m.get("in_border_corridor")),
        "devices": sorted({m["device_signature"] for m in media_items if m.get("device_signature")}),
        "gps_fixes": [
            {
                "lat": m["gps"]["lat"], "lon": m["gps"]["lon"],
                "district": (m.get("geo") or {}).get("nearest_known_location"),
                "distance_to_border_km": (m.get("geo") or {}).get("distance_to_border_km"),
                "source_url": m["url"],
            }
            for m in with_gps
        ],
        "ocr_chars": sum(len(m.get("ocr_text") or "") for m in media_items),
    }
