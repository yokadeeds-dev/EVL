"""
EVL-2026-003 · Synthetische Legal-Dokumente
Generiert 1.000 realistische Legal-Dokumente für den PoC.

Kategorien:
  - Mandantendokumente (pro Mandat getrennt, Chinese-Wall-Paare)
  - Allgemeine Leitfäden (für alle sichtbar)
  - Präzedenzfälle (für alle sichtbar)

Ausgabe: docs/ Ordner mit .txt Dateien + metadata.json
"""

import json
import random
import uuid
from pathlib import Path

random.seed(42)

# ── Simulierte Nutzer & Mandate ───────────────────────────────────────────────

USERS = {
    "anwalt_a": {"name": "Dr. Anna Kraft",      "mandate": ["M001", "M003"]},
    "anwalt_b": {"name": "Prof. Bernd Schuster", "mandate": ["M002", "M003"]},
    "anwalt_c": {"name": "Maria Voss",           "mandate": ["M001", "M002", "M004"]},
}

# Chinese Wall: M001 <-> M002 (Gegenseitige Parteien)
CHINESE_WALLS = [("M001", "M002")]

MANDANTEN = {
    "M001": "TechCorp AG",
    "M002": "DigitalVentures GmbH",
    "M003": "Stadtwerke Hamm",
    "M004": "Müller Immobilien KG",
}

# ── Textbausteine ─────────────────────────────────────────────────────────────

VERTRAGSTYPEN = [
    "Kaufvertrag", "Dienstleistungsvertrag", "Mietvertrag",
    "Lizenzvertrag", "NDA", "Gesellschaftsvertrag", "Arbeitsvertrag",
]

KLAUSELN = [
    "§ 1 Vertragsgegenstand\nDer Auftragnehmer verpflichtet sich zur Erbringung der vereinbarten Leistungen "
    "gemäß den in Anlage A spezifizierten Bedingungen innerhalb der festgelegten Fristen.",

    "§ 2 Vergütung\nDie Vergütung beträgt {betrag} EUR zzgl. gesetzlicher MwSt. und ist innerhalb von "
    "30 Tagen nach Rechnungsstellung fällig. Bei Zahlungsverzug gilt § 288 BGB.",

    "§ 3 Haftung\nDie Haftung des Auftragnehmers ist auf Vorsatz und grobe Fahrlässigkeit beschränkt. "
    "Eine Haftung für mittelbare Schäden, entgangenen Gewinn oder Datenverlust ist ausgeschlossen.",

    "§ 4 Vertraulichkeit\nBeiden Parteien ist es untersagt, vertrauliche Informationen an Dritte "
    "weiterzugeben. Diese Verpflichtung gilt für die Dauer von 5 Jahren nach Vertragsende.",

    "§ 5 Gerichtsstand\nGerichtsstand für alle Streitigkeiten aus diesem Vertrag ist {ort}. "
    "Es gilt deutsches Recht unter Ausschluss des UN-Kaufrechts.",

    "§ 6 Kündigung\nDer Vertrag kann von beiden Parteien mit einer Frist von {frist} Wochen "
    "zum Monatsende gekündigt werden. Das Recht zur außerordentlichen Kündigung bleibt unberührt.",

    "§ 7 Datenschutz\nDie Parteien verpflichten sich zur Einhaltung der DSGVO sowie der "
    "anwendbaren nationalen Datenschutzgesetze. Eine Auftragsverarbeitungsvereinbarung "
    "ist als Anlage B beigefügt.",
]

PRAEZEDENZFAELLE = [
    ("BGH-Urteil zu Softwarelizenzrecht",
     "Der BGH hat mit Urteil vom {datum} (Az. {az}) entschieden, dass die Erschöpfungslehre "
     "auch auf Software-Downloads Anwendung findet. Der Ersterwerber kann seine Lizenz "
     "weiterveräußern, sofern er seine eigene Kopie unbrauchbar macht."),

    ("OLG Düsseldorf zu Haftungsausschluss AGB",
     "Das OLG Düsseldorf hat Klauseln, die Haftung für leichte Fahrlässigkeit vollständig "
     "ausschließen, als unwirksam nach § 309 Nr. 7 BGB eingestuft. Az. {az}."),

    ("EuGH zu DSGVO-Schadensersatz",
     "Der EuGH hat klargestellt, dass ein immaterieller Schaden im Sinne des Art. 82 DSGVO "
     "nicht die Erheblichkeitsschwelle überwinden muss. Jeder Kontrollverlust über "
     "personenbezogene Daten kann schadensersatzbegründend sein."),

    ("BAG zu Homeoffice-Vereinbarungen",
     "Das BAG hat entschieden, dass einseitige Widerrufsvorbehalte in Homeoffice-Vereinbarungen "
     "einer AGB-Kontrolle standhalten müssen. Az. {az}."),

    ("LG München zu KI-generierten Inhalten",
     "Das LG München hat festgestellt, dass KI-generierte Texte ohne menschliche Schöpfungshöhe "
     "nicht urheberrechtlich schutzfähig sind. Dies gilt unabhängig vom verwendeten Modell."),
]

LEITFAEDEN = [
    ("Interne Richtlinie: Mandatsprüfung und Interessenkonflikte",
     "Vor Annahme eines neuen Mandats ist zwingend eine Konfliktprüfung im Fallverwaltungssystem "
     "durchzuführen. Bei Zweifeln ist die Bereichsleitung zu konsultieren. Chinese Walls sind "
     "im System einzutragen und betreffen alle am Mandat beteiligten Personen."),

    ("Datenschutz-Leitfaden für Anwälte",
     "Mandantendaten dürfen ausschließlich auf freigegebenen Systemen verarbeitet werden. "
     "Die Nutzung privater Geräte oder Cloud-Dienste ohne explizite IT-Freigabe ist untersagt. "
     "Verstöße sind unverzüglich der Datenschutzbeauftragten zu melden."),

    ("Kommunikationsrichtlinie: Verschlüsselung",
     "Alle Mandantenkommunikation per E-Mail muss S/MIME oder PGP-verschlüsselt erfolgen. "
     "Unverschlüsselte Übertragung vertraulicher Dokumente ist verboten."),

    ("Abrechnung und Stundensätze 2026",
     "Partner: 450 EUR/h | Senior Associate: 320 EUR/h | Associate: 220 EUR/h | "
     "Paralegal: 120 EUR/h. Reisezeiten werden zu 50% abgerechnet. "
     "Alle Zeiten sind täglich im Zeiterfassungssystem einzutragen."),

    ("Notfallprotokoll: Datenpanne",
     "Bei Verdacht auf eine Datenpanne ist innerhalb von 2 Stunden die Datenschutzbeauftragte "
     "zu informieren. Die Behördenmeldung nach Art. 33 DSGVO muss innerhalb von 72 Stunden erfolgen."),
]

# ── Generator ─────────────────────────────────────────────────────────────────

def make_vertrag(mandant_id: str, mandant_name: str, idx: int) -> tuple[str, dict]:
    vtype = random.choice(VERTRAGSTYPEN)
    partner = random.choice([
        "Mustermann GmbH", "Alpha Solutions AG", "Beta Partners KG",
        "Gamma Consulting", "Delta Systems SE",
    ])
    betrag = random.choice([15000, 48000, 125000, 280000, 950000])
    frist = random.choice([4, 8, 12])
    ort = random.choice(["Hamburg", "München", "Berlin", "Frankfurt am Main", "Düsseldorf"])
    datum = f"2026-0{random.randint(1,9)}-{random.randint(10,28)}"

    klauseln = random.sample(KLAUSELN, k=random.randint(3, 6))
    text_klauseln = "\n\n".join(
        k.format(betrag=betrag, frist=frist, ort=ort) for k in klauseln
    )

    text = (
        f"{vtype}\n"
        f"zwischen {mandant_name} (nachfolgend 'Auftraggeber')\n"
        f"und {partner} (nachfolgend 'Auftragnehmer')\n"
        f"Datum: {datum}\n\n"
        f"{text_klauseln}\n\n"
        f"Unterzeichnet am {datum}\n"
        f"{mandant_name}                    {partner}"
    )

    meta = {
        "doc_id": str(uuid.uuid4()),
        "doc_type": "vertrag",
        "mandant_id": mandant_id,
        "mandant_name": mandant_name,
        "title": f"{vtype} #{idx:04d} – {mandant_name}",
        "date": datum,
        "category": "mandant_dokumente",
    }
    return text, meta


def make_praezedenz(idx: int) -> tuple[str, dict]:
    template_title, template_text = random.choice(PRAEZEDENZFAELLE)
    az = f"{random.randint(1,12)} {random.choice(['ZR','U','O','K'])} {random.randint(10,999)}/{random.randint(20,26)}"
    datum = f"202{random.randint(0,5)}-{random.randint(1,12):02d}-{random.randint(1,28):02d}"
    text = f"{template_title}\n\n{template_text.format(az=az, datum=datum)}"
    meta = {
        "doc_id": str(uuid.uuid4()),
        "doc_type": "praezedenzfall",
        "mandant_id": None,
        "title": f"{template_title} ({az})",
        "date": datum,
        "category": "praezedenzfaelle",
    }
    return text, meta


def make_leitfaden(idx: int) -> tuple[str, dict]:
    title, body = random.choice(LEITFAEDEN)
    text = f"{title}\n\nStand: 2026-01-01\n\n{body}"
    meta = {
        "doc_id": str(uuid.uuid4()),
        "doc_type": "leitfaden",
        "mandant_id": None,
        "title": title,
        "date": "2026-01-01",
        "category": "leitfaeden_allgemein",
    }
    return text, meta


def generate_docs(output_dir: str = "./docs", n_total: int = 1000):
    out = Path(output_dir)
    out.mkdir(exist_ok=True)

    docs = []
    idx = 0

    # 700 Mandantendokumente (verteilt auf Mandate)
    mandate_list = list(MANDANTEN.items())
    for i in range(700):
        mandant_id, mandant_name = mandate_list[i % len(mandate_list)]
        text, meta = make_vertrag(mandant_id, mandant_name, i)
        fname = f"vertrag_{mandant_id}_{i:04d}.txt"
        (out / fname).write_text(text, encoding="utf-8")
        meta["filename"] = fname
        docs.append(meta)
        idx += 1

    # 150 Präzedenzfälle
    for i in range(150):
        text, meta = make_praezedenz(i)
        fname = f"praezedenz_{i:04d}.txt"
        (out / fname).write_text(text, encoding="utf-8")
        meta["filename"] = fname
        docs.append(meta)

    # 150 Leitfäden
    for i in range(150):
        text, meta = make_leitfaden(i)
        fname = f"leitfaden_{i:04d}.txt"
        (out / fname).write_text(text, encoding="utf-8")
        meta["filename"] = fname
        docs.append(meta)

    # Metadata speichern
    (out / "metadata.json").write_text(
        json.dumps(docs, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"✓ {len(docs)} Dokumente generiert in {out}/")
    print(f"  Mandantendokumente : {sum(1 for d in docs if d['category']=='mandant_dokumente')}")
    print(f"  Präzedenzfälle     : {sum(1 for d in docs if d['category']=='praezedenzfaelle')}")
    print(f"  Leitfäden          : {sum(1 for d in docs if d['category']=='leitfaeden_allgemein')}")
    return docs


if __name__ == "__main__":
    generate_docs()
