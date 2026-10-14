"""
Echte main.py-Tests via FastAPI TestClient (nicht der Mock aus test_e2e).

Deckt die tatsaechliche App ab: JWT-Auth-Kette, Admin-Autorisierung (Regression
fuer Finding #1) und den /generate-Pfad mit gemocktem LLM. use_real_model=False →
deterministisches Embedding ohne sentence-transformers. Store: DATABASE_URL gesetzt
→ Postgres/pgvector, sonst In-Memory-Fallback (Test laeuft in beiden Faellen).
"""

import os

# jwt_auth und main pruefen diese Variablen beim Import → vor dem main-Import setzen.
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-nur-fuer-tests-0123456789abcdef")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-dummy-key-unused")

import pytest
from fastapi.testclient import TestClient

import rag_engine

rag_engine.embedder.use_real_model = False  # kein Modell-Download im Test

import main


class _FakeBlock:
    def __init__(self, text: str):
        self.text = text


class _FakeMessage:
    def __init__(self, text: str):
        self.content = [_FakeBlock(text)]


class _FakeMessages:
    def create(self, **kwargs):
        return _FakeMessage("GENERIERTER-TEXT")


class _FakeClient:
    def __init__(self):
        self.messages = _FakeMessages()


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:  # startet den Lifespan → store, llm_client
        yield c


# Demo-Passwörter (Defaults aus acl._DEMO_PASSWORDS)
_PASSWORDS = {
    "anwalt_a": "kraft-demo-2026",
    "anwalt_b": "schuster-demo-2026",
    "anwalt_c": "voss-demo-2026",
}


def _token(client, username: str) -> str:
    r = client.post(
        "/auth/token",
        data={"username": username, "password": _PASSWORDS[username]},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_status_is_public(client):
    r = client.get("/status")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_templates_requires_auth(client):
    assert client.get("/templates").status_code == 401


def test_login_rejects_wrong_password(client):
    # Regression: Login MUSS das Passwort prüfen (Auth-Bypass-Fix).
    r = client.post("/auth/token", data={"username": "anwalt_a", "password": "falsch"})
    assert r.status_code == 401, r.text


def test_login_rejects_unknown_user(client):
    r = client.post("/auth/token", data={"username": "hacker", "password": "x"})
    assert r.status_code == 401, r.text


def test_login_accepts_correct_password(client):
    r = client.post(
        "/auth/token", data={"username": "anwalt_a", "password": "kraft-demo-2026"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["access_token"]


def test_list_documents_requires_admin(client):
    # Regression fuer #1: Nicht-Admin (anwalt_b) darf die KB NICHT auflisten
    r = client.get("/admin/documents", headers=_auth(_token(client, "anwalt_b")))
    assert r.status_code == 403
    # Admin (anwalt_a) darf
    r = client.get("/admin/documents", headers=_auth(_token(client, "anwalt_a")))
    assert r.status_code == 200


def test_delete_document_requires_admin(client):
    # Regression fuer #1: Nicht-Admin darf NICHT loeschen
    r = client.delete("/admin/documents/beliebig.pdf", headers=_auth(_token(client, "anwalt_b")))
    assert r.status_code == 403


def test_kb_reset_requires_admin_and_clears(client):
    assert client.delete("/admin/kb-reset", headers=_auth(_token(client, "anwalt_b"))).status_code == 403
    r = client.delete("/admin/kb-reset", headers=_auth(_token(client, "anwalt_a")))
    assert r.status_code == 200
    st = client.get("/admin/kb-status", headers=_auth(_token(client, "anwalt_a")))
    assert st.json()["is_empty"] is True


def test_generate_happy_path_with_mocked_llm(client, monkeypatch):
    monkeypatch.setattr(main, "llm_client", _FakeClient())
    r = client.post(
        "/generate",
        headers=_auth(_token(client, "anwalt_a")),
        json={"text_type": "seo", "topic": "Qualitaetsmanagement", "use_rag": False},
    )
    assert r.status_code == 200, r.text
    assert r.json()["result"] == "GENERIERTER-TEXT"


def test_ingest_generates_sandbox_docs_when_metadata_missing(client, tmp_path):
    # Regression: /admin/ingest rief synthetic_docs.generate_synthetic_docs (existiert nicht)
    # → AttributeError/500, sobald kein metadata.json im Zielordner lag.
    admin = _auth(_token(client, "anwalt_a"))
    r = client.post("/admin/ingest", headers=admin, json={"path": str(tmp_path / "kb")})
    assert r.status_code == 200, r.text
    assert r.json()["documents_ingested"] > 0
    client.delete("/admin/kb-reset", headers=admin)


def test_generation_skips_thinking_blocks():
    # Regression: content[0].text brach bei Modellen, die einen thinking-Block voranstellen.
    import generation

    class Block:
        def __init__(self, type_, text=None):
            self.type, self.text = type_, text

    class Msg:
        content = [Block("thinking"), Block("text", "Antwort")]
        usage = None
        stop_reason = "end_turn"
        model = "claude-opus-5-5"

    class Client:
        class messages:  # noqa: N801
            @staticmethod
            def create(**kwargs):
                return Msg()

    gen = generation.generate(Client(), generation.Retrieval([], []), "faq", "Test", use_cache=False)
    assert gen.result == "Antwort" and gen.served_model == "claude-opus-5-5"


def test_ingest_only_uses_public_store_interface():
    # Regression: ingest_documents darf keine Interna eines konkreten Stores nutzen
    # (store._store gibt es nur im In-Memory-Store; mit pgvector -> AttributeError).
    import inspect

    import rag_engine

    code = "\n".join(line.split("#", 1)[0] for line in inspect.getsource(rag_engine.ingest_documents).splitlines())
    assert "._store" not in code
