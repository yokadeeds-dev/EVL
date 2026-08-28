# ADR 0002 — Bewusst zurückgestellte Produktionsthemen (Prototyp-Scope)

- **Status:** akzeptiert
- **Datum:** 2026-08-28
- **Kontext:** EVL-2026-002 ist ein Walking Skeleton / Nachweis-Prototyp, kein
  produktiv betriebenes System.

## Kontext

Ein Architektur-Review nannte mehrere Produktionsthemen (Observability,
Circuit-Breaker, asynchrone Job-Queues, Auto-Deploy). Diese sind real und richtig
— aber nicht jedes gehört in den Prototyp-Scope. Diese Entscheidung hält fest,
**was bewusst zurückgestellt wird und warum**. Bewusst gewählte Schulden schlagen
unbewusste: die Lücken sind bekannt und benannt, nicht übersehen.

## Entscheidung: zurückgestellt (mit Trigger für die Umsetzung)

| Thema | Warum jetzt nicht | Trigger für Umsetzung |
|-------|-------------------|-----------------------|
| **Observability** (OpenTelemetry, Prometheus, SLOs) | Größter realer Gap, aber ohne Produktionslast kein Messwert. | Erster echter Betrieb / Pilot mit Nutzerlast. |
| **Circuit-Breaker vor dem LLM** | Der Anthropic-SDK retryt bereits (`max_retries`); Fehler werden als 502 sauber durchgereicht. Ein echter Breaker (z. B. `pybreaker`, **nicht** `tenacity` — das ist Retry, kein Breaker) lohnt erst bei echter Ausfall-Resilienz-Anforderung. | Wiederkehrende LLM-Ausfälle / Latenz-SLO verletzt. |
| **Asynchrone Job-Queue** (Redis Streams, Background-Worker) | `/generate` ist synchron und für den Prototyp schnell genug; Queue-Infra erhöht die Komplexität ohne aktuellen Bedarf. | Lange Ingest-/Batch-Jobs oder Priorisierung (Admin-Queries first). |
| **Automatischer Deploy** | CI baut & scannt Images; der Deploy-Job ist ein Approval-Gate-Gerüst. Auto-Deploy braucht ein reales Zielsystem. | Definiertes Zielsystem (Server/K8s) steht fest. |

## Nicht zurückgestellt (bereits umgesetzt)

- Auth mit echter Passwort-Verifikation (pbkdf2, Konstantzeit).
- ACL / Chinese-Wall als `WHERE`-Vorfilter; nachgelagerte `validate_result`-Ebene.
- Atomares Rate-Limiting (Redis-Lua, TOCTOU-frei) mit In-Memory-Fallback.
- Connection-Pooling (`psycopg_pool`) — war bereits vorhanden.
- Vektor- und ACL-Indizes (ADR 0001).
- CI-Gates: ruff, `tsc`, Tests, CodeQL, Trivy.

## Konsequenzen

Der Prototyp bleibt schlank und schnell verständlich; die Produktions-Roadmap ist
explizit dokumentiert statt implizit. Wer das Repo bewertet, sieht Umfang **und**
das Bewusstsein über die Grenzen des Umfangs.
