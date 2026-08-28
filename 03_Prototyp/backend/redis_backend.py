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
_RECONNECT_BACKOFF = 5.0  # Sekunden bis zum naechsten Verbindungsversuch

_client = None
_next_retry = 0.0


def _get_client():
    """
    Lazy Redis-Client mit Reconnect. None, wenn nicht konfiguriert oder (noch)
    nicht erreichbar. Ein fehlgeschlagener Verbindungsaufbau wird nach kurzem
    Backoff erneut versucht — kein dauerhaftes Einfrieren im In-Memory-Fallback,
    falls Redis erst nach dem App-Start bereit ist (Startup-Race).
    """
    global _client, _next_retry
    if _client is not None:
        return _client
    if not REDIS_URL or _redis_lib is None:
        return None
    now = time.time()
    if now < _next_retry:
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
        return _client
    except Exception:
        _next_retry = now + _RECONNECT_BACKOFF
        return None


def _invalidate():
    """Verbindung als tot markieren → der naechste _get_client() verbindet neu."""
    global _client
    _client = None


def redis_available() -> bool:
    return _get_client() is not None


# ── Rate-Limiting (Sliding-Window) ────────────────────────────────────────────

_mem_store: dict[str, list[float]] = defaultdict(list)

# Atomarer Sliding-Window-Check server-seitig: verhindert die TOCTOU-Luecke
# zwischen ZCARD-Pruefung und ZADD, die bei parallelen Workern zu leichter
# Ueber-Zulassung fuehren wuerde.
_RATE_LUA = """
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, now - window)
if redis.call('ZCARD', KEYS[1]) >= limit then
  return 0
end
redis.call('ZADD', KEYS[1], now, ARGV[4])
redis.call('EXPIRE', KEYS[1], window)
return 1
"""


def check_rate_limit(key: str, limit: int, window: int) -> bool:
    """
    True = Anfrage erlaubt, False = Limit erreicht. Sliding-Window.
    Bis `limit` Anfragen je `window` Sekunden erlaubt; geblockte zaehlen nicht mit.
    Der Redis-Pfad ist via Lua atomar (kein Check-and-Increment-Race).
    """
    now = time.time()
    client = _get_client()
    if client is not None:
        try:
            member = f"{now}:{uuid.uuid4().hex}"
            allowed = client.eval(_RATE_LUA, 1, f"ratelimit:{key}", now, window, limit, member)
            return bool(allowed)
        except Exception:
            _invalidate()  # Verbindung tot → Reconnect beim naechsten Call; jetzt Fallback

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
        _invalidate()
        return None


def cache_set(key: str, value: str, ttl: int = CACHE_TTL) -> None:
    client = _get_client()
    if client is None:
        return
    try:
        client.set(key, value, ex=ttl)
    except Exception:
        _invalidate()
