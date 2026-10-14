"""Telemetrie: Kostenberechnung, Perzentile/SLOs, Prometheus-Format, Endpoint + Integration in /generate."""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-nur-fuer-tests-0123456789abcdef")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-dummy-key-unused")

from fastapi.testclient import TestClient  # noqa: E402

import telemetry  # noqa: E402
from telemetry import RequestEvent, Telemetry  # noqa: E402


def test_cost_uses_model_price_and_unknown_model_is_none():
    assert telemetry.cost_usd("claude-opus-4-5", 1_000_000, 100_000) == 7.5  # 5 + 2.5
    assert telemetry.cost_usd("unbekannt", 10, 10) is None


def test_snapshot_percentiles_availability_and_slo():
    t = Telemetry()
    for ms in range(1, 101):  # 100 erfolgreiche Anfragen, 1..100 ms
        t.record(RequestEvent(status="ok", total_ms=ms, retrieval_ms=ms / 10, context_chunks=1,
                              input_tokens=10, output_tokens=5, cost_usd=0.001))
    t.record(RequestEvent(status="llm_error"))
    t.record(RequestEvent(status="pii_rejected"))  # Nutzerfehler zählt nicht gegen Verfügbarkeit
    s = t.snapshot()
    assert s["requests_total"] == 102 and s["latency_ms"]["p95"] == 95
    assert s["slo"]["availability"]["value"] == 100 / 101
    assert s["slo"]["latency_p95_ms"]["met"] is True
    assert s["tokens"] == {"input": 1000, "output": 500} and s["cost_usd_total"] == 0.1


def test_prometheus_exposition():
    t = Telemetry()
    t.record(RequestEvent(status="ok", total_ms=12, input_tokens=3, output_tokens=4, cost_usd=0.5))
    text = t.prometheus()
    assert 'evl_generate_requests_total{status="ok"} 1' in text
    assert 'evl_llm_tokens_total{kind="input"} 3' in text and "evl_llm_cost_usd_total 0.5" in text


def test_generate_records_event_and_metrics_endpoint_is_admin_only(monkeypatch):
    import main

    class Usage:
        input_tokens, output_tokens = 100, 50

    class Block:
        type, text = "text", "OK"

    class Msg:
        content, usage, stop_reason, model = [Block()], Usage(), "end_turn", "claude-opus-4-5"

    class Client:
        class messages:  # noqa: N801
            @staticmethod
            def create(**kwargs):
                return Msg()

    fresh = Telemetry()
    monkeypatch.setattr(telemetry, "telemetry", fresh)
    with TestClient(main.app) as client:
        monkeypatch.setattr(main, "llm_client", Client())
        tok = lambda u, p: client.post("/auth/token", data={"username": u, "password": p}).json()["access_token"]  # noqa: E731
        admin = {"Authorization": f"Bearer {tok('anwalt_a', 'kraft-demo-2026')}"}
        user = {"Authorization": f"Bearer {tok('anwalt_b', 'schuster-demo-2026')}"}
        r = client.post("/generate", headers=user,
                        json={"text_type": "faq", "topic": "Telemetrie-Test", "use_rag": False})
        assert r.status_code == 200
        client.post("/generate", headers=user, json={"text_type": "faq", "topic": "mail an a@b.de", "use_rag": False})
        assert client.get("/admin/metrics", headers=user).status_code == 403
        m = client.get("/admin/metrics", headers=admin).json()
        prom = client.get("/admin/metrics?format=prometheus", headers=admin).text
    assert m["requests_by_status"] == {"ok": 1, "pii_rejected": 1}
    assert m["tokens"] == {"input": 100, "output": 50}
    assert m["cost_usd_total"] == telemetry.cost_usd("claude-opus-4-5", 100, 50)
    assert 'evl_generate_requests_total{status="pii_rejected"} 1' in prom
