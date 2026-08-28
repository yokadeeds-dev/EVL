"""
Postgres + pgvector Vektorstore — geteilter, prozessuebergreifender RAG-Store.

Ersetzt InMemoryQdrant (der pro Worker-Prozess einen eigenen Store hielt → mit
`uvicorn --workers 2` sah ein nach /admin/ingest load-balanctes /generate auf dem
anderen Worker eine leere Wissensbasis). Postgres teilt den Store ueber alle
Worker/Replicas. Schnittstelle identisch zu InMemoryQdrant: upsert/search/count.

Kein pgvector-Python-Paket noetig — Embeddings werden als Vektor-Literal geschrieben
und via `::vector` gecastet; noetig ist nur die Postgres-Extension `vector`
(im Image pgvector/pgvector vorhanden).
"""

from psycopg_pool import ConnectionPool

from rag_engine import Document

VECTOR_DIM = 384

_SCHEMA = """
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS documents (
    doc_id               TEXT PRIMARY KEY,
    text                 TEXT NOT NULL,
    mandant_id           TEXT,
    category             TEXT NOT NULL,
    title                TEXT NOT NULL,
    doc_hash             TEXT NOT NULL,
    embedding            vector(384) NOT NULL
);

-- ANN-Index für die Similarity-Suche (ORDER BY embedding <=> qvec).
-- Ohne diesen Index ist jede Query ein Full Scan über alle Zeilen; bei
-- zehntausenden Dokumenten der erste Performance-Engpass. HNSW passt zur
-- Cosine-Distanz (<=>), daher vector_cosine_ops.
CREATE INDEX IF NOT EXISTS documents_embedding_hnsw
    ON documents USING hnsw (embedding vector_cosine_ops);

-- ACL-Vorfilter (WHERE, vor der Vektorsortierung): mandant_id ist skalar und
-- deckt sowohl "= ANY(effective)" als auch den Chinese-Wall-Ausschluss ab.
CREATE INDEX IF NOT EXISTS documents_mandant_id_idx
    ON documents (mandant_id);
"""


def _vec_literal(embedding: list[float]) -> str:
    """list[float] → pgvector-Literal '[0.1,0.2,...]'."""
    return "[" + ",".join(repr(float(x)) for x in embedding) + "]"


def _parse_filter(qdrant_filter: dict) -> tuple[list[str], list[str]]:
    """Zieht (erlaubte Mandate, wall-verbotene Mandate) aus dem Qdrant-Filter."""
    allowed: list[str] = []
    forbidden: list[str] = []
    for cond in qdrant_filter.get("should", []):
        if cond.get("key") == "mandant_id" and "match" in cond:
            allowed = cond["match"].get("any", [])
    for cond in qdrant_filter.get("must_not", []):
        if cond.get("key") == "mandant_id" and "match" in cond:
            forbidden = cond["match"].get("any", [])
    return allowed, forbidden


class PgVectorStore:
    """Qdrant-kompatibler Store auf Postgres/pgvector."""

    def __init__(self, dsn: str):
        self.pool = ConnectionPool(
            dsn, min_size=1, max_size=5, open=True, kwargs={"autocommit": True}
        )
        with self.pool.connection() as conn:
            conn.execute(_SCHEMA)

    def upsert(self, doc: Document, persist: bool = True) -> None:
        # persist ist bei Postgres bedeutungslos (autocommit → jeder Insert sofort
        # dauerhaft); Parameter nur für Interface-Gleichheit mit InMemoryQdrant.
        with self.pool.connection() as conn:
            conn.execute(
                """
                INSERT INTO documents
                  (doc_id, text, mandant_id, category, title, doc_hash, embedding)
                VALUES (%s, %s, %s, %s, %s, %s, %s::vector)
                ON CONFLICT (doc_id) DO UPDATE SET
                  text = EXCLUDED.text, mandant_id = EXCLUDED.mandant_id,
                  category = EXCLUDED.category, title = EXCLUDED.title,
                  doc_hash = EXCLUDED.doc_hash, embedding = EXCLUDED.embedding
                """,
                (doc.doc_id, doc.text, doc.mandant_id, doc.category, doc.title,
                 doc.doc_hash, _vec_literal(doc.embedding)),
            )

    def flush(self) -> None:
        """No-op: bei Postgres/autocommit ist jeder upsert bereits persistiert."""

    def search(
        self,
        query_embedding: list[float],
        qdrant_filter: dict,
        top_k: int = 5,
    ) -> list[tuple[Document, float]]:
        """
        ACL-gefilterte Similarity-Suche. Der Filter (Mandanten-Isolation +
        Chinese-Wall) wird als SQL-WHERE VOR der Vektorsortierung angewendet —
        kein Post-Filter, gleiche Semantik wie InMemoryQdrant.
        """
        allowed, forbidden = _parse_filter(qdrant_filter)
        qvec = _vec_literal(query_embedding)
        with self.pool.connection() as conn:
            rows = conn.execute(
                """
                SELECT doc_id, text, mandant_id, category, title, doc_hash,
                       1 - (embedding <=> %s::vector) AS score
                FROM documents
                WHERE (mandant_id = ANY(%s::text[]) OR mandant_id IS NULL)
                  AND (mandant_id IS NULL OR NOT (mandant_id = ANY(%s::text[])))
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """,
                (qvec, allowed, forbidden, qvec, top_k),
            ).fetchall()

        results: list[tuple[Document, float]] = []
        for r in rows:
            doc = Document(
                doc_id=r[0], text=r[1], mandant_id=r[2], category=r[3], title=r[4],
                doc_hash=r[5], embedding=[],
            )
            results.append((doc, float(r[6])))
        return results

    def count(self) -> int:
        with self.pool.connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]

    def clear(self) -> None:
        with self.pool.connection() as conn:
            conn.execute("TRUNCATE documents")
