# CHEV Spillplang

Spielplan aller Mannschaften von CHEV Handball Diekirch auf einer Seite – läuft komplett im Browser über GitHub Pages, ohne Backend. Die Termine werden jeden Morgen automatisch von [chev.lu](https://chev.lu/programme/) übernommen.

**Seite:** https://chev-diekirch.github.io/spillplang/

## Inhalt
- **Wochenende:** alle Spiele und Turniere des nächsten Wochenendes, nach Tag sortiert; mit ‹ › wochenweise vor- und zurückblättern. Spiele unter der Woche (z. B. Donnerstag) stehen darüber.
- **Mannschaft:** eine Mannschaft über einen frei wählbaren Zeitraum (Schnellwahl: ab heute, nächste 30 Tage, ganze Saison), nach Monaten gruppiert.
- **Heim / Auswärts:** Umschalter in beiden Ansichten, jeweils mit Anzahl.
- **Markierungen** wie auf chev.lu: Pokalspiele gelb, verlegte Spiele („remis“) rot. „Tag offen“ heißt, dass auf chev.lu nur das Wochenende feststeht.

„Heim“ = CHEV ist Gastgeber, oder ein Turnier in Diekirch. Die Halle selbst steht nicht auf chev.lu.

## Daten
Quelle sind die Team-Seiten auf chev.lu (`https://chev.lu/match/<mannschaft>/`), z. B. [Hommes 1](https://chev.lu/match/hommes-1/). Es steht also nur drin, was der Verein dort veröffentlicht – aktuell meist die Hinrunde, U7 hat keinen Spielplan.

Ablauf:
1. Die GitHub Action **Spielplan aktualisieren** startet jeden Morgen (05:45 Sommerzeit / 04:45 Winterzeit; GitHub startet oft ein paar Minuten später).
2. Sie führt `scrape.py` aus: das Skript lädt die 12 Team-Seiten, liest die Tabellen aus und schreibt alle Termine in `data.json`.
3. `data.json` wird gespeichert („Spielplan aktualisiert“ in der Commit-Liste). Das passiert jeden Tag, weil sich mindestens der Stand ändert.
4. Die Seite (`index.html`) lädt beim Öffnen `data.json` und zeigt den Stand oben im Kopf an.

Per Hand starten: **Actions → Spielplan aktualisieren → Run workflow**.

## Wenn chev.lu umgebaut wird
Das Skript prüft bei jedem Lauf, ob die Seiten noch wie erwartet aussehen. Als Störung gilt:
- eine Team-Seite ist nicht erreichbar,
- eine Mannschaft liefert plötzlich keine Termine mehr,
- die Tabelle hat andere Spalten oder ein anderes Datumsformat,
- in einer Zeile kommt kein CHEV-Team vor.

Dann behält die betroffene Mannschaft ihre alten Termine, der Lauf wird **rot** und GitHub schickt eine E-Mail. Auf der Seite steht hinter dem Datum „(teilweise veraltet)“. Welche Mannschaft betroffen ist und warum, steht im Lauf unter dem Schritt **chev.lu auslesen**.

## Dateien
| Datei | Was sie macht |
|---|---|
| `index.html` | Die Seite: Aussehen (CSS), Logo und die Logik für Wochenende, Mannschaft und Filter (JavaScript) |
| `data.json` | Alle Termine; wird automatisch überschrieben, nicht von Hand ändern |
| `scrape.py` | Python-Skript, das chev.lu ausliest (ausführlich auf Deutsch kommentiert) |
| `.github/workflows/update.yml` | Zeitplan und Schritte der täglichen Aktualisierung |

### Aufbau von `data.json`
```json
{
 "stand": "2026-10-05T06:01",
 "fehler": [],
 "spiele": [
  ["h1", "29101052", "08.10.26", "20:30", "CHEV", "Standard 1"]
 ]
}
```
Jede Zeile in `spiele`: Mannschaft, Spielnummer, Datum, Uhrzeit, Heim, Gast. Besonderheiten:
- Wochenende ohne festen Tag: Datum wie `27-29.11.26`
- verlegtes Spiel: Datum und Uhrzeit leer
- Turnier (U11, U9): Heim = `T`, Gast = Spielort

## Lokal testen
```bash
pip install requests beautifulsoup4
python scrape.py
```
Das Skript gibt pro Mannschaft die Anzahl Termine aus und schreibt `data.json` neu.

## Anpassen
**Neue Mannschaft:** an zwei Stellen eintragen, mit demselben Kürzel:
- in `scrape.py` im Block `TEAMS`: Kürzel und Adresse der Team-Seite, z. B. `"u15f": "u15-filles/",`
- in `index.html` in `const TEAMS`: Kürzel und Anzeigename, z. B. `["u15f","U15 Filles"],`

Spielt die Mannschaft Turniere statt Einzelspielen, zusätzlich in `scrape.py` bei `TURNIER_TEAMS` eintragen.

**Uhrzeit der Aktualisierung:** in `update.yml` die Zeile `cron: "45 3 * * *"` ändern (Minute, Stunde in UTC).
