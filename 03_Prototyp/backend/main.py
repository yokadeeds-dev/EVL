"""
EVL-2026-002 · Content-Assistant Backend
FastAPI + Postgres/pgvector RAG + Anthropic Claude API + Auth + Rate-Limiting

Starten:
    cp .env.example .env  # Keys eintragen
    pip install -r requirements.txt
    uvicorn main:app --reload
"""

import os
import re
from contextlib import asynccontextmanager

import anthropic
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field

import generation
import jwt_auth
import redis_backend
import synthetic_docs
from acl import UserContext, authenticate
from auth import require_admin, require_user
from prompts import TEMPLATES
from rag_engine import InMemoryQdrant, LegalRAGEngine
from rag_engine import ingest_documents as engine_ingest_documents

load_dotenv()

# ── Rate-Limiting (Redis, prozessuebergreifend; In-Memory-Fallback) ──────────

RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "20"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))


def _check_rate_limit(key: str) -> None:
    if not redis_backend.check_rate_limit(key, RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW):
        raise HTTPException(
            status_code=429,
            detail=f"Rate-Limit erreicht: max. {RATE_LIMIT_REQUESTS} Anfragen / {RATE_LIMIT_WINDOW}s.",
        )


# ── Globale Instanzen ────────────────────────────────────────────────────────

store: InMemoryQdrant | None = None
rag: LegalRAGEngine | None = None
llm_client: anthropic.Anthropic | None = None


def _make_store():
    """DATABASE_URL gesetzt → geteilter Postgres/pgvector-Store; sonst In-Memory-Fallback."""
    dsn = os.getenv("DATABASE_URL", "").strip()
    if dsn:
        from pgvector_store import PgVectorStore
        return PgVectorStore(dsn)
    return InMemoryQdrant()


@asynccontextmanager
async def lifespan(app: FastAPI):
    global store, rag, llm_client
    store = _make_store()
    rag = LegalRAGEngine(store)
    llm_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    yield


app = FastAPI(
    title="EVL-2026-002 Content-Assistant",
    version="1.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("ALLOWED_ORIGIN", "http://localhost:5173")],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Schemas ──────────────────────────────────────────────────────────────────


class GenerateRequest(BaseModel):
    text_type: str = Field(..., pattern="^(seo|produkt|faq|leicht|social)$")
    topic: str = Field(..., min_length=3, max_length=500)
    use_rag: bool = Field(default=True)
    target_mandant: str | None = None


class GenerateResponse(BaseModel):
    result: str
    text_type: str
    label: str
    context_chunks_used: int
    rag_active: bool


class IngestRequest(BaseModel):
    path: str = Field(default="./knowledge_base")


class StatusResponse(BaseModel):
    status: str
    knowledge_base_empty: bool
    available_templates: list[str]
    version: str


class KBStatusResponse(BaseModel):
    document_count: int
    is_empty: bool


# ── Public Endpoints ─────────────────────────────────────────────────────────


@app.get("/status", response_model=StatusResponse)
def get_status():
    """Öffentlicher Systemstatus – kein Auth erforderlich."""
    return {
        "status": "ok",
        "knowledge_base_empty": store is None or store.count() == 0,
        "available_templates": list(TEMPLATES.keys()),
        "version": "1.1.0",
    }


# ── User Endpoints (require_user) ────────────────────────────────────────────


@app.get("/templates")
def list_templates(user: UserContext = Depends(require_user)):
    """Alle Template-IDs und Labels."""
    return [{"id": k, "label": v["label"]} for k, v in TEMPLATES.items()]


@app.post("/auth/token")
def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """OAuth2 Login. Prüft Benutzername UND Passwort (pbkdf2-Hash in acl.USERS)."""
    user = authenticate(form_data.username, form_data.password)
    if user is None:
        # Bewusst generisch: keine Auskunft, ob User oder Passwort falsch war.
        raise HTTPException(
            status_code=401,
            detail="Benutzername oder Passwort falsch.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    jwt_token = jwt_auth.create_jwt({"sub": user.user_id})
    return {"access_token": jwt_token, "token_type": "bearer"}


@app.get("/me")
def get_me(user: UserContext = Depends(require_user)):
    """Aktuellen authentifizierten User zurückgeben."""
    return {
        "user_id": user.user_id,
        "name": user.name,
        "allowed_mandate": user.allowed_mandate,
        "effective_allowed": user.effective_allowed(),
        "chinese_wall_pairs": user.chinese_wall_pairs
    }


@app.post("/generate", response_model=GenerateResponse)
def generate_text(req: GenerateRequest, user: UserContext = Depends(require_user)):
    """RAG-Retrieval + LLM-Generierung (ACL-geschützt)."""
    # Rate-Limit pro User-Identität (nicht pro API-Key-String).
    _check_rate_limit(user.user_id)

    if llm_client is None:
        raise HTTPException(status_code=503, detail="LLM-Client nicht initialisiert.")

    # PII-Check auf dem User-Input VOR teurer RAG-/LLM-Arbeit (F6: früh ablehnen).
    _check_for_pii(req.topic)

    if req.use_rag:
        retrieval = generation.retrieve(rag, store.count() if store else 0, user, req.topic,
                                        req.target_mandant, top_k=5)
    else:
        retrieval = generation.Retrieval([], [])

    try:
        gen = generation.generate(llm_client, retrieval, req.text_type, req.topic)
    except anthropic.APIStatusError as e:
        raise HTTPException(status_code=502, detail=f"LLM-API Fehler: {e.message}")

    return GenerateResponse(
        result=gen.result,
        text_type=req.text_type,
        label=gen.label,
        context_chunks_used=gen.chunks_used,
        rag_active=gen.chunks_used > 0,
    )


# ── Admin Endpoints (require_admin) ──────────────────────────────────────────


@app.post("/admin/ingest")
def ingest_documents(req: IngestRequest, user: UserContext = Depends(require_admin)):
    """Wissensbasis einlesen."""
    if store is None or rag is None:
        raise HTTPException(status_code=503, detail="RAG-Pipeline nicht initialisiert.")
    try:
        import os
        os.makedirs(req.path, exist_ok=True)
        meta_path = f"{req.path}/metadata.json"
        
        # Generiere Sandbox Docs mit Mandant-Metadaten falls abwesend
        if not os.path.exists(meta_path):
            synthetic_docs.generate_docs(output_dir=req.path)
            
        stats = engine_ingest_documents(meta_path, req.path, store, verbose=True)
        return {"status": "ok", "documents_ingested": stats["ingested"]}
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/admin/kb-status", response_model=KBStatusResponse)
def kb_status(user: UserContext = Depends(require_admin)):
    """Wissensbasis-Status."""
    if store is None:
        raise HTTPException(status_code=503, detail="RAG-Pipeline nicht initialisiert.")
    count = store.count()
    return {"document_count": count, "is_empty": count == 0}


@app.delete("/admin/kb-reset")
def kb_reset(user: UserContext = Depends(require_admin)):
    """Wissensbasis vollständig leeren."""
    if store is None:
        raise HTTPException(status_code=503, detail="RAG-Pipeline nicht initialisiert.")
    store.clear()
    return {"status": "ok", "message": "Wissensbasis geleert."}


# ── PII-Sanitizer ────────────────────────────────────────────────────────────

PII_PATTERNS = [
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "E-Mail-Adresse"),
    # Kein \b vor "+": nach einem Leerzeichen gibt es dort keine Wortgrenze, "+49 170 …"
    # rutschte durch (gefunden per eval/redteam). Lookbehind statt Wortgrenze.
    (r"(?<![\w+])(?:\+49|0049|0)[\s\-/]?\d[\d\s\-/]{6,}\d", "Telefonnummer"),
    (r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}([A-Z0-9]?){0,16}\b", "IBAN"),
    (r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "IP-Adresse"),
]


def _check_for_pii(text: str) -> None:
    for pattern, label in PII_PATTERNS:
        if re.search(pattern, text):
            raise HTTPException(
                status_code=422,
                detail=f"Eingabe enthält möglicherweise personenbezogene Daten ({label}). Bitte entfernen.",
            )


# ── Admin-Upload-Router einbinden ─────────────────────────────────────────────
from admin_upload import router as upload_router

app.include_router(upload_router)
