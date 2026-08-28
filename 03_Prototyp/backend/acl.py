"""
EVL-2026-003 · Access Control Layer
Mandanten-Isolation und Chinese-Wall-Enforcement für Qdrant-Queries.

Kernprinzip: Kein Code-Pfad führt zu einer ungefilterten Query.
build_filter() ist der einzige Einstiegspunkt — mandatory, nicht optional.
"""

import hashlib
import hmac
import os
from dataclasses import dataclass, field

# ── Passwort-Hashing (pbkdf2-hmac-sha256, Stdlib – keine Extra-Dependency) ────
#
# In Production kommen Hashes aus AD/LDAP bzw. einer User-DB. Für das Demo-Setup
# werden sie beim Import aus _DEMO_PASSWORDS erzeugt (frischer Salt pro Start).

_PBKDF2_ITERATIONS = 200_000


def hash_password(password: str, salt: bytes | None = None) -> str:
    """Erzeugt 'salt_hex:hash_hex'. Salt zufällig, falls nicht angegeben."""
    if salt is None:
        salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return f"{salt.hex()}:{dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Konstantzeit-Vergleich gegen einen 'salt_hex:hash_hex'-Eintrag."""
    if not stored or ":" not in stored:
        return False
    salt_hex, dk_hex = stored.split(":", 1)
    try:
        salt = bytes.fromhex(salt_hex)
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return hmac.compare_digest(dk.hex(), dk_hex)


# ── Nutzer-Kontext (kommt aus JWT in Production) ──────────────────────────────

@dataclass
class UserContext:
    user_id:        str
    name:           str
    allowed_mandate: list[str]         # Mandate auf die der User Zugriff hat
    chinese_wall_pairs: list[tuple[str, str]] = field(default_factory=list)
    is_admin:       bool = False
    password_hash:  str = ""           # 'salt_hex:hash_hex'; Demo: siehe unten

    def effective_allowed(self) -> list[str]:
        """Mandate nach Chinese-Wall-Abzug."""
        blocked = self._blocked_mandate()
        return [m for m in self.allowed_mandate if m not in blocked]

    def _blocked_mandate(self) -> set[str]:
        """Mandate die aufgrund Chinese Walls gesperrt sind."""
        blocked = set()
        for m_a, m_b in self.chinese_wall_pairs:
            if m_a in self.allowed_mandate and m_b in self.allowed_mandate:
                # Beide Seiten einer Chinese Wall → Konflikt → beide sperren
                # In Realität: manuell aufgelöst durch Bereichsleitung
                blocked.add(m_a)
                blocked.add(m_b)
            elif m_a in self.allowed_mandate:
                blocked.add(m_b)
            elif m_b in self.allowed_mandate:
                blocked.add(m_a)
        return blocked

    def can_see_mandant(self, mandant_id: str) -> bool:
        return mandant_id in self.effective_allowed()

    def wall_forbidden_mandate(self) -> set[str]:
        """
        Mandate, die dieser User wegen einer Chinese Wall NICHT sehen darf –
        weil er die Gegenseite in allowed_mandate hält. Query-Zeit-dynamisch:
        kein pro-Dokument gespeicherter (und bei Rechte-Änderung veraltender)
        Zustand mehr (früher: chinese_wall_exclude, beim Ingest eingefroren).
        """
        forbidden: set[str] = set()
        for m_a, m_b in self.chinese_wall_pairs:
            if m_a in self.allowed_mandate:
                forbidden.add(m_b)
            if m_b in self.allowed_mandate:
                forbidden.add(m_a)
        return forbidden


# ── Simulierte User-Datenbank (in Production: aus AD/LDAP) ───────────────────

CHINESE_WALLS = [("M001", "M002")]

USERS: dict[str, UserContext] = {
    "anwalt_a": UserContext(
        user_id="anwalt_a",
        name="Dr. Anna Kraft",
        allowed_mandate=["M001", "M003"],
        chinese_wall_pairs=CHINESE_WALLS,
        is_admin=True,   # einziger Admin im Demo-Setup
    ),
    "anwalt_b": UserContext(
        user_id="anwalt_b",
        name="Prof. Bernd Schuster",
        allowed_mandate=["M002", "M003"],
        chinese_wall_pairs=CHINESE_WALLS,
    ),
    "anwalt_c": UserContext(
        user_id="anwalt_c",
        name="Maria Voss",
        allowed_mandate=["M001", "M002", "M004"],
        chinese_wall_pairs=CHINESE_WALLS,
    ),
}


# ── Demo-Passwörter ───────────────────────────────────────────────────────────
# NUR für das Demo-Setup. In Production: Hashes aus AD/LDAP, keine Klartext-Liste
# im Code. Beim Import wird pro User ein frischer Salt-Hash erzeugt.

_DEMO_PASSWORDS = {
    "anwalt_a": os.getenv("DEMO_PW_ANWALT_A", "kraft-demo-2026"),
    "anwalt_b": os.getenv("DEMO_PW_ANWALT_B", "schuster-demo-2026"),
    "anwalt_c": os.getenv("DEMO_PW_ANWALT_C", "voss-demo-2026"),
}

for _uid, _pw in _DEMO_PASSWORDS.items():
    USERS[_uid].password_hash = hash_password(_pw)


def get_user(user_id: str) -> UserContext:
    if user_id not in USERS:
        raise ValueError(f"Unbekannter User: {user_id}")
    return USERS[user_id]


def authenticate(user_id: str, password: str) -> UserContext | None:
    """Prüft User + Passwort in Konstantzeit. Gibt None bei Fehlschlag zurück.

    Verifiziert immer gegen einen Hash (auch bei unbekanntem User), um
    Timing-Unterschiede zwischen 'User existiert nicht' und 'falsches Passwort'
    zu vermeiden (User-Enumeration)."""
    user = USERS.get(user_id)
    stored = user.password_hash if user else _DUMMY_HASH
    ok = verify_password(password, stored)
    return user if (ok and user is not None) else None


# Dummy-Hash für Konstantzeit-Verhalten bei unbekannten Usern.
_DUMMY_HASH = hash_password("dummy-password-never-matches")


# ── Filter-Builder für Qdrant ────────────────────────────────────────────────

def build_qdrant_filter(user: UserContext) -> dict:
    """
    Baut den Qdrant-Payload-Filter für eine Query.
    Gibt immer einen Filter zurück — niemals None.

    Logik:
      Dokument ist sichtbar wenn:
        (mandant_id IN user.effective_allowed) OR (mandant_id IS None)
      AND
        (mandant_id NOT IN user.wall_forbidden_mandate)   # Chinese Wall, dynamisch
    """
    effective = user.effective_allowed()
    forbidden = sorted(user.wall_forbidden_mandate())
    # None-mandant_id = öffentliche Dokumente (Leitfäden, Präzedenzfälle) → via is_null unten

    return {
        "should": [
            {"key": "mandant_id", "match": {"any": effective}},
            {"key": "mandant_id", "is_null": True},
        ],
        "must_not": [
            # Chinese Wall query-zeit-dynamisch: verbotene Mandate direkt statt
            # einer beim Ingest eingefrorenen pro-Dokument-Ausschlussliste.
            {"key": "mandant_id", "match": {"any": forbidden}},
        ],
        "_meta": {
            "user_id": user.user_id,
            "effective_mandate": effective,
            "wall_forbidden": forbidden,
            "filter_version": "2.0",
        }
    }


def validate_result(doc_meta: dict, user: UserContext) -> tuple[bool, str]:
    """
    Nachgelagerte Validierung (Audit-Layer): War das Ergebnis erlaubt?
    Prüft Chinese Wall + Mandanten-Sicht query-zeit-dynamisch.
    """
    mandant_id = doc_meta.get("mandant_id")
    if mandant_id is None:
        return True, "OK (öffentlich)"
    if mandant_id in user.wall_forbidden_mandate():
        return False, f"Chinese Wall: Mandat {mandant_id} für {user.user_id} gesperrt"
    if not user.can_see_mandant(mandant_id):
        return False, f"ACL: Mandat {mandant_id} nicht in allowed_mandate"
    return True, "OK"
