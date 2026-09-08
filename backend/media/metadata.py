"""
Forensic Metadata Extraction for Images and Video.

Photographs and videos posted by traffickers frequently carry metadata the
poster never intended to publish:

  * GPS coordinates of where the shot was taken (EXIF GPSInfo)
  * Camera make/model and lens - links separate posts to one physical device
  * Original capture timestamp, distinct from the upload time
  * Software fingerprints showing editing or metadata scrubbing

A GPS fix is the most valuable artifact here: it turns an anonymous photograph
into a map reference, which ai.geo_resolver then measures against the Indo-Pak
border.
"""

from typing import Any, Dict, Optional
from datetime import datetime
import struct
import logging

logger = logging.getLogger("media_metadata")

try:
    from PIL import Image, ExifTags
except ImportError:
    Image = None
    ExifTags = None

try:
    import cv2
except ImportError:
    cv2 = None

# EXIF tag name -> numeric id, resolved once at import.
_TAG_IDS = {v: k for k, v in ExifTags.TAGS.items()} if ExifTags else {}

# Fields worth surfacing to an investigator; the rest is camera noise.
INTERESTING_EXIF = [
    "Make", "Model", "LensModel", "Software", "Artist", "Copyright",
    "DateTime", "DateTimeOriginal", "DateTimeDigitized",
    "ImageWidth", "ImageLength", "Orientation", "ExposureTime", "FNumber",
    "ISOSpeedRatings", "FocalLength", "BodySerialNumber",
]

# EXIF epoch for MP4 container timestamps (1904-01-01 -> 1970-01-01).
_MP4_EPOCH_OFFSET = 2082844800


def _to_degrees(value) -> Optional[float]:
    """Convert an EXIF rational triple (deg, min, sec) to decimal degrees."""
    try:
        d, m, s = value
        return float(d) + float(m) / 60.0 + float(s) / 3600.0
    except Exception:
        return None


def _clean(value):
    """Coerce an EXIF value into something JSON-serialisable."""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", "ignore").strip("\x00").strip()
        except Exception:
            return repr(value)
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if hasattr(value, "numerator") and hasattr(value, "denominator"):
        try:
            return float(value)
        except Exception:
            return str(value)
    return str(value)


def extract_gps(exif_raw: Dict[int, Any]) -> Optional[Dict[str, Any]]:
    """Pull a decimal lat/lon out of the EXIF GPSInfo block, if one is present."""
    if not ExifTags:
        return None

    gps_ifd = exif_raw.get(_TAG_IDS.get("GPSInfo"))
    if not gps_ifd:
        return None

    gps = {ExifTags.GPSTAGS.get(k, k): v for k, v in gps_ifd.items()}

    lat = _to_degrees(gps.get("GPSLatitude"))
    lon = _to_degrees(gps.get("GPSLongitude"))
    if lat is None or lon is None:
        return None

    if str(gps.get("GPSLatitudeRef", "N")).upper().startswith("S"):
        lat = -lat
    if str(gps.get("GPSLongitudeRef", "E")).upper().startswith("W"):
        lon = -lon

    out: Dict[str, Any] = {"lat": round(lat, 6), "lon": round(lon, 6)}

    altitude = gps.get("GPSAltitude")
    if altitude is not None:
        try:
            alt = float(altitude)
            if str(gps.get("GPSAltitudeRef", 0)).strip() in ("1", "b'\\x01'"):
                alt = -alt
            out["altitude_m"] = round(alt, 1)
        except Exception:
            pass

    datestamp = gps.get("GPSDateStamp")
    if datestamp:
        out["gps_datestamp"] = _clean(datestamp)

    stamp = gps.get("GPSTimeStamp")
    if stamp:
        try:
            h, m, s = [int(float(x)) for x in stamp]
            out["gps_timestamp"] = "%02d:%02d:%02d" % (h, m, s)
        except Exception:
            pass

    return out


def extract_image_metadata(path: str) -> Dict[str, Any]:
    """Read dimensions, selected EXIF fields, and any embedded GPS fix."""
    result: Dict[str, Any] = {
        "media_type": "IMAGE",
        "width": None,
        "height": None,
        "format": None,
        "exif": {},
        "gps": None,
        "has_exif": False,
    }
    if Image is None:
        result["error"] = "Pillow not installed"
        return result

    try:
        with Image.open(path) as img:
            result["width"], result["height"] = img.size
            result["format"] = img.format
            result["mode"] = img.mode

            try:
                exif_raw = img._getexif()
            except Exception:
                exif_raw = None

            if exif_raw:
                result["has_exif"] = True
                for tag_id, value in exif_raw.items():
                    name = ExifTags.TAGS.get(tag_id, str(tag_id))
                    if name in INTERESTING_EXIF:
                        result["exif"][name] = _clean(value)
                result["gps"] = extract_gps(exif_raw)
    except Exception as e:
        result["error"] = "%s: %s" % (type(e).__name__, e)

    return result


def _mp4_creation_time(path: str) -> Optional[str]:
    """
    Read the creation timestamp from an MP4/MOV 'mvhd' atom.

    Container timestamps survive re-encoding more often than people expect and
    record when the footage was shot, not when it was uploaded.
    """
    try:
        with open(path, "rb") as f:
            data = f.read(4 * 1024 * 1024)
        idx = data.find(b"mvhd")
        if idx < 0:
            return None
        version = data[idx + 4]
        if version == 1:
            secs = struct.unpack(">Q", data[idx + 8:idx + 16])[0]
        else:
            secs = struct.unpack(">I", data[idx + 8:idx + 12])[0]
        if not secs:
            return None
        unix = secs - _MP4_EPOCH_OFFSET
        if unix <= 0 or unix > 4102444800:  # sanity: not before 1970, not after 2100
            return None
        return datetime.utcfromtimestamp(unix).isoformat() + "Z"
    except Exception:
        return None


def extract_video_metadata(path: str) -> Dict[str, Any]:
    """Read resolution, duration, frame rate, and container creation time."""
    result: Dict[str, Any] = {
        "media_type": "VIDEO",
        "width": None,
        "height": None,
        "duration_seconds": None,
        "fps": None,
        "frame_count": None,
        "creation_time": _mp4_creation_time(path),
        "gps": None,
    }
    if cv2 is None:
        result["error"] = "opencv not installed"
        return result

    cap = None
    try:
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            result["error"] = "could not open video"
            return result
        result["width"] = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or None
        result["height"] = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or None
        fps = cap.get(cv2.CAP_PROP_FPS) or 0
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        result["fps"] = round(fps, 2) if fps else None
        result["frame_count"] = frames or None
        if fps > 0 and frames > 0:
            result["duration_seconds"] = round(frames / fps, 2)
    except Exception as e:
        result["error"] = "%s: %s" % (type(e).__name__, e)
    finally:
        if cap is not None:
            cap.release()

    return result


def extract_metadata(path: str, media_type: str) -> Dict[str, Any]:
    """Dispatch to the image or video extractor."""
    if media_type == "VIDEO":
        return extract_video_metadata(path)
    return extract_image_metadata(path)
