# Business Case · EVL-2026-002
**Version:** 1.0 | **Datum:** 2026-04-08

---

## Ausgangslage

Im Unternehmen erstellen aktuell 3 Mitarbeitende regelmäßig Website-Texte, Produktbeschreibungen und FAQ-Inhalte. Der Prozess umfasst Recherche, Schreiben, interne Abstimmung und Korrektur. Durchschnittlich entstehen so pro Woche ca. 6 Arbeitsstunden Aufwand allein für das Texten und Abstimmen.

---

## Quantitative Einsparung

| Parameter | Wert | Annahme |
|-----------|------|---------|
| Mitarbeitende, die texten | 3 | konservativ |
| Zeitaufwand pro Person/Woche (bisher) | 2 h | Schätzung Auftraggeber |
| Erwartete Zeitersparnis durch Tool | 65 % | Entwurf in 2 min statt 30 min |
| Verbleibender Aufwand (Prüfen, Freigabe) | 35 % | bleibt menschlich |
| Effektive Einsparung pro Woche | ~3,9 h | 6 h × 0,65 |
| Arbeitsstunden pro Jahr (50 Wochen) | ~195 h | |
| Ø Personalkosten (inkl. Nebenkosten) | 48 €/h | branchenüblich |
| **Einsparung Personalkosten/Jahr** | **~9.360 €** | |

### Laufende Tool-Kosten

| Position | Kosten/Monat |
|----------|-------------|
| Claude API (ca. 500 Anfragen × 1.000 Token) | ~35 € |
| Server (VPS, 4 GB RAM) | ~15 € |
| **Gesamt laufende Kosten/Jahr** | **~600 €** |

### Netto-Einsparung

| | Betrag |
|-|--------|
| Personalkosten-Einsparung/Jahr | 9.360 € |
| Laufende Tool-Kosten/Jahr | – 600 € |
| **Netto-Einsparung/Jahr** | **~8.760 €** |

---

## Projektkosten und Break-even

Angenommenes Projektbudget: **4.000 €** (untere Range für diese Projektgröße)

Break-even: 4.000 € ÷ (8.760 € / 12 Monate) = **ca. 5,5 Monate**

Ab Monat 6 arbeitet das System im Plus.

---

## Qualitative Vorteile

Konsistente Markenstimme in allen Website-Texten, unabhängig davon, welche Person textet. Mitarbeitende ohne Texter-Ausbildung können sofort hochwertige Entwürfe erstellen. Weniger Abstimmungsschleifen mit externen Agenturen oder Texter-Freelancern. Schnellere Reaktionsfähigkeit bei Produktneuheiten oder Kampagnen. Das System ist ohne Mehraufwand auf weitere Sprachen und Texttypen erweiterbar.

---

## Risiken und Grenzen

Das System erstellt Entwürfe – keine fertigen, veröffentlichungsreifen Texte. Menschliche Prüfung und Freigabe bleiben obligatorisch. Die Textqualität hängt von der Qualität der Wissensbasis ab; veraltete oder fehlerhafte Dokumente führen zu schlechteren Ergebnissen. Bei sehr spezifischen Fachthemen kann ein lokales Modell Qualitätsabstriche bedeuten (relevant nur bei vollständiger Offline-Variante).

---

## Empfehlung

Investition klar empfehlenswert. ROI innerhalb von 6 Monaten, danach ca. 8.760 € Nettoeinsparung pro Jahr bei konservativer Schätzung. Einstieg mit Claude API (Qualität), mittelfristig Prüfung lokales Modell (Datensouveränität + Kostenreduktion).
