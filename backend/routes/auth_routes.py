"""
Authentication & User Management Endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime, timedelta

from database.postgres import get_db, User
from auth.hashing import hash_password, verify_password
from auth.jwt_handler import (
    create_access_token, create_refresh_token,
    get_current_user_payload, get_refresh_token_payload,
)
from auth.rbac import require_admin, UserRole
from evidence.audit_log import record_audit_event

router = APIRouter(prefix="/api/auth", tags=["Authentication"])

# Sign-in throttling. The administrator username is predictable, so an
# unthrottled login endpoint is a standing password-guessing target.
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


class RegisterRequest(BaseModel):
    username: str
    email: EmailStr
    password: str
    badge_number: Optional[str] = None
    role: Optional[str] = "INVESTIGATOR"


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    username: str
    role: str


@router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """Authenticate investigator credentials and issue JWT tokens."""
    stmt = select(User).where(User.username == form_data.username)
    user = (await db.execute(stmt)).scalars().first()

    # A locked account is refused before the password is even checked, so
    # lockout cannot be probed by timing the response.
    if user and user.locked_until and user.locked_until > datetime.utcnow():
        remaining = int((user.locked_until - datetime.utcnow()).total_seconds() // 60) + 1
        await record_audit_event(
            "LOGIN_BLOCKED", user_id=user.id,
            details=f"Sign-in attempted on a locked account ({remaining} min remaining)")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Account locked after repeated failed attempts. "
                   f"Try again in {remaining} minute(s).")

    if not user or not verify_password(form_data.password, user.hashed_password):
        # Count the failure against the account when one exists. The response
        # is identical either way so the endpoint does not reveal which
        # usernames are real.
        if user:
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
                user.locked_until = datetime.utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
                user.failed_login_attempts = 0
                await record_audit_event(
                    "ACCOUNT_LOCKED", user_id=user.id,
                    details=f"Locked for {LOCKOUT_MINUTES} minutes after "
                            f"{MAX_FAILED_ATTEMPTS} failed sign-in attempts")
            await db.commit()

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is suspended.")

    user.failed_login_attempts = 0
    user.locked_until = None
    user.last_login_at = datetime.utcnow()
    await db.commit()

    access_token = create_access_token(data={"sub": user.username, "role": user.role, "user_id": user.id})
    refresh_token = create_refresh_token(data={"sub": user.username, "role": user.role, "user_id": user.id})

    await record_audit_event("LOGIN", user_id=user.id, details="User successfully logged in")

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        username=user.username,
        role=user.role
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    req: RegisterRequest,
    db: AsyncSession = Depends(get_db),
    admin: dict = Depends(require_admin),
):
    """
    Create an investigator account. Administrators only.

    This endpoint imported require_admin but never applied it, so anyone who
    could reach the port could create themselves an ADMIN account and hold
    every privilege in the system.
    """
    # Check if user already exists
    stmt = select(User).where((User.username == req.username) | (User.email == req.email))
    existing = (await db.execute(stmt)).scalars().first()
    if existing:
        raise HTTPException(status_code=400, detail="Username or Email already registered.")

    role = (req.role or "INVESTIGATOR").upper()
    if role not in {r.value for r in UserRole}:
        raise HTTPException(
            status_code=400,
            detail=f"role must be one of {sorted(r.value for r in UserRole)}")

    new_user = User(
        username=req.username,
        email=req.email,
        hashed_password=hash_password(req.password),
        badge_number=req.badge_number,
        role=role,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    await record_audit_event(
        "USER_CREATED",
        resource=new_user.username,
        user_id=admin.get("user_id"),
        details=(f"Account '{new_user.username}' created with role "
                 f"{new_user.role} by {admin.get('sub')}"),
    )
    return {"message": "User registered successfully", "id": new_user.id, "username": new_user.username}


@router.get("/me")
async def get_current_user_profile(
    payload: dict = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db)
):
    """Fetch current investigator profile from token payload."""
    stmt = select(User).where(User.username == payload["sub"])
    user = (await db.execute(stmt)).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "badge_number": user.badge_number,
        "department": user.department,
        "role": user.role,
        # The client blocks the rest of the UI on this, so an account created
        # with a generated password cannot be used until it is replaced.
        "must_change_password": bool(user.must_change_password),
        "last_login_at": user.last_login_at.isoformat() + "Z" if user.last_login_at else None,
    }


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/refresh", response_model=TokenResponse)
async def refresh_access_token(
    payload: dict = Depends(get_refresh_token_payload),
    db: AsyncSession = Depends(get_db),
):
    """
    Exchange a refresh token for a new access token.

    This endpoint exists because access tokens are now genuinely short-lived:
    before the type claim was added, a refresh token was itself a valid access
    token, so no exchange was ever needed and the 60-minute expiry was fiction.
    """
    user = (await db.execute(
        select(User).where(User.username == payload.get("sub"))
    )).scalars().first()

    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The account for this token no longer exists or is suspended.")

    claims = {"sub": user.username, "role": user.role, "user_id": user.id}
    return TokenResponse(
        access_token=create_access_token(data=claims),
        refresh_token=create_refresh_token(data=claims),
        username=user.username,
        role=user.role,
    )


@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    payload: dict = Depends(get_current_user_payload),
    db: AsyncSession = Depends(get_db),
):
    """
    Change the signed-in user's password.

    Clears must_change_password, which is what unblocks an account created
    with a generated initial password.
    """
    user = (await db.execute(
        select(User).where(User.username == payload.get("sub"))
    )).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="Account not found.")

    if not verify_password(req.current_password, user.hashed_password):
        await record_audit_event(
            "PASSWORD_CHANGE_FAILED", user_id=user.id,
            details="Password change rejected: current password incorrect")
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    if len(req.new_password) < 12:
        raise HTTPException(
            status_code=400,
            detail="New password must be at least 12 characters.")
    if req.new_password == req.current_password:
        raise HTTPException(
            status_code=400,
            detail="New password must differ from the current one.")

    user.hashed_password = hash_password(req.new_password)
    user.must_change_password = False
    await db.commit()

    await record_audit_event(
        "PASSWORD_CHANGED", user_id=user.id,
        details=f"Password changed for '{user.username}'")

    return {
        "status": "SUCCESS",
        "message": "Password updated. Existing tokens remain valid until they expire.",
    }
