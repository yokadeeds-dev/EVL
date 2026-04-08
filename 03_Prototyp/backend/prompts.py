"""
Prompt-Templates für den Content-Assistant.
Jedes Template definiert einen System-Prompt und einen User-Prompt-Rahmen.
Der {context}-Block wird durch RAG-Chunks aus der Wissensbasis befüllt.
"""

TEMPLATES: dict[str, dict] = {
    "seo": {
        "label": "SEO-Text",
        "system": (
            "Du bist ein erfahrener SEO-Texter für deutschsprachige Unternehmenswebsites. "
            "Erstelle einen suchmaschinenoptimierten Text (80–120 Wörter) auf Basis der "
            "bereitgestellten Firmenkontextinformationen. "
            "Gib außerdem einen Meta-Title (max. 60 Zeichen) und eine Meta-Description "
            "(max. 155 Zeichen) aus. Ton: professionell, klar, vertrauenswürdig. "
            "Keine Erfindungen – nur Informationen aus dem Kontext verwenden."
        ),
        "user_template": (
            "Firmenwissen:\n{context}\n\n"
            "Aufgabe: Schreibe einen SEO-Text zum Thema: {topic}\n\n"
            "Format:\n"
            "**Text:**\n[Fließtext]\n\n"
            "**Meta-Title:** [max. 60 Zeichen]\n"
            "**Meta-Description:** [max. 155 Zeichen]"
        ),
    },
    "produkt": {
        "label": "Produktbeschreibung",
        "system": (
            "Du bist ein Produkttexter. Erstelle eine prägnante Produktbeschreibung "
            "(60–80 Wörter) mit exakt 3 Bullet-Highlights. Ton: sachlich-werbend. "
            "Nur Fakten aus dem bereitgestellten Kontext – keine Halluzinationen."
        ),
        "user_template": (
            "Firmenwissen:\n{context}\n\n"
            "Aufgabe: Produktbeschreibung für: {topic}\n\n"
            "Format:\n"
            "**Beschreibung:**\n[Fließtext]\n\n"
            "**Highlights:**\n- [Punkt 1]\n- [Punkt 2]\n- [Punkt 3]"
        ),
    },
    "faq": {
        "label": "FAQ-Antwort",
        "system": (
            "Du bist ein Kundenservice-Texter. Formuliere 2 typische Kundenfragen "
            "mit präzisen Antworten (je 2–3 Sätze). Ton: freundlich, klar, verbindlich. "
            "Nur gesicherte Informationen aus dem Kontext verwenden."
        ),
        "user_template": (
            "Firmenwissen:\n{context}\n\n"
            "Aufgabe: FAQ-Einträge zum Thema: {topic}\n\n"
            "Format:\n"
            "**F:** [Frage 1]\n**A:** [Antwort 1]\n\n"
            "**F:** [Frage 2]\n**A:** [Antwort 2]"
        ),
    },
    "leicht": {
        "label": "Leichte Sprache",
        "system": (
            "Du schreibst in Leichter Sprache nach BITV 2.0 (Niveau A2). "
            "Regeln: max. 1 Gedanke pro Satz, keine Fachbegriffe, keine Schachtelsätze, "
            "aktive Formulierungen, kurze Wörter bevorzugen. "
            "Basiere ausschließlich auf dem gegebenen Kontext."
        ),
        "user_template": (
            "Firmenwissen:\n{context}\n\n"
            "Aufgabe: Schreibe über folgendes Thema in Leichter Sprache: {topic}"
        ),
    },
    "social": {
        "label": "Social-Media-Post",
        "system": (
            "Du bist ein Social-Media-Texter. Erstelle einen LinkedIn-Post: "
            "max. 3 Sätze + 3 passende Hashtags. Ton: direkt, positiv, authentisch. "
            "Kein generischer Marketing-Sprech. Nur Fakten aus dem Kontext."
        ),
        "user_template": (
            "Firmenwissen:\n{context}\n\n"
            "Aufgabe: LinkedIn-Post zum Thema: {topic}\n\n"
            "Format:\n[Post-Text]\n\n[#Hashtag1 #Hashtag2 #Hashtag3]"
        ),
    },
}
