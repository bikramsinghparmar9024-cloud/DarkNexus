"""
Manually submitted image evidence.

Photographs seized from a handset are often the only intelligence in a case
that was never posted anywhere, so there has to be a way in that is not a
crawler. What matters is that a submitted photograph goes through the same
forensic path as one recovered from a page - one pipeline, so neither gets a
weaker chain of custody than the other.

The other thing under test is honesty about absence. Most images that have
passed through a messaging app carry no EXIF at all, and a result that simply
shows empty fields invites the reader to assume extraction failed. The
response says which of those it is.
"""

import io

import pytest


def _jpeg(with_gps: bool = False) -> bytes:
    """A small JPEG, optionally carrying EXIF GPS for Attari."""
    from PIL import Image

    buffer = io.BytesIO()
    image = Image.new("RGB", (48, 32), (90, 120, 160))

    if with_gps:
        import piexif

        def rational(value: float):
            degrees = int(value)
            minutes = int((value - degrees) * 60)
            seconds = round((((value - degrees) * 60) - minutes) * 60 * 100)
            return ((degrees, 1), (minutes, 1), (seconds, 100))

        lat, lon = 31.6026, 74.6033          # Attari, ~2.5 km from the border
        exif = {
            "0th": {
                piexif.ImageIFD.Make: b"Xiaomi",
                piexif.ImageIFD.Model: b"Redmi Note 12",
            },
            "Exif": {piexif.ExifIFD.DateTimeOriginal: b"2026:09:02 23:14:07"},
            "GPS": {
                piexif.GPSIFD.GPSLatitudeRef: b"N",
                piexif.GPSIFD.GPSLatitude: rational(lat),
                piexif.GPSIFD.GPSLongitudeRef: b"E",
                piexif.GPSIFD.GPSLongitude: rational(lon),
            },
            "1st": {}, "thumbnail": None,
        }
        image.save(buffer, format="JPEG", exif=piexif.dump(exif))
    else:
        image.save(buffer, format="JPEG")

    return buffer.getvalue()


class TestUploadedImageForensics:

    async def test_a_photograph_with_gps_is_placed_on_the_map(self, db, client):
        response = await client.post(
            "/api/media/upload",
            files={"file": ("seized.jpg", _jpeg(with_gps=True), "image/jpeg")},
            data={"case_reference": "FIR-101/2026"},
        )
        assert response.status_code == 200
        forensics = response.json()["forensics"]

        assert forensics["has_exif"] is True
        assert forensics["device_signature"] == "Xiaomi Redmi Note 12"
        assert forensics["gps"] is not None
        assert forensics["in_border_corridor"] is True
        assert forensics["distance_to_border_km"] is not None

    async def test_the_original_bytes_are_hashed(self, db, client):
        """Chain of custody: the digest covers the file as submitted."""
        import hashlib

        payload = _jpeg()
        response = await client.post(
            "/api/media/upload",
            files={"file": ("photo.jpg", payload, "image/jpeg")})

        assert response.json()["sha256"] == hashlib.sha256(payload).hexdigest()

    async def test_the_submitter_comes_from_the_token(self, db, client):
        """
        Who submitted a piece of evidence is not something the caller should
        be able to assert in the request body.
        """
        response = await client.post(
            "/api/media/upload",
            files={"file": ("photo.jpg", _jpeg(), "image/jpeg")})
        assert response.json()["submitted_by"]

    async def test_a_media_artifact_row_is_created(self, db, client):
        from sqlalchemy import select
        from database.postgres import MediaArtifact

        await client.post(
            "/api/media/upload",
            files={"file": ("seized.jpg", _jpeg(with_gps=True), "image/jpeg")})

        artifacts = (await db.execute(select(MediaArtifact))).scalars().all()
        assert len(artifacts) == 1
        assert artifacts[0].in_border_corridor is True
        assert artifacts[0].device_signature == "Xiaomi Redmi Note 12"

    async def test_the_submission_becomes_a_searchable_record(self, db, client):
        from sqlalchemy import select
        from database.postgres import ScrapedData

        response = await client.post(
            "/api/media/upload",
            files={"file": ("seized.jpg", _jpeg(with_gps=True), "image/jpeg")},
            data={"case_reference": "FIR-101/2026"})

        record = (await db.execute(
            select(ScrapedData).where(
                ScrapedData.id == response.json()["record_id"]))).scalars().first()

        assert record is not None
        assert record.source_type == "FORENSIC"
        provenance = (record.metadata_json or {}).get("provenance", {})
        assert provenance["acquisition_method"] == "MANUAL_SUBMISSION"
        assert provenance["case_reference"] == "FIR-101/2026"


class TestHonestyAboutAbsence:

    async def test_a_stripped_image_says_why_it_is_empty(self, db, client):
        """
        An image with no EXIF is the normal case for anything forwarded
        through a messaging app. Blank fields alone would read as a failure.
        """
        response = await client.post(
            "/api/media/upload",
            files={"file": ("forwarded.jpg", _jpeg(), "image/jpeg")})
        body = response.json()

        assert body["forensics"]["has_exif"] is False
        assert body["forensics"]["gps"] is None
        assert any("strip it on upload" in note for note in body["notes"])

    async def test_gps_absence_is_stated_explicitly(self, db, client):
        response = await client.post(
            "/api/media/upload",
            files={"file": ("forwarded.jpg", _jpeg(), "image/jpeg")})
        assert any("No GPS coordinates" in n for n in response.json()["notes"])

    async def test_a_border_hit_is_stated_explicitly(self, db, client):
        response = await client.post(
            "/api/media/upload",
            files={"file": ("seized.jpg", _jpeg(with_gps=True), "image/jpeg")})
        assert any("border corridor" in n for n in response.json()["notes"])


class TestRejections:

    async def test_a_non_image_is_refused(self, db, client):
        response = await client.post(
            "/api/media/upload",
            files={"file": ("notes.txt", b"just text", "text/plain")})
        assert response.status_code == 415

    async def test_an_empty_file_is_refused(self, db, client):
        response = await client.post(
            "/api/media/upload",
            files={"file": ("empty.jpg", b"", "image/jpeg")})
        assert response.status_code == 400

    async def test_an_oversized_file_is_refused_with_the_limit(self, db, client):
        from routes.media_routes import MAX_UPLOAD_BYTES

        response = await client.post(
            "/api/media/upload",
            files={"file": ("huge.jpg", b"\xff" * (MAX_UPLOAD_BYTES + 1),
                            "image/jpeg")})
        assert response.status_code == 413
        assert "limit" in response.json()["detail"]


class TestOcrAvailabilityIsNotConfusedWithAbsence:
    """
    pytesseract installs cleanly while the tesseract binary it drives may be
    missing, in which case every image returns empty text. Reported as "no
    readable text found", a broken installation is indistinguishable from a
    photograph that genuinely contains none - so a number visible in a seized
    photo would silently never be extracted, and the panel would say the
    analysis completed.
    """

    async def test_a_missing_engine_is_reported_as_such(self, db, client, monkeypatch):
        import media.pipeline as pipeline

        monkeypatch.setattr(pipeline, "ocr_available",
                            lambda: (False, "tesseract is not installed."))

        response = await client.post(
            "/api/media/upload",
            files={"file": ("photo.jpg", _jpeg(), "image/jpeg")})
        body = response.json()

        assert body["forensics"]["ocr_available"] is False
        assert any("could not be read" in n for n in body["notes"])
        assert not any("found no readable text" in n for n in body["notes"]), (
            "a missing engine must not be reported as an empty photograph")

    async def test_a_working_engine_reporting_nothing_says_nothing_was_found(
            self, db, client, monkeypatch):
        import media.pipeline as pipeline

        monkeypatch.setattr(pipeline, "ocr_available", lambda: (True, None))

        response = await client.post(
            "/api/media/upload",
            files={"file": ("photo.jpg", _jpeg(), "image/jpeg")})
        body = response.json()

        assert body["forensics"]["ocr_available"] is True
        assert any("found no readable text" in n for n in body["notes"])

    def test_availability_check_never_raises(self):
        """Called on every upload; it must degrade, not fail the request."""
        from media.pipeline import ocr_available

        available, reason = ocr_available()
        assert isinstance(available, bool)
        assert available or reason
