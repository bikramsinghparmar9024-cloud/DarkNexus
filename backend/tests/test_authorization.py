"""
Authorization coverage.

Every endpoint in this system was reachable without a token. The RBAC layer
existed, was correct, and was imported exactly once across 71 endpoints - the
evidence vault, media downloads, surveillance controls and suspect data were
all open to anyone who could reach the port.

The first test here is the one that matters: it walks every registered route
and fails if any of them lacks an authentication dependency. Adding a router
without a guard breaks the build rather than silently shipping open.
"""

import pytest

# Routes that are deliberately reachable without a token, with the reason.
PUBLIC_ROUTES = {
    "/health": "liveness probe; returns no intelligence",
    "/api/auth/login": "issues the token, so cannot require one",
    "/api/auth/refresh": "exchanges a refresh token, validated separately",
    "/ws": "websocket; authenticated via its own handshake",
    # FastAPI's own documentation endpoints.
    "/docs": "API documentation",
    "/redoc": "API documentation",
    "/openapi.json": "API schema",
    "/docs/oauth2-redirect": "swagger OAuth2 helper",
}

AUTH_DEPENDENCY_NAMES = {
    "require_admin", "require_investigator", "require_any_authenticated",
    "role_checker", "get_current_user_payload", "get_refresh_token_payload",
}


def _iter_routes(app):
    """
    Walk the application's routes.

    Newer FastAPI defers included routers, so the tree must be flattened
    rather than read from app.routes directly.
    """
    seen = []

    def walk(router, inherited):
        for route in getattr(router, "routes", []):
            path = getattr(route, "path", None)
            deps = list(inherited)
            deps.extend(_dependency_names(route))
            if path is not None:
                seen.append((path, getattr(route, "methods", set()), deps))
            else:
                inner = getattr(route, "original_router", None)
                if inner is not None:
                    walk(inner, deps + _dependency_names(inner))

    walk(app.router, _dependency_names(app.router))
    return seen


def _dependency_names(obj):
    names = []
    for dep in getattr(obj, "dependencies", []) or []:
        call = getattr(dep, "dependency", None)
        if call is not None:
            names.append(getattr(call, "__name__", str(call)))
    dependant = getattr(obj, "dependant", None)
    if dependant is not None:
        for sub in getattr(dependant, "dependencies", []):
            call = getattr(sub, "call", None)
            if call is not None:
                names.append(getattr(call, "__name__", str(call)))
    return names


class TestEveryRouteIsGuarded:

    def test_no_endpoint_is_unintentionally_public(self):
        import app as application

        unguarded = []
        for path, methods, deps in _iter_routes(application.app):
            if path in PUBLIC_ROUTES:
                continue
            if not any(name in AUTH_DEPENDENCY_NAMES for name in deps):
                unguarded.append(f"{sorted(methods or [])} {path}")

        assert not unguarded, (
            "These endpoints are reachable without authentication:\n  "
            + "\n  ".join(sorted(unguarded))
            + "\n\nAdd a guard to the router, or list the path in PUBLIC_ROUTES "
              "with the reason it is safe."
        )

    def test_public_allowlist_stays_small(self):
        """
        Every entry here is a deliberate hole. Growth in this list should be a
        conscious decision, not something that accumulates.
        """
        assert len(PUBLIC_ROUTES) <= 10
        for path, reason in PUBLIC_ROUTES.items():
            assert reason, f"{path} is public without a stated reason"

    def test_sensitive_routers_require_more_than_viewer(self):
        """
        Read-only access is not enough to run collection, read the evidence
        vault, or download seized media.
        """
        import app as application

        elevated_prefixes = ("/api/vault", "/api/media", "/api/scrape",
                             "/api/targets", "/api/cti", "/api/proxy")
        checked = 0
        for path, _methods, deps in _iter_routes(application.app):
            if not path.startswith(elevated_prefixes):
                continue
            checked += 1
            assert any(name in ("require_investigator", "require_admin", "role_checker")
                       for name in deps), f"{path} is not restricted beyond VIEWER"
        assert checked > 0, "no elevated routes were found to check"


class TestTokenSeparation:

    def test_refresh_token_is_not_an_access_token(self):
        """
        create_refresh_token() used to delegate to create_access_token(),
        making a refresh token a fully valid 7-day access credential where a
        60-minute one was intended.
        """
        from auth.jwt_handler import (
            create_access_token, create_refresh_token, decode_token,
            TOKEN_TYPE_ACCESS, TOKEN_TYPE_REFRESH,
        )
        payload = {"sub": "officer", "role": "ADMIN", "user_id": 1}

        assert decode_token(create_access_token(payload))["type"] == TOKEN_TYPE_ACCESS
        assert decode_token(create_refresh_token(payload))["type"] == TOKEN_TYPE_REFRESH

    async def test_refresh_token_is_rejected_at_resource_endpoints(self):
        from fastapi import HTTPException
        from auth.jwt_handler import create_refresh_token, get_current_user_payload

        token = create_refresh_token({"sub": "officer", "role": "ADMIN"})
        with pytest.raises(HTTPException) as excinfo:
            await get_current_user_payload(token)
        assert excinfo.value.status_code == 401
        assert "refresh token" in excinfo.value.detail.lower()

    async def test_access_token_is_accepted(self):
        from auth.jwt_handler import create_access_token, get_current_user_payload

        token = create_access_token({"sub": "officer", "role": "INVESTIGATOR"})
        payload = await get_current_user_payload(token)
        assert payload["sub"] == "officer"
        assert payload["role"] == "INVESTIGATOR"

    async def test_token_without_a_type_claim_is_rejected(self):
        """Tokens minted before the type claim existed must not be honoured."""
        from datetime import datetime, timedelta
        from jose import jwt
        from fastapi import HTTPException
        from config import settings
        from auth.jwt_handler import get_current_user_payload

        legacy = jwt.encode(
            {"sub": "officer", "role": "ADMIN",
             "exp": datetime.utcnow() + timedelta(minutes=30)},
            settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)

        with pytest.raises(HTTPException) as excinfo:
            await get_current_user_payload(legacy)
        assert excinfo.value.status_code == 401


class TestSecretsValidation:

    def test_startup_refuses_placeholder_secrets(self):
        import copy
        from config import (
            settings, verify_security_configuration, InsecureConfiguration,
            PLACEHOLDER_JWT_SECRET,
        )

        unsafe = copy.copy(settings)
        unsafe.DEBUG = False
        unsafe.JWT_SECRET = PLACEHOLDER_JWT_SECRET

        with pytest.raises(InsecureConfiguration) as excinfo:
            verify_security_configuration(unsafe)
        assert "JWT_SECRET" in str(excinfo.value)

    def test_debug_mode_warns_instead_of_refusing(self):
        """Local development must stay possible without ceremony."""
        import copy
        from config import (
            settings, verify_security_configuration, PLACEHOLDER_JWT_SECRET,
        )

        dev = copy.copy(settings)
        dev.DEBUG = True
        dev.JWT_SECRET = PLACEHOLDER_JWT_SECRET
        verify_security_configuration(dev)   # must not raise

    def test_short_secrets_are_rejected(self):
        import copy
        from config import settings, verify_security_configuration, InsecureConfiguration

        weak = copy.copy(settings)
        weak.DEBUG = False
        weak.JWT_SECRET = "tooshort"
        with pytest.raises(InsecureConfiguration):
            verify_security_configuration(weak)


class TestAuditAttribution:
    """
    Chain of custody needs to say who, not only what. The audit logger accepted
    a user_id that no caller ever passed, so every entry was anonymous.
    """

    async def test_events_are_attributed_to_the_request_actor(self, db):
        from sqlalchemy import select
        from auth.context import set_current_actor, reset_current_actor
        from evidence.audit_log import record_audit_event
        from database.postgres import AuditLog, AsyncSessionLocal

        token = set_current_actor({
            "user_id": 7, "username": "officer_kaur",
            "role": "INVESTIGATOR", "ip_address": "10.0.0.5",
        })
        try:
            await record_audit_event("ACCESS_VAULT_RECORD", resource="record_47",
                                     details="Vault record 47 accessed")
        finally:
            reset_current_actor(token)

        async with AsyncSessionLocal() as session:
            entry = (await session.execute(
                select(AuditLog).order_by(AuditLog.id.desc())
            )).scalars().first()

        assert entry.user_id == 7
        assert entry.ip_address == "10.0.0.5"
        assert "officer_kaur" in entry.details

    async def test_unattributed_events_still_record(self, db):
        """
        Background jobs have no actor. They must still be logged, marked as
        system activity rather than silently attributed to a person.
        """
        from sqlalchemy import select
        from evidence.audit_log import record_audit_event
        from database.postgres import AuditLog, AsyncSessionLocal

        await record_audit_event("SCHEDULED_COLLECTION", resource="target_3",
                                 details="Automated collection cycle")

        async with AsyncSessionLocal() as session:
            entry = (await session.execute(
                select(AuditLog).order_by(AuditLog.id.desc())
            )).scalars().first()

        assert entry.user_id is None
        assert "Automated collection cycle" in entry.details


class TestAccountSecurity:

    async def test_repeated_failures_lock_the_account(self, db):
        """
        The administrator username is predictable, so an unthrottled login
        endpoint is a standing password-guessing target.
        """
        from fastapi import HTTPException
        from sqlalchemy import select
        from database.postgres import User
        from auth.hashing import hash_password
        from routes.auth_routes import login, MAX_FAILED_ATTEMPTS

        db.add(User(username="target_user", email="t@example.gov.in",
                    hashed_password=hash_password("correct-horse-battery"),
                    role="INVESTIGATOR", is_active=True))
        await db.commit()

        class _Form:
            username = "target_user"
            password = "wrong"

        for _ in range(MAX_FAILED_ATTEMPTS):
            with pytest.raises(HTTPException) as excinfo:
                await login(_Form(), db)
            assert excinfo.value.status_code == 401

        # The next attempt is refused before the password is even considered.
        with pytest.raises(HTTPException) as excinfo:
            await login(_Form(), db)
        assert excinfo.value.status_code == 429

        user = (await db.execute(
            select(User).where(User.username == "target_user")
        )).scalars().first()
        assert user.locked_until is not None

    async def test_successful_login_clears_the_failure_count(self, db):
        from sqlalchemy import select
        from database.postgres import User
        from auth.hashing import hash_password
        from routes.auth_routes import login

        db.add(User(username="good_user", email="g@example.gov.in",
                    hashed_password=hash_password("correct-horse-battery"),
                    role="INVESTIGATOR", is_active=True,
                    failed_login_attempts=3))
        await db.commit()

        class _Form:
            username = "good_user"
            password = "correct-horse-battery"

        await login(_Form(), db)

        user = (await db.execute(
            select(User).where(User.username == "good_user")
        )).scalars().first()
        assert user.failed_login_attempts == 0
        assert user.last_login_at is not None

    async def test_new_admin_account_must_change_its_password(self, db):
        """
        The initial password is generated and printed once; the account is
        blocked from other use until it is replaced.
        """
        from sqlalchemy import select
        from database.postgres import User
        import app as application

        await application.seed_initial_data()

        admin = (await db.execute(
            select(User).where(User.username == "admin_punjab")
        )).scalars().first()

        assert admin is not None
        assert admin.must_change_password is True
        # The published credential must not be the one in use.
        from auth.hashing import verify_password
        assert not verify_password("PunjabPolice@2026", admin.hashed_password)
