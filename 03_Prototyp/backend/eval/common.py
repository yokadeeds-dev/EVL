"""Gemeinsame Bausteine der Evaluation: Golden Set laden, Eval-Korpus aufbauen."""

from __future__ import annotations

import random
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml

import rag_engine
import synthetic_docs
from acl import USERS, UserContext
from rag_engine import Document, InMemoryQdrant, LegalRAGEngine, QueryResult

EVAL_DIR = Path(__file__).resolve().parent


@dataclass
class Item:
    id: str
    user: str
    question: str
    text_type: str
    relevant: dict
    facts: list[str]
    reference: str
    forbidden_mandates: list[str] = field(default_factory=list)

    @property
    def ctx(self) -> UserContext:
        return USERS[self.user]

    @property
    def answerable(self) -> bool:
        return bool(self.relevant)

    @property
    def group(self) -> str:
        return {"L": "leitfaden", "P": "praezedenz", "M": "mandant", "X": "acl_negativ",
                "U": "unbeantwortbar"}[self.id[0]]

    def is_relevant(self, r: QueryResult | Document) -> bool:
        prefixes = self.relevant.get("title_prefix", [])
        if prefixes and any(r.title.startswith(p) for p in prefixes):
            return True
        return "mandant" in self.relevant and r.mandant_id == self.relevant["mandant"]


def load_items(path: Path = EVAL_DIR / "golden_set.yaml") -> list[Item]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    items = [Item(**{k: v for k, v in entry.items()}) for entry in raw["items"]]
    ids = [i.id for i in items]
    assert len(ids) == len(set(ids)), "doppelte IDs im Golden Set"
    return items


def use_embedder(kind: str) -> None:
    """'hash' = deterministischer Fallback (CI, kein Modell); 'e5' = multilingual-e5-small."""
    if kind not in ("hash", "e5"):
        raise ValueError(f"unbekannter Embedder {kind!r}")
    rag_engine.embedder.use_real_model = kind == "e5"


def build_engine(workdir: Path | None = None) -> tuple[LegalRAGEngine, InMemoryQdrant]:
    """Erzeugt den synthetischen Korpus (Seed 42) und ingestet ihn in einen frischen Store.

    Läuft bewusst gegen den In-Memory-Store: Die Evaluation misst Retrieval-Qualität,
    nicht die Datenbank; pgvector nutzt dieselbe Embedding- und Filterlogik.
    """
    workdir = Path(workdir or tempfile.mkdtemp(prefix="evl-eval-"))
    docs_dir = workdir / "docs"
    random.seed(42)  # synthetic_docs nutzt das globale random → reproduzierbarer Korpus
    synthetic_docs.generate_docs(output_dir=str(docs_dir))
    store = InMemoryQdrant(persist_path=str(workdir / "store.json"))
    rag_engine.ingest_documents(str(docs_dir / "metadata.json"), str(docs_dir), store)
    return LegalRAGEngine(store), store
