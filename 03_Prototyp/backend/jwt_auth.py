"""
JWT-Handling via PyJWT (etablierte Bibliothek statt Eigenbau).

HS256 mit vollständigen Standard-Claims (iss/aud/iat/nbf/exp). Der Algorithmus
wird bei der Verifikation fest auf HS256 gepinnt → kein alg=none / alg-Confusion.
Revocation/Refresh sind bewusst Prototyp-Scope (siehe ADR 0003).
"""

import datetime
import os

import jwt

SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "")
if not SECRET_KEY:
    raise RuntimeError("JWT_SECRET_KEY ist nicht gesetzt! Bitte in .env eintragen.")

_ALGORITHM = "HS256"
_ISSUER = "evl-content-assistant"
_AUDIENCE = "evl-api"
_DEFAULT_TTL = 3600  # Sekunden


def create_jwt(payload: dict, expires_in: int = _DEFAULT_TTL) -> str:
    now = datetime.datetime.now(datetime.UTC)
    claims = {
        **payload,
        "iss": _ISSUER,
        "aud": _AUDIENCE,
        "iat": now,
        "nbf": now,
        "exp": now + datetime.timedelta(seconds=expires_in),
    }
    return jwt.encode(claims, SECRET_KEY, algorithm=_ALGORITHM)


def verify_jwt(token: str) -> dict:
    """Dekodiert + validiert (Signatur, exp, nbf, iss, aud). Wirft bei Ungültigkeit."""
    return jwt.decode(
        token,
        SECRET_KEY,
        algorithms=[_ALGORITHM],
        issuer=_ISSUER,
        audience=_AUDIENCE,
        options={"require": ["exp", "iat", "nbf", "iss", "aud", "sub"]},
    )
