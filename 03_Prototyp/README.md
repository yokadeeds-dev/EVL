# Prototyp · Quickstart

## Voraussetzungen

- Python 3.11+
- Node.js 18+

---

## Backend starten

```bash
cd backend
cp .env.example .env
# ANTHROPIC_API_KEY in .env eintragen

pip install -r requirements.txt
uvicorn main:app --reload
# → läuft auf http://localhost:8000
# → API-Doku: http://localhost:8000/docs
```

### Wissensbasis befüllen (optional, aber empfohlen)

```bash
mkdir knowledge_base
# PDFs, .txt oder .md der Firmendokumente in knowledge_base/ legen

curl -X POST http://localhost:8000/admin/ingest \
  -H "Content-Type: application/json" \
  -H "X-API-Key: key-admin-xyz789" \
  -d '{"path": "./knowledge_base"}'
```

---

## Frontend starten

```bash
cd frontend
npm install
npm run dev
# → läuft auf http://localhost:5173
```

---

## Struktur

```
03_Prototyp/
├── backend/
│   ├── main.py          ← FastAPI App, alle Endpoints
│   ├── rag.py           ← ChromaDB + LlamaIndex RAG-Pipeline
│   ├── prompts.py       ← 5 Prompt-Templates
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── App.jsx      ← React-Hauptkomponente
│   │   ├── main.jsx
│   │   └── index.css
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── tailwind.config.js
└── README.md            ← diese Datei
```

---

## API-Endpoints

| Methode | Pfad | Beschreibung |
|---------|------|--------------|
| GET | /status | Systemstatus + KB-Größe |
| GET | /templates | Verfügbare Template-IDs |
| POST | /generate | Text generieren (RAG + LLM) |
| POST | /admin/ingest | Dokumente in ChromaDB einlesen |
| GET | /admin/kb-status | Status der Wissensbasis abfragen |
| DELETE | /admin/kb-reset | Wissensbasis leeren |

Vollständige Doku: http://localhost:8000/docs (Swagger UI, auto-generiert)
