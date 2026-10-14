"""
RAG-Generierung als eigenständiges Modul.

Vorher lebte dieser Pfad inline in main.generate_text. Herausgelöst, damit
API, Offline-Evaluation (eval/) und Telemetrie exakt denselben Code-Pfad nutzen:
was die Evaluation misst, ist das, was der Endpoint ausliefert.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field, replace

import anthropic

import redis_backend
from acl import UserContext
from prompts import TEMPLATES
from rag_engine import LegalRAGEngine, QueryResult

DEFAULT_MODEL = "claude-opus-4-5"
NO_CONTEXT_FALLBACK = (
    "Kein spezifisches Firmenwissen verfügbar. "
    "Allgemeines Branchenwissen verwenden und darauf hinweisen, "
    "dass der Text mit unternehmensspezifischen Informationen ergänzt werden sollte."
)


@dataclass
class Retrieval:
    contexts: list[str]          # exakt die Texte, die das LLM als Kontext sieht
    results: list[QueryResult]   # alle Treffer inkl. ACL-Audit-Status
    latency_ms: float = 0.0


@dataclass
class Generation:
    result: str
    label: str
    retrieval: Retrieval
    model: str
    cache_hit: bool
    llm_latency_ms: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    stop_reason: str = ""
    served_model: str = ""          # Modell laut API-Antwort (kann von `model` abweichen)
    extra: dict = field(default_factory=dict)

    @property
    def chunks_used(self) -> int:
        return len(self.retrieval.contexts)


def model_name() -> str:
    return os.getenv("LLM_MODEL", DEFAULT_MODEL)


def retrieve(rag: LegalRAGEngine | None, store_count: int, user: UserContext, topic: str,
             target_mandant: str | None = None, top_k: int = 5) -> Retrieval:
    """ACL-geschütztes Retrieval. target_mandant engt nur ein, erweitert nie."""
    if rag is None or store_count == 0:
        return Retrieval([], [])
    effective_user = user
    if target_mandant and target_mandant in user.effective_allowed():
        effective_user = replace(user, allowed_mandate=[target_mandant])
    t0 = time.perf_counter()
    results = rag.query(effective_user, topic, top_k=top_k)
    latency = (time.perf_counter() - t0) * 1000
    return Retrieval([r.excerpt for r in results if r.acl_valid], results, latency)


def build_prompt(text_type: str, topic: str, contexts: list[str]) -> tuple[str, str]:
    """(system, user_prompt) für ein Template."""
    template = TEMPLATES[text_type]
    context = "\n\n---\n\n".join(contexts) if contexts else NO_CONTEXT_FALLBACK
    return template["system"], template["user_template"].format(context=context, topic=topic)


def generate(llm_client: anthropic.Anthropic, retrieval: Retrieval, text_type: str, topic: str,
             model: str | None = None, use_cache: bool = True) -> Generation:
    """LLM-Aufruf mit Redis-Cache. Wirft anthropic.APIStatusError weiter."""
    model = model or model_name()
    system, user_prompt = build_prompt(text_type, topic, retrieval.contexts)
    # Cache-Key ueber alle preisbestimmenden Eingaben (Modell, System, Prompt inkl.
    # ACL-gefiltertem RAG-Kontext) → nur identischer Input teilt einen Eintrag.
    ck = redis_backend.cache_key(model, system, user_prompt)
    cached = redis_backend.cache_get(ck) if use_cache else None
    label = TEMPLATES[text_type]["label"]
    if cached is not None:
        return Generation(cached, label, retrieval, model, cache_hit=True)

    t0 = time.perf_counter()
    message = llm_client.messages.create(
        model=model,
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
    )
    llm_ms = (time.perf_counter() - t0) * 1000
    # Nur Text-Blöcke: neuere Modelle (Opus 5.5+) liefern zuerst einen thinking-Block,
    # content[0].text wäre dort ein AttributeError.
    text = "".join(b.text for b in message.content if getattr(b, "type", "text") == "text")
    if use_cache:
        redis_backend.cache_set(ck, text)
    usage = getattr(message, "usage", None)
    return Generation(
        text, label, retrieval, model, cache_hit=False, llm_latency_ms=llm_ms,
        input_tokens=getattr(usage, "input_tokens", 0) or 0,
        output_tokens=getattr(usage, "output_tokens", 0) or 0,
        stop_reason=getattr(message, "stop_reason", "") or "",
        served_model=getattr(message, "model", "") or "",
    )
