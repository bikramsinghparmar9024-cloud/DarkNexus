"""
JWT Token Creation, Decoding, and Header Verification for FastAPI.
"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# Tokens carry their purpose so the two cannot be substituted for one another.
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create a short-lived signed access token."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({
        "exp": expire,
        "iat": datetime.utcnow(),
        "type": TOKEN_TYPE_ACCESS,
    })
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_refresh_token(data: Dict[str, Any]) -> str:
    """
    Create a long-lived refresh token.

    This previously delegated to create_access_token(), which meant a refresh
    token was itself a fully valid access token - turning an intended
    60-minute credential into a 7-day one. The type claim below is what makes
    them distinguishable, and get_current_user_payload() rejects refresh
    tokens presented to ordinary endpoints.
    """
    to_encode = data.copy()
    to_encode.update({
        "exp": datetime.utcnow() + timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS),
        "iat": datetime.utcnow(),
        "type": TOKEN_TYPE_REFRESH,
    })
    return jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    """Decode and validate a JWT token signature."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid, malformed, or expired security authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


async def get_current_user_payload(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    """
    Resolve the caller's identity from a bearer token.

    Rejects refresh tokens: they are long-lived and exist only to obtain a new
    access token at /api/auth/refresh.
    """
    payload = decode_token(token)

    username: str = payload.get("sub")
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload is missing subject identity.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token_type = payload.get("type")
    if token_type == TOKEN_TYPE_REFRESH:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A refresh token cannot be used to access resources. "
                   "Exchange it at /api/auth/refresh for an access token.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    # Tokens issued before the type claim existed are no longer accepted.
    if token_type != TOKEN_TYPE_ACCESS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is missing a valid type claim; sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return payload


async def get_refresh_token_payload(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    """Resolve a refresh token, for the token-exchange endpoint only."""
    payload = decode_token(token)
    if payload.get("type") != TOKEN_TYPE_REFRESH:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A refresh token is required here.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return payload
