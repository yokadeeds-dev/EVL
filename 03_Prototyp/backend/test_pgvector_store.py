"""
Tests fuer PgVectorStore gegen echtes Postgres/pgvector.
Skippt, wenn DATABASE_URL nicht gesetzt oder Postgres nicht erreichbar ist.
Nutzt _simple_embed (kein sentence-transformers noetig).
"""

import os
import uuid

import pytest

from acl import USERS, build_qdrant_filter
from rag_engine import Document, _simple_embed

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()


def _store():
    if not DATABASE_URL:
        pytest.skip("kein DATABASE_URL gesetzt")
    try:
        from pgvector_store import PgVectorStore
        return PgVectorStore(DATABASE_URL)
    except Exception as exc:
        pytest.skip(f"Postgres/pgvector nicht erreichbar: {exc}")


def _doc(doc_id: str, text: str, mandant_id, cw_exclude: list[str]) -> Document:
    return Document(
        doc_id=doc_id, text=text, mandant_id=mandant_id, category="test",
        title=doc_id, chinese_wall_exclude=cw_exclude, doc_hash=doc_id,
        embedding=_simple_embed(text),
    )


class TestPgVectorStore:
    def test_count_and_mandant_isolation(self):
        store = _store()
        p = uuid.uuid4().hex[:8]
        d1 = _doc(f"{p}-1", "vertrag mandant eins", "M001", ["anwalt_b", "anwalt_c"])
        d2 = _doc(f"{p}-2", "vertrag mandant zwei", "M002", ["anwalt_a", "anwalt_c"])
        d3 = _doc(f"{p}-3", "oeffentlicher leitfaden", None, [])
        before = store.count()
        for d in (d1, d2, d3):
            store.upsert(d)
        assert store.count() == before + 3

        # anwalt_a (effektiv M001,M003): sieht M001 + oeffentlich, nicht M002
        seen_a = {
            d.doc_id
            for d, _ in store.search(_simple_embed("vertrag"), build_qdrant_filter(USERS["anwalt_a"]), top_k=50)
        }
        assert f"{p}-1" in seen_a
        assert f"{p}-3" in seen_a
        assert f"{p}-2" not in seen_a

        # anwalt_b (effektiv M002,M003): sieht M002 + oeffentlich, nicht M001
        seen_b = {
            d.doc_id
            for d, _ in store.search(_simple_embed("vertrag"), build_qdrant_filter(USERS["anwalt_b"]), top_k=50)
        }
        assert f"{p}-2" in seen_b
        assert f"{p}-3" in seen_b
        assert f"{p}-1" not in seen_b

    def test_upsert_is_idempotent(self):
        store = _store()
        p = uuid.uuid4().hex[:8]
        d = _doc(f"{p}-x", "irgendein text", "M001", [])
        before = store.count()
        store.upsert(d)
        store.upsert(d)
        assert store.count() == before + 1
