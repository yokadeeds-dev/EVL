"""
CI-Gate: Retrieval-Qualität darf gegenüber eval/baseline_hash.json nicht sinken,
und kein Treffer darf die ACL/Chinese Wall verletzen.

Läuft mit dem deterministischen Hash-Embedder (kein Modell-Download, kein API-Key).
Bewusste Verbesserungen: `python -m eval.retrieval --update-baseline` und die neue
Baseline mit committen — so ist jede Qualitätsänderung im PR-Diff sichtbar.
"""

import json

from eval import retrieval
from eval.common import EVAL_DIR


def test_retrieval_has_no_regression_and_no_acl_leak():
    summary, scores = retrieval.run("hash")
    baseline = json.loads((EVAL_DIR / "baseline_hash.json").read_text(encoding="utf-8"))
    problems = retrieval.compare(summary, baseline)
    assert not problems, "\n" + "\n".join(problems) + "\n\n" + retrieval.report_markdown(summary, scores, "hash")


def test_acl_negative_items_never_retrieve_forbidden_mandates():
    _, scores = retrieval.run("hash")
    for s in scores:
        if s.group == "acl_negativ":
            assert s.acl_leaks == 0, s
