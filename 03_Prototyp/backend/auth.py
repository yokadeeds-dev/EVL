"""
Authentifizierung via API-Key (Header: X-API-Key).
Zwei Rollen: user (generate, templates, status) und admin (+ ingest).

Setup: API-Keys in .env eintragen:
    USER_API_KEYS=key-abc123,key-def456
    ADMIN_API_KEYS=key-admin-xyz
"""

import os
import secrets
from fastapi import HTTPException, Security, status
from fastapi.security import OAuth2PasswordBearer
import jwt_auth
from acl import get_user, UserContext

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")

def require_user(token: str = Security(oauth2_scheme)) -> UserContext:
    """Endpoint-Dependency: validates JWT Token an returns UserContext."""
    try:
        payload = jwt_auth.verify_jwt(token)
        user_id = payload.get("sub")
        return get_user(user_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Ungültiger oder abgelaufener Token: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
