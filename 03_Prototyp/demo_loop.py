"""
EVL-2026-002 · KI-basierter Content-Assistant
Demo-Loop (regelbasiert, kein API-Key nötig)

Verwendung:
    python demo_loop.py

Für Live-Betrieb mit echter LLM-API:
    pip install anthropic
    Dann ANTHROPIC_API_KEY in .env setzen und den Live-Modus aktivieren.
"""

import sys

# ─── Prompt-Templates ──────────────────────────────────────────────────────────

TEMPLATES = {
    "seo": {
        "label": "SEO-Text",
        "system": (
            "Du bist ein erfahrener SEO-Texter. Erstelle einen kurzen, "
            "suchmaschinenoptimierten Text (ca. 80 Wörter) inklusive "
            "Meta-Title und Meta-Description. Ton: professionell, klar."
        ),
        "demo_fn": lambda thema: f"""[SEO-Text-Entwurf]

{thema.split(',')[0].strip()} – Qualität, die überzeugt

Entdecken Sie unsere Lösungen rund um {thema.strip()} – entwickelt für
Unternehmen, die auf Qualität und Verlässlichkeit setzen. Erfahren Sie mehr.

Meta-Title : {thema.split(',')[0].strip()} | IhrUnternehmen – Ihr Partner
Meta-Description: {thema.strip()} – jetzt informieren und Angebot anfordern.

[Template: seo_v1 | Kontext-Chunks: 3]""",
    },
    "produkt": {
        "label": "Produktbeschreibung",
        "system": (
            "Du bist ein Produkttexter. Erstelle eine prägnante Produktbeschreibung "
            "(ca. 60 Wörter) mit 3 Bullet-Highlights. Ton: sachlich-werbend."
        ),
        "demo_fn": lambda thema: f"""[Produktbeschreibung-Entwurf]

{thema.split(',')[0].strip()}

Unser Produkt überzeugt durch durchdachte Qualität und einfache Handhabung –
entwickelt für den modernen Einsatz.

Highlights:
• {thema.split(',')[0].strip()} – bewährt und zuverlässig
• Einfache Integration in bestehende Prozesse
• Langlebig und nachhaltig produziert

[Template: produkt_v1 | Ton: sachlich-werbend]""",
    },
    "faq": {
        "label": "FAQ-Antwort",
        "system": (
            "Du bist ein Kundenservice-Texter. Formuliere 2 typische FAQ-Fragen "
            "mit Antworten (je ca. 2 Sätze). Ton: freundlich, klar, verbindlich."
        ),
        "demo_fn": lambda thema: f"""[FAQ-Entwurf]

F: Was macht {thema.split(',')[0].strip()} besonders?
A: Unsere Lösung zeichnet sich durch hohe Qualität und einfache Bedienung aus.
   Kunden profitieren sofort – ohne langen Einarbeitungsaufwand.

F: Gibt es einen Support?
A: Ja – unser Team ist werktags von 8–17 Uhr erreichbar. Anfragen werden
   in der Regel innerhalb von 24 Stunden beantwortet.

[Template: faq_v1 | Quellen: interne Wissensbasis]""",
    },
    "leicht": {
        "label": "Leichte Sprache",
        "system": (
            "Du schreibst in Leichter Sprache (Niveau A2). Kurze Sätze, "
            "keine Fachbegriffe, max. 1 Gedanke pro Satz."
        ),
        "demo_fn": lambda thema: f"""[Leichte Sprache-Entwurf]

Das ist {thema.split(',')[0].strip()}.
Das Produkt ist einfach zu benutzen.
Es hilft Ihnen bei Ihrer Arbeit.
Sie können uns jederzeit fragen.
Wir helfen Ihnen gerne.

[Template: leichte_sprache_v1 | Niveau: A2]""",
    },
    "social": {
        "label": "Social-Media-Post",
        "system": (
            "Du bist ein Social-Media-Texter. Erstelle einen kurzen Post "
            "(max. 3 Sätze + 3 Hashtags) für LinkedIn. Ton: direkt, positiv."
        ),
        "demo_fn": lambda thema: f"""[Social-Post-Entwurf]

Neu bei uns: {thema.split(',')[0].strip()} – jetzt noch besser.
Wir haben zugehört und weiterentwickelt. Überzeugen Sie sich selbst!

#{thema.split(',')[0].strip().replace(' ', '')} #Innovation #Qualität

[Template: social_v1 | Kanal: LinkedIn]""",
    },
}

# ─── Demo-Loop ─────────────────────────────────────────────────────────────────

def run_demo():
    print("\n" + "=" * 60)
    print("  EVL-2026-002 · Content-Assistant Demo-Loop")
    print("  (regelbasiert – kein API-Key erforderlich)")
    print("=" * 60)

    print("\nVerfügbare Texttypen:")
    for key, val in TEMPLATES.items():
        print(f"  [{key}]  {val['label']}")

    typ = input("\nTexttyp eingeben: ").strip().lower()
    if typ not in TEMPLATES:
        print(f"Unbekannter Typ '{typ}'. Abbruch.")
        sys.exit(1)

    thema = input("Thema / Stichwörter: ").strip()
    if not thema:
        thema = "Beispielprodukt, Qualität, Innovation"

    print("\n" + "-" * 60)
    print(TEMPLATES[typ]["demo_fn"](thema))
    print("-" * 60)
    print("\n[Demo-Modus] Für echte KI-Ausgabe: ANTHROPIC_API_KEY setzen")
    print("             und live_mode() in diesem Script aktivieren.\n")


# ─── Live-Modus (auskommentiert – aktivieren für Produktion) ──────────────────

# def live_mode(typ: str, thema: str) -> str:
#     import anthropic, os
#     client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
#     tmpl = TEMPLATES[typ]
#     message = client.messages.create(
#         model="claude-sonnet-4-20250514",
#         max_tokens=512,
#         system=tmpl["system"],
#         messages=[{"role": "user", "content": f"Thema: {thema}"}],
#     )
#     return message.content[0].text


if __name__ == "__main__":
    run_demo()
