"""Phase 9: Live-Abgleich mit Bild-CDN (ab Phase 45 auch die Bildformate small und normal samt Größe), Scryfall (ab Phase 31 auch die Gesamtdaten, ab Phase 45 deren Größen), EDHREC (ab Phase 21 auch Salt), Commander Spellbook und (Phase 14) Cardmarket-Preisliste: stimmen Formate und Annahmen noch?
Liest die Datenbank nur lesend (MTG_DB oder data/mtg.db) und braucht Netz. ca. 30 s, wenige Anfragen, Rate-Limits über sources._call.
Aufruf: .venv/Scripts/python tests/live_check.py   (nicht Teil von pytest; Ende mit Code 1, wenn etwas nicht mehr passt)"""
import json
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import deckbuild  # noqa: E402
import katalog  # noqa: E402
import mtg  # noqa: E402
import sources  # noqa: E402

fehler = []


def pruefe(name, ok, detail):
    print(f"{'ok  ' if ok else 'FEHL'} {name}: {detail}")
    if not ok:
        fehler.append(name)


def head(url):
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": sources.HEADERS["User-Agent"], "Accept": "image/*"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        return e.code, ""


def bilder(conn):
    """Bild-CDN (kein Limit): normal, small und art_crop einer normalen, einer doppelseitigen und einer geteilten Karte."""
    erst = lambda layout: conn.execute("SELECT name, image_url FROM cards WHERE json_extract(json, '$.layout') = ? LIMIT 1", (layout,)).fetchone()
    ok = n = 0
    for layout in ("normal", "transform", "split"):
        karte = erst(layout)
        for variante in ("normal", "small", "art_crop") if karte else ():
            status, typ = head(karte["image_url"].replace("/normal/", f"/{variante}/"))
            n, ok = n + 1, ok + (status == 200 and typ.startswith("image/"))
            time.sleep(0.1)
    pruefe("Bilder", n > 0 and ok == n, f"{ok}/{n} Abrufe HTTP 200 (normal, small, art_crop; auch doppelseitig und geteilt)")


def scryfall(conn):
    """Namenssuche (/cards/collection) und Anzahl einer Tag-Suche (/cards/search) gegen die gespeicherten Rollen-Tags."""
    karten, fehlt = sources.scryfall_names(["Sol Ring", "Xyzzy Fakecard"])
    pruefe("Scryfall Namenssuche", len(karten) == 1 and len(fehlt) == 1 and "eur" in karten[0]["prices"], f"{len(karten)} gefunden, {len(fehlt)} nicht gefunden")
    d = sources._call("https://api.scryfall.com/cards/search?" + urllib.parse.urlencode({"q": "otag:boardwipe f:commander", "unique": "cards"}))
    alt = conn.execute("SELECT COUNT(*) FROM tags WHERE tag = 'boardwipe'").fetchone()[0]
    pruefe("Scryfall Tag-Suche", alt == 0 or abs(d["total_cards"] - alt) <= 0.15 * alt, f"otag:boardwipe {d['total_cards']} Treffer, gespeichert {alt}")


def edhrec(conn):
    """Zwei Commander frisch von EDHREC: gleiches Format (parse_edhrec) und ähnlich viele Karten wie im Cache."""
    slugs = [r[0] for r in conn.execute("SELECT slug FROM edhrec WHERE json != 'null' ORDER BY slug LIMIT 2")]
    for sl in slugs:
        neu = deckbuild.parse_edhrec(sources.edhrec_commander(sl))
        alt = deckbuild.edhrec_cached(conn, sl)[1]
        pruefe(f"EDHREC {sl}", abs(len(neu["cards"]) - len(alt["cards"])) <= 0.1 * len(alt["cards"]) and neu["decks"] > 0,
               f"{len(neu['cards'])} Karten (Cache {len(alt['cards'])}), {neu['decks']} Decks")
    if not slugs:
        print("---- EDHREC: Cache leer, übersprungen (erst mtg commanders)")
        return
    # Themenseite (Phase 10): gleiche Form wie die Commander-Seite, Themen mit Slug, Karten nur aus Decks des Themas
    neu = deckbuild.parse_edhrec(sources.edhrec_commander(slugs[0]))
    th = next((t for t in neu["themes"] if t[0].lower() not in deckbuild.GENERIC), None)
    if th:
        seite = deckbuild.parse_edhrec(sources.edhrec_commander(f"{slugs[0]}/{th[2]}"))
        pruefe(f"EDHREC Thema {slugs[0]}/{th[2]}", len(seite["cards"]) > 20 and seite["decks"] > 0 and len(th) == 3,
               f"{len(seite['cards'])} Karten, {seite['decks']} Decks (Thema {th[0]}, zählt {seite['decks'] / (seite['decks'] + deckbuild.THEME_PRIOR):.0%})")


def spellbook():
    """find-my-combos mit einer bekannten 2-Karten-Combo: Antwortform, die combo_news erwartet."""
    r = sources.spellbook_combos({"main": [{"card": "Thassa's Oracle", "quantity": 1}, {"card": "Demonic Consultation", "quantity": 1}], "commanders": []})
    combos = r["results"]["included"]
    namen = {u["card"]["name"] for c in combos for u in c["uses"]}
    pruefe("Commander Spellbook", bool(combos) and namen >= {"Thassa's Oracle", "Demonic Consultation"} and "feature" in combos[0]["produces"][0],
           f"{len(combos)} Combo(s), Ergebnis: {combos[0]['produces'][0]['feature']['name'] if combos else '-'}")
    # Phase 11: estimate-bracket (Bracket-Check) mit derselben Combo und einem Game Changer; bracket_check liest genau diese Felder
    liste = "Commander\n1 Kenrith, the Returned King\n\nDeck\n1 Thassa's Oracle\n1 Demonic Consultation\n1 Rhystic Study\n1 Sol Ring\n"
    r = deckbuild.bracket_check(liste, sources.spellbook_bracket)
    pruefe("Spellbook Bracket", r["min_bracket"] == 4 and "Rhystic Study" in r["game_changers"] and any(c["two_card"] for c in r["combos"]) and r["spellbook"] in deckbuild.BRACKET_TAG.values(),
           f"mindestens Bracket {r['min_bracket']}, {len(r['game_changers'])} Game Changer, {len(r['combos'])} Combo(s), Spellbook: {r['spellbook']}")


def cardmarket(conn):
    """Phase 14: Cardmarket-Preisliste (26 MB, einmal): Aufbau und Zuordnung über cardmarket_id der eigenen Karten (in einer Kopie im Speicher)."""
    text = sources.cardmarket_guide()
    kopie = sqlite3.connect(":memory:")
    conn.backup(kopie)
    kopie.row_factory = sqlite3.Row
    eigene = kopie.execute("SELECT COUNT(DISTINCT json_extract(c.json, '$.cardmarket_id')) FROM collection col JOIN cards c USING (scryfall_id)").fetchone()[0]
    n = mtg.cardmarket_store(kopie, text)
    pruefe("Cardmarket-Preisliste", '"priceGuides"' in text[:200] and (eigene == 0 or n >= 0.9 * eigene),
           f"{len(text) / 1e6:.1f} MB, {n} von {eigene} eigenen Produkten zugeordnet")


def salt():
    """Phase 21: Salt-Liste von EDHREC (Top 100), Form wie sources.edhrec_salt sie liest."""
    liste = sources.edhrec_salt()
    pruefe("EDHREC Salt", len(liste) >= 50 and all(0 <= s <= 4 for _, s in liste), f"{len(liste)} Karten, salzigste: {liste[0][0]} ({liste[0][1]:.2f})")


def bildformate():
    """Phase 45: Scryfall nennt je Karte noch image_uris.small und .normal (die Erkennung rechnet ihre Fingerabdrücke aus small, die Oberfläche zeigt
    normal), beide Adressen antworten, und die kleine Größe hat die Größenordnung, mit der die Oberfläche rechnet (KAT_BILD_KB in ui/app.js, eine
    Schätzung vor dieser Probe). Drei Karten, sechs HEAD-Abrufe auf dem Bild-CDN (kein Limit)."""
    karten, _ = sources.scryfall_names(["Sol Ring", "Lightning Bolt", "Counterspell"])
    uris = [(k.get("image_uris") or {}) for k in karten]
    da = len(karten) == 3 and all(u.get("small") and u.get("normal") for u in uris)
    groessen = []
    for u in uris if da else ():
        for variante in ("small", "normal"):
            req = urllib.request.Request(u[variante], method="HEAD", headers={"User-Agent": sources.HEADERS["User-Agent"], "Accept": "image/*"})
            with urllib.request.urlopen(req, timeout=30) as r:
                groessen.append((variante, r.status, int(r.headers.get("Content-Length") or 0)))
            time.sleep(0.1)
    klein = [g for v, _, g in groessen if v == "small"]
    schnitt = sum(klein) / len(klein) / 1000 if klein else 0
    kb = next((int(z) for z in re.findall(r"KAT_BILD_KB = (\d+)", (Path(__file__).parent.parent / "ui" / "app.js").read_text(encoding="utf-8"))), 0)
    pruefe("Bildformate", da and len(groessen) == 6 and all(s == 200 for _, s, _ in groessen) and kb and 0.5 * kb <= schnitt <= 2 * kb,
           f"small und normal da und HTTP 200; small im Schnitt {schnitt:.1f} KB (die Oberfläche rechnet mit {kb} KB: bei starker Abweichung KAT_BILD_KB anpassen)")


def gesamtdaten_groessen():
    """Phase 45: /bulk-data nennt für default_cards und all_cards noch compressed_size (der Fortschritt des Hintergrund-Jobs rechnet damit), und die
    Größen liegen in der Nähe dessen, was die Oberfläche anzeigt (katalog.KATALOG_MB und DEUTSCH_MB, Stand 2026-10-12)."""
    daten = {x["type"]: x.get("compressed_size") for x in sources._call("https://api.scryfall.com/bulk-data")["data"]}
    mb = lambda t: (daten.get(t) or 0) / 1e6
    pruefe("Größen der Gesamtdaten", all(0.5 * soll <= mb(t) <= 2 * soll for t, soll in (("default_cards", katalog.KATALOG_MB), ("all_cards", katalog.DEUTSCH_MB))),
           f"default_cards {mb('default_cards'):.0f} MB (Anzeige {katalog.KATALOG_MB}), all_cards {mb('all_cards'):.0f} MB (Anzeige {katalog.DEUTSCH_MB})")


def gesamtdaten(n=3000):
    """Phase 31: Scryfall-Gesamtdaten (default_cards). /bulk-data nennt die Datei, der gzip-Strom liefert Karten in der Form, die katalog.zeile
    liest. Nur die ersten n Karten (rund 2 von 80 MB), dann endet der Abruf."""
    strom = sources.scryfall_bulk()
    karten = [k for k, _ in zip(strom, range(n))]
    strom.close()
    zeilen = [katalog.zeile(k) for k in karten if "paper" in k["games"]]
    voll = sum(all(z[i] for i in (0, 1, 2, 3, 4, 6, 12, 14)) for z in zeilen)  # id, oracle_id, Name, Set, Nummer, Datum, Rahmen, Bild
    pruefe("Scryfall-Gesamtdaten", len(karten) == n and len(zeilen) > 0.7 * n and voll >= 0.98 * len(zeilen) and len({z[13] for z in zeilen}) > 0.5 * len(zeilen),
           f"{len(zeilen)} von {len(karten)} Karten sind Papier-Drucke, {voll} mit allen Feldern, {len({z[13] for z in zeilen})} Aussehen")


def gedruckte_namen(n=20000):
    """Phase 35: Gesamtdaten all_cards (jeder Druck in jeder Sprache, rund 400 MB). Deutsche Drucke nennen ihren gedruckten Namen in der Form, die
    katalog.namen_zeilen liest. Nur die ersten n Karten (rund 15 MB), dann endet der Abruf."""
    strom = sources.scryfall_bulk("all_cards")
    karten = [k for k, _ in zip(strom, range(n))]
    strom.close()
    deutsch = [k for k in karten if k.get("lang") == "de" and "paper" in k["games"]]
    zeilen = [z for k in deutsch for z in katalog.namen_zeilen(k)]
    pruefe("Gedruckte Namen", len(karten) == n and len(deutsch) > 100 and len(zeilen) >= 0.95 * len(deutsch) and all(z[0] and z[2] for z in zeilen)
           and sum(bool(z[3]) for z in zeilen) > 0.5 * len(zeilen),
           f"{len(deutsch)} deutsche Papier-Drucke unter {len(karten)} Karten, {len(zeilen)} gedruckte Namen, {sum(bool(z[3]) for z in zeilen)} mit Bild")


if __name__ == "__main__":
    if not mtg.DB.exists():
        sys.exit(f"Keine Datenbank unter {mtg.DB}")
    conn = sqlite3.connect(f"file:{mtg.DB.as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    for name, pruef in (("Bilder", lambda: bilder(conn)), ("Scryfall", lambda: scryfall(conn)), ("EDHREC", lambda: edhrec(conn)), ("Spellbook", spellbook),
                        ("Cardmarket", lambda: cardmarket(conn)), ("Salt", salt), ("Bildformate", bildformate), ("Größen der Gesamtdaten", gesamtdaten_groessen), ("Scryfall-Gesamtdaten", gesamtdaten),
                        ("Gedruckte Namen", gedruckte_namen)):
        try:
            pruef()
        except sources.QuelleAus as e:  # Phase 44: vom Betreiber abgeschaltet ist kein Fehler der Quelle
            print(f"---- {name}: übersprungen ({e})")
        except (urllib.error.URLError, KeyError, TypeError, IndexError, ValueError, EOFError) as e:  # ValueError schließt JSONDecodeError ein  # Netz weg oder Format geändert
            pruefe(name, False, f"{type(e).__name__}: {e}")
    sys.exit(1 if fehler else 0)
