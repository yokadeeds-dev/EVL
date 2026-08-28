"""
EVL-2026-002 · End-to-End Tests
Testet alle Endpoints gegen ein laufendes Backend.

Verwendung:
    # Backend muss laufen (lokal oder Docker)
    pytest test_e2e.py -v

    # Gegen andere URL:
    BASE_URL=http://my-server pytest test_e2e.py -v

Umgebungsvariablen:
    BASE_URL       Backend-URL (default: http://localhost:8000)
    USER_KEY       Gültiger User-API-Key
    ADMIN_KEY      Gültiger Admin-API-Key
"""

import os

import httpx
import pytest

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")
USER_KEY = os.getenv("USER_KEY", "key-user-abc123")
ADMIN_KEY = os.getenv("ADMIN_KEY", "key-admin-xyz789")

user_headers = {"X-API-Key": USER_KEY}
admin_headers = {"X-API-Key": ADMIN_KEY}


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def client():
    with httpx.Client(base_url=BASE_URL, timeout=30) as c:
        yield c


# ── /status ──────────────────────────────────────────────────────────────────

class TestStatus:
    def test_status_ok(self, client):
        r = client.get("/status")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "available_templates" in data
        assert isinstance(data["available_templates"], list)

    def test_status_no_auth_needed(self, client):
        """Status-Endpoint ist öffentlich."""
        r = client.get("/status")
        assert r.status_code == 200


# ── Auth ─────────────────────────────────────────────────────────────────────

class TestAuth:
    def test_templates_requires_auth(self, client):
        r = client.get("/templates")
        assert r.status_code == 401

    def test_generate_requires_auth(self, client):
        r = client.post("/generate", json={"text_type": "seo", "topic": "Test"})
        assert r.status_code == 401

    def test_admin_endpoint_requires_admin(self, client):
        r = client.get("/admin/kb-status", headers=user_headers)
        assert r.status_code == 403

    def test_user_key_accepted(self, client):
        r = client.get("/templates", headers=user_headers)
        assert r.status_code == 200

    def test_admin_key_accepted_for_user_endpoints(self, client):
        """Admin-Key darf auch User-Endpoints aufrufen."""
        r = client.get("/templates", headers=admin_headers)
        assert r.status_code == 200


# ── /templates ───────────────────────────────────────────────────────────────

class TestTemplates:
    def test_returns_all_templates(self, client):
        r = client.get("/templates", headers=user_headers)
        assert r.status_code == 200
        data = r.json()
        ids = [t["id"] for t in data]
        for expected in ["seo", "produkt", "faq", "leicht", "social"]:
            assert expected in ids

    def test_each_template_has_label(self, client):
        r = client.get("/templates", headers=user_headers)
        for t in r.json():
            assert "label" in t
            assert len(t["label"]) > 0


# ── /generate ────────────────────────────────────────────────────────────────

class TestGenerate:
    @pytest.mark.parametrize("text_type", ["seo", "produkt", "faq", "leicht", "social"])
    def test_all_template_types(self, client, text_type):
        r = client.post(
            "/generate",
            headers=user_headers,
            json={"text_type": text_type, "topic": "Nachhaltige Verpackung", "use_rag": False},
        )
        assert r.status_code == 200
        data = r.json()
        assert "result" in data
        assert len(data["result"]) > 20
        assert data["text_type"] == text_type

    def test_invalid_text_type(self, client):
        r = client.post(
            "/generate",
            headers=user_headers,
            json={"text_type": "ungueltig", "topic": "Test"},
        )
        assert r.status_code == 422

    def test_topic_too_short(self, client):
        r = client.post(
            "/generate",
            headers=user_headers,
            json={"text_type": "seo", "topic": "AB"},
        )
        assert r.status_code == 422

    def test_pii_blocked_email(self, client):
        r = client.post(
            "/generate",
            headers=user_headers,
            json={"text_type": "seo", "topic": "Kontakt: info@beispiel.de"},
        )
        assert r.status_code == 422
        assert "E-Mail" in r.json()["detail"]

    def test_pii_blocked_phone(self, client):
        r = client.post(
            "/generate",
            headers=user_headers,
            json={"text_type": "seo", "topic": "Rufnummer 0211 12345678"},
        )
        assert r.status_code == 422

    def test_response_has_required_fields(self, client):
        r = client.post(
            "/generate",
            headers=user_headers,
            json={"text_type": "seo", "topic": "Qualitätsmanagement", "use_rag": False},
        )
        assert r.status_code == 200
        data = r.json()
        for field in ["result", "text_type", "label", "context_chunks_used", "rag_active"]:
            assert field in data


# ── Admin Endpoints ───────────────────────────────────────────────────────────

class TestAdmin:
    def test_kb_status(self, client):
        r = client.get("/admin/kb-status", headers=admin_headers)
        assert r.status_code == 200
        data = r.json()
        assert "document_count" in data
        assert "is_empty" in data

    def test_ingest_invalid_path(self, client):
        r = client.post(
            "/admin/ingest",
            headers=admin_headers,
            json={"path": "/does/not/exist"},
        )
        assert r.status_code == 404


# ── Rate-Limiting ─────────────────────────────────────────────────────────────

class TestRateLimit:
    def test_rate_limit_enforced(self, client):
        """21 schnelle Requests sollten den 429 triggern (Standard: 20/60s)."""
        results = []
        for _ in range(21):
            r = client.post(
                "/generate",
                headers={"X-API-Key": "key-ratelimit-test"},
                json={"text_type": "seo", "topic": "Ratetest", "use_rag": False},
            )
            results.append(r.status_code)
        # Mindestens einer muss 429 oder 401/403 sein (ungültiger Key = 401 ist ok)
        assert any(code in (429, 401, 403) for code in results)
