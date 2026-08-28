# ADR 0001 — Postgres/pgvector als RAG-Store (statt dedizierter Vektor-DB)

- **Status:** akzeptiert
- **Datum:** 2026-08-28
- **Kontext:** EVL-2026-002 Content-Assistant, Prototyp/Walking Skeleton

## Kontext

Der Legal-RAG-Assistent braucht einen Vektor-Store für ACL-gefilterte
Similarity-Suche (Mandanten-Isolation + Chinese-Wall). Der frühe Prototyp nutzte
einen In-Memory-Store (`InMemoryQdrant`), der pro Worker-Prozess einen eigenen
Zustand hielt: mit `uvicorn --workers 2` sah ein nach `/admin/ingest`
load-balanctes `/generate` auf dem anderen Worker eine leere Wissensbasis.

Kandidaten für einen geteilten Store: dedizierte Vektor-DB (Qdrant, Weaviate)
oder **Postgres + pgvector**.

## Entscheidung

**Postgres/pgvector.**

Gründe:

- **Eine Datenquelle, ein Betriebsmodell.** ACL-Metadaten (`mandant_id`,
  `chinese_wall_exclude`) und Embeddings liegen in derselben Tabelle; der
  ACL-Vorfilter ist ein `WHERE` *vor* der Vektorsortierung — kein Post-Filtering,
  keine Konsistenz zwischen zwei Systemen.
- **On-Premise-Anforderung.** Postgres ist überall reproduzierbar betreibbar
  (Docker-Image `pgvector/pgvector`), ohne zusätzlichen Dienst.
- **Multi-Worker-tauglich** über einen geteilten Server, inkl.
  `psycopg_pool.ConnectionPool`.

### Indizierung (siehe PR `perf/pgvector-indexes`)

- **HNSW** auf `embedding` (`vector_cosine_ops`, passend zum `<=>`-Operator) —
  ohne diesen Index ist jede Suche ein Full Scan; das ist bei zehntausenden
  Dokumenten der erste Engpass.
- **B-Tree** auf `mandant_id` (skalar, `= ANY / IS NULL`).
- **GIN** auf `chinese_wall_exclude` (`TEXT[]`, Overlap-Operator `&&`).
- Regressionstest: `EXPLAIN` mit `enable_seqscan=off` belegt „Index Scan" statt
  „Seq Scan".

## Konsequenzen

- **Positiv:** ein System weniger; ACL und Vektor-Suche transaktional konsistent;
  Standard-Postgres-Tooling (Backup, Migrationen, EXPLAIN).
- **Negativ / Tradeoffs:** pgvector erreicht bei sehr großen Korpora (Millionen
  Vektoren) nicht die spezialisierte Performance/Feature-Tiefe einer dedizierten
  Vektor-DB (z. B. Payload-Sharding, quantisierte Indizes). Für die erwartete
  Größenordnung dieses Assistenten ist das akzeptabel; ein späterer Umstieg
  bleibt möglich, weil die Store-Schnittstelle (`upsert/search/count/clear`)
  abstrahiert ist.
