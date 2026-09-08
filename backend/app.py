"""
FastAPI Main Application Entry Point.
AI-Powered Dark Web & Encrypted Platform Drug Intelligence System for Punjab Police.
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
import logging
from typing import List

from config import settings, verify_security_configuration
from database.postgres import init_db, AsyncSessionLocal, User, ScrapedData
from database.graph_db import graph_manager
from proxy.pool import proxy_pool
from auth.hashing import hash_password, generate_sha256
from sqlalchemy import select

# Import routes
from routes.auth_routes import router as auth_router
from routes.dashboard import router as dashboard_router
from routes.scraper_routes import router as scraper_router
from routes.data_routes import router as data_router
from routes.proxy_routes import router as proxy_router
from routes.blockchain_routes import router as blockchain_router
from routes.evidence_routes import router as evidence_router
from routes.ai_routes import router as ai_router
from routes.geo_routes import router as geo_router
from routes.simulator_routes import router as simulator_router, register_broadcast_callback
from routes.cti_routes import router as cti_router
from routes.entity_resolution_routes import router as entity_resolution_router
from routes.verification_routes import router as verification_router
from routes.vault_routes import router as vault_router
from routes.media_routes import router as media_router
from routes.target_routes import router as target_router
from routes.correlation_routes import router as correlation_router
from scheduler import intel_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("app")


# Active WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass


ws_manager = ConnectionManager()
register_broadcast_callback(ws_manager.broadcast)


async def seed_initial_data():
    """
    Create the initial administrator account if none exists.

    The password is generated and printed once rather than shipped in source.
    It was previously PunjabPolice@2026, published in the README, which meant
    every deployment of this system shared one publicly known administrator
    credential.
    """
    async with AsyncSessionLocal() as session:
        # 1. Admin Investigator user
        stmt = select(User).where(User.username == "admin_punjab")
        user = (await session.execute(stmt)).scalars().first()
        if not user:
            import secrets as _secrets
            generated = _secrets.token_urlsafe(18)

            admin_user = User(
                username="admin_punjab",
                email="intel@punjabpolice.gov.in",
                hashed_password=hash_password(generated),
                badge_number="PB-CID-8821",
                department="Punjab State Narcotics Control Bureau",
                role="ADMIN",
                must_change_password=True,
            )
            session.add(admin_user)
            await session.commit()

            banner = "=" * 68
            logger.warning(
                "%s%sINITIAL ADMINISTRATOR ACCOUNT CREATED%s"
                "  username: admin_punjab%s"
                "  password: %s%s"
                "This password is shown once and is not stored anywhere in%s"
                "readable form. Sign in and change it immediately - the%s"
                "account cannot be used for anything else until you do.%s%s",
                banner, chr(10), chr(10), chr(10), generated, chr(10),
                chr(10), chr(10), chr(10), banner)

        # Admin user is created above; do not seed demo records so the system starts clean for actual websites.
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    # Refuse to start on placeholder signing keys unless DEBUG is set.
    verify_security_configuration()

    logger.info("Initializing database and models...")
    await init_db()
    await seed_initial_data()

    logger.info("Initializing Neo4j graph driver...")
    await graph_manager.connect()

    logger.info("Initializing Proxy Pool in background...")
    asyncio.create_task(proxy_pool.initialize())

    logger.info("Starting background intelligence crawler scheduler...")
    intel_scheduler.start()

    yield

    logger.info("Shutting down resources...")
    intel_scheduler.shutdown()
    await graph_manager.close()


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="Unified Intelligence Gathering & Anti-Detection System for Punjab Police",
    lifespan=lifespan
)

# CORS for the React frontend. Methods and headers are enumerated rather than
# wildcarded: with allow_credentials the browser sends the bearer token, and a
# wildcard grants any origin in the list more than this API actually uses.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
    max_age=600,
)


@app.middleware("http")
async def attach_request_actor(request, call_next):
    """
    Resolve the caller from their bearer token and publish it for this request.

    Deliberately best-effort: this middleware never rejects anything. Access
    control is enforced by the route dependencies, which return proper 401 and
    403 responses. All this does is make the authenticated identity available
    to the audit logger so evidence access is attributable.
    """
    from auth.context import set_current_actor, reset_current_actor

    actor = None
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        try:
            from auth.jwt_handler import decode_token
            payload = decode_token(header.split(" ", 1)[1].strip())
            if payload.get("type") == "access":
                actor = {
                    "user_id": payload.get("user_id"),
                    "username": payload.get("sub"),
                    "role": payload.get("role"),
                    "ip_address": request.client.host if request.client else None,
                }
        except Exception:
            actor = None  # an invalid token is simply an unattributed request

    token = set_current_actor(actor)
    try:
        return await call_next(request)
    finally:
        reset_current_actor(token)

# Register API Routers
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(scraper_router)
app.include_router(data_router)
app.include_router(proxy_router)
app.include_router(blockchain_router)
app.include_router(evidence_router)
app.include_router(ai_router)
app.include_router(geo_router)
app.include_router(simulator_router)
app.include_router(cti_router)
app.include_router(entity_resolution_router)
app.include_router(verification_router)
app.include_router(vault_router)
app.include_router(media_router)
app.include_router(target_router)
app.include_router(correlation_router)


@app.get("/health")
async def health_check():
    """Health status check."""
    return {
        "status": "HEALTHY",
        "app": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "pipelines": ["SURFACE_WEB", "DARK_WEB", "TELEGRAM"]
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Real-time intelligence feed websocket."""
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keepalive listener
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
