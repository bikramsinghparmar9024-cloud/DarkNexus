"""
SQLAlchemy database models and connection engine.
Supports PostgreSQL (asyncpg) or SQLite (aiosqlite) as fallback.
"""

from datetime import datetime
from typing import AsyncGenerator
import json

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, ForeignKey, JSON, Float, Enum as SQLEnum
)
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base, relationship

from config import settings

# Setup Base
Base = declarative_base()


class User(Base):
    """Investigator / Admin User model."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    badge_number = Column(String(50), nullable=True)
    department = Column(String(100), default="Punjab Police Anti-Drug Intelligence Unit")
    role = Column(String(20), default="INVESTIGATOR")  # ADMIN, INVESTIGATOR, VIEWER
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # ── Account security ─────────────────────────────────────────
    must_change_password = Column(Boolean, default=False)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime, nullable=True)
    last_login_at = Column(DateTime, nullable=True)

    audit_logs = relationship("AuditLog", back_populates="user")


class Target(Base):
    """Target URL, onion domain, or Telegram channel/group for scraping."""
    __tablename__ = "targets"

    id = Column(Integer, primary_key=True, index=True)
    identifier = Column(String(500), unique=True, index=True, nullable=False) # URL, onion, @channel
    source_type = Column(String(50), nullable=False) # SURFACE_WEB, DARK_WEB, TELEGRAM
    label = Column(String(200), nullable=True)
    priority = Column(Integer, default=1) # 1=Normal, 2=High, 3=Critical
    status = Column(String(20), default="ACTIVE") # ACTIVE, PAUSED, COMPLETED, FAILED
    discovered_by = Column(String(50), default="MANUAL") # MANUAL, CRAWLER
    last_scraped_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # ── Continuous surveillance ──────────────────────────────────
    scan_interval_minutes = Column(Integer, default=60)   # how often to revisit
    consecutive_failures = Column(Integer, default=0)     # backoff / auto-pause
    last_error = Column(Text, nullable=True)
    total_records_collected = Column(Integer, default=0)
    next_scan_at = Column(DateTime, nullable=True, index=True)

    scraped_items = relationship("ScrapedData", back_populates="target")


class ScrapedData(Base):
    """Raw scraped intelligence with SHA-256 evidence verification."""
    __tablename__ = "scraped_data"

    id = Column(Integer, primary_key=True, index=True)
    target_id = Column(Integer, ForeignKey("targets.id"), nullable=True)
    source_type = Column(String(50), nullable=False) # SURFACE_WEB, DARK_WEB, TELEGRAM
    source_url = Column(String(1000), nullable=False)
    raw_content = Column(Text, nullable=False) # HTML, JSON, or message text
    cleaned_text = Column(Text, nullable=True)
    ocr_extracted_text = Column(Text, nullable=True) # Text extracted from attached images
    
    # Evidence & integrity
    sha256_hash = Column(String(64), nullable=False, index=True)
    author_or_handle = Column(String(200), nullable=True)
    published_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Classification / metadata
    flagged_entities = Column(JSON, nullable=True) # Extracted drugs, phone nos, crypto wallets, locations
    threat_level = Column(String(20), default="UNREVIEWED") # UNREVIEWED, LOW, MEDIUM, HIGH, SEVERE
    metadata_json = Column(JSON, nullable=True)

    target = relationship("Target", back_populates="scraped_items")


class ScrapeJob(Base):
    """Track execution of background crawler/scraper tasks."""
    __tablename__ = "scrape_jobs"

    id = Column(Integer, primary_key=True, index=True)
    pipeline = Column(String(50), nullable=False) # SURFACE_WEB, DARK_WEB, TELEGRAM
    target_identifier = Column(String(500), nullable=False)
    status = Column(String(20), default="PENDING") # PENDING, RUNNING, COMPLETED, FAILED
    items_scraped = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


class ProxyEntry(Base):
    """Proxy pool management table."""
    __tablename__ = "proxies"

    id = Column(Integer, primary_key=True, index=True)
    proxy_url = Column(String(255), unique=True, index=True, nullable=False) # e.g. socks5://ip:port or http://ip:port
    protocol = Column(String(20), default="http")
    is_alive = Column(Boolean, default=True)
    latency_ms = Column(Float, default=0.0)
    fail_count = Column(Integer, default=0)
    success_count = Column(Integer, default=0)
    last_checked = Column(DateTime, default=datetime.utcnow)


class CryptoWalletIntel(Base):
    """Tracked cryptocurrency wallets discovered in illicit drug listings."""
    __tablename__ = "crypto_wallets"

    id = Column(Integer, primary_key=True, index=True)
    wallet_address = Column(String(200), unique=True, index=True, nullable=False)
    crypto_type = Column(String(20), default="BTC") # BTC, ETH, XMR, USDT
    associated_source_url = Column(String(1000), nullable=True)
    total_received = Column(Float, default=0.0)
    current_balance = Column(Float, default=0.0)
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_activity = Column(DateTime, nullable=True)
    risk_score = Column(Integer, default=50) # 0-100


class MediaArtifact(Base):
    """
    An image or video recovered alongside a scraped record.

    Stores the file location, its own SHA-256 (separate from the parent page
    hash, so the artifact is independently verifiable), and the forensic
    metadata lifted out of it - most importantly any EXIF GPS fix.
    """
    __tablename__ = "media_artifacts"

    id = Column(Integer, primary_key=True, index=True)
    scraped_data_id = Column(Integer, ForeignKey("scraped_data.id"), nullable=True, index=True)

    source_url = Column(String(1000), nullable=False)
    local_path = Column(String(1000), nullable=True)
    media_type = Column(String(20), default="IMAGE")     # IMAGE, VIDEO
    mime_type = Column(String(100), nullable=True)
    file_size = Column(Integer, default=0)
    sha256_hash = Column(String(64), nullable=False, index=True)

    # Intrinsic properties
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    # Forensic metadata
    exif_json = Column(JSON, nullable=True)              # camera, software, timestamps
    capture_timestamp = Column(String(64), nullable=True)
    device_signature = Column(String(200), nullable=True, index=True)  # "Make Model"

    # Geolocation lifted from EXIF
    gps_lat = Column(Float, nullable=True)
    gps_lon = Column(Float, nullable=True)
    geo_json = Column(JSON, nullable=True)               # resolved district + border distance
    in_border_corridor = Column(Boolean, default=False, index=True)

    # Derived content
    ocr_text = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)


class GraphNode(Base):
    """
    A node in the correlation graph.

    The graph used to live in two Python lists, pre-loaded with invented
    suspects: anything an investigator built was lost on restart, and the
    fictional entries came back. Persisting it here means the graph reflects
    collected intelligence and survives a restart, without requiring a Neo4j
    server for a deployment this size.
    """
    __tablename__ = "graph_nodes"

    id = Column(Integer, primary_key=True, index=True)
    node_key = Column(String(255), unique=True, index=True, nullable=False)
    label = Column(String(500), nullable=False)
    node_type = Column(String(50), default="entity", index=True)  # suspect, channel, onion, drug, wallet
    threat_level = Column(String(20), default="UNREVIEWED")
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)
    mention_count = Column(Integer, default=1)
    # Set when an investigator confirms the label. A verified label is never
    # overwritten by a later scrape; before this existed the merge rule kept
    # whichever label was longest, which is unrelated to being correct.
    label_verified = Column(Boolean, default=False)


class GraphEdge(Base):
    """A directed, labelled relationship between two graph nodes."""
    __tablename__ = "graph_edges"

    id = Column(Integer, primary_key=True, index=True)
    edge_key = Column(String(600), unique=True, index=True, nullable=False)
    source_key = Column(String(255), index=True, nullable=False)
    target_key = Column(String(255), index=True, nullable=False)
    relation = Column(String(100), nullable=False)
    # How many times this relationship was independently observed - the
    # difference between a one-off mention and an established connection.
    observation_count = Column(Integer, default=1)
    first_seen = Column(DateTime, default=datetime.utcnow)
    last_seen = Column(DateTime, default=datetime.utcnow)
    # Which collected records produced this edge. An edge with no traceable
    # source cannot be evidence of anything: an investigator must be able to
    # ask "show me the message that created this link" and get an answer.
    evidence_record_ids = Column(JSON, default=list)

    # Investigator review. An edge an analyst has judged wrong must stop being
    # shown, but must not be deleted: the observation still happened, and
    # destroying evidence-linked rows to tidy a view is not acceptable in a
    # system whose output has to survive disclosure.
    status = Column(String(20), default="PENDING", index=True)  # PENDING/VERIFIED/REJECTED
    reviewed_by = Column(String(200), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_note = Column(Text, nullable=True)


class CTIProject(Base):
    """
    An investigation workspace: a topic, the sources being watched for it, and
    the suspects being tracked under it.

    Previously a module-level Python list of invented operations that emptied
    on every restart, so nothing an investigator created survived.
    """
    __tablename__ = "cti_projects"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(300), nullable=False)
    topic = Column(String(200), nullable=True)
    topic_key = Column(String(100), nullable=True)
    description = Column(Text, nullable=True)
    is_observing = Column(Boolean, default=True)
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class CTIProjectSource(Base):
    """
    A source watched under a project.

    Linked to a surveillance Target where one exists, so adding a source to a
    project actually places it under collection rather than only listing it.
    """
    __tablename__ = "cti_project_sources"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("cti_projects.id"), index=True, nullable=False)
    target_id = Column(Integer, ForeignKey("targets.id"), nullable=True)
    identifier = Column(String(500), nullable=False)
    source_type = Column(String(50), nullable=False)
    label = Column(String(300), nullable=True)
    status = Column(String(20), default="ACTIVE")
    created_at = Column(DateTime, default=datetime.utcnow)


class CTIProjectSuspect(Base):
    """
    A tracked account within a project.

    risk_score and matched_sources are derived from collected records at
    correlation time. Where nothing has been collected about an account, the
    score is zero and the evidence list empty - the previous implementation
    invented a score of 75-96 from whether the handle contained certain
    substrings.
    """
    __tablename__ = "cti_project_suspects"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("cti_projects.id"), index=True, nullable=False)

    username = Column(String(200), nullable=False)
    alias = Column(String(200), nullable=True)
    platform = Column(String(100), nullable=True)
    role = Column(String(200), nullable=True)
    notes = Column(Text, nullable=True)

    # Derived from evidence, recomputed on demand.
    risk_score = Column(Integer, default=0)
    matched_sources = Column(JSON, nullable=True)
    evidence_record_ids = Column(JSON, nullable=True)
    correlation_count = Column(Integer, default=0)
    correlation_summary = Column(Text, nullable=True)
    last_correlated_at = Column(DateTime, nullable=True)
    last_active = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)


class AuditLog(Base):
    """Chain of custody & tamper-evident action audit trail for law enforcement."""
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String(100), nullable=False) # VIEW_RECORD, EXPORT_PDF, TRIGGER_SCRAPE, etc.
    resource = Column(String(255), nullable=True) # Target ID, Evidence ID
    ip_address = Column(String(50), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    details = Column(Text, nullable=True)

    user = relationship("User", back_populates="audit_logs")


# Engine & Session Setup
engine = create_async_engine(
    settings.DATABASE_URL,
    echo=False,
    future=True,
    # For SQLite, avoid thread check issues in async
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {}
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)


# Columns added after the initial schema shipped. create_all() only creates
# missing *tables*, never missing columns, so existing databases need these
# applied by hand. ADD COLUMN is safe to repeat - failures are ignored.
_LATE_COLUMNS = {
    "users": [
        ("must_change_password", "BOOLEAN DEFAULT 0"),
        ("failed_login_attempts", "INTEGER DEFAULT 0"),
        ("locked_until", "DATETIME"),
        ("last_login_at", "DATETIME"),
    ],
    "targets": [
        ("scan_interval_minutes", "INTEGER DEFAULT 60"),
        ("consecutive_failures", "INTEGER DEFAULT 0"),
        ("last_error", "TEXT"),
        ("total_records_collected", "INTEGER DEFAULT 0"),
        ("next_scan_at", "DATETIME"),
    ],
}


async def _apply_late_columns(conn):
    """Add columns introduced after a database was first created."""
    from sqlalchemy import text as _text
    for table, columns in _LATE_COLUMNS.items():
        for name, ddl in columns:
            try:
                await conn.execute(_text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
            except Exception:
                pass  # already present


async def init_db():
    """Create all tables, then bring older databases up to the current schema."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await _apply_late_columns(conn)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for obtaining an async database session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
