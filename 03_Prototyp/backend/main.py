"""
EVL-2026-002 · Content-Assistant Backend
FastAPI + ChromaDB RAG + Anthropic Claude API + Auth + Rate-Limiting

Starten:
    cp .env.example .env  # Keys eintragen
    pip install -r requirements.txt
    uvicorn main:app --reload
"""

import os
import re
import time
from collections import defaultdict
from contextlib import asynccontextmanager

import anthropic
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from auth import require_user, require_admin
from prompts import TEMPLATES
from acl import UserContext, USERS
from rag_engine import InMemoryQdrant, LegalRAGEngine, ingest_documents as engine_ingest_documents
import synthetic_docs
import jwt_auth
from fastapi.security import OAuth2PasswordRequestForm

load_dotenv()

# ── Rate-Limiting (in-memory, per API-Key) ───────────────────────────────────

RATE_LIMIT_REQUESTS = int(os.getenv("RATE_LIMIT_REQUESTS", "20"))
RATE_LIMIT_WINDOW = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

_rate_store: dict[str, list[float]] = defaultdict(list)


def _check_rate_limit(api_key: str) -> None:
    now = time.time()
    window_start = now - RATE_LIMIT_WINDOW
    calls = [t for t in _rate_store[api_key] if t > window_start]
    if len(calls) >= RATE_LIMIT_REQUESTS:
        raise HTTPException(
            status_code=429,
            detail=f"Rate-Limit erreicht: max. {RATE_LIMIT_REQUESTS} Anfragen / {RATE_LIMIT_WINDOW}s.",
        )
    calls.append(now)
    _rate_store[api_key] = calls


# ── Globale Instanzen ────────────────────────────────────────────────────────

store: InMemoryQdrant | None = None
rag: LegalRAGEngine | None = None
llm_client: anthropic.Anthropic | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global store, rag, llm_client
    store = InMemoryQdrant()
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
    """OAuth2 Login. Akzeptiert anwalt_a, anwalt_b, anwalt_c."""
    user_id = form_data.username
    if user_id not in USERS:
        raise HTTPException(status_code=400, detail="Falscher Benutzername. Test-User: anwalt_a, anwalt_b, anwalt_c")
    
    jwt_token = jwt_auth.create_jwt({"sub": user_id})
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
    # use user.user_id for rate limiting instead of api_key string
    _check_rate_limit(user.user_id)

    if llm_client is None:
        raise HTTPException(status_code=503, detail="LLM-Client nicht initialisiert.")

    template = TEMPLATES[req.text_type]

    # RAG
    context = ""
    chunks_used = 0
    rag_active = False
    if req.use_rag and rag and store and store.count() > 0:
        if req.target_mandant and req.target_mandant in user.effective_allowed():
            from dataclasses import replace
            effective_user = replace(user, allowed_mandate=[req.target_mandant])
        else:
            effective_user = user
            
        query_results = rag.query(effective_user, req.topic, top_k=5)
        valid_excerpts = [r.excerpt for r in query_results if r.acl_valid]
        context = "\n\n---\n\n".join(valid_excerpts)
        chunks_used = len(valid_excerpts)
        rag_active = bool(chunks_used > 0)

    if not context:
        context = (
            "Kein spezifisches Firmenwissen verfügbar. "
            "Allgemeines Branchenwissen verwenden und darauf hinweisen, "
            "dass der Text mit unternehmensspezifischen Informationen ergänzt werden sollte."
        )

    # PII-Check
    _check_for_pii(req.topic)

    user_prompt = template["user_template"].format(context=context, topic=req.topic)

    try:
        message = llm_client.messages.create(
            model=os.getenv("LLM_MODEL", "claude-opus-4-5"),
            max_tokens=1024,
            system=template["system"],
            messages=[{"role": "user", "content": user_prompt}],
        )
    except anthropic.APIStatusError as e:
        raise HTTPException(status_code=502, detail=f"LLM-API Fehler: {e.message}")

    return GenerateResponse(
        result=message.content[0].text,
        text_type=req.text_type,
        label=template["label"],
        context_chunks_used=chunks_used,
        rag_active=rag_active,
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
            synthetic_docs.generate_synthetic_docs(num_docs=100, out_dir=req.path)
            
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
    global store, rag
    if store is None:
        raise HTTPException(status_code=503, detail="RAG-Pipeline nicht initialisiert.")
    
    store = InMemoryQdrant()
    rag = LegalRAGEngine(store)
    return {"status": "ok", "message": "Wissensbasis geleert."}


# ── PII-Sanitizer ────────────────────────────────────────────────────────────

PII_PATTERNS = [
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "E-Mail-Adresse"),
    (r"\b(\+49|0)[0-9\s\-/]{7,}\b", "Telefonnummer"),
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
