"""
EVL-2026-003 · RAG Engine mit ACL-Enforcement
In-Memory-Simulation von Qdrant für den PoC (kein laufender Qdrant-Server nötig).
Selbe Schnittstelle wie die Production-Implementierung.

Für Production: QdrantClient durch echten Client ersetzen —
die ACL-Logik bleibt identisch.
"""

import dataclasses
import hashlib
import json
import math
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

from acl import UserContext, build_qdrant_filter, validate_result

# ── Datenstrukturen ───────────────────────────────────────────────────────────

@dataclass
class Document:
    doc_id:              str
    text:                str
    mandant_id:          str | None
    category:            str
    title:               str
    doc_hash:            str
    embedding:           list[float]


@dataclass
class QueryResult:
    doc_id:    str
    title:     str
    score:     float
    excerpt:   str
    mandant_id: str | None
    category:  str
    acl_valid: bool
    acl_reason: str


# ── Minimales Embedding (TF-IDF-ähnlich, kein Modell nötig) ──────────────────
# VOCAB_SIZE = 384 entspricht der Ausgabe-Dimension von intfloat/multilingual-e5-small,
# damit Fallback-Embeddings und echte Modell-Embeddings kompatibel bleiben.
VOCAB_SIZE = 384

def _simple_embed(text: str) -> list[float]:
    """
    Deterministisches Pseudo-Embedding für den PoC.
    """
    text = text.lower()
    vec = [0.0] * VOCAB_SIZE
    words = re.findall(r'\w+', text)
    for word in words:
        idx = int(hashlib.md5(word.encode()).hexdigest(), 16) % VOCAB_SIZE
        vec[idx] += 1.0
    # L2-Normalisierung
    norm = math.sqrt(sum(x*x for x in vec)) or 1.0
    return [x / norm for x in vec]

class SemanticEmbedder:
    """Wrapper, der einfach ausgetauscht werden kann für sentence-transformers."""
    def __init__(self):
        self.use_real_model = True
        self.model = None
    
    def embed(self, text: str) -> list[float]:
        if self.use_real_model:
            if self.model is None:
                from sentence_transformers import SentenceTransformer
                print("Lade Vektor-Modell (intfloat/multilingual-e5-small)...")
                # Dies lädt das Modell beim ersten Embedding herunter (~450MB)
                self.model = SentenceTransformer("intfloat/multilingual-e5-small")
            
            # e5-small generiert 384-dimensionale Embeddings
            return self.model.encode(text).tolist()
        return _simple_embed(text)

embedder = SemanticEmbedder()


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x*y for x, y in zip(a, b))


# ── In-Memory Vektorstore (Qdrant-kompatible Schnittstelle) ──────────────────

class InMemoryQdrant:
    """
    Simuliert Qdrant-Verhalten inkl. Payload-Filter.
    Interface ist identisch zu qdrant_client.QdrantClient.
    """

    def __init__(self, persist_path: str = "qdrant_store.json"):
        self._store: dict[str, Document] = {}
        self.persist_path = persist_path
        self._load()

    def _load(self):
        if os.path.exists(self.persist_path):
            with open(self.persist_path, encoding="utf-8") as f:
                data = json.load(f)
            for k, v in data.items():
                self._store[k] = Document(**v)

    def _save(self):
        with open(self.persist_path, "w", encoding="utf-8") as f:
            data = {k: dataclasses.asdict(v) for k, v in self._store.items()}
            json.dump(data, f)

    def upsert(self, doc: Document, persist: bool = True) -> None:
        self._store[doc.doc_id] = doc
        if persist:
            self._save()

    def flush(self) -> None:
        """Persistiert den Stand einmalig (nach Batch-Ingest mit persist=False)."""
        self._save()

    def search(
        self,
        query_embedding: list[float],
        qdrant_filter: dict,
        top_k: int = 5,
    ) -> list[tuple[Document, float]]:
        """
        Suche mit Payload-Filter — Filter wird VOR Score-Berechnung angewendet.
        Kein Post-Filter: entspricht Qdrant-Verhalten.
        """
        results = []
        for doc in self._store.values():
            if not self._matches_filter(doc, qdrant_filter):
                continue
            score = _cosine(query_embedding, doc.embedding)
            results.append((doc, score))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def _matches_filter(self, doc: Document, f: dict) -> bool:
        """Qdrant-Filter-Semantik: should (OR) + must_not."""
        # should: mindestens eine Bedingung muss zutreffen
        should = f.get("should", [])
        if should:
            passed_should = False
            for cond in should:
                if "match" in cond and "any" in cond["match"]:
                    if doc.mandant_id in cond["match"]["any"]:
                        passed_should = True
                        break
                if cond.get("is_null") and doc.mandant_id is None:
                    passed_should = True
                    break
            if not passed_should:
                return False

        # must_not: keine Bedingung darf zutreffen (Chinese Wall: verbotene Mandate)
        must_not = f.get("must_not", [])
        for cond in must_not:
            if "match" in cond and "any" in cond["match"]:
                if cond.get("key") == "mandant_id" and doc.mandant_id in cond["match"]["any"]:
                    return False

        return True

    def count(self) -> int:
        return len(self._store)

    def clear(self) -> None:
        self._store.clear()
        self._save()


# ── Ingest-Pipeline ───────────────────────────────────────────────────────────


def ingest_documents(
    metadata_path: str,
    docs_dir: str,
    store: InMemoryQdrant,
    verbose: bool = False,
) -> dict:
    """
    Ingest-Pipeline: Liest Docs, berechnet Embeddings, speichert in Store.
    Idempotent: bereits vorhandene doc_hashes werden übersprungen.
    """
    meta_path = Path(metadata_path)
    if not meta_path.exists():
        raise FileNotFoundError(f"metadata.json nicht gefunden: {meta_path}")

    all_meta = json.loads(meta_path.read_text(encoding="utf-8"))
    docs_path = Path(docs_dir)

    stats = {"ingested": 0, "skipped": 0, "errors": 0}
    existing_hashes = {d.doc_hash for d in store._store.values()}

    t0 = time.perf_counter()
    for meta in all_meta:
        try:
            fname = meta["filename"]
            text = (docs_path / fname).read_text(encoding="utf-8")
            doc_hash = hashlib.sha256(text.encode()).hexdigest()[:16]

            if doc_hash in existing_hashes:
                stats["skipped"] += 1
                continue

            embedding = embedder.embed(text)

            doc = Document(
                doc_id=meta["doc_id"],
                text=text,
                mandant_id=meta.get("mandant_id"),
                category=meta["category"],
                title=meta["title"],
                doc_hash=doc_hash,
                embedding=embedding,
            )
            # persist=False: nicht je upsert die ganze JSON schreiben (F7: O(n²)
            # beim Batch-Ingest) — einmaliges flush() nach der Schleife.
            store.upsert(doc, persist=False)
            existing_hashes.add(doc_hash)
            stats["ingested"] += 1

            if verbose and stats["ingested"] % 100 == 0:
                elapsed = time.perf_counter() - t0
                rate = stats["ingested"] / elapsed
                print(f"  Ingest: {stats['ingested']} Docs  ({rate:.0f} Docs/s)")

        except Exception as e:
            stats["errors"] += 1
            if verbose:
                print(f"  Fehler bei {meta.get('filename','?')}: {e}")

    store.flush()
    elapsed = time.perf_counter() - t0
    stats["elapsed_s"] = round(elapsed, 2)
    stats["docs_per_s"] = round(stats["ingested"] / elapsed, 1) if elapsed > 0 else 0
    return stats


# ── RAG Query Engine ──────────────────────────────────────────────────────────

class LegalRAGEngine:
    """
    Hauptschnittstelle für RAG-Queries mit ACL-Enforcement.
    Jede Query geht durch build_qdrant_filter() — nicht bypassbar.
    """

    def __init__(self, store: InMemoryQdrant):
        self._store = store

    def query(
        self,
        user: UserContext,
        question: str,
        top_k: int = 5,
    ) -> list[QueryResult]:
        """
        Führt eine ACL-geschützte Similarity-Suche durch.
        Filter wird VOR der Suche gesetzt — kein Datenleck möglich.
        """
        # Schritt 1: Filter erzwingen (keine Query ohne Filter möglich)
        qdrant_filter = build_qdrant_filter(user)

        # Schritt 2: Query embedden
        query_emb = embedder.embed(question)

        # Schritt 3: Gefilterte Suche
        raw_results = self._store.search(query_emb, qdrant_filter, top_k=top_k)

        # Schritt 4: Nachgelagerte ACL-Validierung (Audit-Layer)
        results = []
        for doc, score in raw_results:
            valid, reason = validate_result({"mandant_id": doc.mandant_id}, user)
            excerpt = doc.text[:200].replace("\n", " ") + "…"
            results.append(QueryResult(
                doc_id=doc.doc_id,
                title=doc.title,
                score=round(score, 4),
                excerpt=excerpt,
                mandant_id=doc.mandant_id,
                category=doc.category,
                acl_valid=valid,
                acl_reason=reason,
            ))

        return results
