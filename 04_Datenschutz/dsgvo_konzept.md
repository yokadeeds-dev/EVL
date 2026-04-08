# Datenschutzkonzept · EVL-2026-002
**Version:** 1.0 | **Datum:** 2026-04-08

---

## Überblick

Der Content-Assistant verarbeitet ausschließlich nicht-personenbezogene Inhaltsdaten (Texte, Produktinformationen, FAQ-Inhalte). Dennoch gelten DSGVO-Anforderungen, da das System im unternehmerischen Umfeld betrieben wird und potenziell personenbezogene Daten in Eingaben enthalten sein könnten.

---

## Datenflüsse

### 1. Firmenwissen (Vektordatenbank)

- Verarbeitung: lokal, on-premise
- Speicherort: ChromaDB auf dem Unternehmens-Server
- Verlässt das Netz: nein
- Betroffene Daten: öffentliche Website-Texte, interne Produktdokus (keine PII)
- Maßnahme: Beim initialen Einlesen werden Dokumente auf PII geprüft (manuell oder per Regex-Filter). Dokumente mit personenbezogenen Daten werden nicht in die Wissensbasis aufgenommen.

### 2. LLM-API-Calls (Anthropic Claude API)

- Verarbeitung: externe Cloud (Anthropic, USA)
- Verlässt das Netz: ja – Prompt-Text + Kontext-Chunks
- Betroffene Daten: nur nicht-personenbezogene Firmeninhalte
- Rechtsgrundlage: Art. 6 Abs. 1 lit. f DSGVO (berechtigtes Interesse) oder Auftragsverarbeitungsvertrag (AVV) mit Anthropic
- Maßnahme 1: AVV mit Anthropic abschließen (verfügbar unter anthropic.com/legal)
- Maßnahme 2: Eingabe-Sanitizer im Backend – vor jedem API-Call wird der Text auf PII-Muster geprüft (E-Mail-Adressen, Telefonnummern, Namen via Regex). Bei Treffer: Anfrage abgebrochen + Hinweis an Nutzer.
- Alternative (zero external transfer): Lokales Modell via Ollama (z. B. Mistral 7B oder LLaMA 3). Geringere Textqualität, aber vollständige Datensouveränität.

### 3. Web-Interface (Mitarbeitende)

- Keine Nutzer-Accounts, kein Login
- Keine Cookies, kein Tracking, kein Analytics
- Logs: nur technische Request-Logs (Timestamp, Endpunkt, HTTP-Status) – keine Inhalte, keine IPs
- Session-Daten: nur im Browser (kein Server-Side-State)

---

## Technische Schutzmaßnahmen

| Maßnahme | Umsetzung |
|----------|-----------|
| API-Key-Sicherheit | Umgebungsvariable (.env), nie im Code, in .gitignore |
| Transport-Verschlüsselung | HTTPS (TLS 1.3) für Frontend ↔ Backend und Backend ↔ API |
| Eingabe-Sanitizer | Regex-Filter für E-Mail, Telefon, IBAN vor API-Call |
| Minimalitätsprinzip | Nur notwendige Daten werden verarbeitet |
| Kein Logging von Inhalten | Request-Logs enthalten keine Prompt-Texte |

---

## Verarbeitungsverzeichnis (Art. 30 DSGVO)

| Feld | Inhalt |
|------|--------|
| Verantwortlicher | Auftraggeber-Unternehmen (Name, Adresse einzutragen) |
| Verarbeitungszweck | Erstellung von Website- und Marketing-Texten |
| Kategorien betroffener Personen | keine (System verarbeitet keine Kundendaten) |
| Empfänger | Anthropic PBC (USA) als Auftragsverarbeiter |
| Übermittlung in Drittland | ja (USA) – Grundlage: EU-Standardvertragsklauseln + AVV |
| Löschfristen | Wissensbasis: bei Projektende; Logs: 30 Tage rolling |
| Technische Maßnahmen | siehe Tabelle oben |

---

## AI Act (EU-KI-Verordnung)

Ein interner Content-Assistant fällt in der Regel in den Low-Risk-Bereich des AI Act. Damit entfallen die strengen Pflichten der Hochrisiko-Klassen, aber folgende Mindestanforderungen gelten trotzdem:

Transparenz gegenüber Mitarbeitenden: Die Nutzenden müssen wissen, dass sie mit einem KI-System arbeiten. Eine kurze Hinweiszeile im Interface genügt. Governance-Dokumentation: Zweck, Datenflüsse und Risikoanalyse müssen schriftlich festgehalten sein (liegt vor — dieses Dokument). Menschliche Kontrolle: KI-Outputs dürfen nicht automatisch und ohne Prüfung veröffentlicht werden. Das ist im vorliegenden Setup durch den obligatorischen Freigabe-Schritt sichergestellt.

Der AI Act ergänzt die DSGVO — er hebt sie nicht auf. Beide Regime müssen gleichzeitig eingehalten werden.

---

## Empfehlung

Für maximale Datensouveränität wird empfohlen, in einer zweiten Projektphase das externe LLM durch ein lokales Modell (Ollama + Mistral oder LLaMA 3) zu ersetzen. Die Architektur ist darauf vorbereitet – der Austausch erfordert nur eine Konfigurationsänderung im Backend, keinen Umbau.
