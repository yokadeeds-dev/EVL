"""
Tests fuer redis_backend — In-Memory-Fallback (immer) und echtes Redis (falls erreichbar).

Der In-Memory-Pfad wird erzwungen, indem der gecachte Client auf None gesetzt wird;
der Redis-Pfad laeuft nur, wenn REDIS_URL auf ein erreichbares Redis zeigt (sonst skip).
"""

import uuid

import pytest

import redis_backend


def _force_memory():
    """Erzwingt den In-Memory-Pfad (kein Redis)."""
    redis_backend._mem_store.clear()
    redis_backend._connect_tried = True
    redis_backend._client = None


def _try_redis():
    """Setzt den Verbindungs-Cache zurueck und versucht eine echte Verbindung."""
    redis_backend._connect_tried = False
    redis_backend._client = None
    return redis_backend.redis_available()


# ── In-Memory-Fallback ────────────────────────────────────────────────────────


class TestInMemoryFallback:
    def test_rate_limit_allows_then_blocks(self):
        _force_memory()
        key = f"k-{uuid.uuid4().hex}"
        assert all(redis_backend.check_rate_limit(key, 3, 60) for _ in range(3))
        assert not redis_backend.check_rate_limit(key, 3, 60)

    def test_rate_limit_isolated_per_key(self):
        _force_memory()
        k1 = f"k-{uuid.uuid4().hex}"
        k2 = f"k-{uuid.uuid4().hex}"
        for _ in range(3):
            redis_backend.check_rate_limit(k1, 3, 60)
        assert not redis_backend.check_rate_limit(k1, 3, 60)
        assert redis_backend.check_rate_limit(k2, 3, 60)

    def test_cache_is_noop_without_redis(self):
        _force_memory()
        ck = redis_backend.cache_key("model", "system", "prompt")
        redis_backend.cache_set(ck, "wert")
        assert redis_backend.cache_get(ck) is None

    def test_cache_key_is_deterministic_and_input_sensitive(self):
        a = redis_backend.cache_key("m", "sys", "prompt")
        b = redis_backend.cache_key("m", "sys", "prompt")
        c = redis_backend.cache_key("m", "sys", "anders")
        assert a == b
        assert a != c
        assert a.startswith("llmcache:")


# ── Echtes Redis (nur wenn erreichbar) ────────────────────────────────────────


class TestWithRedis:
    def test_cache_roundtrip(self):
        if not _try_redis():
            pytest.skip("kein erreichbares Redis (REDIS_URL)")
        ck = redis_backend.cache_key("m", "sys", uuid.uuid4().hex)
        assert redis_backend.cache_get(ck) is None
        redis_backend.cache_set(ck, "hallo", ttl=30)
        assert redis_backend.cache_get(ck) == "hallo"

    def test_rate_limit_blocks_in_redis(self):
        if not _try_redis():
            pytest.skip("kein erreichbares Redis (REDIS_URL)")
        key = f"rl-{uuid.uuid4().hex}"
        assert all(redis_backend.check_rate_limit(key, 2, 60) for _ in range(2))
        assert not redis_backend.check_rate_limit(key, 2, 60)
