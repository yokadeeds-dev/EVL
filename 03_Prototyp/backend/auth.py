"""
Authentifizierung via JWT-Bearer-Token (OAuth2 Password Flow).
Zwei Rollen: user (generate, templates, status) und admin (+ ingest, upload, reset).

Setup:
    JWT_SECRET_KEY=<langes-zufälliges-geheimnis>  in .env eintragen
    Admin-Status wird über is_admin=True in acl.py USERS gesteuert.
"""

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import OAuth2PasswordBearer

import jwt_auth
from acl import UserContext, get_user

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token")


def require_user(token: str = Security(oauth2_scheme)) -> UserContext:
    """Endpoint-Dependency: validiert JWT-Token und gibt UserContext zurück."""
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


def require_admin(user: UserContext = Depends(require_user)) -> UserContext:
    """Endpoint-Dependency: Nur für User mit is_admin=True."""
    if not user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Kein Admin-Zugriff.",
        )
    return user
