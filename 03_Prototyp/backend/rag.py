"""
RAG-Pipeline: Dokumente einlesen → ChromaDB → Kontext-Retrieval.

Verwendung:
    rag = RAGPipeline()
    rag.ingest_documents("./knowledge_base")   # einmalig beim Setup
    context = rag.retrieve("Produktbeschreibung Nachhaltige Verpackung")
"""

import os
from pathlib import Path

import chromadb
from chromadb.config import Settings
from llama_index.core import SimpleDirectoryReader, VectorStoreIndex, StorageContext
from llama_index.core.node_parser import SentenceSplitter
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core import Settings as LISettings


def _get_embed_model() -> HuggingFaceEmbedding:
    """
    Lokales Embedding-Modell – läuft vollständig on-premise,
    kein API-Call für Embeddings nötig (DSGVO-Vorteil).
    """
    return HuggingFaceEmbedding(
        model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    )


class RAGPipeline:
    """
    Kapselt ChromaDB-Verbindung und LlamaIndex-Retrieval.
    Thread-safe für FastAPI-Einsatz (read-only nach Ingest).
    """

    COLLECTION_NAME = "evl_knowledge_base"

    def __init__(self, chroma_path: str | None = None):
        self.chroma_path = chroma_path or os.getenv("CHROMA_PATH", "./chroma_db")
        LISettings.embed_model = _get_embed_model()
        LISettings.llm = None  # LLM-Calls laufen separat über Anthropic SDK

        self._client = chromadb.PersistentClient(
            path=self.chroma_path,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._client.get_or_create_collection(
            name=self.COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )
        self._index: VectorStoreIndex | None = None
        self._load_index()

    # ── Index laden (falls bereits befüllt) ──────────────────────────────────

    def _load_index(self) -> None:
        if self._collection.count() == 0:
            return
        vector_store = ChromaVectorStore(chroma_collection=self._collection)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        self._index = VectorStoreIndex.from_vector_store(
            vector_store, storage_context=storage_context
        )

    # ── Dokumente einlesen ───────────────────────────────────────────────────

    def ingest_documents(self, knowledge_base_path: str) -> int:
        """
        Liest alle Dateien aus knowledge_base_path ein (PDF, TXT, MD, DOCX).
        Gibt Anzahl der verarbeiteten Nodes zurück.
        Idempotent: bereits vorhandene Docs werden übersprungen.
        """
        path = Path(knowledge_base_path)
        if not path.exists():
            raise FileNotFoundError(f"Wissensbasis-Pfad nicht gefunden: {path}")

        documents = SimpleDirectoryReader(
            input_dir=str(path),
            required_exts=[".pdf", ".txt", ".md", ".docx"],
            recursive=True,
        ).load_data()

        if not documents:
            return 0

        splitter = SentenceSplitter(chunk_size=300, chunk_overlap=30)
        vector_store = ChromaVectorStore(chroma_collection=self._collection)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)

        self._index = VectorStoreIndex.from_documents(
            documents,
            storage_context=storage_context,
            transformations=[splitter],
            show_progress=True,
        )
        return len(documents)

    # ── Kontext abrufen ──────────────────────────────────────────────────────

    def retrieve(self, query: str, top_k: int = 3) -> str:
        """
        Gibt die top_k relevantesten Text-Chunks als zusammengeführten
        Kontextstring zurück. Leerer String wenn Index leer.
        """
        if self._index is None or self._collection.count() == 0:
            return ""

        retriever = self._index.as_retriever(similarity_top_k=top_k)
        nodes = retriever.retrieve(query)

        if not nodes:
            return ""

        chunks = [node.get_content().strip() for node in nodes]
        return "\n\n---\n\n".join(chunks)

    def is_empty(self) -> bool:
        return self._collection.count() == 0
