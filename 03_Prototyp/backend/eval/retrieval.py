"""
Retrieval-Evaluation — deterministisch, ohne LLM, ohne API-Key.

Misst für jede Frage des Golden Sets genau das, was der /generate-Endpoint als
Kontext an das LLM gibt (generation.retrieve):

  hit@k            mindestens ein relevantes Dokument unter den Top-k
  precision@k      relevante Treffer / min(k, Anzahl relevanter Dokumente im Korpus)
                   (normalisiert: bei nur einem relevanten Dokument ist 1/1 erreichbar, nicht 1/5)
  mrr              1 / Rang des ersten relevanten Treffers
  fact_recall      Anteil der Pflicht-Fakten, die im LLM-Kontext tatsächlich stehen
  acl_leaks        Treffer, die der Nutzer nicht sehen darf (muss 0 sein)

Aufruf:
  python -m eval.retrieval                      # Hash-Embedder (wie CI)
  python -m eval.retrieval --embedder e5        # echtes Modell (lädt ~450 MB)
  python -m eval.retrieval --update-baseline    # Baseline neu schreiben (bewusst!)
Exit-Code 1 bei Regression gegenüber eval/baseline_<embedder>.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean

import generation
from eval.common import EVAL_DIR, Item, build_engine, fact_present, load_items, use_embedder

TOP_K = 5
TOLERANCE = 0.02  # erlaubte Verschlechterung je Kennzahl (absolut), Rauschen bei Retrieval = 0
GATED = ("hit_at_k", "precision_at_k", "mrr", "fact_recall")


@dataclass
class ItemScore:
    id: str
    group: str
    hit_at_k: float | None
    precision_at_k: float | None
    mrr: float | None
    fact_recall: float | None
    acl_leaks: int
    retrieved: list[str]


def score_item(item: Item, rag, store) -> ItemScore:
    store_count = store.count()
    retrieval = generation.retrieve(rag, store_count, item.ctx, item.question, top_k=TOP_K)
    results = retrieval.results
    user = item.ctx
    leaks = sum(1 for r in results if r.mandant_id is not None and not user.can_see_mandant(r.mandant_id))
    leaks += sum(1 for r in results if r.mandant_id in item.forbidden_mandates)

    hit = prec = rr = None
    if item.answerable:
        flags = [item.is_relevant(r) for r in results]
        hit = float(any(flags))
        n_relevant = sum(1 for d in store._store.values() if item.is_relevant(d))
        prec = sum(flags) / min(TOP_K, n_relevant) if n_relevant else 0.0
        rr = next((1 / (i + 1) for i, f in enumerate(flags) if f), 0.0)

    fact_recall = None
    if item.facts:
        context = "\n".join(retrieval.contexts)
        fact_recall = sum(fact_present(f, context) for f in item.facts) / len(item.facts)

    return ItemScore(item.id, item.group, hit, prec, rr, fact_recall, leaks,
                     [f"{r.title} [{r.mandant_id or 'öffentlich'}]" for r in results])


def aggregate(scores: list[ItemScore]) -> dict:
    def avg(attr: str, subset: list[ItemScore]) -> float | None:
        vals = [getattr(s, attr) for s in subset if getattr(s, attr) is not None]
        return round(mean(vals), 4) if vals else None

    out = {k: avg(k, scores) for k in GATED}
    out["acl_leaks"] = sum(s.acl_leaks for s in scores)
    out["n_items"] = len(scores)
    out["by_group"] = {
        g: {k: avg(k, [s for s in scores if s.group == g]) for k in GATED}
        for g in sorted({s.group for s in scores})
    }
    return out


def run(embedder: str = "hash") -> tuple[dict, list[ItemScore]]:
    use_embedder(embedder)
    rag, store = build_engine()
    scores = [score_item(i, rag, store) for i in load_items()]
    return aggregate(scores), scores


def compare(current: dict, baseline: dict) -> list[str]:
    """Liste der Regressionen (leer = ok)."""
    problems = []
    if current["acl_leaks"] > 0:
        problems.append(f"ACL-Leaks: {current['acl_leaks']} (erlaubt: 0)")
    for key in GATED:
        cur, base = current.get(key), baseline.get(key)
        if cur is not None and base is not None and cur < base - TOLERANCE:
            problems.append(f"{key}: {cur:.4f} < Baseline {base:.4f} (Toleranz {TOLERANCE})")
    return problems


def report_markdown(summary: dict, scores: list[ItemScore], embedder: str) -> str:
    def f(v):
        return "–" if v is None else f"{v:.2f}"

    lines = [f"### Retrieval-Evaluation · Embedder `{embedder}` · top_k={TOP_K}", "",
             "| Gruppe | hit@k | precision@k | MRR | Fakten im Kontext |", "|---|---:|---:|---:|---:|"]
    for g, m in summary["by_group"].items():
        lines.append(f"| {g} | {f(m['hit_at_k'])} | {f(m['precision_at_k'])} | {f(m['mrr'])} | {f(m['fact_recall'])} |")
    lines.append(f"| **gesamt** | **{f(summary['hit_at_k'])}** | **{f(summary['precision_at_k'])}** | "
                 f"**{f(summary['mrr'])}** | **{f(summary['fact_recall'])}** |")
    lines += ["", f"ACL-Leaks: **{summary['acl_leaks']}** · Fragen: {summary['n_items']}", "",
              "<details><summary>Pro Frage</summary>", "",
              "| ID | hit | MRR | Fakten | Top-1 |", "|---|---:|---:|---:|---|"]
    for s in scores:
        lines.append(f"| {s.id} | {f(s.hit_at_k)} | {f(s.mrr)} | {f(s.fact_recall)} | "
                     f"{s.retrieved[0] if s.retrieved else '–'} |")
    lines += ["", "</details>"]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--embedder", choices=["hash", "e5"], default="hash")
    ap.add_argument("--update-baseline", action="store_true")
    ap.add_argument("--json", type=Path, help="Ergebnis zusätzlich als JSON schreiben")
    args = ap.parse_args(argv)

    summary, scores = run(args.embedder)
    print(report_markdown(summary, scores, args.embedder))
    if args.json:
        args.json.write_text(json.dumps({"summary": summary, "items": [asdict(s) for s in scores]},
                                        ensure_ascii=False, indent=2), encoding="utf-8")

    baseline_path = EVAL_DIR / f"baseline_{args.embedder}.json"
    if args.update_baseline:
        baseline_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
                                 newline="\n")
        print(f"\nBaseline geschrieben: {baseline_path.name}")
        return 0
    if not baseline_path.exists():
        print(f"\nKeine Baseline {baseline_path.name} – mit --update-baseline anlegen.")
        return 0
    problems = compare(summary, json.loads(baseline_path.read_text(encoding="utf-8")))
    for p in problems:
        print(f"REGRESSION: {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
