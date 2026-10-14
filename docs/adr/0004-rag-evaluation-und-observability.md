# ADR 0004 — RAG-Evaluation und Observability

- **Status:** akzeptiert
- **Datum:** 2026-10-14
- **Kontext:** EVL-2026-002 · löst den Observability-Punkt aus ADR 0002 teilweise ein

## Kontext

Bis hier gab es Tests für Auth, ACL, Store und Cache — aber keine Aussage darüber, ob die
**Antworten** stimmen. Ein RAG-System kann jeden Unit-Test bestehen und trotzdem falsche
oder unbelegte Antworten liefern. Genau das hat die erste Messung gezeigt
([eval/RESULTS.md](../../03_Prototyp/backend/eval/RESULTS.md)).

## Entscheidung

**Drei Ebenen, getrennt nach Kosten und Häufigkeit:**

| Ebene | Was | Wann | Kosten |
|---|---|---|---|
| Retrieval-Gate | hit@k, Precision, MRR, Fakten-im-Kontext, ACL-Leaks (`eval/retrieval.py`) | jede CI, Hash-Embedder | 0 |
| Red-Team-Gate | 6 ACL-Angriffe + PII-Abweisung (`eval/redteam.py`) | jede CI | 0 |
| Antwort-Evaluation | DeepEval + RAGAS + Claude-Judge (`eval/answers.py`) | manuell / vor Releases, Workflow `eval.yml` | ~$1,90 je Lauf |

Weitere Festlegungen:

- **Messen über den echten App-Pfad.** `generation.py` wurde aus `main.py` herausgelöst; Evaluation
  und Endpoint teilen denselben Code — keine nachgebaute Pipeline, die etwas anderes misst.
- **Zwei Frameworks für Faithfulness** (DeepEval und RAGAS) als gegenseitige Kalibrierung;
  große Abweichungen markieren Fälle für manuelle Prüfung.
- **Eigener Judge-Adapter** über structured outputs statt der eingebauten Anthropic-Anbindungen
  beider Frameworks (forced `tool_choice` / `temperature` → HTTP 400 bei aktuellen Modellen).
- **Judge `claude-sonnet-5-5`**, nicht das App-Modell; ohne Refusal-Fallback, damit kein stiller
  Modellwechsel die Scores verzerrt.
- **Grader vor dem Modell prüfen**: Oracle-, Null- und Copy-Läufe vor jedem Vergleich; nach jeder
  Grader-Änderung alle Varianten neu bewerten (`--regrade`).
- **Baselines im Repo**: Qualitätsänderungen sind im PR-Diff von `eval/baseline_*.json` sichtbar.
- **Telemetrie ohne Inhalte**: `/admin/metrics` und JSON-Logs enthalten Latenz, Tokens, Kosten,
  Status — nie Nutzer-Input oder Antworttext.

## Verworfen

- **Nur ein Framework**: einfacher, aber ohne Kalibrierung. Der Default von DeepEval-Faithfulness hätte
  unbelegte Aussagen als treu gewertet — erst der Vergleich mit RAGAS hat das sichtbar gemacht.
- **Antwort-Evaluation in jeder CI**: ~$1,90 und ~3,5 Minuten pro PR, Secret-Pflicht in Forks;
  das deterministische Gate fängt die häufigsten Regressionen kostenlos.
- **e5 im CI-Gate**: realistischer, aber ~450 MB Modell + Torch pro Lauf. Hash-Embedder als
  Proxy; e5-Zahlen im manuellen Lauf.

## Konsequenzen

- Jede Änderung an Retrieval oder Prompts hat jetzt eine Zahl. Die Kontextkürzung (200 Zeichen)
  und die Übertragung fremder Vertragsdaten wären ohne Evaluation unbemerkt geblieben.
- Offene Grenzen (25 Fragen, ein Durchlauf, synthetischer Korpus, Judge aus derselben
  Modellfamilie) sind in `eval/RESULTS.md` benannt.
- Telemetrie-Aggregate sind pro Worker; für Multi-Worker-Betrieb bleibt der Trigger aus ADR 0002
  (zentrale Logs / OpenTelemetry) bestehen.
