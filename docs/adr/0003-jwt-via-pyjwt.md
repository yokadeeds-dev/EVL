# ADR 0003 — JWT via PyJWT (statt Eigenbau)

- **Status:** akzeptiert
- **Datum:** 2026-08-28
- **Kontext:** EVL-2026-002, Auth-Layer

## Kontext

Die Authentifizierung nutzt Bearer-JWTs. Der frühe Prototyp hatte eine
**handgeschriebene** HMAC-SHA256-Implementierung (stdlib). Sie war zwar korrekt
(fester Algorithmus, Konstantzeit-Vergleich, `exp`-Prüfung), aber „roll your own
crypto" ist ein vermeidbares Risiko und ein berechtigter Review-Einwand — und es
fehlten Standard-Claims (`iss`/`aud`/`nbf`) sowie deren Validierung.

## Entscheidung

**PyJWT** (etablierte, breit auditierte Bibliothek).

- **HS256**, Algorithmus bei der Verifikation fest auf `["HS256"]` gepinnt →
  kein `alg=none` / alg-Confusion.
- Vollständige Claims: `iss`, `aud`, `iat`, `nbf`, `exp`; bei `verify` werden
  Signatur, Ablauf, `nbf`, `iss` und `aud` geprüft (`require`-Liste erzwingt die
  Präsenz von `exp/iat/nbf/iss/aud/sub`).

## Konsequenzen

- **Positiv:** keine eigene Krypto mehr; Standard-Claims validiert; Wartung/CVEs
  über die Bibliothek statt Eigenpflege. Eine kleine, weit verbreitete Dependency.
- **Bewusst zurückgestellt (Prototyp-Scope):**
  - **Token-Revocation / Refresh-Tokens** — braucht einen serverseitigen Zustand
    (Denylist/Session-Store, z. B. Redis). Trigger: echter Betrieb mit Logout /
    erzwungener Session-Invalidierung.
  - **Asymmetrisch (RS256/EdDSA)** — sinnvoll, sobald mehrere Dienste Tokens
    verifizieren, ohne das Signaturgeheimnis zu teilen. Trigger: Aufteilung in
    mehrere verifizierende Services.
