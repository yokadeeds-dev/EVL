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
from fastapi.security import APIKeyHeader

_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _load_keys(env_var: str) -> set[str]:
    raw = os.getenv(env_var, "")
    return {k.strip() for k in raw.split(",") if k.strip()}


def _get_keys() -> tuple[set[str], set[str]]:
    user_keys = _load_keys("USER_API_KEYS")
    admin_keys = _load_keys("ADMIN_API_KEYS")
    return user_keys, admin_keys


def require_user(api_key: str = Security(_header)) -> str:
    """Endpoint-Dependency: user oder admin Key akzeptiert."""
    user_keys, admin_keys = _get_keys()
    all_keys = user_keys | admin_keys
    if not api_key or not secrets.compare_digest(
        api_key, next((k for k in all_keys if secrets.compare_digest(api_key, k)), "")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Ungültiger oder fehlender API-Key (Header: X-API-Key).",
        )
    return api_key


def require_admin(api_key: str = Security(_header)) -> str:
    """Endpoint-Dependency: nur admin Key akzeptiert."""
    _, admin_keys = _get_keys()
    if not api_key or not any(
        secrets.compare_digest(api_key, k) for k in admin_keys
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin-Rechte erforderlich.",
        )
    return api_key
