"""Offline-Tests des Antwort-Runners (keine API-Aufrufe): programmatische Grader + Aggregation."""

import json

from eval import answers
from eval.common import load_items

ITEMS = {i.id: i for i in load_items()}


def test_fact_coverage_is_case_insensitive_and_partial():
    g = answers.programmatic(ITEMS["L02"], "Bitte binnen 2 STUNDEN melden.")
    assert g["fact_coverage"] == 0.5  # "2 Stunden" ja, "Datenschutzbeauftragte" nein


def test_fact_coverage_null_when_item_has_no_facts():
    assert answers.programmatic(ITEMS["M01"], "irgendwas")["fact_coverage"] is None


def test_acl_safe_flags_forbidden_client_name():
    # anwalt_a darf M002 (DigitalVentures GmbH) nicht sehen
    assert answers.programmatic(ITEMS["L01"], "Wie bei DigitalVentures GmbH ...")["acl_safe"] == 0.0
    assert answers.programmatic(ITEMS["L01"], "Wie bei TechCorp AG ...")["acl_safe"] == 1.0


def test_name_from_the_question_itself_is_not_a_leak():
    # X01 fragt selbst nach DigitalVentures — das Echo des Namens ist kein Leak
    assert "DigitalVentures GmbH" not in answers.forbidden_names(ITEMS["X01"])


def test_summary_ignores_truncated_rows_and_nulls(tmp_path, monkeypatch):
    monkeypatch.setattr(answers, "RUNS_DIR", tmp_path)
    (tmp_path / "v").mkdir()
    rows = [
        {"status": "ok", "grade": {"fact_coverage": 1.0, "acl_safe": 1.0}, "judge_usage": {"input_tokens": 1, "output_tokens": 1, "calls": 1}},
        {"status": "ok", "grade": {"fact_coverage": 0.0, "acl_safe": 1.0}, "judge_usage": {"input_tokens": 1, "output_tokens": 1, "calls": 1}},
        {"status": "truncated", "grade": {"fact_coverage": 0.0}, "judge_usage": {"input_tokens": 1, "output_tokens": 1, "calls": 1}},
        {"status": "ok", "grade": {"fact_coverage": None, "acl_safe": 1.0}, "judge_usage": {"input_tokens": 1, "output_tokens": 1, "calls": 1}},
    ]
    (tmp_path / "v" / "results.jsonl").write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    s = answers.summarize("v")
    assert s["n_rows"] == 3 and s["fact_coverage"]["mean"] == 0.5 and s["fact_coverage"]["n"] == 2
    assert s["acl_safe"]["mean"] == 1.0 and s["errors"] == 0


def test_fact_matching_tolerates_formatting_variants():
    from eval.common import fact_present

    # Regression: "50 %" (mit Leerzeichen) wurde als fehlender Fakt "50%" gewertet
    assert fact_present("50%", "Reisezeiten werden zu 50 % abgerechnet.")
    assert fact_present("450 EUR", "Partner: 450 € pro Stunde") and fact_present("450 EUR", "450 Euro")
    assert not fact_present("450 EUR", "4500 EUR")
    # Alternativen: korrekte Umformulierung darf nicht durchfallen
    assert fact_present(["im System einzutragen", "Fallverwaltungssystem einzutragen"],
                        "im Fallverwaltungssystem einzutragen")
