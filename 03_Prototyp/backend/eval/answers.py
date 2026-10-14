"""
Antwort-Evaluation: echter App-Pfad (generation.retrieve + generation.generate),
bewertet mit DeepEval, RAGAS, einem eigenen Claude-Judge und programmatischen Checks.

Metriken (grade-Schlüssel, erste = Headline):
  fact_coverage        Anteil Pflicht-Fakten in der Antwort                 (programmatisch)
  faithfulness_de      Aussagen der Antwort durch den Kontext gedeckt       (DeepEval)
  faithfulness_ragas   dito, unabhängige Implementierung                    (RAGAS)
  relevancy_de         Antwort geht auf die Frage ein                       (DeepEval)
  context_recall_ragas Musterantwort aus dem Kontext ableitbar              (RAGAS)
  acl_safe             keine Namen gesperrter Mandanten in der Antwort      (programmatisch)
  abstention           enthält sich bei fehlendem/gesperrtem Wissen         (Claude-Judge)
Nicht anwendbare Metriken sind null (z. B. Faithfulness bei Enthaltungsfällen).

Modi (--mode): app (Standard) · oracle (Musterantwort statt App) · null (leere Antwort)
· copy (erster Kontext wörtlich) — oracle/null/copy prüfen den Grader, nicht die App.

Ausgabe: eval/runs/<variant>/results.jsonl, traces/<id>_rep<k>.json, errors.jsonl
Resume: bereits geschriebene (id, rep) werden übersprungen.

Kosten: jeder Lauf im Modus app ruft das App-Modell UND den Judge auf.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from statistics import mean

import anthropic

import generation
import synthetic_docs
from eval.common import EVAL_DIR, Item, build_engine, fact_present, load_items, use_embedder
from eval.judge import ClaudeJudge, JudgeError, deepeval_model, judge_abstention, ragas_llm

RUNS_DIR = EVAL_DIR / "runs"
METRICS = ["fact_coverage", "faithfulness_de", "faithfulness_ragas", "relevancy_de",
           "context_recall_ragas", "acl_safe", "abstention"]
CASE_TIMEOUT_S = 600


def forbidden_names(item: Item) -> list[str]:
    """Mandanten-Namen, die der Nutzer nicht sehen darf und die nicht schon in der Frage stehen."""
    visible = set(item.ctx.effective_allowed())
    names = [n for m, n in synthetic_docs.MANDANTEN.items() if m not in visible]
    return [n for n in names if n.lower() not in item.question.lower()]


def programmatic(item: Item, response: str) -> dict:
    low = response.lower()
    return {
        "fact_coverage": (sum(fact_present(f, response) for f in item.facts) / len(item.facts)) if item.facts else None,
        "acl_safe": float(not any(n.lower() in low for n in forbidden_names(item))),
    }


def judged(item: Item, response: str, contexts: list[str], judge: ClaudeJudge) -> tuple[dict, dict]:
    from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric
    from deepeval.test_case import LLMTestCase
    from ragas.metrics.collections import ContextRecall, Faithfulness

    scores: dict = {k: None for k in ("faithfulness_de", "faithfulness_ragas", "relevancy_de",
                                      "context_recall_ragas", "abstention")}
    why: dict = {}
    if not item.answerable:
        v = judge_abstention(judge, item.question, response)
        scores["abstention"] = float(v.abstains and not v.invents_specifics)
        why["abstention"] = v.reason
        return scores, why
    if not response.strip():
        # Leere Antwort: Faithfulness wäre trivial 1.0 (keine Aussagen) — bewusst nicht bewertet.
        scores["relevancy_de"] = 0.0
        return scores, why

    model = deepeval_model(judge)
    tc = LLMTestCase(input=item.question, actual_output=response, retrieval_context=contexts or ["(kein Kontext)"])
    # penalize_ambiguous_claims: Default-DeepEval zählt nur WIDERSPRÜCHE als untreu — eine Aussage,
    # die im Kontext schlicht fehlt ("idk"), gälte als treu. Grader-Check (oracle L01/M01) hat
    # das gezeigt; für Halluzinationserkennung muss "nicht belegt" zählen.
    for key, metric in (("faithfulness_de", FaithfulnessMetric(model=model, async_mode=False,
                                                                penalize_ambiguous_claims=True)),
                        ("relevancy_de", AnswerRelevancyMetric(model=model, async_mode=False))):
        metric.measure(tc)
        if metric.error:
            raise JudgeError(f"{key}: {metric.error}")
        scores[key], why[key] = float(metric.score), metric.reason

    llm = ragas_llm(judge)
    ctx = contexts or ["(kein Kontext)"]
    scores["faithfulness_ragas"] = _ragas_value(
        Faithfulness(llm=llm).score(user_input=item.question, response=response, retrieved_contexts=ctx))
    scores["context_recall_ragas"] = _ragas_value(
        ContextRecall(llm=llm).score(user_input=item.question, retrieved_contexts=ctx, reference=item.reference))
    return scores, why


def _ragas_value(result) -> float | None:
    v = getattr(result, "value", result)
    return None if v is None or (isinstance(v, float) and math.isnan(v)) else float(v)


class Runner:
    def __init__(self, variant: str, mode: str, reps: int, judge_model: str | None, embedder: str):
        self.dir = RUNS_DIR / variant
        (self.dir / "traces").mkdir(parents=True, exist_ok=True)
        self.mode, self.reps, self.judge_model = mode, reps, judge_model
        self._lock = threading.Lock()
        use_embedder(embedder)
        self.rag, self.store = build_engine()
        self.client = anthropic.Anthropic(max_retries=4)  # SDK: jittered backoff auf 429/5xx

    def done(self) -> set[tuple[str, int]]:
        path = self.dir / "results.jsonl"
        if not path.exists():
            return set()
        return {(r["prompt_id"], r["rep"]) for r in map(json.loads, path.read_text(encoding="utf-8").splitlines())}

    def _append(self, name: str, row: dict) -> None:
        with self._lock, open(self.dir / name, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    def run_case(self, item: Item, rep: int) -> None:
        t0 = time.perf_counter()
        retrieval = generation.retrieve(self.rag, self.store.count(), item.ctx, item.question, top_k=5)
        gen = None
        if self.mode == "app":
            gen = generation.generate(self.client, retrieval, item.text_type, item.question, use_cache=False)
            requested = generation.model_name()
            if gen.served_model and not gen.served_model.startswith(requested):
                raise RuntimeError(f"served-model mismatch: {gen.served_model} != {requested}")
            response = gen.result
        elif self.mode == "oracle":
            response = item.reference
        elif self.mode == "copy":
            response = retrieval.contexts[0] if retrieval.contexts else ""
        else:
            response = ""
        latency_s = time.perf_counter() - t0

        judge = ClaudeJudge(self.judge_model, client=self.client)
        grade = programmatic(item, response)
        scores, why = judged(item, response, retrieval.contexts, judge)
        grade.update(scores)

        status = "truncated" if gen and gen.stop_reason == "max_tokens" else "ok"
        system, user_prompt = generation.build_prompt(item.text_type, item.question, retrieval.contexts)
        trace = [{"role": "system", "content": system}, {"role": "user", "content": user_prompt},
                 {"role": "assistant", "content": response}]
        (self.dir / "traces" / f"{item.id}_rep{rep}.json").write_text(
            json.dumps(trace, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")
        self._append("results.jsonl", {
            "prompt_id": item.id, "rep": rep, "prompt": item.question, "tags": [item.group, item.user],
            "mode": self.mode, "status": status, "stop_reason": gen.stop_reason if gen else None,
            "grade": {k: grade.get(k) for k in METRICS}, "explanation": why,
            "model": gen.served_model if gen else None,
            "usage": {"input_tokens": gen.input_tokens, "output_tokens": gen.output_tokens} if gen else None,
            "judge_model": judge.model, "judge_usage": judge.usage,
            "latency_s": round(latency_s, 2), "retrieval_ms": round(retrieval.latency_ms, 1),
            "contexts": len(retrieval.contexts),
        })

    def run(self, items: list[Item], workers: int) -> None:
        done = self.done()
        todo = [(i, r) for i in items for r in range(self.reps) if (i.id, r) not in done]
        print(f"{len(todo)} Fälle offen ({self.mode}) → {self.dir}")
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(self.run_case, i, r): (i, r) for i, r in todo}
            for fut, (item, rep) in futures.items():
                try:
                    fut.result(timeout=CASE_TIMEOUT_S)
                    print(f"  ✓ {item.id}#{rep}")
                except FutureTimeout:
                    self._error(item, rep, "timeout", f">{CASE_TIMEOUT_S}s")
                except JudgeError as exc:
                    self._error(item, rep, "judge_error", str(exc))
                except anthropic.APIError as exc:
                    self._error(item, rep, "api_error", str(exc))
                except Exception as exc:  # noqa: BLE001 — Harness-Fehler nie als Modell-Null werten
                    self._error(item, rep, "harness_error", f"{type(exc).__name__}: {exc}")

    def _error(self, item: Item, rep: int, kind: str, detail: str) -> None:
        print(f"  ✗ {item.id}#{rep} {kind}: {detail[:200]}", file=sys.stderr)
        self._append("errors.jsonl", {"prompt_id": item.id, "rep": rep, "failure_class": kind,
                                      "detail": detail[:2000], "at": time.strftime("%Y-%m-%dT%H:%M:%S")})


def summarize(variant: str) -> dict:
    """Mittelwerte je Metrik über status=ok-Zeilen, mit grobem 95 %-Intervall."""
    path = RUNS_DIR / variant / "results.jsonl"
    rows = [r for r in map(json.loads, path.read_text(encoding="utf-8").splitlines()) if r["status"] == "ok"]
    out: dict = {"n_rows": len(rows)}
    for m in METRICS:
        vals = [r["grade"][m] for r in rows if r["grade"].get(m) is not None]
        if not vals:
            continue
        mu = mean(vals)
        sd = (sum((v - mu) ** 2 for v in vals) / (len(vals) - 1)) ** 0.5 if len(vals) > 1 else 0.0
        out[m] = {"mean": round(mu, 3), "ci95": round(1.96 * sd / len(vals) ** 0.5, 3), "n": len(vals)}
    errors = RUNS_DIR / variant / "errors.jsonl"
    out["errors"] = len(errors.read_text(encoding="utf-8").splitlines()) if errors.exists() else 0
    usage = [r["usage"] for r in rows if r.get("usage")]
    out["app_tokens"] = {k: sum(u[k] for u in usage) for k in ("input_tokens", "output_tokens")} if usage else None
    out["judge_tokens"] = {k: sum(r["judge_usage"][k] for r in rows) for k in ("input_tokens", "output_tokens", "calls")}
    return out


def regrade(variant: str) -> int:
    """Programmatische Metriken aus den gespeicherten Antworten neu berechnen (kein API-Aufruf).

    Nach jeder Änderung an einem programmatischen Grader für ALLE Varianten ausführen —
    sonst vergleicht man Scores von zwei verschiedenen Gradern.
    """
    items = {i.id: i for i in load_items()}
    run = RUNS_DIR / variant
    rows = [json.loads(line) for line in (run / "results.jsonl").read_text(encoding="utf-8").splitlines()]
    for row in rows:
        trace = json.loads((run / "traces" / f"{row['prompt_id']}_rep{row['rep']}.json").read_text(encoding="utf-8"))
        row["grade"].update(programmatic(items[row["prompt_id"]], trace[-1]["content"]))
    (run / "results.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows),
                                       encoding="utf-8", newline="\n")
    return len(rows)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--variant", default="baseline")
    ap.add_argument("--mode", choices=["app", "oracle", "null", "copy"], default="app")
    ap.add_argument("--reps", type=int, default=1)
    ap.add_argument("--ids", help="Komma-getrennte IDs (Pilot)")
    ap.add_argument("--judge-model", default=None)
    ap.add_argument("--embedder", choices=["hash", "e5"], default="e5")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--summary-only", action="store_true")
    ap.add_argument("--regrade", action="store_true", help="programmatische Metriken neu berechnen")
    args = ap.parse_args(argv)

    if args.regrade:
        print(f"{regrade(args.variant)} Zeilen neu bewertet")
    elif not args.summary_only:
        items = load_items()
        if args.ids:
            wanted = set(args.ids.split(","))
            items = [i for i in items if i.id in wanted]
        if not os.getenv("ANTHROPIC_API_KEY"):
            print("ANTHROPIC_API_KEY fehlt.", file=sys.stderr)
            return 2
        Runner(args.variant, args.mode, args.reps, args.judge_model, args.embedder).run(items, args.workers)
    print(json.dumps(summarize(args.variant), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
