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

    def test_ann_index_used_for_vector_search(self):
        """
        Regression gegen den Full-Scan-Fall: die Similarity-Suche muss den
        HNSW-Index nutzen, nicht sequentiell scannen. enable_seqscan=off zwingt
        den Planner, den Index zu wählen, falls er verfügbar ist — fehlt der
        Index, bleibt nur der (dann teure) Seq Scan und der Test schlägt fehl.
        """
        from pgvector_store import _vec_literal

        store = _store()
        p = uuid.uuid4().hex[:8]
        for i in range(30):
            store.upsert(_doc(f"{p}-{i}", f"vertrag nummer {i}", "M001", []))

        qvec = _vec_literal(_simple_embed("vertrag"))
        with store.pool.connection() as conn:
            conn.execute("SET enable_seqscan = off")
            try:
                rows = conn.execute(
                    "EXPLAIN (FORMAT TEXT) "
                    "SELECT doc_id FROM documents "
                    "ORDER BY embedding <=> %s::vector LIMIT 5",
                    (qvec,),
                ).fetchall()
            finally:
                conn.execute("SET enable_seqscan = on")

        plan = "\n".join(r[0] for r in rows)
        assert "Index Scan" in plan, f"HNSW-Index nicht genutzt:\n{plan}"
        assert "Seq Scan" not in plan, f"Fällt auf Seq Scan zurück:\n{plan}"
