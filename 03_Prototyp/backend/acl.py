"""
EVL-2026-003 · Access Control Layer
Mandanten-Isolation und Chinese-Wall-Enforcement für Qdrant-Queries.

Kernprinzip: Kein Code-Pfad führt zu einer ungefilterten Query.
build_filter() ist der einzige Einstiegspunkt — mandatory, nicht optional.
"""

from dataclasses import dataclass, field

# ── Nutzer-Kontext (kommt aus JWT in Production) ──────────────────────────────

@dataclass
class UserContext:
    user_id:        str
    name:           str
    allowed_mandate: list[str]         # Mandate auf die der User Zugriff hat
    chinese_wall_pairs: list[tuple[str, str]] = field(default_factory=list)
    is_admin:       bool = False

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


def get_user(user_id: str) -> UserContext:
    if user_id not in USERS:
        raise ValueError(f"Unbekannter User: {user_id}")
    return USERS[user_id]


# ── Filter-Builder für Qdrant ────────────────────────────────────────────────

def build_qdrant_filter(user: UserContext) -> dict:
    """
    Baut den Qdrant-Payload-Filter für eine Query.
    Gibt immer einen Filter zurück — niemals None.

    Logik:
      Dokument ist sichtbar wenn:
        (mandant_id IN user.effective_allowed) OR (mandant_id IS None)
      AND
        (user.user_id NOT IN chinese_wall_exclude)
    """
    effective = user.effective_allowed()
    # None-mandant_id = öffentliche Dokumente (Leitfäden, Präzedenzfälle) → via is_null unten

    return {
        "should": [
            {"key": "mandant_id", "match": {"any": effective}},
            {"key": "mandant_id", "is_null": True},
        ],
        "must_not": [
            {"key": "chinese_wall_exclude", "match": {"any": [user.user_id]}},
        ],
        "_meta": {
            "user_id": user.user_id,
            "effective_mandate": effective,
            "filter_version": "1.0",
        }
    }


def validate_result(doc_meta: dict, user: UserContext) -> tuple[bool, str]:
    """
    Nachgelagerte Validierung: War das Ergebnis erlaubt?
    Für Audit-Logging und Tests — zusätzliche Sicherheitsebene.
    """
    mandant_id = doc_meta.get("mandant_id")
    cw_exclude = doc_meta.get("chinese_wall_exclude", [])

    if user.user_id in cw_exclude:
        return False, f"Chinese Wall: {user.user_id} in exclude-Liste"

    if mandant_id is not None and not user.can_see_mandant(mandant_id):
        return False, f"ACL: Mandat {mandant_id} nicht in allowed_mandate"

    return True, "OK"
