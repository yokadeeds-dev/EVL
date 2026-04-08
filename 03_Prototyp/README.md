# Prototyp · Content-Assistant mit Legal-RAG (Production-Engine)

Dieses Projekt vereint die einfache Web-Applikation des Content-Assistants (`002`) mit der hochsicheren Qdrant "Chinese-Wall" ACL-Retrieval-Engine aus `003`.

## Was ist neu im Production-Merge?
- **Persistenz ohne externe DB**: Nutzt `InMemoryQdrant` mit robuster, platzsparender `.json`-Persistenz auf der lokalen Festplatte.
- **Echte Semantische Modelle**: Nutzt `sentence-transformers` (`intfloat/multilingual-e5-small`), lokal gehostet (100% On-Premise).
- **OAuth2 & JWT Auth**: Zugriff auf das Backend ist per klassischem "SSO Login" über JSON Web Tokens abgesichert.
- **ACL & Chinese Walls**: Strikt isolierte Datentrennung zwischen Mandanten. Das Frontend warnt bei Einbezug via § 203 StGB automatisiert.

---

## Voraussetzungen

- Python 3.11+
- Node.js 18+

---

## Backend starten

```bash
cd backend
# 1. Environment-Datei ausfüllen (Dummy wird mitgeliefert)
cp .env.example .env
# ANTHROPIC_API_KEY in .env zwingend eintragen!

# 2. Abhängigkeiten
pip install -r requirements.txt

# 3. Server starten (lädt beim ersten Mal ~450MB für das HF-Embeddings Modell)
uvicorn main:app --reload
# → läuft auf http://localhost:8000
# → API-Doku: http://localhost:8000/docs
```

### Wissensbasis befüllen (Ingestion)

Ein Skript (`synthetic_docs.py`) greift als Helfer ein. Über das Frontend (klicke oben auf den Tab/Button **Admin**) kannst du dich als `anwalt_a` anmelden und bequem per Klick zehntausende Dokumente in das Vektor-Modell indizieren lassen.

Alternativ per Terminal (JWT-Auth):
```bash
# Token holen
TOKEN=$(curl -s -X POST http://localhost:8000/auth/token -d "username=anwalt_a&password=x" | jq -r .access_token)

# Ingest anstoßen
curl -X POST http://localhost:8000/admin/ingest -H "Authorization: Bearer $TOKEN"
```

---

## Frontend starten

```bash
cd frontend
npm install
npm run dev
# → läuft auf http://localhost:5173
```

- **Logins für Tester:** `anwalt_a`, `anwalt_b`, `anwalt_c`
- **Passwort:** Egal (es wird für den PoC nur der Username im Mock-Active-Directory evaluiert).

---

## Struktur-Übersicht

```
03_Prototyp/
├── backend/
│   ├── main.py              ← FastAPI App (JWT Auth, Endpoints)
│   ├── rag_engine.py        ← Die Qdrant-RAG Engine inkl. Semantic Embeddings
│   ├── acl.py               ← Chinese-Walls + Mandanten-Logik (UserContext)
│   ├── jwt_auth.py          ← Pure Python HMAC SHA-256 Auth Server
│   ├── admin_upload.py      ← Router für Datei-Uploads
│   ├── synthetic_docs.py    ← Testdaten-Generator
│   └── requirements.txt
├── frontend/
│   ├── src/App.jsx          ← React UI (inklusive Mandantenauswahl & Warnung)
└── README.md
```

## API-Endpoints & Sicherheit

Alle Endpoints erfordern ein gültiges JWT (`Authorization: Bearer <Token>`), welches über `POST /auth/token` erzeugt wird.

| Pfad | Beschreibung | Relevanz |
|------|--------------|----------|
| `/auth/token` | Erzeugt das OAuth2 Access Token. | Login |
| `/me` | Zeigt den aktuellen ACL-UserContext (Welche Mandate sind wie freigeschaltet?). | App Initialization |
| `/generate` | Haupt-Endpoint. Der User-Kontext zwingt das Qdrant-Retrieval strictly zum Bypass bestimmter Chinese Walls. | Assistenz |
| `/admin/ingest` | Triggert den Embedding-Prozess durch `sentence-transformers`. | Ingestion |
