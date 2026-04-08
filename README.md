# EVL-2026-002 · KI-basierter Content-Assistant
**Datum:** 2026-04-08 | **Verantwortlich:** Everlast AI | **Status:** Abgabebereit

---

## Problem in einem Satz

Mitarbeitende verlieren wöchentlich mehrere Stunden mit dem manuellen Erstellen und Abstimmen von Website-Texten – das Tool löst das durch geführte Prompt-Templates und firmeneigenes Kontextwissen.

---

## Anforderungscheck

| Aufgabe | Status | Hinweis |
|---------|--------|---------|
| Texte sammeln + strukturieren (RAG-Basis) | ✅ | PDF/Webseite → ChromaDB lokal |
| LLM-API-Anbindung (Backend) | ✅ | FastAPI + Anthropic SDK · main.py |
| Prompt-Templates (SEO, Leichte Sprache, FAQ, …) | ✅ | 5 Templates · prompts.py |
| Web-Interface (Eingabe, Typ-Auswahl, Copy-Button) | ✅ | React · App.jsx · Tailwind |
| Doku / Guide für Mitarbeitende | ✅ | Markdown-Anleitung enthalten |
| Business Case | ✅ | ~8.760 € Netto-Einsparung/Jahr |
| AI Act / Haftung / Urheberrecht | ✅ | vertrag_haftung.md |

---

## Schnellstart

```bash
# Backend
cd 03_Prototyp/backend
cp .env.example .env     # ANTHROPIC_API_KEY eintragen
pip install -r requirements.txt
uvicorn main:app --reload
# → http://localhost:8000  |  Swagger-Doku: /docs

# Frontend (neues Terminal)
cd 03_Prototyp/frontend
npm install && npm run dev
# → http://localhost:5173
```

---

## Projektstruktur

```
EVL-2026-002_Content-Assistant/
├── README.md
├── 01_Auftrag/
├── 02_Konzept/
│   └── konzept.md
├── 03_Prototyp/
│   ├── README.md                      ← Quickstart-Anleitung
│   ├── backend/
│   │   ├── main.py                    ← FastAPI App, alle Endpoints
│   │   ├── rag.py                     ← ChromaDB + LlamaIndex RAG-Pipeline
│   │   ├── prompts.py                 ← 5 Prompt-Templates
│   │   ├── requirements.txt
│   │   └── .env.example
│   └── frontend/
│       ├── src/App.jsx                ← React-Hauptkomponente
│       ├── src/main.jsx
│       ├── index.html
│       ├── package.json
│       └── vite.config.js
├── 04_Datenschutz/
│   └── dsgvo_konzept.md
└── 05_Abgabe/
    ├── business_case.md
    └── vertrag_haftung.md
```

---

## Kontakt für Rückfragen

Everlast AI – Projektteam EVL-2026-002
