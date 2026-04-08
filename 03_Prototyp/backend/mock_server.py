"""
Mock-Backend für den Stresstest — läuft komplett mit Python stdlib.
Simuliert alle Endpoints inklusive Auth, Rate-Limiting, PII-Check, Validierung.
"""

import json
import re
import time
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse

USER_KEYS  = {"key-user-abc123", "key-user-def456"}
ADMIN_KEYS = {"key-admin-xyz789"}
RATE_WINDOW = 60
RATE_LIMIT  = 60  # erhöht für Testlauf
_rate_store: dict[str, list[float]] = defaultdict(list)

PII_PATTERNS = [
    (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "E-Mail-Adresse"),
    (r"\b(\+49|0)[0-9\s\-/]{7,}\b", "Telefonnummer"),
    (r"\bDE\d{2}[A-Z0-9]{4}\d{7}[A-Z0-9]{0,16}\b", "IBAN"),
    (r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b", "IP-Adresse"),
]

VALID_TYPES = {"seo", "produkt", "faq", "leicht", "social"}


def _auth(key, require_admin=False):
    if not key:
        return 401, "Ungültiger oder fehlender API-Key"
    if require_admin:
        if key not in ADMIN_KEYS:
            return 403, "Admin-Rechte erforderlich"
    else:
        if key not in (USER_KEYS | ADMIN_KEYS):
            return 401, "Ungültiger oder fehlender API-Key"
    return 200, ""


def _rate_check(key):
    now = time.time()
    window = now - RATE_WINDOW
    calls = [t for t in _rate_store[key] if t > window]
    if len(calls) >= RATE_LIMIT:
        return False
    calls.append(now)
    _rate_store[key] = calls
    return True


def _pii_check(text):
    for pat, label in PII_PATTERNS:
        if re.search(pat, text):
            return label
    return None


class Handler(BaseHTTPRequestHandler):

    def log_message(self, *_): pass  # Logs unterdrücken

    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        length = int(self.headers.get("Content-Length", 0))
        if not length:
            return {}
        try:
            return json.loads(self.rfile.read(length))
        except Exception:
            return None

    def _key(self):
        return self.headers.get("X-API-Key", "")

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/status":
            self._send(200, {"status": "ok", "knowledge_base_empty": True,
                             "available_templates": list(VALID_TYPES), "version": "1.1.0-mock"})

        elif path == "/templates":
            code, msg = _auth(self._key())
            if code != 200:
                self._send(code, {"detail": msg}); return
            self._send(200, [{"id": k, "label": k.upper()} for k in VALID_TYPES])

        elif path == "/admin/kb-status":
            code, msg = _auth(self._key(), require_admin=True)
            if code != 200:
                self._send(code, {"detail": msg}); return
            self._send(200, {"document_count": 0, "is_empty": True})

        elif path == "/admin/documents":
            code, msg = _auth(self._key(), require_admin=True)
            if code != 200:
                self._send(code, {"detail": msg}); return
            self._send(200, {"documents": [], "count": 0})

        else:
            self._send(404, {"detail": "Not found"})

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/generate":
            key = self._key()
            code, msg = _auth(key)
            if code != 200:
                self._send(code, {"detail": msg}); return

            if not _rate_check(key):
                self._send(429, {"detail": "Rate-Limit erreicht"}); return

            body = self._body()
            if body is None:
                self._send(400, {"detail": "Ungültiger JSON-Body"}); return

            text_type = body.get("text_type", "")
            topic = body.get("topic", "")

            if text_type not in VALID_TYPES:
                self._send(422, {"detail": f"Ungültiger text_type: {text_type}"}); return
            if not isinstance(topic, str) or len(topic) < 3:
                self._send(422, {"detail": "topic zu kurz (min. 3 Zeichen)"}); return
            if len(topic) > 500:
                self._send(422, {"detail": "topic zu lang (max. 500 Zeichen)"}); return

            pii = _pii_check(topic)
            if pii:
                self._send(422, {"detail": f"Eingabe enthält {pii}. Bitte entfernen."}); return

            self._send(200, {
                "result": f"[Mock] {text_type.upper()}-Entwurf für: {topic[:60]}",
                "text_type": text_type,
                "label": text_type.upper(),
                "context_chunks_used": 0,
                "rag_active": False,
            })

        elif path == "/admin/ingest":
            code, msg = _auth(self._key(), require_admin=True)
            if code != 200:
                self._send(code, {"detail": msg}); return
            body = self._body() or {}
            p = body.get("path", "")
            if "/nonexistent" in p or not p:
                self._send(404, {"detail": f"Pfad nicht gefunden: {p}"}); return
            self._send(200, {"status": "ok", "documents_ingested": 3})

        else:
            self._send(404, {"detail": "Not found"})

    def do_DELETE(self):
        path = urlparse(self.path).path
        if path == "/admin/kb-reset":
            code, msg = _auth(self._key(), require_admin=True)
            if code != 200:
                self._send(code, {"detail": msg}); return
            self._send(200, {"status": "ok", "message": "Wissensbasis geleert."})
        elif path.startswith("/admin/documents/"):
            code, msg = _auth(self._key(), require_admin=True)
            if code != 200:
                self._send(code, {"detail": msg}); return
            self._send(200, {"status": "ok", "deleted": path.split("/")[-1]})
        else:
            self._send(404, {"detail": "Not found"})


def run(port=18000):
    server = HTTPServer(("127.0.0.1", port), Handler)
    return server
