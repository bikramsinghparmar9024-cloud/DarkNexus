"""
Shared test fixtures.

Every test runs against a throwaway SQLite database and throwaway media and
report directories. The environment is configured BEFORE any backend module is
imported, because config.py reads settings at import time and creates
directories as a side effect - importing first would touch the real project
data.
"""

import os
import sys
import tempfile
from pathlib import Path

# ── Isolate the test environment before anything imports config ──────
_TMP = Path(tempfile.mkdtemp(prefix="drugintel_tests_"))

os.environ["SQLITE_URL"] = f"sqlite+aiosqlite:///{_TMP.as_posix()}/test.db"
os.environ["MEDIA_DIR"] = str(_TMP / "media")
os.environ["CHROMADB_PATH"] = str(_TMP / "chroma")
os.environ["REPORTS_DIR"] = str(_TMP / "reports")
# Keep the suite fast and deterministic: the transformer is advisory only.
os.environ["SEMANTIC_CLASSIFIER_ENABLED"] = "False"
# Media downloads must never hit the network from a unit test.
os.environ["MEDIA_ENABLED"] = "False"
# Embedding every test record costs minutes and proves nothing about the logic
# under test; semantic search has its own integration coverage.
os.environ["VECTOR_SEARCH_ENABLED"] = "False"

# Make the backend package importable when pytest is run from anywhere.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402


@pytest.fixture(scope="session")
def tmp_root() -> Path:
    """Root of the throwaway directory tree for this test session."""
    return _TMP


@pytest_asyncio.fixture
async def db():
    """
    A fresh database for one test.

    Tables are dropped and recreated so tests never see each other's rows.
    """
    from database.postgres import engine, Base, init_db, AsyncSessionLocal

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await init_db()

    async with AsyncSessionLocal() as session:
        yield session


@pytest.fixture
def gps_photo(tmp_root) -> str:
    """
    A JPEG carrying EXIF GPS for Attari - 2.5 km from the border.

    Built rather than committed so the fixture stays readable and there is no
    binary blob in the repository.
    """
    import piexif
    from PIL import Image

    path = tmp_root / "gps_photo.jpg"
    if path.exists():
        return str(path)

    def to_rational(value: float):
        deg = int(value)
        minutes = int((value - deg) * 60)
        seconds = round((((value - deg) * 60) - minutes) * 60 * 100)
        return ((deg, 1), (minutes, 1), (seconds, 100))

    lat, lon = 31.6026, 74.6033  # Attari
    exif = {
        "0th": {
            piexif.ImageIFD.Make: b"Xiaomi",
            piexif.ImageIFD.Model: b"Redmi Note 12",
            piexif.ImageIFD.Software: b"MIUI Camera",
            piexif.ImageIFD.DateTime: b"2026:09:02 23:14:07",
        },
        "Exif": {
            piexif.ExifIFD.DateTimeOriginal: b"2026:09:02 23:14:07",
            piexif.ExifIFD.ISOSpeedRatings: 1600,
        },
        "GPS": {
            piexif.GPSIFD.GPSLatitudeRef: b"N",
            piexif.GPSIFD.GPSLatitude: to_rational(lat),
            piexif.GPSIFD.GPSLongitudeRef: b"E",
            piexif.GPSIFD.GPSLongitude: to_rational(lon),
            piexif.GPSIFD.GPSAltitude: (218, 1),
            piexif.GPSIFD.GPSAltitudeRef: 0,
        },
    }
    Image.new("RGB", (640, 480), (30, 30, 40)).save(str(path), exif=piexif.dump(exif))
    return str(path)


# ── Shared sample texts ──────────────────────────────────────────────
# Referenced across several test modules so the same real-world examples are
# exercised consistently.

DEALER_OFFER = (
    "Veere Attari border te 2 packet chitta ready aa. Cash nahi lena, "
    "direct crypto ya UPI barcode te transaction karo. "
    "BTC 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa Phone 9814098211"
)

NEWS_REPORT = (
    "Punjab Police seized 2 kg of chitta near Attari yesterday. Three men "
    "were arrested and the payment was traced to a Bitcoin wallet."
)

WIKI_ARTICLE = (
    "The illegal drug trade in India involves heroin, opium and cannabis. "
    "Punjab has been particularly affected by heroin smuggled across the border."
)

PRECURSOR_OFFER = (
    "Acetic Anhydride industrial drums 50L available without NOC clearance. "
    "Immediate overnight transit to Fazilka godowns."
)

BENIGN_TEXT = (
    "The weather in Ludhiana is pleasant today and the wheat harvest "
    "looks good this season."
)


@pytest_asyncio.fixture
async def client(db):
    """
    An authenticated HTTP client against the real application.

    Routes are exercised through the ASGI app rather than by calling handler
    functions directly, so the auth dependency, request parsing and file
    upload handling are all covered - the parts most likely to break without
    a unit test noticing.
    """
    import httpx

    from app import app
    from auth.jwt_handler import create_access_token
    from database.postgres import get_db

    # The application's session dependency must use the throwaway database
    # this test is running against, not open its own.
    async def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    token = create_access_token({"sub": "test_investigator", "role": "ADMIN"})

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://testserver",
        headers={"Authorization": f"Bearer {token}"},
    ) as http_client:
        yield http_client

    app.dependency_overrides.clear()
