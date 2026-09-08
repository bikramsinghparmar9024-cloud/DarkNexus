"""
Central configuration for the Drug Intelligence System.
Uses Pydantic BaseSettings for environment variable loading and validation.
"""

import os
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional


# The values shipped in source. Anyone with a copy of this repository can
# forge a valid token while these are in use, so startup refuses them unless
# DEBUG is explicitly on.
PLACEHOLDER_SECRET = "change-this-in-production-use-openssl-rand-hex-32"
PLACEHOLDER_JWT_SECRET = "jwt-secret-change-in-production"


class InsecureConfiguration(RuntimeError):
    """Raised when the application is asked to run with placeholder secrets."""


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env file."""

    # ── App ──────────────────────────────────────────────
    APP_NAME: str = "Drug Intelligence System"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = True
    SECRET_KEY: str = PLACEHOLDER_SECRET
    BASE_DIR: Path = Path(__file__).resolve().parent

    # ── Database: PostgreSQL (primary) ───────────────────
    # Falls back to SQLite if POSTGRES_URL is not set
    POSTGRES_URL: Optional[str] = None
    SQLITE_URL: str = "sqlite+aiosqlite:///./drug_intel.db"

    @property
    def DATABASE_URL(self) -> str:
        """Use PostgreSQL if configured, otherwise fall back to SQLite."""
        if self.POSTGRES_URL:
            return self.POSTGRES_URL
        return self.SQLITE_URL

    # ── Database: Neo4j (graph DB) ───────────────────────
    NEO4J_URI: str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password"
    NEO4J_ENABLED: bool = False  # Set True when Neo4j is installed

    # ── Database: ChromaDB (vector store) ────────────────
    CHROMADB_PATH: str = "./chroma_data"
    CHROMADB_COLLECTION: str = "drug_intel_embeddings"

    # ── Authentication ───────────────────────────────────
    JWT_SECRET: str = PLACEHOLDER_JWT_SECRET
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # ── Tor Configuration ────────────────────────────────
    # Host running the Tor daemon. Localhost when Tor is installed alongside
    # the application; a service name such as "tor" when each runs in its own
    # container, where 127.0.0.1 would resolve to the backend container itself
    # and every hidden-service fetch would fail with connection refused.
    TOR_HOST: str = "127.0.0.1"
    TOR_SOCKS_PORT: int = 9050
    TOR_CONTROL_PORT: int = 9051
    TOR_CONTROL_PASSWORD: Optional[str] = None
    TOR_ENABLED: bool = False  # Set True when Tor is installed

    # ── Telegram Configuration ───────────────────────────
    TELEGRAM_API_ID: Optional[int] = None
    TELEGRAM_API_HASH: Optional[str] = None
    TELEGRAM_PHONE: Optional[str] = None
    TELEGRAM_SESSION_NAME: str = "drug_intel_session"

    # ── Proxy Configuration ──────────────────────────────
    PROXY_ROTATION_STRATEGY: str = "round_robin"  # round_robin | random
    PROXY_HEALTH_CHECK_INTERVAL: int = 300  # seconds
    PROXY_MAX_LATENCY_MS: int = 5000
    PROXY_SOURCES: list[str] = [
        "https://api.proxyscrape.com/v4/free-proxy-list/get?request=display_proxies&proxy_format=protocolipport&format=text",
    ]

    # ── Scraper Configuration ────────────────────────────
    SCRAPE_DELAY_MIN: float = 2.0  # seconds
    SCRAPE_DELAY_MAX: float = 7.0  # jitter range
    SCRAPE_MAX_RETRIES: int = 3
    SCRAPE_TIMEOUT: int = 30  # seconds per request
    SCRAPE_MAX_CONCURRENT: int = 3

    # ── Semantic / ML Analysis ───────────────────────────
    # Advisory only - the speech-act detector drives threat adjustment.
    # Measured worse than useless as a decision-maker (see ai/speech_act.py),
    # and costs 1-3s per record on CPU. Off by default.
    SEMANTIC_CLASSIFIER_ENABLED: bool = False
    SEMANTIC_CLASSIFIER_MODEL: str = "valhalla/distilbart-mnli-12-3"
    SEMANTIC_MIN_CHARS: int = 25       # skip the model on trivially short text
    VECTOR_SEARCH_ENABLED: bool = True

    # ── Media Acquisition & Forensics ────────────────────
    MEDIA_ENABLED: bool = True
    MEDIA_DIR: str = "./evidence_media"
    MEDIA_MAX_BYTES: int = 25_000_000       # skip anything larger than 25 MB
    MEDIA_MAX_PER_RECORD: int = 8           # cap downloads per scraped page
    MEDIA_TIMEOUT: int = 30                 # seconds per file
    MEDIA_OCR_ENABLED: bool = True

    # ── OCR Configuration ────────────────────────────────
    TESSERACT_CMD: Optional[str] = None  # Path to tesseract.exe if not on PATH

    # ── Blockchain Configuration ─────────────────────────
    BLOCKSTREAM_API_URL: str = "https://blockstream.info/api"
    ETH_PROVIDER_URL: Optional[str] = None  # Infura/Alchemy RPC URL
    BLOCKCHAIN_ENABLED: bool = False

    # ── Surface Web Targets ──────────────────────────────
    SURFACE_WEB_TARGETS: list[str] = [
        # Add target URLs here
    ]

    # ── Dark Web Targets ─────────────────────────────────
    DARK_WEB_TARGETS: list[str] = [
        # Add .onion URLs here
    ]

    # ── Telegram Targets ─────────────────────────────────
    TELEGRAM_TARGETS: list[str] = [
        # Add channel/group usernames here
    ]

    # ── Evidence & Reports ───────────────────────────────
    REPORTS_DIR: str = "./reports"
    AUDIT_LOG_ENABLED: bool = True

    # ── CORS (for React frontend) ────────────────────────
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",  # Vite dev server
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ]

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


# Singleton instance
settings = Settings()


def verify_security_configuration(settings_obj: "Settings" = None) -> None:
    """
    Refuse to start with the shipped placeholder secrets.

    Failing loudly is the point. A system that boots happily with a signing key
    published in its own source gives every appearance of being secured while
    anyone holding the repository can mint an administrator token.
    """
    s = settings_obj or settings
    problems = []

    if s.JWT_SECRET == PLACEHOLDER_JWT_SECRET:
        problems.append("JWT_SECRET is the placeholder value from source")
    if s.SECRET_KEY == PLACEHOLDER_SECRET:
        problems.append("SECRET_KEY is the placeholder value from source")
    if len(s.JWT_SECRET) < 32:
        problems.append("JWT_SECRET is shorter than 32 characters")

    if not problems:
        return

    message = ("Refusing to start with insecure configuration:" + chr(10)
               + chr(10).join("  - " + p for p in problems) + chr(10) + chr(10)
               + "Generate secrets and place them in backend/.env:" + chr(10)
               + "  python scripts/generate_secrets.py" + chr(10) + chr(10)
               + "Set DEBUG=True to run anyway for local development.")

    if s.DEBUG:
        import logging
        logging.getLogger("config").warning(
            "INSECURE CONFIGURATION - running only because DEBUG=True. %s",
            "; ".join(problems))
        return

    raise InsecureConfiguration(message)

# Ensure required directories exist
os.makedirs(settings.REPORTS_DIR, exist_ok=True)
os.makedirs(settings.CHROMADB_PATH, exist_ok=True)
os.makedirs(settings.MEDIA_DIR, exist_ok=True)
