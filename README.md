# EVL-2026-002 · KI-basierter Content-Assistant
**Datum:** 2026-04-08 | **Verantwortlich:** Everlast AI | **Status:** Abgabebereit

---

## Problem in einem Satz

Mitarbeitende verlieren wöchentlich mehrere Stunden mit dem manuellen Erstellen und Abstimmen von Website-Texten – das Tool löst das durch geführte Prompt-Templates und firmeneigenes Kontextwissen.

---

## Anforderungscheck

| Aufgabe | Status | Hinweis |
|---------|--------|---------|
| Texte sammeln + strukturieren (RAG-Basis) | ✅ | PDF/TXT/MD → InMemoryQdrant (PoC), Qdrant-kompatibel |
| LLM-API-Anbindung (Backend) | ✅ | FastAPI + Anthropic SDK · main.py |
| Prompt-Templates (SEO, Leichte Sprache, FAQ, …) | ✅ | 5 Templates · prompts.py |
| Web-Interface (Eingabe, Typ-Auswahl, Copy-Button) | ✅ | React · App.jsx · Tailwind |
| JWT-Authentifizierung + Rollenmodell | ✅ | require_user / require_admin · auth.py |
| ACL / Chinese-Wall-Enforcement | ✅ | Mandanten-Isolation · acl.py |
| Admin-Panel (Upload, Ingest, Reset) | ✅ | AdminPanel.jsx + admin_upload.py |
| Doku / Guide für Mitarbeitende | ✅ | Markdown-Anleitung enthalten |
| Business Case | ✅ | ~8.760 € Netto-Einsparung/Jahr |
| AI Act / Haftung / Urheberrecht | ✅ | vertrag_haftung.md |

---

## Schnellstart

```bash
# Backend
cd 03_Prototyp/backend
cp .env.example .env
# .env befüllen:
#   ANTHROPIC_API_KEY=sk-ant-...
#   JWT_SECRET_KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
pip install -r requirements.txt
uvicorn main:app --reload
# → http://localhost:8000  |  Swagger-Doku: /docs

# Frontend (neues Terminal)
cd 03_Prototyp/frontend
npm install && npm run dev
# → http://localhost:5173
```

### Demo-Login

| Benutzer | Rolle | Erlaubte Mandate |
|----------|-------|-----------------|
| `anwalt_a` | Admin + User | M001, M003 |
| `anwalt_b` | User | M002, M003 |
| `anwalt_c` | User | M001, M002, M004 (Chinese Wall aktiv) |

> Das Passwort wird im Demo-Modus nicht geprüft – beliebigen Wert eintragen.

---

## Architektur

```
Browser (React + Tailwind)
       │  OAuth2 Bearer JWT
       ▼
FastAPI Backend
├── auth.py          JWT verifizieren, require_user / require_admin
├── acl.py           Mandanten-ACL + Chinese-Wall-Enforcement
├── rag_engine.py    InMemoryQdrant + ACL-gefilterter Retrieval
├── prompts.py       5 Prompt-Templates
├── admin_upload.py  Dokument-Upload/-Verwaltung
└── main.py          Alle Endpoints + PII-Sanitizer + Rate-Limiting
       │
       ├── Anthropic Claude API  (LLM-Generierung)
       └── qdrant_store.json     (lokale Vektordatenbank, on-premise)
```

---

## Projektstruktur

```
EVL-2026-002/
├── README.md
├── 02_Konzept/
│   └── konzept.md
├── 03_Prototyp/
│   ├── README.md                      ← Quickstart-Anleitung
│   ├── backend/
│   │   ├── main.py                    ← FastAPI App, alle Endpoints
│   │   ├── rag_engine.py              ← InMemoryQdrant RAG-Pipeline mit ACL
│   │   ├── acl.py                     ← Mandanten-ACL + Chinese-Wall-Enforcement
│   │   ├── auth.py                    ← JWT-Auth (require_user / require_admin)
│   │   ├── jwt_auth.py                ← JWT erstellen + verifizieren
│   │   ├── prompts.py                 ← 5 Prompt-Templates
│   │   ├── admin_upload.py            ← Dokument-Upload/-Verwaltung
│   │   ├── synthetic_docs.py          ← Demo-Dokumente generieren
│   │   ├── requirements.txt
│   │   └── .env.example
│   └── frontend/
│       ├── src/App.jsx                ← React-Hauptkomponente
│       ├── src/admin/AdminPanel.jsx   ← Admin-Bereich
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

## Sicherheitsmerkmale

| Maßnahme | Umsetzung |
|----------|-----------|
| JWT-Authentifizierung | HS256, 1h Ablauf, Secret aus Umgebungsvariable |
| Rollenmodell | `require_user` / `require_admin` – Admin-Endpoints strikt getrennt |
| ACL + Chinese Wall | Mandanten-Isolation vor jeder RAG-Query, nachgelagerte Validierung |
| PII-Sanitizer | Regex-Filter für E-Mail, Telefon, IBAN, IP vor jedem API-Call |
| Path-Traversal-Schutz | Upload + Delete validieren Zielpfad via `.resolve().is_relative_to()` |
| Rate-Limiting | 20 Anfragen / 60 s pro User (in-memory) |
| CORS | Nur konfigurierter Origin via `ALLOWED_ORIGIN` |

---

## Kontakt für Rückfragen

Everlast AI – Projektteam EVL-2026-002
