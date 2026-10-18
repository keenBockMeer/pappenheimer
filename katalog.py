"""Katalog (Phase 31, PLAN E20): alle Papier-Drucke aus den Scryfall-Gesamtdaten in data/katalog.db. Eine Datei für alle Konten, nicht in der
Sicherung (aus Scryfall neu ladbar). Kein Netz hier: Die Karten kommen als Strom herein (sources.scryfall_bulk), der Pfad vom Aufrufer
(mtg.katalog_pfad). Gebaut wird in eine neue Datei, die dann die alte ersetzt; gelesen wird deshalb immer nur kurz (offen).
Phase 32: Fingerabdrücke je Aussehen (aussehen_fp, rechnet der Browser) und die Suche darüber im Server-Prozess (index, suche).
Phase 35: gedruckte Namen anderer Sprachen (namen, aus den Gesamtdaten all_cards) und die unscharfe Suche nach dem Kartennamen (namen_suche)."""
import difflib
import heapq
import json
import math
import os
import sqlite3
import threading
import time
import unicodedata
from collections import Counter
from contextlib import closing
from datetime import date
from pathlib import Path

ALTER_TAGE = 7  # so alt darf der Katalog werden, bevor der tägliche Lauf ihn neu lädt
# aussehen: was die Kamera unterscheiden kann (Bild-Kennung plus Rahmenart), ein Fingerabdruck je Aussehen genügt (Phase 32)
SCHEMA = """
CREATE TABLE drucke(scryfall_id TEXT PRIMARY KEY, oracle_id TEXT, name TEXT, set_code TEXT, number TEXT, lang TEXT, released TEXT, rarity TEXT,
  finishes TEXT, eur REAL, eur_foil REAL, illustration_id TEXT, frame TEXT, aussehen TEXT, image TEXT) WITHOUT ROWID;
CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);
"""
# Phase 32: ein Fingerabdruck je Aussehen (Version v, wie scan_fp). Ein Katalog aus Phase 31 bekommt beides beim ersten Zugriff nachgelegt (_fp).
FP_SCHEMA = """
CREATE TABLE IF NOT EXISTS aussehen_fp(aussehen TEXT PRIMARY KEY, v INTEGER, fp BLOB);
CREATE INDEX IF NOT EXISTS drucke_aussehen ON drucke(aussehen);
"""
# Phase 35: Der Katalog kennt je Druck nur den englischen Namen. Hier steht, was auf deutschen Karten gedruckt ist: text = Name einer Seite,
# name = der englische Name der Karte wie in drucke; image und frame = großes Bild und Rahmen dieses Drucks (nur für die Messung,
# tests/titel_eval.js)
NAMEN_SCHEMA = "CREATE TABLE IF NOT EXISTS namen(text TEXT, lang TEXT, name TEXT, image TEXT, frame TEXT, PRIMARY KEY(text, lang, name)) WITHOUT ROWID;"


def zeile(k):
    """Ein Druck aus den Scryfall-Gesamtdaten als Zeile für drucke (die einzige Stelle, die dieses Format liest). aussehen = Bild-Kennung, Rahmen
    (frame: 1993, 1997, 2003, 2015, future) und Rahmenart (v Vollbild, r randlos, e Extended Art, s Showcase); ohne Bild-Kennung steht der Druck
    für sich."""
    f0 = (k.get("card_faces") or [{}])[0]
    p = k.get("prices") or {}
    zahl = lambda x: float(x) if x else None
    bild, effekte = k.get("illustration_id") or f0.get("illustration_id"), k.get("frame_effects") or ()
    art = "".join(z for z, da in (("v", k.get("full_art")), ("r", k.get("border_color") == "borderless"), ("e", "extendedart" in effekte),
                                  ("s", "showcase" in effekte)) if da)
    return (k["id"], k.get("oracle_id") or f0.get("oracle_id"), k["name"], k["set"].upper(), k["collector_number"], k.get("lang"), k.get("released_at"),
            k.get("rarity"), json.dumps(k.get("finishes") or []), zahl(p.get("eur")), zahl(p.get("eur_foil") or p.get("eur_etched")), bild, k.get("frame"),
            f"{bild}:{k.get('frame')}{art}" if bild else k["id"], (k.get("image_uris") or f0.get("image_uris") or {}).get("normal"))


def kandidaten(sets):
    """Kürzel der Papier-Sets mit Karten aus der Set-Liste (mtg.sets_info): Die sollte der Katalog kennen."""
    return {code for code, s in sets.items() if not s.get("digital") and s.get("size")}


def bauen(karten, pfad, kuerzel=(), tag=None):
    """Katalog aus einem Strom von Scryfall-Karten neu bauen, nur Papier. Erst in eine neue Datei, dann austauschen: Bricht der Strom ab oder
    bringt er keinen Druck, bleibt der alte Stand liegen. kuerzel = Papier-Sets der Set-Liste von heute (kandidaten); fehlt eins davon auch im
    neuen Stand, löst es keinen weiteren Abruf aus. Die Fingerabdrücke (aussehen_fp) ziehen in den neuen Stand um, soweit es ihr Aussehen
    noch gibt, die gedruckten Namen (namen) alle. -> stand"""
    pfad = Path(pfad)
    neu = pfad.with_name(pfad.name + ".neu")
    pfad.parent.mkdir(parents=True, exist_ok=True)
    neu.unlink(missing_ok=True)
    try:
        with closing(sqlite3.connect(neu)) as c, c:
            c.executescript(SCHEMA + FP_SCHEMA + NAMEN_SCHEMA)
            if pfad.exists():
                c.execute("ATTACH ? AS alt", (str(pfad),))  # vor dem ersten INSERT: in einer Transaktion ginge es nicht
            c.executemany("INSERT OR REPLACE INTO drucke VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (zeile(k) for k in karten if "paper" in (k.get("games") or ())))
            n, a = c.execute("SELECT COUNT(*), COUNT(DISTINCT aussehen) FROM drucke").fetchone()
            if not n:
                raise ValueError("Die Scryfall-Gesamtdaten enthalten keinen Papier-Druck")
            sets = set(kuerzel) | {r[0] for r in c.execute("SELECT DISTINCT set_code FROM drucke")}
            c.executemany("INSERT INTO meta VALUES (?,?)", [("gebaut", tag or date.today().isoformat()), ("drucke", str(n)), ("aussehen", str(a)),
                                                           ("sets", json.dumps(sorted(sets)))])
            if pfad.exists() and c.execute("SELECT 1 FROM alt.sqlite_master WHERE name = 'aussehen_fp'").fetchone():
                c.execute("INSERT INTO aussehen_fp SELECT * FROM alt.aussehen_fp WHERE aussehen IN (SELECT aussehen FROM drucke)")
            if pfad.exists() and c.execute("SELECT 1 FROM alt.sqlite_master WHERE name = 'namen'").fetchone():
                c.execute("INSERT INTO namen SELECT * FROM alt.namen")
                c.execute("INSERT INTO meta SELECT * FROM alt.meta WHERE key = 'namen'")
        for versuch in range(40):
            try:
                os.replace(neu, pfad)
                break
            except PermissionError:  # Windows: Solange jemand den alten Stand liest, lässt sich die Datei nicht ersetzen
                if versuch == 39:
                    raise
                time.sleep(0.25)
    finally:
        neu.unlink(missing_ok=True)
    return stand(pfad)


def offen(pfad):
    """Lesende Verbindung zum Katalog, None solange es keinen gibt. Gleich wieder schließen (closing), sonst blockiert sie den Austausch."""
    if not Path(pfad).exists():
        return None
    c = sqlite3.connect(f"file:{Path(pfad).as_posix()}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def stand(pfad):
    """-> {drucke, aussehen, gebaut (Tag), sets (Kürzel), bytes} oder None ohne Katalog"""
    c = offen(pfad)
    if not c:
        return None
    with closing(c):
        m = dict(c.execute("SELECT key, value FROM meta"))
    return {"drucke": int(m["drucke"]), "aussehen": int(m["aussehen"]), "gebaut": m["gebaut"], "sets": set(json.loads(m["sets"])), "bytes": Path(pfad).stat().st_size}


def faellig(pfad, kuerzel=(), heute=None):
    """Soll der tägliche Lauf den Katalog neu laden? Ja, wenn er älter als ALTER_TAGE ist oder die Set-Liste (kuerzel = kandidaten) ein Set
    kennt, das ihm fehlt; ohne Katalog fehlen ihm alle. -> Grund als Text oder None"""
    s = stand(pfad)
    fehlt = sorted(set(kuerzel) - (s["sets"] if s else set()))
    if s and (date.fromisoformat(heute or date.today().isoformat()) - date.fromisoformat(s["gebaut"])).days > ALTER_TAGE:
        return f"älter als {ALTER_TAGE} Tage"
    if fehlt:
        return ("neues Set " + ", ".join(fehlt[:3]) + (" …" if len(fehlt) > 3 else "")) if s else "erster Aufbau"
    return None


# --- Wann geladen wird (Phase 45, PLAN E26): Katalog und Namen nur bei Bedarf --------------------------------------------------------------
# Zwei Merker für die ganze Installation, in meta der Hauptsammlung (conn ist deren Verbindung; keine eigene Tabelle): „Erfassen“ wurde zuletzt an
# diesem Tag geöffnet, und der Schalter „Deutsche Kartennamen laden“. Wann was fällig ist, entscheidet weiter faellig bzw. namen_faellig; hier
# steht nur, ob geladen werden darf. Kein Netz.

GENUTZT_KEY = "katalog:genutzt"   # meta: Tag (JJJJ-MM-TT), an dem zuletzt jemand „Erfassen“ geöffnet hat
SCHALTER_KEY = "katalog:namen"    # meta: "1" oder "0", der Schalter; fehlt er, gilt: an, wo der Katalog schon Namen hat
GENUTZT_TAGE = 30                 # so lange nach dem letzten Öffnen von „Erfassen“ hält der tägliche Lauf den Katalog frisch
KATALOG_MB, DEUTSCH_MB = 75, 378  # gepackte Größe von default_cards und all_cards, /bulk-data am 2026-10-12 (75,2 und 378 MB); nur für die Anzeige


def genutzt(conn):
    """Tag des letzten Öffnens von „Erfassen“ (JJJJ-MM-TT) oder None."""
    r = conn.execute("SELECT value FROM meta WHERE key = ?", (GENUTZT_KEY,)).fetchone()
    try:
        return date.fromisoformat(r[0]).isoformat() if r else None
    except ValueError:
        return None


def genutzt_merken(conn, heute=None):
    """„Erfassen“ wurde heute geöffnet (oder der Katalog gilt als heute benutzt). Schreibt nur, wenn sich der Tag ändert."""
    heute = heute or date.today().isoformat()
    if genutzt(conn) != heute:
        with conn:
            conn.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (GENUTZT_KEY, heute))
    return heute


def gebraucht(tag, heute=None, liste_da=False):
    """Braucht die Installation den Katalog? Ja, wenn in den letzten GENUTZT_TAGE Tagen jemand „Erfassen“ geöffnet hat (tag = genutzt) oder auf
    irgendeiner Scan-Liste etwas liegt. -> Grund als Text oder None"""
    heute = date.fromisoformat(heute or date.today().isoformat())
    if tag and (heute - date.fromisoformat(tag)).days <= GENUTZT_TAGE:
        return f"Erfassen zuletzt am {tag} geöffnet"
    return "Karten auf einer Scan-Liste" if liste_da else None


def namen_schalter(conn, pfad):
    """Soll die Installation die deutschen Kartennamen laden? Der gespeicherte Schalter; ohne ihn (neue Installation, oder eine von vor Phase 45)
    an, wo der Katalog schon Namen hat, sonst aus."""
    r = conn.execute("SELECT value FROM meta WHERE key = ?", (SCHALTER_KEY,)).fetchone()
    if r and r[0] in ("0", "1"):
        return r[0] == "1"
    try:
        return namen_stand(pfad) is not None
    except sqlite3.Error:
        return False


def namen_schalter_setzen(conn, an):
    with conn:
        conn.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (SCHALTER_KEY, "1" if an else "0"))
    return bool(an)


# --- Erkennung ohne Set-Wahl (Phase 32, PLAN E20): ein Fingerabdruck je Aussehen, Suche im Server-Prozess -------------------------------------
# Den Fingerabdruck (Phase 24: Int8 je Feld und Farbkanal) rechnet der Browser, aus dem Scryfall-Bild wie aus dem Kamerabild. Gesucht wird hier,
# nur mit der Standardbibliothek: grob über Bit-Codes (je Wert ein Bit: über dem Durchschnitt aller oder nicht; Abstand = Zahl verschiedener
# Bits), fein per Kosinus über die besten GROB. Gemessen mit tests/suche_eval.js, Werte in docs/PLAN.md (Phase 32).

SUCHE_LAGEN = 5  # so viele Lagen (dieselbe Karte, im Rahmen leicht versetzt) nimmt eine Anfrage an
GROB_VOR, GROB = 2000, 200  # Grobsuche: die erste Lage gegen alle, die übrigen nur gegen deren beste rund GROB_VOR; die besten GROB gehen in den Feinvergleich
# Kosinus: ab SICHER mit ABSTAND zum nächsten Bild erkannt, unter NEIN keine Karte. Gemessen an 1.300 verzerrten Scryfall-Bildern gegen 66.079
# Einträge (PLAN Phase 32): Unter so vielen Karten liegt das beste falsche Bild im Mittel bei 0,65 (5 % über 0,79), der Wert allein trennt also
# nicht. Der Abstand trennt: Kein falscher Treffer lag weiter als 0,075 vor dem nächsten Bild, auch nicht bei Karten weit neben dem Rahmen
# (mit 0,65 und 0,05 waren dort 2,3 % „sicher, aber falsch“), die Hälfte der richtigen liegt über 0,16.
SUCHE_SICHER, SUCHE_NEIN, SUCHE_ABSTAND = 0.7, 0.6, 0.08
# Mit gelesenem Namen (Phase 35) stehen nur wenige Bilder zur Wahl, das beste falsche liegt dann viel tiefer: Gemessen (PLAN Phase 35) erreicht
# das richtige Bild bei 98 % der Proben 0,55, das beste Bild einer falsch gelesenen Karte in der Hälfte der Fälle nicht einmal 0,4.
BILD_MIN = 0.5
WAHL = 6  # so viele andere Drucke nennt ein Treffer zum Tauschen (so viele merkt sich die Scan-Liste, mtg.LISTE_WAHL)
_PLUS = bytes((i + 128) & 255 for i in range(256))         # Int8 als Byte -> Wert + 128
_HALB = bytes(((i + 128) & 255) >> 1 for i in range(256))  # Int8 als Byte -> (Wert + 128) // 2, also sieben Bit
_EINS = bytes(49 if i & 128 else 48 for i in range(256))   # oberstes Bit -> Ziffer „1“ oder „0“
_index, _index_sperre = {}, threading.Lock()


def _fp(pfad):
    """Schreibende Verbindung für die Fingerabdrücke, None ohne Katalog. Gleich wieder schließen (wie offen)."""
    if not pfad or not Path(pfad).exists():
        return None
    c = sqlite3.connect(pfad, timeout=30)
    c.executescript(FP_SCHEMA)
    return c


def fp_speichern(pfad, v, fps):
    """Fingerabdrücke merken (fps: {aussehen: Bytes}): nur für Aussehen aus dem Katalog, eine Länge je Version, eine neuere Version ersetzt die
    ältere ganz. Was schon da ist, bleibt (der Katalog gehört allen Konten, keins überschreibt die Arbeit eines anderen). -> Zahl der neuen"""
    c = _fp(pfad)
    if not c:
        raise ValueError("Noch kein Katalog: Der tägliche Lauf lädt ihn, sofort geht es mit mtg katalog --neu")
    with closing(c), c:
        da = c.execute("SELECT v, length(fp) FROM aussehen_fp LIMIT 1").fetchone()
        if da and da[0] > v:
            raise ValueError("Es gibt schon Fingerabdrücke einer neueren Version. Bitte die Seite neu laden.")
        if da and da[0] < v:
            c.execute("DELETE FROM aussehen_fp")
        soll = da[1] if da and da[0] == v else len(next(iter(fps.values()), b""))
        bekannt = {r[0] for r in c.execute("SELECT DISTINCT aussehen FROM drucke WHERE aussehen IN (SELECT value FROM json_each(?))", (json.dumps(sorted(fps)),))}
        for a, fp in fps.items():
            if a not in bekannt or not fp or len(fp) != soll:
                raise ValueError(f"Fingerabdruck für {a} passt nicht")
        return c.executemany("INSERT OR IGNORE INTO aussehen_fp VALUES (?,?,?)", [(a, v, fp) for a, fp in fps.items()]).rowcount


def fp_stand(pfad, v=None, eigen=(), limit=0):
    """Wie weit die Erkennung vorbereitet ist: gesamt = Aussehen mit Bild, fertig = davon mit Fingerabdruck der Version v (ohne v: der
    gespeicherten), fehlt = die nächsten limit ohne, je mit dem Bild des Vertreters (englisch vor anderen Sprachen, dann der neueste Druck).
    Zuerst die Aussehen aus den Sets der eigenen Sammlung (eigen: Kürzel), dann die neuesten. -> {gesamt, fertig, fehlt: [{id (das Aussehen), image}]}"""
    c = _fp(pfad)
    if not c:
        return {"gesamt": 0, "fertig": 0, "fehlt": []}
    with closing(c):
        passt = v in (None, *(c.execute("SELECT v FROM aussehen_fp LIMIT 1").fetchone() or ()))  # es gibt immer nur eine Version (fp_speichern)
        fehlt = c.execute(
            "WITH f AS (SELECT aussehen, MAX(set_code IN (SELECT value FROM json_each(?))) eigen, MAX(released) neu FROM drucke WHERE image IS NOT NULL "
            f"{'AND aussehen NOT IN (SELECT aussehen FROM aussehen_fp) ' if passt else ''}GROUP BY aussehen ORDER BY eigen DESC, neu DESC, aussehen LIMIT ?) "
            "SELECT aussehen, (SELECT image FROM drucke d WHERE d.aussehen = f.aussehen AND image IS NOT NULL ORDER BY lang != 'en', released DESC, "
            "scryfall_id LIMIT 1) FROM f ORDER BY eigen DESC, neu DESC, aussehen", (json.dumps(sorted(set(eigen))), limit)).fetchall()
        # Aussehen mit Bild = alle (nur über den Index gezählt) ohne die wenigen, von denen kein Druck ein Bild hat: zusammen 60 ms statt 1 s
        gesamt = c.execute("SELECT (SELECT COUNT(DISTINCT aussehen) FROM drucke) - (SELECT COUNT(DISTINCT aussehen) FROM drucke a WHERE image IS NULL "
                           "AND NOT EXISTS (SELECT 1 FROM drucke b WHERE b.aussehen = a.aussehen AND b.image IS NOT NULL))").fetchone()[0]
        return {"gesamt": gesamt,
                "fertig": c.execute("SELECT COUNT(*) FROM aussehen_fp").fetchone()[0] if passt else 0, "fehlt": [{"id": a, "image": b} for a, b in fehlt]}


def fp_probe(pfad, n):
    """Für die Messung (tests/suche_eval.js, tests/titel_eval.js): n Aussehen mit Fingerabdruck, gleichmäßig über alle verteilt, je mit Bild,
    Namen, Karte, Set und Nummer des Vertreters wie in fp_stand. -> [{id (das Aussehen), image, name, oid, set_code, number}]"""
    c = _fp(pfad)
    if not c:
        return []
    with closing(c):
        alle = [r[0] for r in c.execute("SELECT aussehen FROM aussehen_fp ORDER BY aussehen")]
        wahl = alle[::max(1, len(alle) // max(1, n))][:n]
        return [dict(zip(("id", "image", "name", "oid", "set_code", "number"), r)) for r in c.execute(
            "SELECT aussehen, image, name, oracle_id, set_code, number FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY aussehen ORDER BY lang != 'en', "
            "released DESC, scryfall_id) platz FROM drucke WHERE image IS NOT NULL AND aussehen IN (SELECT value FROM json_each(?))) WHERE platz = 1", (json.dumps(wahl),))]


def _coder(mu):
    """-> Funktion Fingerabdruck (Bytes) -> Bit-Code als Zahl, je Wert ein Bit: gesetzt, wenn er über dem Durchschnitt mu liegt. Ohne Schleife
    in Python (66.000 Einträge in 0,2 statt 4 s): Werte auf sieben Bit halbieren und als eine große Zahl lesen, je Byte 127 minus Schwelle
    dazuzählen (kein Übertrag ins nächste Byte), dann sagt das oberste Bit jedes Bytes „größer als die Schwelle“."""
    plus = int.from_bytes(bytes(127 - (int(m + 128) >> 1) for m in mu), "big")
    return lambda fp: int((int.from_bytes(fp.translate(_HALB), "big") + plus).to_bytes(len(mu), "big").translate(_EINS), 2)


def _laden(pfad, v):
    c, rows, karte = offen(pfad) if pfad else None, [], {}
    if c:
        with closing(c):
            if c.execute("SELECT 1 FROM sqlite_master WHERE name = 'aussehen_fp'").fetchone():
                rows = c.execute("SELECT aussehen, fp FROM aussehen_fp WHERE v = ?", (v,)).fetchall()
                platz = {r[0]: j for j, r in enumerate(rows)}
                for oid, a in c.execute("SELECT DISTINCT oracle_id, aussehen FROM drucke WHERE oracle_id IS NOT NULL"):  # Phase 35: Karte -> ihre Bilder
                    if a in platz:
                        karte.setdefault(oid, []).append(platz[a])
    n, L, roh = len(rows), len(rows[0][1]) if rows else 0, b"".join(r[1] for r in rows)
    spalten = roh.translate(_PLUS)
    mu = [sum(spalten[i::L]) / n - 128 for i in range(L)]  # Durchschnitt je Stelle: Rahmen, Rand und Namenszeile sehen bei vielen Karten gleich aus
    code = _coder(mu)
    return {"n": n, "L": L, "aus": [r[0] for r in rows], "roh": memoryview(roh).cast("b"), "mu": mu, "mumu": math.sumprod(mu, mu), "code": code,
            "bits": [code(roh[j * L:(j + 1) * L]) for j in range(n)], "norm": {}, "karte": karte}


def index(pfad, v):
    """Suchindex im Prozess: Durchschnitt, Fingerabdrücke (roh, 672 Byte je Aussehen) und Bit-Codes. Beim ersten Suchen geladen und neu, sobald
    sich die Datei geändert hat (neue Fingerabdrücke, neuer Katalog)."""
    st = Path(pfad).stat() if pfad and Path(pfad).exists() else None
    marke = (v, st.st_mtime_ns, st.st_size) if st else None
    with _index_sperre:  # ponytail: nach jeder Änderung ganz neu (unter 1 s bei 66.000 Einträgen); schrittweise nachladen, wenn das beim Vorbereiten stört
        if pfad not in _index or _index[pfad]["marke"] != marke:
            _index[pfad] = _laden(pfad, v) | {"marke": marke}
        return _index[pfad]


def druckwahl(drucke, sets=(), kontext=(), eigen=()):
    """Welcher Druck eines Aussehens es ist, sieht die Kamera nicht, das entscheidet der Zusammenhang (E20): genau einer in den bevorzugten Sets,
    dann der; sonst genau einer im Set der zuletzt gezählten Karten (kontext, jüngstes zuerst), dann der; sonst einer, den die Sammlung schon hat
    oder der auf der Scan-Liste liegt (eigen: Kennungen; dort hat ihn jemand gewählt oder korrigiert, Phase 60); sonst der neueste (drucke kommt
    so sortiert). -> (Druck, prüfen): prüfen heißt, nach Vorliebe und Zusammenhang blieben mehrere und der Druck ist geraten (auch aus eigen)."""
    for menge in (set(sets), *({k} for k in kontext)):
        da = [d for d in drucke if d["set_code"] in menge]
        if len(da) == 1:
            return da[0], False
        drucke = da or drucke
    return next((d for d in drucke if d.get("id") in eigen), drucke[0]), len(drucke) > 1


def suche(pfad, v, lagen, sets=(), kontext=(), pruef=None, karten=None, sicher=None, eigen=()):
    """Welche Karte zeigen diese Fingerabdrücke (lagen: Bytes je Lage)? Die besten drei Bilder: je Treffer das beste Aussehen, sein Wert
    (Kosinus), der Abstand zum nächsten Bild, der gewählte Druck (druckwahl, eigen wie dort), ob er zu prüfen ist, und bis zu WAHL andere Drucke zum
    Tauschen.
    Dasselbe Bild in mehreren Rahmenarten ist ein Treffer: Liegen ihre Werte näher als SUCHE_ABSTAND beieinander, stehen ihre Drucke alle zur
    Wahl. urteil: sicher, unsicher (die App fragt) oder nichts. pruef (nur Messung): ein Aussehen, grob nennt seinen Platz in der Grobsuche.
    Mit gelesenem Namen (Phase 35, PLAN E21; Kennungen der Karten aus namen_suche): karten = alle Karten, deren Name passte, sicher = die Karte
    des sicher gelesenen Namens. Wo das Bild allein sicher ist, gilt es weiter (in allen Messungen nie falsch, ein sicher gelesener Name schon);
    der Name hilft, wo es das nicht ist. Dann stehen nur die Bilder der gelesenen Karten zur Wahl, und das Urteil fällt so:
    - Name sicher gelesen: Das beste Bild dieser Karte gilt, sobald es BILD_MIN erreicht. Liegt ein zweites Bild der Karte zu nah, ist der
      Druck geraten (pruefen, die anderen Bilder stehen zur Wahl), die Karte stimmt trotzdem.
    - Name sicher gelesen, aber kein Bild der Karte passt: unsicher. Die App fragt, mit dem besten Bild der Karte und denen der Suche über alle.
    - Name nicht sicher: Das beste Bild der gelesenen Karten ist sicher ab BILD_MIN mit SUCHE_ABSTAND zum nächsten; liegen mehrere zu nah
      beieinander, fragt die App mit ihnen als Kandidaten.
    - Passt kein Bild der gelesenen Karten (oder hat keine ein Bild im Index), bleibt es bei der Suche über alle.
    - Ist das Bild allein sicher, ein sicher gelesener Name mit passendem Bild meint aber eine andere Karte: unsicher, die App fragt mit beiden.
    Unter den Drucken eines Bilds gehen die der gelesenen Karten vor (dasselbe Bild tragen auch andere, etwa die Themenkarten aus Jumpstart).
    Die Antwort nennt unter karten, wie viele Bilder zur Wahl standen, und unter titel, dass das Urteil aus Name und Bild kam.
    -> {v, n (Einträge im Index), urteil, treffer: [{aussehen, wert, abstand, druck, pruefen, drucke}], ms}"""
    t0 = time.perf_counter()
    ix = index(pfad, v)
    out = {"v": v, "n": ix["n"], "urteil": "nichts", "treffer": [], "ms": 0.0}
    if not ix["n"] or not lagen:
        return out
    if any(len(fp) != ix["L"] for fp in lagen):
        raise ValueError("Fingerabdruck passt nicht zum Index")
    aus, bits, roh, mu, L = ix["aus"], ix["bits"], ix["roh"], ix["mu"], ix["L"]
    codes = [ix["code"](fp) for fp in lagen]
    q = []  # je Lage: ohne Durchschnitt, auf Länge 1, und ihr Skalarprodukt mit dem Durchschnitt
    for fp in lagen:
        w = [a - m for a, m in zip(memoryview(fp).cast("b"), mu)]
        f = 1 / math.sqrt(math.sumprod(w, w) or 1)
        w = [x * f for x in w]
        q.append((w, math.sumprod(mu, w)))

    genannt = set(karten or ()) | set(sicher or ())  # Karten, deren Name gelesen wurde: Ihre Drucke gehen unter den Drucken eines Bilds vor

    def beste(vor):
        """Die besten drei Bilder unter den Einträgen vor -> (Treffer, Kandidaten des Feinvergleichs)"""
        grob = {j: min(((bits[j] ^ c).bit_count(), i) for i, c in enumerate(codes)) for j in vor}  # je Eintrag (Abstand, beste Lage)
        kand = heapq.nsmallest(GROB, vor, key=grob.__getitem__)

        def kosinus(j):
            r, (w, muw) = roh[j * L:(j + 1) * L], q[grob[j][1]]
            if j not in ix["norm"]:
                ix["norm"][j] = math.sqrt(max(math.sumprod(r, r) - 2 * math.sumprod(r, mu) + ix["mumu"], 0)) or 1
            return (math.sumprod(r, w) - muw) / ix["norm"][j]
        bilder, treffer = {}, []  # Bild-Kennung (der Teil des Aussehens vor dem Doppelpunkt, siehe zeile) -> [(Wert, Aussehen)], bestes zuerst
        for wert, a in sorted(((kosinus(j), aus[j]) for j in kand), reverse=True):
            bilder.setdefault(a.partition(":")[0], []).append((wert, a))
        gruppen = list(bilder.items())
        with closing(offen(pfad)) as c:
            for i, (bild, glieder) in enumerate(gruppen[:3]):
                wert = glieder[0][0]
                drucke = [dict(r) for r in c.execute(  # alle Drucke dieses Bilds: das Aussehen ist die Bild-Kennung allein oder beginnt mit „Kennung:“
                    "SELECT scryfall_id id, oracle_id oid, name, set_code, number, image, aussehen FROM drucke WHERE aussehen >= ?1 AND aussehen < ?1 || ';' "
                    "ORDER BY released DESC, set_code, CAST(number AS INTEGER), number", (bild,))]
                nah = {a for w, a in glieder if wert - w < SUCHE_ABSTAND}
                pool = [d for d in drucke if d["aussehen"] in nah]
                pool = [d for d in pool if d["oid"] in genannt] or pool
                if not pool:
                    continue
                druck, pruefen = druckwahl(pool, sets, kontext, eigen)
                treffer.append({"aussehen": glieder[0][1], "wert": round(wert, 4), "abstand": round(wert - (gruppen[i + 1][1][0][0] if i + 1 < len(gruppen) else 0), 4),
                                "druck": druck, "pruefen": pruefen,
                                "drucke": ([d for d in pool if d is not druck] + [d for d in drucke if d not in pool])[:WAHL]})
        return treffer, kand

    def alle():
        """Suche über alle Bilder mit dem Urteil ohne Namen -> (Urteil, Treffer)"""
        # Jeder Durchgang über alle Einträge kostet Millisekunden, deshalb nur einer: Die Schwelle für „unter den besten GROB_VOR“ schätzt jeder
        # 16. Eintrag, dann bleiben die Einträge darunter (mal etwas mehr, mal etwas weniger als GROB_VOR)
        probe = sorted((b ^ codes[0]).bit_count() for b in bits[::16])
        schwelle = probe[min(len(probe) - 1, GROB_VOR // 16)]
        treffer, kand = beste([j for j, b in enumerate(bits) if (b ^ codes[0]).bit_count() <= schwelle] if ix["n"] > GROB_VOR else range(ix["n"]))
        if pruef:
            out["grob"] = next((i for i, j in enumerate(kand) if aus[j] == pruef), None)
        t = treffer[0] if treffer else None
        return ("nichts" if not t or t["wert"] < SUCHE_NEIN else "sicher" if t["wert"] >= SUCHE_SICHER and t["abstand"] >= SUCHE_ABSTAND else "unsicher"), treffer

    bilder_von = lambda kennungen: sorted({j for k in kennungen or () for j in ix["karte"].get(k, ())})
    gelesen, gewiss = bilder_von(karten), bilder_von(sicher)
    if karten is not None:
        out["karten"] = len(gelesen)
    urteil, treffer = alle()  # das Bild allein, wie ohne Namen
    eng = beste(gewiss)[0] if gewiss else []
    weit = beste(gelesen)[0] if gelesen and not eng else []
    if urteil == "sicher":
        if eng and eng[0]["wert"] >= BILD_MIN and eng[0]["druck"]["oid"] != treffer[0]["druck"]["oid"]:  # Name und Bild meinen verschiedene Karten
            out |= {"urteil": "unsicher", "treffer": [treffer[0], eng[0]], "titel": True}
        else:
            out |= {"urteil": urteil, "treffer": treffer}
    elif eng and eng[0]["wert"] >= BILD_MIN:  # Name sicher gelesen und das Bild passt
        if len(eng) > 1 and eng[0]["abstand"] < SUCHE_ABSTAND:
            eng[0] |= {"pruefen": True, "drucke": ([x["druck"] for x in eng[1:]] + eng[0]["drucke"])[:WAHL]}
        out |= {"urteil": "sicher", "treffer": eng, "titel": True}
    elif eng:  # Name sicher gelesen, aber kein Bild der Karte passt
        out |= {"urteil": "unsicher", "treffer": (eng[:1] + [x for x in treffer if x["aussehen"] != eng[0]["aussehen"]])[:3], "titel": True}
    elif weit and weit[0]["wert"] >= BILD_MIN:  # Name nicht sicher, ein Bild der gelesenen Karten passt
        out |= {"urteil": "sicher" if weit[0]["abstand"] >= SUCHE_ABSTAND else "unsicher", "treffer": weit, "titel": True}
    else:
        out |= {"urteil": urteil, "treffer": treffer}
    return out | {"ms": round((time.perf_counter() - t0) * 1000, 1)}


# --- Erst den Namen lesen (Phase 35, PLAN E21): gedruckte Namen und die unscharfe Suche danach -----------------------------------------------
# Die Texterkennung liest die Namenszeile mit Fehlern („Reißkctten-Schnctzclvolk“), dahinter oft Reste der Manakosten. Gesucht wird unter allen
# Namen: englisch aus drucke, deutsch aus namen. Erst grob über gemeinsame Trigramme, dann die besten NAMEN_VOR genau (difflib), beides
# Standardbibliothek. Gemessen (PLAN Phase 35): 6 ms je Suche; bei 20 % falschen Zeichen liegt der richtige Name in 97 % vorn.

NAMEN_TAGE = 30                       # so alt dürfen die gedruckten Namen werden (all_cards hat 396 MB)
NAMEN_VOR, NAMEN_ZAHL = 30, 5         # so viele Namen gehen in den genauen Vergleich, so viele nennt die Antwort
NAMEN_KARTEN = 40                     # so viele Karten je Name höchstens (Spielmarken teilen sich Namen)
NAMEN_AB = .6                         # ab diesem Wert zählt ein gelesener Name überhaupt (darunter: weiterer Streifen bzw. Suche über alle)
NAMEN_KURZ = 5                        # kürzere Lesungen zählen nur, wenn sie genau ein Name sind: Aus dem Rest „eee“ wurde sonst „Ebene“
NAMEN_SICHER, NAMEN_ABSTAND = .8, .1  # Name gilt als sicher gelesen ab diesem Wert und mit diesem Abstand zur nächsten anderen Karte
_namen = {}


def namen_zeilen(k):
    """Ein Druck aus all_cards -> je Seite (text, lang, name, image, frame): was auf der Karte als Name gedruckt ist. Das Bild nur, wo Scryfall
    einen echten Scan dieses Drucks hat. Leer bei englischen Drucken ohne printed_name."""
    scan = k.get("image_status") in ("highres_scan", "lowres")
    return [(s["printed_name"], k["lang"], k["name"], (s.get("image_uris") or k.get("image_uris") or {}).get("large") if scan else None, k.get("frame"))
            for s in (k.get("card_faces") or [k]) if s.get("printed_name")]


def namen_bauen(karten, pfad, sprachen=("de",), tag=None):
    """Gedruckte Namen dieser Sprachen neu aus dem Strom all_cards, nur Papier. Erst sammeln, dann in einem Zug schreiben: Der Strom läuft
    Minuten, gesperrt ist der Katalog nur einen Augenblick. Bricht der Strom ab oder bringt er nichts, bleibt der alte Stand. -> Zahl der Namen"""
    zeilen = {}
    for k in karten:
        if k.get("lang") in sprachen and "paper" in (k.get("games") or ()):
            for z in namen_zeilen(k):
                if z[3] or z[:3] not in zeilen:
                    zeilen[z[:3]] = z
    if not zeilen:
        raise ValueError("Die Scryfall-Gesamtdaten enthalten keinen gedruckten Namen in " + ", ".join(sprachen))
    c = _fp(pfad)
    if not c:
        raise ValueError("Noch kein Katalog: Der tägliche Lauf lädt ihn, sofort geht es mit mtg katalog --neu")
    with closing(c):
        c.executescript(NAMEN_SCHEMA)
        with c:
            c.execute("DELETE FROM namen WHERE lang IN (SELECT value FROM json_each(?))", (json.dumps(list(sprachen)),))
            c.executemany("INSERT INTO namen VALUES (?,?,?,?,?)", zeilen.values())
            c.execute("INSERT OR REPLACE INTO meta VALUES ('namen', ?)", (tag or date.today().isoformat(),))
    return len(zeilen)


def namen_stand(pfad):
    """-> {zahl, gebaut (Tag)} der gedruckten Namen oder None, solange es keine gibt"""
    c = offen(pfad)
    if not c:
        return None
    with closing(c):
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name = 'namen'").fetchone():
            return None
        tag = c.execute("SELECT value FROM meta WHERE key = 'namen'").fetchone()
        return {"zahl": c.execute("SELECT COUNT(*) FROM namen").fetchone()[0], "gebaut": tag[0]} if tag else None


def namen_faellig(pfad, heute=None):
    """Soll der tägliche Lauf die gedruckten Namen neu laden? Nur mit Katalog; ja, wenn es keine gibt oder sie älter als NAMEN_TAGE sind.
    -> Grund als Text oder None"""
    if not stand(pfad):
        return None
    s = namen_stand(pfad)
    if not s:
        return "erster Aufbau"
    return f"älter als {NAMEN_TAGE} Tage" if (date.fromisoformat(heute or date.today().isoformat()) - date.fromisoformat(s["gebaut"])).days > NAMEN_TAGE else None


def namen_probe(pfad, n, lang="de"):
    """Für die Messung (tests/titel_eval.js): n gedruckte Namen dieser Sprache mit Bild, gleichmäßig verteilt, je mit Rahmen und der Kennung
    der Karte. -> [{text, name, image, frame, oid}]"""
    c = offen(pfad)
    if not c:
        return []
    with closing(c):
        if not c.execute("SELECT 1 FROM sqlite_master WHERE name = 'namen'").fetchone():
            return []
        alle = c.execute("SELECT text, name, image, frame FROM namen WHERE lang = ? AND image IS NOT NULL ORDER BY text, name", (lang,)).fetchall()
        wahl = [dict(r) for r in alle[::max(1, len(alle) // max(1, n))][:n]]
        oid = dict(c.execute("SELECT name, oracle_id FROM drucke WHERE name IN (SELECT value FROM json_each(?))", (json.dumps([w["name"] for w in wahl]),)))
    return [w | {"oid": oid.get(w["name"])} for w in wahl]


def _norm(s):
    """Name oder gelesene Zeile zum Vergleichen: Kleinbuchstaben, Umlaute und Akzente aufgelöst (ä wie a: so liest sie auch ein englisches
    Modell), nur Buchstaben und Ziffern, einfache Leerzeichen."""
    s = unicodedata.normalize("NFKD", s.replace("ß", "ss").replace("Æ", "Ae").replace("æ", "ae")).encode("ascii", "ignore").decode().lower()
    return " ".join("".join(ch if ch.isalnum() else " " for ch in s).split())


def _tri(s):
    return {f"  {s} "[i:i + 3] for i in range(len(s) + 1)}


def _namen_laden(pfad):
    texte = {}  # Text zum Vergleichen -> {Kennung der Karte: (Rang, Name, Sprache)}; Rang 0 = der ganze Name, 1 = Vorderseite, 2 = andere Seite

    def merke(text, oid, rang, name, lang):
        da = texte.setdefault(_norm(text), {})
        if oid not in da or rang < da[oid][0]:
            da[oid] = (rang, name, lang)
    with closing(offen(pfad)) as c:
        karte = {}
        for name, oid in c.execute("SELECT name, COALESCE(oracle_id, scryfall_id) FROM drucke GROUP BY name, 2"):
            karte.setdefault(name, []).append(oid)
            teile = name.split(" // ")  # oben auf der Karte steht nur eine Seite
            for i, teil in enumerate(teile):
                merke(teil, oid, (len(teile) > 1) + (i > 0), name, "en")
        if c.execute("SELECT 1 FROM sqlite_master WHERE name = 'namen'").fetchone():
            for text, lang, name in c.execute("SELECT text, lang, name FROM namen"):
                for oid in karte.get(name, ()):
                    merke(text, oid, " // " in name, name, lang)
    texte.pop("", None)
    liste, tri = sorted(texte), {}
    for j, t in enumerate(liste):
        for g in _tri(t):
            tri.setdefault(g, []).append(j)
    # je Text die Karten nach Rang: „Swords to Plowshares“ ist zuerst die Karte, die so heißt, dann die Rückseite einer anderen
    karten = [{oid: x[1:] for oid, x in sorted(texte[t].items(), key=lambda kv: kv[1][0])} for t in liste]
    return {"texte": liste, "karten": karten, "tri": tri, "n": [len(t) + 1 for t in liste]}


def namen_index(pfad):
    """Alle Namen zum Suchen im Prozess, neu geladen, sobald sich der Katalog ändert (wie index)."""
    st = Path(pfad).stat()
    marke = (st.st_mtime_ns, st.st_size)
    with _index_sperre:
        if pfad not in _namen or _namen[pfad]["marke"] != marke:
            _namen[pfad] = _namen_laden(pfad) | {"marke": marke}
        return _namen[pfad]


def namen_suche(pfad, text):
    """Welcher Name steht da (text: eine gelesene Zeile)? Die besten NAMEN_ZAHL Namen, bester zuerst: wert = Ähnlichkeit von 0 bis 1 zwischen
    Zeile und Name, lang = Sprache des Namens, der passte, name = der englische Name der Karte, karten = Kennungen der Karten, die so heißen
    (für suche; mehrere bei Spielmarken wie „Elemental“). -> [{name, lang, wert, karten}]"""
    q = _norm(text)
    if len(q) < 3 or not pfad or not Path(pfad).exists():
        return []
    ix = namen_index(pfad)
    g = _tri(q)
    gemeinsam = Counter(j for x in g for j in ix["tri"].get(x, ()))
    vor = heapq.nlargest(NAMEN_VOR, gemeinsam, key=lambda j: gemeinsam[j] / (len(g) + ix["n"][j]))
    out = []
    for wert, j in sorted(((difflib.SequenceMatcher(None, q, ix["texte"][j]).ratio(), j) for j in vor), reverse=True)[:NAMEN_ZAHL]:
        if wert < 1 and len(q) < NAMEN_KURZ:
            break
        name, lang = next(iter(ix["karten"][j].values()))
        out.append({"name": name, "lang": lang, "wert": round(wert, 3), "karten": list(ix["karten"][j])[:NAMEN_KARTEN]})
    return out


def namen_sicher(treffer):
    """Ist der erste Name sicher gelesen? Wert ab NAMEN_SICHER und NAMEN_ABSTAND vor dem nächsten Namen einer anderen Karte (derselbe Name
    englisch und deutsch ist eine Karte)."""
    return bool(treffer) and treffer[0]["wert"] >= NAMEN_SICHER and all(
        treffer[0]["wert"] - t["wert"] >= NAMEN_ABSTAND for t in treffer[1:] if t["name"] != treffer[0]["name"])
