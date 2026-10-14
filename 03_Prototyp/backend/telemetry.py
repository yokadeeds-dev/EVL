"""
Telemetrie für /generate: Latenz, Tokens, Kosten, Cache, Ergebnisstatus — plus SLO-Auswertung.

Datenschutz: Es wird NIE der Nutzer-Input (topic) oder die Antwort geloggt, nur Metadaten.
Das Log ist eine JSON-Zeile pro Anfrage (Logger "evl.telemetry") und kann direkt von
Loki/Elastic/Dynatrace-Log-Ingest gelesen werden.

Grenze (bewusst, siehe ADR 0002/0004): Die Aggregate liegen im Prozess. Bei mehreren
Uvicorn-Workern sieht /admin/metrics nur den eigenen Worker — für Produktion die JSON-Logs
zentral aggregieren oder OpenTelemetry mit Collector anbinden.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import Counter, deque
from dataclasses import asdict, dataclass

log = logging.getLogger("evl.telemetry")

# USD pro 1 Mio. Tokens (input, output) — Stand 2026-10, Anthropic First-Party-API.
PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-4-5": (5.0, 25.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-haiku-4-5": (1.0, 5.0),
}


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    price = PRICES.get(model)
    if price is None:
        return None
    return round(input_tokens / 1e6 * price[0] + output_tokens / 1e6 * price[1], 6)


@dataclass
class RequestEvent:
    status: str                  # ok | llm_error | pii_rejected | rate_limited | error
    text_type: str = ""
    user_id: str = ""
    model: str = ""
    total_ms: float = 0.0
    retrieval_ms: float = 0.0
    llm_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float | None = None
    cache_hit: bool = False
    context_chunks: int = 0
    ts: float = 0.0


@dataclass
class SLO:
    name: str
    target: float
    description: str


# Zielwerte aus der Messung abgeleitet (eval/RESULTS.md, 25 Anfragen, 5 parallel, claude-opus-4-5):
# Gesamtlatenz p95 ≈ 6 s, Retrieval p95 ≈ 140 ms (e5 auf CPU) → SLO mit ~1,7× bzw. ~2× Puffer.
SLOS = [
    SLO("availability", float(os.getenv("SLO_AVAILABILITY", "0.99")),
        "Anteil /generate-Anfragen ohne Server-/LLM-Fehler (4xx durch Nutzereingaben zählen nicht)"),
    SLO("latency_p95_ms", float(os.getenv("SLO_LATENCY_P95_MS", "10000")),
        "95. Perzentil der Gesamtlatenz erfolgreicher Anfragen"),
    SLO("retrieval_p95_ms", float(os.getenv("SLO_RETRIEVAL_P95_MS", "300")),
        "95. Perzentil der Retrieval-Latenz"),
]


def _percentile(values: list[float], p: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = max(0, min(len(s) - 1, round(p / 100 * (len(s) - 1))))
    return round(s[k], 1)


class Telemetry:
    def __init__(self, window: int = 1000):
        self._lock = threading.Lock()
        self._events: deque[RequestEvent] = deque(maxlen=window)  # gleitendes Fenster für Perzentile
        self._status = Counter()
        self._tokens = Counter()
        self._cost = 0.0
        self._cache_hits = 0
        self.started = time.time()

    def record(self, event: RequestEvent) -> None:
        event.ts = event.ts or time.time()
        with self._lock:
            self._events.append(event)
            self._status[event.status] += 1
            self._tokens["input"] += event.input_tokens
            self._tokens["output"] += event.output_tokens
            self._cost += event.cost_usd or 0.0
            self._cache_hits += event.cache_hit
        log.info(json.dumps({"event": "generate", **asdict(event)}, ensure_ascii=False))

    def snapshot(self) -> dict:
        with self._lock:
            events = list(self._events)
            status = dict(self._status)
            tokens, cost, hits = dict(self._tokens), self._cost, self._cache_hits
        ok = [e for e in events if e.status == "ok"]
        server_side = [e for e in events if e.status in ("ok", "llm_error", "error")]
        availability = (sum(e.status == "ok" for e in server_side) / len(server_side)) if server_side else None
        values = {
            "availability": availability,
            "latency_p95_ms": _percentile([e.total_ms for e in ok], 95),
            "retrieval_p95_ms": _percentile([e.retrieval_ms for e in ok if e.context_chunks or e.retrieval_ms], 95),
        }
        slo = {}
        for s in SLOS:
            v = values[s.name]
            met = None if v is None else (v >= s.target if s.name == "availability" else v <= s.target)
            slo[s.name] = {"target": s.target, "value": v, "met": met, "description": s.description}
        total = sum(status.values())
        return {
            "uptime_s": round(time.time() - self.started),
            "requests_total": total,
            "requests_by_status": status,
            "latency_ms": {"p50": _percentile([e.total_ms for e in ok], 50),
                           "p95": values["latency_p95_ms"],
                           "llm_p95": _percentile([e.llm_ms for e in ok if not e.cache_hit], 95),
                           "retrieval_p95": values["retrieval_p95_ms"]},
            "tokens": tokens,
            "cost_usd_total": round(cost, 6),
            "cost_usd_per_request": round(cost / len(ok), 6) if ok else None,
            "cache_hit_rate": round(hits / total, 3) if total else None,
            "window_size": len(events),
            "slo": slo,
        }

    def prometheus(self) -> str:
        s = self.snapshot()
        lines = ["# TYPE evl_generate_requests_total counter"]
        for st, n in sorted(s["requests_by_status"].items()):
            lines.append(f'evl_generate_requests_total{{status="{st}"}} {n}')
        lines += ["# TYPE evl_llm_tokens_total counter"]
        for kind, n in sorted(s["tokens"].items()):
            lines.append(f'evl_llm_tokens_total{{kind="{kind}"}} {n}')
        lines += ["# TYPE evl_llm_cost_usd_total counter", f"evl_llm_cost_usd_total {s['cost_usd_total']}",
                  "# TYPE evl_generate_latency_ms gauge"]
        for q, key in (("0.5", "p50"), ("0.95", "p95")):
            if s["latency_ms"][key] is not None:
                lines.append(f'evl_generate_latency_ms{{quantile="{q}"}} {s["latency_ms"][key]}')
        lines.append("# TYPE evl_slo_met gauge")
        for name, v in s["slo"].items():
            if v["met"] is not None:
                lines.append(f'evl_slo_met{{slo="{name}"}} {int(v["met"])}')
        return "\n".join(lines) + "\n"


telemetry = Telemetry()
