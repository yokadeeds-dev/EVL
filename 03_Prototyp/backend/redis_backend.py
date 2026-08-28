"""
Redis-Backend fuer EVL — prozessuebergreifendes Rate-Limiting und LLM-Response-Cache.

Warum: Das Backend laeuft mit `uvicorn --workers 2` (mehrere Prozesse). Ein reiner
In-Memory-Rate-Limiter haelt pro Prozess einen eigenen Zaehler → das Limit greift
inkonsistent und effektiv N-fach. Redis teilt den Zustand ueber alle Worker/Replicas.

Graceful Fallback: ist REDIS_URL leer oder Redis nicht erreichbar, faellt das
Rate-Limiting auf einen In-Memory-Store zurueck und der Cache wird zum No-Op.
So laufen lokale Dev und CI (test_e2e/mock_server) unveraendert ohne Redis.
"""

import hashlib
import os
import time
import uuid
from collections import defaultdict

try:
    import redis as _redis_lib
except ImportError:  # redis-Paket ist optional
    _redis_lib = None

REDIS_URL = os.getenv("REDIS_URL", "").strip()
CACHE_TTL = int(os.getenv("LLM_CACHE_TTL_SECONDS", "3600"))

_client = None
_connect_tried = False


def _get_client():
    """Lazy, gecachter Redis-Client. None, wenn nicht konfiguriert/erreichbar."""
    global _client, _connect_tried
    if _connect_tried:
        return _client
    _connect_tried = True
    if not REDIS_URL or _redis_lib is None:
        _client = None
        return None
    try:
        c = _redis_lib.from_url(
            REDIS_URL,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
            decode_responses=True,
        )
        c.ping()
        _client = c
    except Exception:
        _client = None
    return _client


def redis_available() -> bool:
    return _get_client() is not None


# ── Rate-Limiting (Sliding-Window) ────────────────────────────────────────────

_mem_store: dict[str, list[float]] = defaultdict(list)


def check_rate_limit(key: str, limit: int, window: int) -> bool:
    """
    True = Anfrage erlaubt, False = Limit erreicht.
    Semantik identisch zum urspruenglichen In-Memory-Limiter: bis `limit`
    Anfragen je `window` Sekunden sind erlaubt; geblockte zaehlen nicht mit.
    """
    now = time.time()
    client = _get_client()
    if client is not None:
        try:
            rkey = f"ratelimit:{key}"
            client.zremrangebyscore(rkey, 0, now - window)
            if client.zcard(rkey) >= limit:
                return False
            client.zadd(rkey, {f"{now}:{uuid.uuid4().hex}": now})
            client.expire(rkey, window)
            return True
        except Exception:
            pass  # Verbindung mitten im Betrieb verloren → In-Memory-Fallback

    calls = [t for t in _mem_store[key] if t > now - window]
    if len(calls) >= limit:
        _mem_store[key] = calls
        return False
    calls.append(now)
    _mem_store[key] = calls
    return True


# ── LLM-Response-Cache ────────────────────────────────────────────────────────


def cache_key(*parts: str) -> str:
    """Deterministischer Schluessel ueber alle preisbestimmenden Eingaben."""
    digest = hashlib.sha256("\x00".join(parts).encode("utf-8")).hexdigest()
    return f"llmcache:{digest}"


def cache_get(key: str) -> str | None:
    client = _get_client()
    if client is None:
        return None
    try:
        return client.get(key)
    except Exception:
        return None


def cache_set(key: str, value: str, ttl: int = CACHE_TTL) -> None:
    client = _get_client()
    if client is None:
        return
    try:
        client.set(key, value, ex=ttl)
    except Exception:
        pass
