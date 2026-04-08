# Konzept · EVL-2026-002
**Version:** 1.0 | **Datum:** 2026-04-08 | **Verantwortlich:** Everlast AI

---

## Problemanalyse

Das Unternehmen erstellt regelmäßig Website-Texte, Produktbeschreibungen und FAQ-Antworten – bisher manuell durch Mitarbeitende ohne dedizierte Texter-Ausbildung. Ergebnis: inkonsistente Markenstimme, langer Abstimmungsaufwand, Flaschenhals bei Veröffentlichungen.

Ziel: Ein internes Werkzeug, das Mitarbeitende in die Lage versetzt, hochwertige Text-Entwürfe in Minuten statt Stunden zu erstellen – ohne Prompting-Kenntnisse.

---

## Lösungsarchitektur

```
Mitarbeitende (Browser)
       │
       ▼
  React-Frontend
  ├── Texttyp wählen (Dropdown)
  ├── Thema/Stichworte eingeben
  └── Ergebnis anzeigen + kopieren
       │
       ▼
  FastAPI-Backend (Python)
  ├── Eingabe validieren + sanitizen
  ├── Prompt-Template auswählen
  ├── RAG: relevante Kontext-Chunks laden
  └── LLM-API aufrufen
       │
       ▼
  ChromaDB (lokal)          Claude API (Anthropic)
  └── Vektordatenbank       └── claude-sonnet-4-20250514
      (Firmenwissen)
```

---

## Stack-Entscheidung

### Backend: Python + FastAPI

Python ist die Standardsprache im LLM-Ökosystem – alle relevanten Bibliotheken (LlamaIndex, ChromaDB, Anthropic SDK) sind nativ verfügbar. FastAPI generiert automatisch eine OpenAPI-Dokumentation, was die spätere Wartung erleichtert. Alternativstack Node.js wurde verworfen, da das Team Python-Kenntnisse mitbringt.

### LLM: Claude API (Anthropic)

Stärken bei Textqualität auf Deutsch, präzise Instruction-Following für Tonvorgaben, DPA verfügbar. Austauschbar gegen OpenAI oder ein lokales Modell (Ollama + Mistral) ohne Architekturänderung – die Abstraktion liegt im Backend.

### Vektordatenbank: ChromaDB (lokal)

Läuft vollständig on-premise, keine Cloud-Anbindung für Firmenwissen nötig. Einfache Python-Integration. Für größere Datenmengen (>100.000 Dokumente) empfiehlt sich ein späterer Wechsel zu Qdrant oder Weaviate.

### Frontend: React + Vite + Tailwind

Minimaler Scope – keine komplexen State-Management-Anforderungen. Vite für schnelle Builds. Tailwind reduziert Custom-CSS auf ein Minimum. Deploybar als statische Seite ohne separaten Web-Server.

---

## Prompt-Templates (5 Typen)

Jedes Template besteht aus einem System-Prompt (Rolle + Ton + Format-Vorgabe) und einem User-Prompt-Rahmen mit Platzhaltern. Mitarbeitende sehen nur das Eingabefeld – die Prompt-Logik ist intern.

| ID | Texttyp | Ausgabe-Format | Ton |
|----|---------|----------------|-----|
| seo_v1 | SEO-Text | Fließtext + Meta-Tags | Professionell, klar |
| produkt_v1 | Produktbeschreibung | Fließtext + 3 Bullets | Sachlich-werbend |
| faq_v1 | FAQ-Antwort | 2 Frage-Antwort-Paare | Freundlich, verbindlich |
| leichte_sprache_v1 | Leichte Sprache | Kurzsätze A2 | Einfach, direkt |
| social_v1 | Social-Media-Post | 3 Sätze + Hashtags | Direkt, positiv |

---

## RAG-Pipeline (Retrieval-Augmented Generation)

1. Bestehende Dokumente (Website-Export, PDFs, interne Dokus) werden beim Setup einmalig eingelesen.
2. LlamaIndex zerlegt sie in Chunks (ca. 300 Token, 10 % Überlappung).
3. Embeddings werden in ChromaDB gespeichert.
4. Bei jeder Anfrage: Die k=3 ähnlichsten Chunks werden dem Prompt als Kontext beigefügt.
5. Das Modell erzeugt einen Text, der auf dem Firmenwissen basiert – keine Halluzinationen zu internen Produktdetails.

---

## Deployment

Für eine erste Version reicht ein einzelner Linux-Server (2 vCPU, 4 GB RAM):

- Backend: `uvicorn main:app --host 0.0.0.0 --port 8000`
- Frontend: statisch via nginx
- ChromaDB: lokal, persistiert auf Disk

Skalierung auf Kubernetes oder Cloud-Hosting ist möglich, aber für den Projektumfang nicht nötig.

---

## Mitarbeitenden-Guide

Eine kompakte Schritt-für-Schritt-Anleitung (3 Seiten Markdown + optionales 5-Minuten-Screencast-Skript) ist im Abgabepaket enthalten. Kernschritte:

1. Browser öffnen, URL eingeben.
2. Texttyp aus Dropdown wählen.
3. Thema/Stichwörter eingeben (1–3 Sätze reichen).
4. "Entwurf generieren" klicken.
5. Text prüfen, ggf. anpassen, kopieren.
