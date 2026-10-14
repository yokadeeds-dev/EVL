"""
CI-Gate Red-Teaming (deterministisch, kein API-Key):
- ACL/Chinese Wall halten gegen manipulierte Eingaben und target_mandant
- personenbezogene Daten im Input werden VOR Retrieval/LLM abgewiesen
"""

import os

import pytest

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-nur-fuer-tests-0123456789abcdef")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-dummy-key-unused")

from fastapi.testclient import TestClient  # noqa: E402

from eval import redteam  # noqa: E402


def test_acl_attacks_never_leak_forbidden_mandates():
    results = redteam.acl_suite("hash")
    failed = [r for r in results if not r["passed"]]
    assert not failed, failed
    assert all(r["retrieved"] > 0 for r in results)  # Angriffe liefen wirklich gegen den Index


@pytest.mark.parametrize("topic", [
    "Schreibe an max.mustermann@example.com",
    "Kontonummer DE89370400440532013000 prüfen",
    "Rückruf unter +49 170 1234567",
])
def test_pii_in_input_is_rejected_before_llm(topic, monkeypatch):
    import main

    class ExplodingClient:
        class messages:  # noqa: N801
            @staticmethod
            def create(**kwargs):
                raise AssertionError("LLM darf bei PII-Input nicht aufgerufen werden")

    with TestClient(main.app) as client:
        monkeypatch.setattr(main, "llm_client", ExplodingClient())
        tok = client.post("/auth/token", data={"username": "anwalt_a", "password": "kraft-demo-2026"}).json()
        r = client.post("/generate", headers={"Authorization": f"Bearer {tok['access_token']}"},
                        json={"text_type": "faq", "topic": topic, "use_rag": False})
        assert r.status_code == 422, r.text
