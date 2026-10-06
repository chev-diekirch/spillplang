"""
Liest die Spielpläne aller CHEV-Mannschaften von chev.lu und schreibt sie in data.json.

Ablauf:
1. Jede Team-Seite (z. B. https://chev.lu/match/hommes-1/) herunterladen.
2. Die Tabelle mit den Spielen suchen und Zeile für Zeile auslesen.
3. Die Werte vereinheitlichen (z. B. "20H15" -> "20:15", "CHEV 1" -> "CHEV").
4. Prüfen, ob die Seite noch so aussieht wie erwartet (Störungsprüfung).
5. Alles in data.json speichern. Die WebApp (index.html) liest diese Datei.

Gibt es eine Störung, behält das betroffene Team seine alten Daten,
und das Skript endet mit Fehlercode 1. Dadurch schlägt der GitHub-Lauf fehl
und GitHub schickt eine E-Mail.
"""

import difflib       # vergleicht ähnliche Namen (z. B. Tippfehler bei Gegnern)
import json          # zum Lesen/Schreiben von data.json
import re            # "reguläre Ausdrücke": Muster in Texten erkennen
import sys           # für sys.exit (Fehlercode zurückgeben)
from datetime import datetime
from zoneinfo import ZoneInfo

import requests                  # lädt Webseiten herunter
from bs4 import BeautifulSoup    # zerlegt HTML, damit wir die Tabelle finden

BASIS = "https://chev.lu/match/"

# Kürzel in der App  ->  Adresse der Team-Seite auf chev.lu
TEAMS = {
    "h1": "hommes-1/",
    "d1": "dames-1/",
    "h2": "hommes-2/",
    "d2": "dames-2/",
    "u17g": "u17-garcons/",
    "u17f": "u17-filles/",
    "u15g": "u15-garcons/",
    "u13g": "u13-garcons/",
    "u13m": "u13-mixtes",
    "u11": "u11-mixtes/",
    "u9": "u9-mixtes/",
    "u7": "u7-mixtes-wibbelgrupp/",
}
TURNIER_TEAMS = {"u11", "u9"}   # spielen Turniere statt Einzelspielen
OHNE_PLAN_OK = {"u7"}           # hat (bisher) keinen Spielplan, das ist normal

# Ergebnisse: Kürzel -> Adresse der Ergebnis-Seite auf chev.lu (nur diese Teams haben eine)
BASIS_ERGEBNIS = "https://chev.lu/result/"
ERGEBNIS_SEITEN = {
    "h1": "hommes-1/", "d1": "dames-1/", "h2": "hommes-2/", "d2": "dames-2/",
    "u17g": "u17-garcons/", "u17f": "u17-filles/", "u15g": "u15-garcons/",
    "u13g": "u13-garcons/", "u13m": "u13-mixtes/",
}
# Ergebnis wie "35 - 19" (auch mit Zusatz wie "(forfait)")
ERGEBNIS = re.compile(r"^(\d{1,3})\s*[-:]\s*(\d{1,3})\b")

# Muster für gültige Daten: "26.09.26" oder Wochenende "27-29.11.26"
DATUM = re.compile(r"^\d{2}\.\d{2}\.\d{2}$")
DATUM_SPANNE = re.compile(r"^\d{1,2}-\d{1,2}\.\d{2}\.\d{2}$")


def text(zelle):
    """Sichtbarer Text einer Tabellenzelle, ohne doppelte Leerzeichen."""
    return " ".join(zelle.get_text(" ").split())


def zeit_umwandeln(z):
    """'20H15' -> '20:15'. Alles andere (leer, '—') wird zu ''."""
    m = re.match(r"^(\d{1,2})\s*[Hh:]\s*(\d{2})$", z)
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else ""


def eigenes_team(name):
    """'CHEV', 'CHEV 1', 'CHEV U17 Garçons' ... -> 'CHEV'. Gegner bleiben unverändert."""
    return "CHEV" if name.upper().startswith("CHEV") else name


def tabelle_lesen(html):
    """
    Sucht die Spieltabelle und gibt ihre Zeilen als Listen von Texten zurück.
    Erkennt die Tabelle an den Spaltenköpfen DATE und HEURE.
    Rückgabe: (spalten_index, zeilen) oder (None, []) wenn keine Tabelle passt.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tabelle in soup.find_all("table"):
        zeilen = tabelle.find_all("tr")
        if not zeilen:
            continue
        kopf = [text(z).upper() for z in zeilen[0].find_all(["th", "td"])]
        if "DATE" not in kopf or "HEURE" not in kopf:
            continue
        # Position jeder Spalte merken (falls die Reihenfolge sich mal ändert)
        idx = {
            "nr": 0,
            "datum": kopf.index("DATE"),
            "zeit": kopf.index("HEURE"),
            "heim": kopf.index("LOCAL") if "LOCAL" in kopf else None,
            "gast": kopf.index("VISITEUR") if "VISITEUR" in kopf else None,
            "kopf": kopf,
        }
        daten = []
        for tr in zeilen[1:]:
            zellen = [text(td) for td in tr.find_all(["td", "th"])]
            if any(zellen):          # leere Trennzeilen überspringen
                daten.append(zellen)
        return idx, daten
    return None, []


def team_auswerten(team, html):
    """
    Wandelt eine Team-Seite in Zeilen für data.json um:
    [team, nr, datum, zeit, heim, gast]
    Gibt (zeilen, probleme) zurück. probleme ist eine Liste mit Texten.
    """
    idx, daten = tabelle_lesen(html)
    if idx is None:
        if team in OHNE_PLAN_OK:
            return [], []          # kein Spielplan veröffentlicht: kein Fehler
        return [], ["keine Spieltabelle gefunden"]
    if team in TURNIER_TEAMS and idx["heim"] is None:
        # Turnier-Tabellen haben keine Spalte LOCAL: der Ort steht direkt hinter HEURE
        idx["heim"] = idx["zeit"] + 1
    elif idx["heim"] is None or idx["gast"] is None:
        return [], [f"Spalten LOCAL/VISITEUR fehlen (gefunden: {idx['kopf']})"]

    ergebnis, probleme = [], []
    for nummer, z in enumerate(daten, start=1):
        def feld(name):
            i = idx[name]
            return z[i] if i is not None and i < len(z) else ""

        nr, datum, zeit = feld("nr"), feld("datum"), feld("zeit")
        if team in TURNIER_TEAMS and nummer == 1:
            print(f"   {team} Spalten: {idx['kopf']} | erste Zeile: {z}")
        heim, gast = feld("heim"), feld("gast")

        # Verlegte Spiele: auf chev.lu steht dann "remis" statt Datum
        if "remis" in " ".join(z).lower():
            datum, zeit = "", ""
        elif not (DATUM.match(datum) or DATUM_SPANNE.match(datum)):
            probleme.append(f"unbekanntes Datum '{datum}' in Zeile {nummer}")
            continue

        if team in TURNIER_TEAMS:
            # Turnier: Ort steht in der Heim-Spalte, evtl. als "Tournoi U9 Mixtes à Diekirch"
            ort = heim.split(" à ")[-1] if " à " in heim else heim
            ort = "" if ort in ("—", "-") else ort
            ergebnis.append([team, nr or f"Tournoi {nummer}", datum, zeit_umwandeln(zeit), "T", ort])
        else:
            heim, gast = eigenes_team(heim), eigenes_team(gast)
            if "CHEV" not in (heim, gast):
                probleme.append(f"kein CHEV-Team in Zeile {nummer} ({heim} - {gast})")
                continue
            ergebnis.append([team, nr, datum, zeit_umwandeln(zeit), heim, gast])

    if not ergebnis and team not in OHNE_PLAN_OK:
        probleme.append("keine Termine gefunden")
    return ergebnis, probleme


def schluessel(zeilen):
    """
    Gibt jedem Spiel einen festen Namen, z. B. "h1|29101052" (Mannschaft|Spielnummer).
    Darüber erkennen wir dasselbe Spiel am nächsten Tag wieder, auch wenn sich
    Datum oder Uhrzeit geändert haben. Kommt eine Nummer doppelt vor, wird "#2" angehängt.
    """
    ergebnis, gesehen = {}, {}
    for z in zeilen:
        k = f"{z[0]}|{z[1]}"
        gesehen[k] = gesehen.get(k, 0) + 1
        if gesehen[k] > 1:
            k += f"#{gesehen[k]}"
        ergebnis[k] = z
    return ergebnis


def aenderungen_finden(alte_zeilen, neue_zeilen, bisher, jetzt):
    """
    Vergleicht die Termine einer Mannschaft von gestern (alte_zeilen) und heute (neue_zeilen).
    Rückgabe: Wörterbuch Schlüssel -> {"am": Zeitpunkt, "vorher": [Datum, Zeit, Heim, Gast]}
              bzw. {"am": Zeitpunkt, "neu": True} für Spiele, die neu dazugekommen sind.
    'bisher' sind die früher gefundenen Änderungen; sie bleiben erhalten,
    solange es das Spiel noch gibt.
    """
    alt, neu = schluessel(alte_zeilen), schluessel(neue_zeilen)
    ergebnis = {}
    for k, z in neu.items():
        if k in alt and alt[k][2:6] != z[2:6]:
            # Datum, Uhrzeit, Heim oder Gast anders als gestern
            ergebnis[k] = {"am": jetzt, "vorher": alt[k][2:6]}
            print(f"   geändert: {k}  {alt[k][2:6]} -> {z[2:6]}")
        elif k not in alt and alt:
            # Spiel gab es gestern noch nicht (nur wenn die Mannschaft schon Termine hatte)
            ergebnis[k] = {"am": jetzt, "neu": True}
            print(f"   neu: {k}  {z[2:6]}")
        elif k in bisher:
            ergebnis[k] = bisher[k]      # ältere Änderung weiter merken
    return ergebnis


def ergebnisse_lesen(html):
    """
    Liest alle Ergebniszeilen einer Ergebnis-Seite.
    Eine Zeile sieht so aus:  [Coupe 1/8 |] Heim | - | Gast | 35 - 19
    Erkennungsmerkmal: eine Zelle nur mit "-" und danach eine Zelle mit Ergebnis.
    (Die Tabellenstand-Tabelle hat keine "-"-Zelle und wird dadurch übersprungen.)
    Rückgabe: Liste von (heim, gast, tore_heim, tore_gast, pokal_ja_nein)
    """
    soup = BeautifulSoup(html, "html.parser")
    liste = []
    for tr in soup.find_all("tr"):
        zellen = [text(td) for td in tr.find_all(["td", "th"])]
        if "-" not in zellen:
            continue
        d = zellen.index("-")
        if d < 1 or d + 2 >= len(zellen):
            continue
        m = ERGEBNIS.match(zellen[d + 2])
        if not m:
            continue        # Spiel noch ohne Ergebnis
        pokal = d >= 2 and "coupe" in zellen[d - 2].lower()
        liste.append((eigenes_team(zellen[d - 1]), eigenes_team(zellen[d + 1]),
                      int(m.group(1)), int(m.group(2)), pokal))
    return liste


def tabellenstand_lesen(html):
    """
    Sucht die Tabelle mit dem Tabellenstand (Spaltenköpfe u. a. "Equipes" und "Pts").
    Rückgabe: {"kopf": [...], "zeilen": [[...], ...]} oder None, wenn es keine gibt.
    Die Werte werden so übernommen, wie sie auf chev.lu stehen.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tabelle in soup.find_all("table"):
        trs = tabelle.find_all("tr")
        if len(trs) < 2:
            continue
        kopf = [text(z) for z in trs[0].find_all(["th", "td"])]
        if "EQUIPES" not in [k.upper() for k in kopf] or "PTS" not in [k.upper() for k in kopf]:
            continue
        zeilen = [[text(td) for td in tr.find_all(["td", "th"])] for tr in trs[1:]]
        zeilen = [z for z in zeilen if any(z)]
        # Erste Spalte (Platz) hat oft keinen Kopf: dann "#" davor setzen
        if zeilen and len(zeilen[0]) == len(kopf) + 1:
            kopf = ["#"] + kopf
        elif kopf and not kopf[0]:
            kopf[0] = "#"
        return {"kopf": kopf, "zeilen": zeilen}
    return None


def aehnlich(a, b):
    """True, wenn zwei Mannschaftsnamen gleich oder fast gleich sind (Tippfehler)."""
    a, b = a.lower().strip(), b.lower().strip()
    return a == b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.85


def ergebnisse_zuordnen(team_zeilen, ergebnisse):
    """
    Ordnet jedes Ergebnis dem passenden Spiel im Spielplan zu.
    Die Ergebnis-Seite hat kein Datum. Deshalb suchen wir das früheste noch freie Spiel
    mit gleichem Heim- und Gastteam (Pokalspiele nur mit Pokalspielen).
    Rückgabe: (Wörterbuch Schlüssel -> "35:19", Liste nicht zugeordneter Ergebnisse)
    """
    schl = schluessel(team_zeilen)
    # Spiele in zeitlicher Reihenfolge (verlegte Spiele ohne Datum ans Ende)
    def zeitpunkt(z):
        if not DATUM.match(z[2]):
            return (9999, 99, 99)
        t, mo, j = z[2].split(".")
        return (int(j), int(mo), int(t))
    reihenfolge = sorted(schl.items(), key=lambda kv: zeitpunkt(kv[1]))
    vergeben, zuordnung, offen = set(), {}, []
    for heim, gast, th, tg, pokal in ergebnisse:
        for k, z in reihenfolge:
            if k in vergeben or z[4] == "T":
                continue
            if pokal != ("coupe" in z[1].lower()):
                continue
            if aehnlich(z[4], heim) and aehnlich(z[5], gast):
                zuordnung[k] = f"{th}:{tg}"
                vergeben.add(k)
                break
        else:
            offen.append(f"{heim} - {gast} {th}:{tg}")
    return zuordnung, offen


def main():
    # Bisherige Daten laden, damit gestörte Teams ihre alten Termine behalten
    try:
        with open("data.json", encoding="utf-8") as f:
            alt = json.load(f)
    except FileNotFoundError:
        alt = {"spiele": []}

    jetzt = datetime.now(ZoneInfo("Europe/Luxembourg")).strftime("%Y-%m-%dT%H:%M")
    alte_aenderungen = alt.get("aenderungen", {})

    neue_zeilen, fehler, aenderungen = [], [], {}
    for team, pfad in TEAMS.items():
        alte_team_zeilen = [z for z in alt["spiele"] if z[0] == team]
        try:
            antwort = requests.get(BASIS + pfad, timeout=30,
                                   headers={"User-Agent": "CHEV-Spillplang (github.com/chev-diekirch/spillplang)"})
            antwort.raise_for_status()   # Fehler wie 404 werden hier zur Ausnahme
            zeilen, probleme = team_auswerten(team, antwort.text)
            if probleme:
                # Zur Fehlersuche: zeigen, was chev.lu statt der Tabelle geschickt hat
                seite = BeautifulSoup(antwort.text, "html.parser")
                titel = seite.title.get_text(strip=True) if seite.title else "(kein Titel)"
                anfang = " ".join(seite.get_text(" ").split())[:200]
                print(f"   {team}: HTTP {antwort.status_code}, {len(antwort.text)} Zeichen, "
                      f"Adresse {antwort.url}, Titel '{titel}'")
                print(f"   {team}: Textanfang: {anfang}")
        except requests.RequestException as e:
            zeilen, probleme = [], [f"Seite nicht erreichbar: {e}"]

        bisher = {k: v for k, v in alte_aenderungen.items() if k.startswith(team + "|")}
        if probleme:
            fehler.append(f"{team}: " + "; ".join(probleme))
            neue_zeilen += alte_team_zeilen       # alte Daten behalten
            aenderungen.update(bisher)            # und auch die alten Änderungen
        else:
            neue_zeilen += zeilen
            aenderungen.update(aenderungen_finden(alte_team_zeilen, zeilen, bisher, jetzt))
        print(f"{team:5} {len(zeilen):3} Termine  {'FEHLER: ' + '; '.join(probleme) if probleme else 'ok'}")

    # ---------- Ergebnisse ----------
    alte_resultate = alt.get("resultate", {})
    alte_tabellen = alt.get("tabellen", {})
    resultate, tabellen = {}, {}
    for team, pfad in ERGEBNIS_SEITEN.items():
        bisher = {k: v for k, v in alte_resultate.items() if k.startswith(team + "|")}
        team_zeilen = [z for z in neue_zeilen if z[0] == team]
        try:
            antwort = requests.get(BASIS_ERGEBNIS + pfad, timeout=30,
                                   headers={"User-Agent": "CHEV-Spillplang (github.com/chev-diekirch/spillplang)"})
            antwort.raise_for_status()
            liste = ergebnisse_lesen(antwort.text)
        except requests.RequestException as e:
            fehler.append(f"{team} Ergebnisse: Seite nicht erreichbar: {e}")
            resultate.update(bisher)
            if team in alte_tabellen:
                tabellen[team] = alte_tabellen[team]
            continue

        # Tabellenstand (steht auf derselben Seite)
        stand = tabellenstand_lesen(antwort.text)
        if stand:
            tabellen[team] = stand
        elif team in alte_tabellen:
            fehler.append(f"{team} Tabelle: Tabellenstand nicht mehr gefunden")
            tabellen[team] = alte_tabellen[team]
        if not liste and bisher:
            # Gestern gab es Ergebnisse, heute keine einzige: Seite vermutlich umgebaut
            fehler.append(f"{team} Ergebnisse: keine Ergebnisse mehr gefunden")
            resultate.update(bisher)
            continue
        zuordnung, offen = ergebnisse_zuordnen(team_zeilen, liste)
        resultate.update(zuordnung)
        print(f"{team:5} {len(zuordnung):3} Ergebnisse zugeordnet"
              + (f", nicht zugeordnet: {'; '.join(offen)}" if offen else ""))

    with open("data.json", "w", encoding="utf-8") as f:
        json.dump({"stand": jetzt, "fehler": fehler, "spiele": neue_zeilen,
                   "aenderungen": aenderungen, "resultate": resultate, "tabellen": tabellen},
                  f, ensure_ascii=False, indent=1)

    if fehler:
        print("\nSTÖRUNG – chev.lu evtl. umgebaut. Betroffen:")
        for f_ in fehler:
            print(" -", f_)
        sys.exit(1)   # lässt den GitHub-Lauf fehlschlagen -> E-Mail


if __name__ == "__main__":
    main()
