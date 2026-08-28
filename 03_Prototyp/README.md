# Prototyp · Content-Assistant mit Legal-RAG (Production-Engine)

Dieses Projekt vereint die einfache Web-Applikation des Content-Assistants (`002`) mit der hochsicheren Qdrant "Chinese-Wall" ACL-Retrieval-Engine aus `003`.

## Was ist neu im Production-Merge?
- **Persistenz, zwei Stufen**: In-Memory-Store als Fallback für den schnellen Start;
  bei gesetzter `DATABASE_URL` ein geteilter **Postgres/pgvector**-Store (Multi-Worker-fähig).
- **Echte Semantische Modelle**: Nutzt `sentence-transformers` (`intfloat/multilingual-e5-small`), lokal gehostet (100% On-Premise).
- **OAuth2 & JWT Auth**: Zugriff auf das Backend ist per klassischem "SSO Login" über JSON Web Tokens abgesichert.
- **ACL & Chinese Walls**: Strikt isolierte Datentrennung zwischen Mandanten. Das Frontend warnt bei Einbezug via § 203 StGB automatisiert.

---

## Methodik: Walking Skeleton → inkrementelle Erweiterung

Der Prototyp wurde bewusst als **Walking Skeleton** aufgebaut: zuerst ein
dünner, aber durchgängiger End-to-End-Pfad, danach schrittweise Verbreiterung.
Jede Erweiterung lief als eigener Feature-Branch über einen Pull Request mit
grüner CI (Lint · Test · Scan · Build).

1. **Skelett** – durchgängiger Pfad `Login → /generate → RAG-Retrieval → LLM → Antwort`
   mit In-Memory-Store und Mock-Auth (PR #1: CI-Pipeline drumherum).
2. **Cache & Rate-Limiting** – Redis für prozessübergreifende Zustände (PR #2).
3. **Härtung** – Admin-only-Endpoints, ACL/Chinese-Wall-Enforcement (PR #3).
4. **Persistenz** – Postgres/pgvector als geteilter Vektor-Store, Multi-Worker-fähig (PR #4).
5. **Sicherheit & Typsicherheit** – echte Passwort-Verifikation im Login;
   Frontend-Migration nach TypeScript mit `tsc`-Gate in der CI.

Das Skelett war ab Schritt 1 lauffähig; jede spätere Schicht erweiterte es,
ohne den durchgängigen Pfad je zu brechen.

---

## Voraussetzungen

- Python 3.11+
- Node.js 18+
- Optional: Docker + Docker Compose (reproduzierbares Packaging, siehe `docker-compose.yml`)
- Optional: PostgreSQL mit `pgvector` und Redis (sonst In-Memory-Fallback)

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
# Token holen (Demo-Passwort, überschreibbar per Env DEMO_PW_ANWALT_A)
TOKEN=$(curl -s -X POST http://localhost:8000/auth/token -d "username=anwalt_a&password=kraft-demo-2026" | jq -r .access_token)

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

- **Logins für Tester (Demo-Passwörter):**
  - `anwalt_a` (Admin) · `kraft-demo-2026`
  - `anwalt_b` · `schuster-demo-2026`
  - `anwalt_c` · `voss-demo-2026`
- Passwörter sind per Env (`DEMO_PW_ANWALT_A` …) überschreibbar. In Production
  kommen Hashes aus AD/LDAP; das Login prüft Username **und** Passwort
  (pbkdf2-hmac-sha256, Konstantzeit-Vergleich).

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
├── frontend/                ← React + TypeScript (Vite, Tailwind)
│   ├── src/App.tsx          ← UI (Mandantenauswahl, § 203-Warnung, Login)
│   ├── src/admin/AdminPanel.tsx
│   ├── src/types.ts         ← geteilte Typen (spiegeln die Backend-Schemas)
│   └── tsconfig.json        ← strict; `npm run typecheck` als CI-Gate
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
