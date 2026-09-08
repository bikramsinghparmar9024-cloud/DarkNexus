"""
Role-Based Access Control (RBAC) Permissions & Guards.
Enforces privilege levels:
- ADMIN: Manage users, targets, scrapers, proxy settings, audit logs.
- INVESTIGATOR: View intel, run scrapers, search data, export evidence dossiers.
- VIEWER: Read-only access to anonymized reports and statistics.
"""

from typing import List
from enum import Enum
from fastapi import Depends, HTTPException, status
from auth.jwt_handler import get_current_user_payload


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    INVESTIGATOR = "INVESTIGATOR"
    VIEWER = "VIEWER"


def require_roles(allowed_roles: List[UserRole]):
    """
    FastAPI dependency factory enforcing that the authenticated user possesses
    one of the approved role levels.
    """
    def role_checker(token_payload: dict = Depends(get_current_user_payload)):
        user_role_str = token_payload.get("role", UserRole.VIEWER.value)
        try:
            user_role = UserRole(user_role_str)
        except ValueError:
            user_role = UserRole.VIEWER

        if user_role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Role '{user_role.value}' is unauthorized. Required: {[r.value for r in allowed_roles]}"
            )
        return token_payload

    return role_checker


# Convenient role presets
require_admin = require_roles([UserRole.ADMIN])
require_investigator = require_roles([UserRole.ADMIN, UserRole.INVESTIGATOR])
require_any_authenticated = require_roles([UserRole.ADMIN, UserRole.INVESTIGATOR, UserRole.VIEWER])
