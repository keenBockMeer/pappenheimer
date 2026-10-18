"""CLI: Import, DB-Schema, Sortier-Plan. Netz nur über sources.py (die Abruf-Funktion wird übergeben). Name und Version: version.py."""
import argparse
import csv
import hashlib
import io
import json
import os
import re
import signal
import sqlite3
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
from collections import defaultdict
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from itertools import groupby
from pathlib import Path

import katalog
import sources
import version

ROOT = Path(__file__).parent
DB = Path(os.environ.get("MTG_DB") or ROOT / "data" / "mtg.db")  # MTG_DB: andere Datenbank (z. B. zum Ausprobieren)
ARCHIVE = DB.parent / "imports"
INBOX = ROOT / "inbox"

# E1: fertige Decks zählen nicht als verfügbar, ihre Karten stehen im Stapel Deck. Automatisch: Binder Type „deck“ (Sammlungsexport einer
# Scanner-App, importierte Deckliste); dazu die Namen aus der Einstellung der Sammlung (fertige_decks), für Exporte ohne Binder Type (E33).
FERTIGE_DECKS = "fertige_decks"  # meta jeder Sammlung: JSON-Liste von Binder-Namen; fehlt der Eintrag (neue Sammlung), ist die Liste leer
FERTIGE_DECKS_MAX = 200
PROXY_BLATT = "proxy_blatt"      # meta der Hauptsammlung: "1" = das Proxy-Blatt ist eingeschaltet (E23); fehlt der Eintrag, ist es aus
REQUIRED = ("Scryfall ID", "Quantity", "Foil", "Condition", "Language")
MAX_LOSS = 0.25  # Schutzregel: mehr als 25 % des Bestands entfernen nur mit --force
UPDATE_DATEI = 0.2  # ponytail: ein erkannter Binder macht mindestens ein Fünftel der Datei aus (sonst „erkennt“ ein kleiner Binder einen großen Export)
PRICE_MAX_AGE_H = 24
# Sortier-Plan (Phase 8): von jeder Karte KEEP_COPIES behalten, von Staples KEEP_STAPLES, Basics alle; der Rest wird
# verkauft, ab SELL_MIN_EUR einzeln, darunter als Bulk. In der Oberfläche änderbar (meta „rules“).
KEEP_COPIES = 1
KEEP_STAPLES = 2
RANK_STAPLE = 200   # edhrec_rank bis hier = Staple (läuft in sehr vielen Decks); Karten deiner Top-10-Commander auch
SELL_MIN_EUR = 1.0
RULES = {"keep": KEEP_COPIES, "staples": KEEP_STAPLES, "sell_min": SELL_MIN_EUR}
STACKS = ("deck", "keep", "sell", "bulk")
TS = "%Y-%m-%dT%H:%M:%SZ"

# Stand 1 des Schemas (PLAN E27) und bleibt so: Eine Änderung kommt als weiterer Schritt in MIGRATIONEN, nicht hier hinein.
SCHEMA = """
CREATE TABLE IF NOT EXISTS cards(
  scryfall_id TEXT PRIMARY KEY, oracle_id TEXT, name TEXT, set_code TEXT, number TEXT, lang TEXT,
  type_line TEXT, mana_cost TEXT, cmc REAL, color_identity TEXT, oracle_text TEXT, rarity TEXT,
  legal_commander INTEGER, game_changer INTEGER, edhrec_rank INTEGER, price_eur REAL, price_eur_foil REAL,
  image_url TEXT, json TEXT, updated_at TEXT);
CREATE INDEX IF NOT EXISTS cards_oracle ON cards(oracle_id);
CREATE INDEX IF NOT EXISTS cards_name ON cards(name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS cards_set ON cards(set_code, scryfall_id);
CREATE TABLE IF NOT EXISTS collection(
  binder TEXT, binder_type TEXT, scryfall_id TEXT, foil TEXT, condition TEXT, language TEXT, qty INTEGER,
  added TEXT, mbid TEXT, paid REAL,
  PRIMARY KEY (binder, scryfall_id, foil, condition, language));
CREATE INDEX IF NOT EXISTS collection_card ON collection(scryfall_id);
CREATE TABLE IF NOT EXISTS imports(id INTEGER PRIMARY KEY, file TEXT, sha256 TEXT, scope TEXT, added INTEGER, removed INTEGER, at TEXT);
CREATE TABLE IF NOT EXISTS changes(import_id INTEGER, scryfall_id TEXT, delta INTEGER);
CREATE TABLE IF NOT EXISTS card_status(oracle_id TEXT PRIMARY KEY, status TEXT, keep INTEGER, updated_at TEXT);
CREATE TABLE IF NOT EXISTS tags(oracle_id TEXT, tag TEXT, PRIMARY KEY (oracle_id, tag));
CREATE TABLE IF NOT EXISTS edhrec(slug TEXT PRIMARY KEY, json TEXT, fetched_at TEXT);
CREATE TABLE IF NOT EXISTS decks(id INTEGER PRIMARY KEY, name TEXT, commander_oracle_id TEXT, bracket INTEGER, saved_at TEXT);
CREATE TABLE IF NOT EXISTS deck_cards(deck_id INTEGER, oracle_id TEXT, role TEXT);
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS sales(import_id INTEGER, binder TEXT, scryfall_id TEXT, foil TEXT, condition TEXT, language TEXT,
  qty INTEGER, price REAL, at TEXT);
CREATE TABLE IF NOT EXISTS price_history(scryfall_id TEXT, day TEXT, eur REAL, eur_foil REAL, PRIMARY KEY (scryfall_id, day));
CREATE TABLE IF NOT EXISTS value_history(day TEXT PRIMARY KEY, value REAL, cards INTEGER, paid REAL, paid_value REAL);
CREATE TABLE IF NOT EXISTS cm_price(id_product INTEGER PRIMARY KEY, low REAL, trend REAL, avg7 REAL, avg30 REAL,
  low_foil REAL, trend_foil REAL, avg7_foil REAL, avg30_foil REAL, day TEXT);
CREATE TABLE IF NOT EXISTS deck_log(id INTEGER PRIMARY KEY, deck TEXT, at TEXT, import_id INTEGER, rein TEXT, raus TEXT, grund TEXT);
CREATE TABLE IF NOT EXISTS waechter(id INTEGER PRIMARY KEY, day TEXT, oracle_id TEXT, art TEXT, info TEXT, UNIQUE (oracle_id, art, info));
CREATE TABLE IF NOT EXISTS rulings(oracle_id TEXT PRIMARY KEY, json TEXT, fetched_at TEXT);
CREATE TABLE IF NOT EXISTS notizen(binder TEXT, scryfall_id TEXT, foil TEXT, condition TEXT, language TEXT, ort TEXT, verliehen TEXT, notiz TEXT,
  updated TEXT, PRIMARY KEY (binder, scryfall_id, foil, condition, language));
CREATE TABLE IF NOT EXISTS games(id INTEGER PRIMARY KEY, at TEXT, deck TEXT, pod TEXT, players INTEGER, won INTEGER, turns INTEGER, notes TEXT);
CREATE TABLE IF NOT EXISTS gruppe(id INTEGER PRIMARY KEY, pod TEXT, spieler TEXT, deck TEXT, bracket INTEGER, ci TEXT);
CREATE TABLE IF NOT EXISTS set_karten(set_code TEXT PRIMARY KEY, json TEXT, fetched_at TEXT);
CREATE TABLE IF NOT EXISTS card_vec(oracle_id TEXT PRIMARY KEY, model TEXT, vec BLOB);
CREATE TABLE IF NOT EXISTS scan_fp(scryfall_id TEXT PRIMARY KEY, v INTEGER, fp BLOB);
CREATE TABLE IF NOT EXISTS wishlist(oracle_id TEXT PRIMARY KEY, scryfall_id TEXT, qty INTEGER, max_eur REAL, note TEXT, added TEXT);
CREATE TABLE IF NOT EXISTS set_prints(scryfall_id TEXT PRIMARY KEY, set_code TEXT, oracle_id TEXT, name TEXT, number TEXT, lang TEXT, image_url TEXT,
  illustration_id TEXT, finishes TEXT, digital INTEGER, json TEXT, at TEXT);
CREATE INDEX IF NOT EXISTS set_prints_set ON set_prints(set_code);
CREATE TABLE IF NOT EXISTS scan_log(id INTEGER PRIMARY KEY, sitzung INTEGER, scryfall_id TEXT, foil TEXT, condition TEXT, language TEXT, qty INTEGER,
  zug TEXT, at TEXT);
CREATE INDEX IF NOT EXISTS scan_log_sitzung ON scan_log(sitzung);
CREATE TABLE IF NOT EXISTS scan_liste(id INTEGER PRIMARY KEY, scryfall_id TEXT, foil TEXT, condition TEXT, language TEXT, qty INTEGER, zug TEXT,
  at TEXT, wahl TEXT, pruefen INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS messbilder(id INTEGER PRIMARY KEY, at TEXT, scryfall_id TEXT, foil TEXT, language TEXT, merkmale TEXT, breite INTEGER,
  hoehe INTEGER, rahmen TEXT, zug TEXT);
"""
# Sammlungszeile: Schlüssel (binder, scryfall_id, foil, condition, language) -> (qty, binder_type, added, mbid, paid); paid = Kaufpreis je Karte
COLL_INSERT = "INSERT INTO collection(binder, binder_type, scryfall_id, foil, condition, language, qty, added, mbid, paid) VALUES (?,?,?,?,?,?,?,?,?,?)"

CARD_SQL = "INSERT OR REPLACE INTO cards VALUES (" + ",".join("?" * 20) + ")"
# Einzelpreis der Sammlungszeile col zur Karte c: Foil-Preis für Foils, sonst Trend; fehlt einer, der andere
PRICE = ("CASE WHEN col.foil != 'normal' THEN COALESCE(c.price_eur_foil, c.price_eur, 0) "
         "ELSE COALESCE(c.price_eur, c.price_eur_foil, 0) END")
OWNED = "col.binder_type != 'list'"  # Wunschlisten gehören nicht zum Bestand
ARENA = "COALESCE(json_extract(c.json, '$.digital'), 0) = 1"  # Druck gibt es nur digital (MTG Arena, z. B. KLR): als Papierkarte ein Scanfehler


# --- Schema-Version und Migration (Phase 39, PLAN E27) ------------------------------------------------------------------

# Stand der Daten: Jede Datenbank einer Installation (jede Sammlung und konten.db) trägt ihn in PRAGMA user_version; katalog.db nicht.
# Eine Schema-Änderung erhöht STAND um eins und trägt unter der neuen Nummer einen Schritt ein: hier für die Sammlungen, in
# konten.MIGRATIONEN für konten.db. Ein Stand ohne Eintrag ändert an dieser Art Datenbank nur die Nummer. Ein Schritt bekommt (conn, path)
# und läuft samt Versionssprung in einer Transaktion: also nur einzelne execute, kein commit, kein executescript, kein „with conn“ und kein
# Helfer, der so etwas tut (das würde die Transaktion beenden; _kein_abschluss lässt es scheitern). Ein eingetragener Schritt ändert sich
# nie mehr.
STAND = 3
ZU_NEU = "Diese Sammlung stammt aus einer neueren Version. Bitte die App aktualisieren."
_migration = threading.RLock()  # ein Prozess sichert und migriert nur einmal, auch wenn mehrere Anfragen zugleich eine alte Datenbank öffnen


class NichtMigriert(ValueError):
    """Die Datenbank ist nicht auf dem Stand der App und bleibt, wie sie ist: Sie ist neuer als die App (ZU_NEU), die Sicherung davor
    ließ sich nicht anlegen, oder ein Schritt ist gescheitert und zurückgenommen."""


def _stand_1(conn, path):
    """Stand 1 = das Schema bis Phase 38. Eine Datenbank ohne Version ist neu oder stammt aus irgendeiner Phase davor und durchläuft, was
    connect bis dahin bei jedem Verbinden tat: fehlende Tabellen und Indizes anlegen, die Spalten paid (Phase 14, Kaufpreise einmal aus dem
    Archiv) und pruefen (Phase 32) nachziehen, einen leeren Preisverlauf mit den gespeicherten Preisen beginnen (Tag des Abrufs)."""
    for sql in SCHEMA.split(";"):
        if sql.strip():
            conn.execute(sql)
    if "paid" not in [r[1] for r in conn.execute("PRAGMA table_info(collection)")]:
        conn.execute("ALTER TABLE collection ADD COLUMN paid REAL")
        if str(path) != ":memory:":
            kaufpreise_nachtragen(conn, Path(path).parent / "imports")
    if "pruefen" not in [r[1] for r in conn.execute("PRAGMA table_info(scan_liste)")]:
        conn.execute("ALTER TABLE scan_liste ADD COLUMN pruefen INTEGER DEFAULT 0")
    if not conn.execute("SELECT 1 FROM price_history LIMIT 1").fetchone():
        conn.execute("INSERT OR IGNORE INTO price_history SELECT scryfall_id, substr(updated_at, 1, 10), price_eur, price_eur_foil FROM cards "
                     "WHERE updated_at IS NOT NULL AND (price_eur IS NOT NULL OR price_eur_foil IS NOT NULL)")


def _stand_2(conn, path):
    """Stand 2 (Phase 44, PLAN E25): Die Netzquellen bekommen Schalter, EDHREC ist für neue Installationen aus. Eine Sammlung, die schon EDHREC-Daten
    hat (geladene Seiten oder die Salt-Liste), merkt sich das in meta unter sources.KEY_ALT; solange die Oberfläche nichts anderes speichert, bleibt
    EDHREC dann an. Eine neue oder leere Sammlung merkt sich nichts. Es ändert sich keine Tabelle und keine Sammlungszeile."""
    if conn.execute("SELECT 1 FROM edhrec LIMIT 1").fetchone() or conn.execute("SELECT 1 FROM meta WHERE key = 'salt'").fetchone():
        conn.execute("INSERT OR IGNORE INTO meta VALUES (?, ?)", (sources.KEY_ALT, json.dumps({"edhrec": True})))


def _stand_3(conn, path):
    """Stand 3 (Phase 46, PLAN E33): Die Decknamen, die bis dahin fest im Code standen, werden eine Einstellung je Sammlung (meta „fertige_decks“).
    Eine bestehende Sammlung, also eine mit irgendeinem Inhalt, bekommt genau die sieben Namen von damals, ihr Sortier-Plan ändert sich um keine
    Karte. Eine neue oder leere Sammlung bekommt nichts: Ohne Eintrag ist die Liste leer. Es ändert sich keine Tabelle und keine Sammlungszeile.
    Die Namen stehen nur hier: eine Geschichte, die sich nie mehr ändert."""
    if _hat_inhalt(conn):
        namen = ["Death Toll", "Graveyard Overdrive Collector's Edition", "Hare Raising", "Jump Scare!", "Miracle Worker", "Multiverse Reforged", "Otter Limits"]
        conn.execute("INSERT OR IGNORE INTO meta VALUES (?, ?)", (FERTIGE_DECKS, json.dumps(namen, ensure_ascii=False)))


MIGRATIONEN = {1: _stand_1, 2: _stand_2, 3: _stand_3}


def _stand(conn):
    """Stand der Datenbank. Liegt er über dem der App, öffnet die App sie nicht (kein Downgrade ohne Sicherung): NichtMigriert, nichts geschrieben."""
    stand = conn.execute("PRAGMA user_version").fetchone()[0]
    if stand > STAND:
        raise NichtMigriert(ZU_NEU)
    return stand


def _hat_inhalt(conn):
    """Steht in irgendeiner Tabelle eine Zeile? Nur dann braucht es vor einer Migration eine Sicherung."""
    tabellen = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
    return any(conn.execute('SELECT 1 FROM "' + t.replace('"', '""') + '" LIMIT 1').fetchone() for t in tabellen)


def _kein_abschluss(aktion, *rest):
    """Authorizer, solange ein Schritt läuft: COMMIT, ROLLBACK und BEGIN sind verboten. So kann kein Schritt die Transaktion beenden, auch
    nicht über einen Helfer mit commit, executescript oder „with conn“; der Versuch wirft, und der Schritt wird zurückgenommen."""
    return sqlite3.SQLITE_DENY if aktion == sqlite3.SQLITE_TRANSACTION else sqlite3.SQLITE_OK


def migrieren(conn, path, schritte):
    """Datenbank auf den Stand der App bringen, für Sammlungen und konten.db. schritte: {Stand: Schritt}. Gleicher Stand: nichts. Höherer:
    NichtMigriert mit ZU_NEU. Niedrigerer: Hat die Datenbank Inhalt, steht vor dem ersten Schritt eine Sicherung aller Sammlungen
    (konten.sicherung_vor_migration, eine je Versionssprung); gelingt sie nicht, wird nicht migriert. Dann je Stand eine Transaktion mit
    Schritt und Versionssprung: Wirft der Schritt, ist beides zurückgenommen. Jeder Fehler kommt als NichtMigriert heraus; der Grund steht
    nur auf stderr, denn die Meldung geht bis in die Oberfläche."""
    if _stand(conn) == STAND:
        return
    with _migration:
        stand = _stand(conn)  # eine andere Anfrage kann inzwischen fertig sein
        sicherung, gemacht = None, False
        if stand < STAND and str(path) != ":memory:" and _hat_inhalt(conn):
            import konten  # erst hier: konten importiert mtg
            try:
                sicherung = konten.sicherung_vor_migration(STAND, path)
            except Exception as e:
                print(f"Keine Sicherung vor der Umstellung von {path}: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
                raise NichtMigriert("Vor der Umstellung der Datenbank auf den neuen Stand ließ sich keine Sicherung anlegen, deshalb bleibt sie "
                                    "unverändert. Der Grund steht in der Ausgabe des Programms.") from e
        while stand < STAND:
            ziel = stand + 1
            try:
                conn.execute("BEGIN IMMEDIATE")  # ausdrücklich: ohne BEGIN gälten CREATE, ALTER und PRAGMA user_version sofort
                stand = _stand(conn)  # erst mit der Schreibsperre sicher: ein zweiter Prozess kann inzwischen migriert haben
                if stand < STAND:
                    ziel = stand + 1
                    if schritte.get(ziel):
                        conn.set_authorizer(_kein_abschluss)
                        try:
                            schritte[ziel](conn, path)
                        finally:
                            conn.set_authorizer(None)
                    conn.execute(f"PRAGMA user_version = {ziel}")
                    conn.commit()
                    stand, gemacht = ziel, True
                else:
                    conn.rollback()
            except BaseException as e:
                if conn.in_transaction:
                    conn.rollback()
                if isinstance(e, NichtMigriert) or not isinstance(e, Exception):  # zu neu, oder Abbruch von außen
                    raise
                print(f"Umstellung von {path} auf Stand {ziel} gescheitert: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
                raise NichtMigriert("Die Datenbank ließ sich nicht auf den neuen Stand bringen. Der Schritt ist zurückgenommen, die Daten sind "
                                    "unverändert. Der Grund steht in der Ausgabe des Programms.") from e
        if sicherung and gemacht:  # nicht, wenn ein anderer Prozess schneller war: Dessen Sicherung hält den alten Stand
            print(f"Datenbank {path} auf Stand {STAND} gebracht. Sicherung davor: {sicherung}", file=sys.stderr, flush=True)


def _wal(conn, warten):
    """Auf WAL umstellen. Stellen mehrere Verbindungen eine neue Datei zugleich um, wartet SQLite dabei nicht: Das Umstellen liest erst und
    will dann schreiben, und aus einer Lesesperre heraus meldet SQLite „database is locked“ sofort statt nach der Wartezeit (sonst könnten
    sich zwei gegenseitig blockieren). Deshalb hier selbst noch einmal versuchen, höchstens so lange wie die Wartezeit der Verbindung."""
    ende = time.monotonic() + warten
    while True:
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            return
        except sqlite3.OperationalError as e:
            if e.sqlite_errorcode & 0xFF != sqlite3.SQLITE_BUSY or time.monotonic() > ende:
                raise
            time.sleep(0.01)


def connect(path=None):
    """Verbindung zu einer Sammlung auf dem Stand der App: Eine neue oder ältere Datenbank bringt migrieren dorthin, eine neuere
    öffnet die App nicht (NichtMigriert)."""
    path = path or DB
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        _stand(conn)  # vor dem ersten Schreiben: An einer neueren Datenbank ändert die App nichts, auch nicht den Journal-Modus
        if str(path) != ":memory:":
            _wal(conn, 30)
        migrieren(conn, path, MIGRATIONEN)
    except BaseException:
        conn.close()
        raise
    return conn


def now_iso():
    return datetime.now(timezone.utc).strftime(TS)


def eur(x):
    return f"{x:,.2f}".translate(str.maketrans(",.", ".,")) + " €"


def pct(x):
    return f"{x * 100:.0f} %"


def zahl(n):
    return f"{n:,}".replace(",", ".")


def unit_price(card, foil):
    a, b = (card["price_eur_foil"], card["price_eur"]) if foil != "normal" else (card["price_eur"], card["price_eur_foil"])
    return a if a is not None else (b if b is not None else 0.0)


# --- Karten (Scryfall) -------------------------------------------------------------------------------------------

def card_row(d, ts):
    faces = d.get("card_faces") or [{}]
    f0 = faces[0]
    p = d.get("prices") or {}
    num = lambda x: float(x) if x else None
    return (d["id"], d.get("oracle_id") or f0.get("oracle_id"), d["name"], d["set"].upper(), d["collector_number"],
            d.get("lang"), d.get("type_line"), d.get("mana_cost") or f0.get("mana_cost") or "", d.get("cmc"),
            "".join(d.get("color_identity") or []),
            d.get("oracle_text") or "\n//\n".join(f.get("oracle_text", "") for f in faces), d.get("rarity"),
            int((d.get("legalities") or {}).get("commander") == "legal"), int(bool(d.get("game_changer"))),
            d.get("edhrec_rank"), num(p.get("eur")), num(p.get("eur_foil") or p.get("eur_etched")),
            (d.get("image_uris") or f0.get("image_uris") or {}).get("normal"), json.dumps(d, separators=(",", ":")), ts)


def store_cards(conn, cards, ts=None):
    ts = ts or now_iso()
    rows = [card_row(d, ts) for d in cards]
    # Wächter (Phase 19): Legalität und Game-Changer-Flag gegen den gespeicherten Stand; Spalten 12 und 13 = legal_commander, game_changer
    alt = {r[0]: (r[1], r[2]) for r in conn.execute("SELECT scryfall_id, legal_commander, game_changer FROM cards WHERE scryfall_id IN (SELECT value FROM json_each(?))",
                                                    (json.dumps([r[0] for r in rows]),))}
    neu = set()
    for r in rows:
        if r[0] in alt:
            for spalte, (an, aus) in ((12, ("unban", "ban")), (13, ("gc", "gc_weg"))):
                if bool(alt[r[0]][spalte - 12]) != bool(r[spalte]):
                    neu.add((ts[:10], r[1], an if r[spalte] else aus, ""))
    conn.executemany("INSERT OR IGNORE INTO waechter(day, oracle_id, art, info) VALUES (?,?,?,?)", sorted(neu))
    conn.executemany(CARD_SQL, rows)
    # Preisverlauf: ein Wert je Karte und Tag (ein späterer Abruf am selben Tag überschreibt); Spalten 15 und 16 = Preis, Foil-Preis
    conn.executemany("INSERT OR REPLACE INTO price_history VALUES (?,?,?,?)", [(r[0], ts[:10], r[15], r[16]) for r in rows if r[15] is not None or r[16] is not None])
    conn.commit()


def ensure_cards(conn, ids, fetch):
    """Unbekannte Scryfall-IDs nachladen. -> bei Scryfall nicht gefundene IDs"""
    todo = sorted(set(ids) - {r[0] for r in conn.execute("SELECT scryfall_id FROM cards")})
    if not todo:
        return []
    cards, missing = fetch(todo)
    store_cards(conn, cards)
    return missing


def refresh_prices(conn, fetch, now=None):
    """Karten im Besitz neu laden, wenn älter als 24 h, dann den Wert des Tages merken. -> Anzahl"""
    cutoff = ((now or datetime.now(timezone.utc)) - timedelta(hours=PRICE_MAX_AGE_H)).strftime(TS)
    ids = [r[0] for r in conn.execute(
        "SELECT scryfall_id FROM cards WHERE updated_at < ? AND scryfall_id IN (SELECT scryfall_id FROM collection UNION SELECT scryfall_id FROM wishlist)",
        (cutoff,))]
    if ids:
        store_cards(conn, fetch(ids)[0], now.strftime(TS) if now else None)
    record_value(conn, now.date().isoformat() if now else None)
    return len(ids)


# --- Kaufpreis, Wertverlauf, Cardmarket-Preisliste (Phase 14) ---------------------------------------------------------

def kaufpreise_nachtragen(conn, archiv):
    """Einmalig bei der Umstellung: Kaufpreise aus den archivierten ManaBox-CSVs (älteste zuerst, neuere gewinnen). Der Binder-Name steckt nicht
    im Archiv-Dateinamen, deshalb gilt der Preis je Druck, Foil, Zustand und Sprache; nur leere Kaufpreise werden gefüllt, Stückzahlen nie. -> Zeilen"""
    preise = {}
    for f in sorted(Path(archiv).glob("*.csv")) if Path(archiv).is_dir() else []:
        try:
            raw = f.read_bytes()
            if detect(read_text(raw)) != "manabox":
                continue
            rows = read_manabox(raw, f.name)[1]
        except (ValueError, OSError, UnicodeDecodeError):
            continue
        preise.update({k[1:]: v[4] for k, v in rows.items() if v[4] is not None})
    n = 0
    for (sid, foil, cond, lang), p in preise.items():
        n += conn.execute("UPDATE collection SET paid = ? WHERE scryfall_id = ? AND foil = ? AND condition = ? AND language = ? AND paid IS NULL",
                          (p, sid, foil, cond, lang)).rowcount
    return n


def paid_stats(conn):
    """Kaufpreis gegen Marktwert, nur für Karten mit Kaufpreis (Tokens und Decklisten haben keinen). -> {cards, paid, value, all}"""
    r = conn.execute(f"SELECT COALESCE(SUM(CASE WHEN col.paid IS NOT NULL THEN col.qty END), 0), COALESCE(SUM(col.qty * col.paid), 0), "
                     f"COALESCE(SUM(CASE WHEN col.paid IS NOT NULL THEN col.qty * {PRICE} END), 0), COALESCE(SUM(col.qty), 0) "
                     f"FROM collection col JOIN cards c USING (scryfall_id) WHERE {OWNED}").fetchone()
    return {"cards": r[0], "paid": r[1], "value": r[2], "all": r[3]}


def record_value(conn, day=None):
    """Wert der Sammlung an diesem Tag (ein Eintrag je Tag, ein späterer überschreibt) für den Wertverlauf."""
    v = conn.execute(f"SELECT COALESCE(SUM(col.qty * {PRICE}), 0), COALESCE(SUM(col.qty), 0) FROM collection col JOIN cards c USING (scryfall_id) "
                     f"WHERE {OWNED}").fetchone()
    p = paid_stats(conn)
    with conn:
        conn.execute("INSERT OR REPLACE INTO value_history VALUES (?,?,?,?,?)", (day or date.today().isoformat(), v[0], v[1], p["paid"], p["value"]))


def value_history(conn, days=365):
    return [dict(r) for r in conn.execute("SELECT * FROM value_history WHERE day >= ? ORDER BY day",
                                          ((date.today() - timedelta(days=days)).isoformat(),))]


CM_FELDER = ("low", "trend", "avg7", "avg30", "low-foil", "trend-foil", "avg7-foil", "avg30-foil")
CM_PRODUKT = re.compile(r'\{"idProduct":(\d+),[^{}]*\}')


def cardmarket_store(conn, text, day=None):
    """Cardmarket-Preisliste (price_guide_1.json, Parsing nur hier) für die Karten im Besitz übernehmen. Nur passende Produkte werden
    gelesen (die Datei hat ca. 26 MB). Zuordnung über cardmarket_id aus dem Scryfall-JSON. -> Anzahl"""
    ids = {r[0] for r in conn.execute("SELECT DISTINCT json_extract(c.json, '$.cardmarket_id') FROM cards c WHERE json_extract(c.json, '$.cardmarket_id') IS NOT NULL "
                                      "AND c.scryfall_id IN (SELECT scryfall_id FROM collection UNION SELECT scryfall_id FROM wishlist)")}
    rows = []
    for m in CM_PRODUKT.finditer(text):
        if int(m.group(1)) in ids:
            d = json.loads(m.group(0))
            rows.append((d["idProduct"], *(d.get(k) for k in CM_FELDER), day or date.today().isoformat()))
    if not rows and ids and '"priceGuides"' not in text[:200]:
        raise ValueError("Cardmarket-Preisliste hat ein unerwartetes Format")
    with conn:
        conn.executemany("INSERT OR REPLACE INTO cm_price VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    return len(rows)


MOVE_DAYS = 14      # Vergleich: Preis heute gegen den von vor so vielen Tagen
MOVE_PCT = 0.15     # gemeldet ab dieser Änderung ...
MOVE_EUR = 1.0      # ... wenn die Karte heute oder damals mindestens so viel kostete
MOVE_MIN_SPAN = 3   # gibt es den Stand von vor 14 Tagen noch nicht, zählt der älteste, wenn er mindestens so viele Tage zurückliegt
MOVE_TOP = 10


def movers(conn, days=MOVE_DAYS):
    """Preisbewegung der Karten im Besitz aus price_history (Foil-Kopien mit Foil-Preis). Je Karte der Druck mit der größten Änderung.
    -> {"ready" (genug Verlauf?), "span" (Tage Verlauf), "days", "up", "down"}; Einträge: oracle_id, name, image, set, foil, price, old, pct, days, qty"""
    out = {"ready": False, "span": 0, "days": days, "min_pct": MOVE_PCT, "min_eur": MOVE_EUR, "up": [], "down": []}
    ends = conn.execute("SELECT MIN(day), MAX(day) FROM price_history").fetchone()
    if not ends[1]:
        return out
    out["span"] = (date.fromisoformat(ends[1]) - date.fromisoformat(ends[0])).days
    out["ready"] = out["span"] >= MOVE_MIN_SPAN
    cut = (date.fromisoformat(ends[1]) - timedelta(days=days)).isoformat()
    stand = lambda sql, *a: {r["scryfall_id"]: r for r in conn.execute(sql, a)}
    base = "SELECT scryfall_id, eur, eur_foil, {} day FROM price_history {} GROUP BY scryfall_id"
    latest, ref = stand(base.format("MAX(day)", "")), stand(base.format("MAX(day)", "WHERE day <= ?"), cut)
    first = stand(base.format("MIN(day)", ""))
    best = {}
    for o in conn.execute(f"SELECT col.scryfall_id sid, col.foil != 'normal' foil, c.oracle_id, c.name, c.image_url image, c.set_code, SUM(col.qty) qty "
                          f"FROM collection col JOIN cards c USING (scryfall_id) WHERE {OWNED} AND c.oracle_id IS NOT NULL GROUP BY col.scryfall_id, col.foil"):
        new = latest.get(o["sid"])
        old = ref.get(o["sid"]) or first.get(o["sid"])
        if not new or not old or old["day"] >= new["day"] or (old["day"] > cut and (date.fromisoformat(new["day"]) - date.fromisoformat(old["day"])).days < MOVE_MIN_SPAN):
            continue
        price = lambda r: (r["eur_foil"] if r["eur_foil"] is not None else r["eur"]) if o["foil"] else (r["eur"] if r["eur"] is not None else r["eur_foil"])
        p1, p0 = price(new), price(old)
        if not p0 or p1 is None or max(p0, p1) < MOVE_EUR or abs(p1 - p0) < MOVE_PCT * p0:
            continue
        e = {"oracle_id": o["oracle_id"], "name": o["name"], "image": o["image"], "set": o["set_code"], "foil": bool(o["foil"]), "price": p1, "old": p0,
             "pct": (p1 - p0) / p0, "days": (date.fromisoformat(new["day"]) - date.fromisoformat(old["day"])).days, "qty": o["qty"]}
        if o["oracle_id"] not in best or abs(p1 - p0) > abs(best[o["oracle_id"]]["price"] - best[o["oracle_id"]]["old"]):
            best[o["oracle_id"]] = e
    rows = list(best.values())
    out["up"] = sorted((e for e in rows if e["pct"] > 0), key=lambda e: (-(e["price"] - e["old"]), e["name"]))[:MOVE_TOP]
    out["down"] = sorted((e for e in rows if e["pct"] < 0), key=lambda e: (e["price"] - e["old"], e["name"]))[:MOVE_TOP]
    return out


def list_decks(conn):
    """Binder, die aus einer Deckliste importiert wurden (eigene Quelle, ein Sammlungsexport lässt sie stehen). Decks aus dem
    ManaBox-Sammlungsexport können auch einen Eintrag haben (gewählter Commander), aber ohne Datei."""
    return {r[0][len("deckbinder:"):] for r in conn.execute("SELECT key, value FROM meta WHERE key LIKE 'deckbinder:%'")
            if json.loads(r[1]).get("file")}


def fertige_decks(conn):
    """Namen der Binder, die fertige Decks sind, auch wenn der Export keinen Binder Type nennt (Einstellung dieser Sammlung, E33). Eine neue
    Sammlung hat keinen; bestehende bekamen die Namen ihrer Zeit über die Migration (Stand 3). -> Liste"""
    r = conn.execute("SELECT value FROM meta WHERE key = ?", (FERTIGE_DECKS,)).fetchone()
    try:
        namen = json.loads(r[0]) if r else []
    except ValueError:
        namen = []
    return [n for n in namen if isinstance(n, str) and n] if isinstance(namen, list) else []


def set_fertige_decks(conn, namen):
    """Die Namen der fertigen Decks ersetzen (nur Text, ohne Leerraum am Rand, ohne Doppelte). Ein Scan-Binder darf dazugehören (Phase 60: ein
    eingescanntes Deck). Ändert den Sortier-Plan und „verfügbar“ sofort, die Karten selbst bleiben unberührt. -> Liste"""
    if not isinstance(namen, (list, tuple)) or any(not isinstance(n, str) for n in namen):
        raise ValueError("Erwartet: eine Liste von Binder-Namen")
    neu = list(dict.fromkeys(n.strip() for n in namen if n.strip()))
    if len(neu) > FERTIGE_DECKS_MAX or any(len(n) > 80 for n in neu):
        raise ValueError(f"Höchstens {FERTIGE_DECKS_MAX} Namen mit je höchstens 80 Zeichen")
    with conn:
        conn.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (FERTIGE_DECKS, json.dumps(neu, ensure_ascii=False)))
    return fertige_decks(conn)


def haupt_meta(key):
    """Eintrag aus meta der Hauptsammlung (die Datei DB), nur lesend und ohne sie anzulegen oder zu migrieren; ohne Datei, ohne Eintrag oder bei
    einem Lesefehler None. Einstellungen der ganzen Installation stehen dort (wie sources.gespeichert), auch wenn ein Unterkonto offen ist."""
    pfad = Path(DB)
    if str(DB) == ":memory:" or not pfad.is_file():
        return None
    try:
        with closing(sqlite3.connect(f"file:{urllib.parse.quote(pfad.as_posix(), safe='/:')}?mode=ro", uri=True, timeout=5)) as c:
            r = c.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    except sqlite3.Error:
        return None
    return r[0] if r else None


def proxy_blatt():
    """Ist das Proxy-Blatt eingeschaltet? Für die ganze Installation, standardmäßig aus, auch in bestehenden (E23)."""
    return haupt_meta(PROXY_BLATT) == "1"


def proxy_blatt_setzen(conn, an):
    """Proxy-Blatt ein- oder ausschalten (conn: Hauptsammlung; wer es aufruft, prüft, dass es das Hauptkonto ist). -> an?"""
    with conn:
        conn.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (PROXY_BLATT, "1" if an else "0"))
    return bool(an)


def deck_binders(conn, exclude=None):
    """Binder, die fertige Decks sind: Binder Type „deck“ (Sammlungsexport, importierte Deckliste) und die Namen aus fertige_decks (E1, E33)."""
    names = set(fertige_decks(conn) if exclude is None else exclude)
    return names | {r[0] for r in conn.execute("SELECT DISTINCT binder FROM collection WHERE binder_type = 'deck'")}


def scan_binders(conn):
    """Binder, die die App selbst führt (Binder Type „scan“, PLAN E18): per Kamera erfasst oder aus ManaBox übernommen. Kein Import ersetzt,
    löscht oder erkennt sie; Kopien kommen nur über das Erfassen dazu und gehen nur ausdrücklich weg (ändern, als verkauft buchen)."""
    return {r[0] for r in conn.execute("SELECT DISTINCT binder FROM collection WHERE binder_type = 'scan'")}


def available(conn, exclude=None):
    """oracle_id -> verfügbare Kopien (ohne Wunschlisten und fertige Decks)."""
    ex = json.dumps(sorted(deck_binders(conn, exclude)))
    return {r[0]: r[1] for r in conn.execute(
        f"SELECT c.oracle_id, SUM(col.qty) FROM collection col JOIN cards c USING (scryfall_id) "
        f"WHERE {OWNED} AND col.binder NOT IN (SELECT value FROM json_each(?)) AND c.oracle_id IS NOT NULL "
        f"GROUP BY c.oracle_id", (ex,))}


# --- Sortier-Plan ------------------------------------------------------------------------------------------------

def rules(conn):
    """Regeln des Sortier-Plans: Konstanten, überschrieben von den Einstellungen aus der Oberfläche (meta „rules“)."""
    r = conn.execute("SELECT value FROM meta WHERE key = 'rules'").fetchone()
    return RULES | (json.loads(r[0]) if r else {})


def set_rules(conn, keep=None, staples=None, sell_min=None):
    """Regeln ändern (None = unverändert). keep, staples: 0 bis 4 Kopien; sell_min: Euro."""
    neu = rules(conn)
    for k, v, lo, hi, typ in (("keep", keep, 0, 4, int), ("staples", staples, 0, 4, int), ("sell_min", sell_min, 0, 1000, float)):
        if v is not None:
            try:
                v = typ(v)
            except (TypeError, ValueError):
                raise ValueError(f"{k} muss eine Zahl sein") from None
            if not lo <= v <= hi:
                raise ValueError(f"{k} muss zwischen {lo} und {hi} liegen")
            neu[k] = v
    with conn:
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('rules', ?)", (json.dumps(neu),))
    return neu


def plan(conn, sell_min=None, exclude=None, zerlegt=None):
    """Sortier-Plan, bei jedem Aufruf aus den Daten berechnet (gespeichert sind nur manuelle Entscheidungen).
    Fertige Decks (deck_binders) liegen ganz im Stapel Deck. Je übrige Kopie: gespeichertes Deck > manuelle Entscheidung > Regel.
    zerlegt: ID eines gespeicherten Decks oder Name eines fertigen, das als zerlegt gilt (Phase 22, „Deck zerlegen → wohin“).
    -> Zeilen (Druck, Binder, Stapel, Menge)"""
    rg = rules(conn)
    sell_min = rg["sell_min"] if sell_min is None else sell_min
    fest = deck_binders(conn, exclude) - {zerlegt}
    rows = conn.execute(
        f"SELECT col.binder, col.scryfall_id, col.foil, col.condition, col.language, col.qty, col.added, c.oracle_id, c.name, "
        f"c.set_code, c.number, c.type_line, c.rarity, c.image_url, c.edhrec_rank AS rank, {PRICE} AS price, "
        f"EXISTS (SELECT 1 FROM tags t WHERE t.oracle_id = c.oracle_id AND t.tag = 'top10') AS top10 "
        f"FROM collection col JOIN cards c USING (scryfall_id) "
        f"WHERE {OWNED} AND c.oracle_id IS NOT NULL "
        f"ORDER BY c.oracle_id, price, col.binder, col.scryfall_id").fetchall()
    decks = defaultdict(list)
    for oid, name in conn.execute("SELECT dc.oracle_id, d.name FROM deck_cards dc JOIN decks d ON d.id = dc.deck_id WHERE d.id IS NOT ? ORDER BY d.name, d.id",
                                  (zerlegt if isinstance(zerlegt, int) else None,)):
        decks[oid].append(name)
    manual = {r[0]: (r[1], r[2] or 0) for r in conn.execute("SELECT oracle_id, status, keep FROM card_status")}
    out = []

    def zeile(r, stack, deck, n):
        out.append({"binder": r["binder"], "scryfall_id": r["scryfall_id"], "oracle_id": r["oracle_id"], "name": r["name"],
                    "set": r["set_code"], "number": r["number"], "foil": r["foil"], "condition": r["condition"], "language": r["language"],
                    "rarity": r["rarity"], "image": r["image_url"], "price": r["price"], "added": r["added"], "stack": stack, "deck": deck, "qty": n,
                    "basic": r["type_line"].startswith("Basic Land"), "token": "Token" in r["type_line"]})
    for oid, grp in groupby(rows, key=lambda r: r["oracle_id"]):
        grp = list(grp)
        for r in grp:
            if r["binder"] in fest:
                zeile(r, "deck", r["binder"], r["qty"])
        grp = [r for r in grp if r["binder"] not in fest]
        if not grp:
            continue
        basic = grp[0]["type_line"].startswith("Basic Land")
        staple = not basic and any(r["top10"] or (r["rank"] is not None and r["rank"] <= RANK_STAPLE) for r in grp)
        behalten = max(rg["keep"], rg["staples"]) if staple else rg["keep"]
        # ponytail: Kopien nach Preis aufsteigend, die billigsten gehen in Deck/Behalten, die teureren in den Verkauf
        copies = [r for r in grp for _ in range(r["qty"])]
        decked = [] if basic else decks.get(oid, [])[:len(copies)]  # Basics sind unbegrenzt, nie "verplant"
        status, keep = manual.get(oid, (None, 0))
        counts = defaultdict(int)
        for i, r in enumerate(copies):
            j = i - len(decked)  # Position unter den Kopien ohne Deck
            if i < len(decked):
                stack, deck = "deck", decked[i]
            elif status == "keep":
                stack, deck = "keep", None
            elif status in ("sell", "bulk"):
                stack, deck = ("keep" if j < keep else status), None
            elif basic or j < behalten:  # Basics braucht jedes Deck, sie bleiben alle
                stack, deck = "keep", None
            else:
                stack, deck = ("sell" if r["price"] >= sell_min else "bulk"), None
            counts[(r["binder"], r["scryfall_id"], r["foil"], r["condition"], r["language"], stack, deck)] += 1
        meta = {(r["binder"], r["scryfall_id"], r["foil"], r["condition"], r["language"]): r for r in grp}
        for (b, sid, foil, cond, lang, stack, deck), n in counts.items():
            zeile(meta[(b, sid, foil, cond, lang)], stack, deck, n)
    return out


def stacks_by_card(rows):
    """oracle_id -> {deck: [Namen], keep, sell, bulk} (Mengen)."""
    out = defaultdict(lambda: {"deck": [], "keep": 0, "sell": 0, "bulk": 0})
    for r in rows:
        if r["stack"] == "deck":
            out[r["oracle_id"]]["deck"] += [r["deck"]] * r["qty"]
        else:
            out[r["oracle_id"]][r["stack"]] += r["qty"]
    return out


def stack_totals(rows):
    t = {s: {"cards": 0, "value": 0.0} for s in STACKS}
    for r in rows:
        t[r["stack"]]["cards"] += r["qty"]
        t[r["stack"]]["value"] += r["qty"] * r["price"]
    return t


def set_status(conn, oracle_id, status, keep=0):
    """Manuelle Entscheidung für den Rest einer Karte; status None = wieder automatisch."""
    if status not in (None, "keep", "sell", "bulk"):
        raise ValueError("Status muss keep, sell, bulk oder leer sein")
    keep = max(0, int(keep or 0))
    with conn:
        if status is None:
            conn.execute("DELETE FROM card_status WHERE oracle_id = ?", (oracle_id,))
        else:
            conn.execute("INSERT OR REPLACE INTO card_status VALUES (?,?,?,?)", (oracle_id, status, keep, now_iso()))


# --- Import ------------------------------------------------------------------------------------------------------

def diff_lines(conn, delta, top=10):
    """Wichtigste Änderungen als Zeilen (nach Wertänderung) und Gesamt-Wertänderung."""
    ids = json.dumps(sorted({k[1] for k in delta}))
    info = {r["scryfall_id"]: r for r in conn.execute(
        "SELECT scryfall_id, name, set_code, price_eur, price_eur_foil FROM cards "
        "WHERE scryfall_id IN (SELECT value FROM json_each(?))", (ids,))}
    items = []
    for (_, sid, foil, _, _), d in delta.items():
        c = info.get(sid)
        p = unit_price(c, foil) if c else 0.0
        items.append((d * p, c["name"] if c else sid[:8], d, p, c["set_code"] if c else "?", foil))
    items.sort(key=lambda t: (-abs(t[0]), t[1]))
    lines = [f"{'+' if d > 0 else '−'}{abs(d)}× {name} ({st}) {eur(p)}{' Foil' if foil != 'normal' else ''}"
             for _, name, d, p, st, foil in items[:top]]
    return lines, sum(t[0] for t in items)


def scope_name(filename, binder=None):
    """Binder-Name: angegeben, sonst Dateiname (Unterstriche → Leerzeichen, Zusatz „ (1)“ vom doppelten Herunterladen weg)."""
    name = (binder or "").strip() or re.sub(r"\s*\(\d+\)$", "", Path(filename or "").stem.replace("_", " ").strip())
    return name or "Import"


def _preis(text, waehrung=""):
    """Kaufpreis aus einer CSV-Zelle (Punkt oder Komma), nur in Euro (ponytail: keine Umrechnung) -> Zahl oder None (leer, z. B. Tokens)."""
    if (waehrung or "EUR").strip().upper() not in ("EUR", "€"):
        return None
    try:
        return float((text or "").strip().replace("€", "").replace(",", ".")) if (text or "").strip() else None
    except ValueError:
        return None


def _mix(q1, p1, q2, p2):
    """Kaufpreis zusammengelegter Zeilen: Mittel nach Menge; fehlt einer, gilt der andere."""
    if p1 is None or p2 is None:
        return p1 if p2 is None else p2
    return round((q1 * p1 + q2 * p2) / (q1 + q2), 4) if q1 + q2 else p1


def read_manabox(raw, filename, binder=None):
    """ManaBox-CSV -> (Bereich, Zeilen, Übersprungenes). Bereich „*“ = Sammlungsexport (mit Binder-Spalte), sonst der Binder.
    Zeilen: (binder, scryfall_id, foil, condition, language) -> (qty, binder_type, added, mbid, paid), gleiche Schlüssel summiert."""
    reader = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""))
    cols = reader.fieldnames or []
    fehlt = [c for c in REQUIRED if c not in cols]
    if fehlt:
        raise ValueError("Pflichtspalten fehlen: " + ", ".join(fehlt))
    full = "Binder Name" in cols
    scope = "*" if full else scope_name(filename, binder)
    new, skipped = {}, {"Proxy": 0, "ohne Scryfall-ID": 0}
    for n, r in enumerate(reader, 2):
        sid = (r["Scryfall ID"] or "").strip()
        if (r.get("Proxy") or "").strip().lower() == "true":
            skipped["Proxy"] += 1
        elif not sid:
            skipped["ohne Scryfall-ID"] += 1
        else:
            try:
                qty = int(r["Quantity"])
            except ValueError:
                raise ValueError(f"Zeile {n}: Quantity „{r['Quantity']}“ ist keine Zahl") from None
            key = (r["Binder Name"].strip() if full else scope, sid, r["Foil"].strip().lower() or "normal",
                   r["Condition"].strip().lower(), r["Language"].strip())
            typ = (r.get("Binder Type") or "binder").strip().lower() if full else "binder"
            added, prev = r.get("Added") or "", new.get(key)  # gleicher Schlüssel: Mengen aufsummieren
            paid = _preis(r.get("Purchase price"), r.get("Purchase price currency"))
            new[key] = (qty + (prev[0] if prev else 0), typ, max(added, prev[2]) if prev else added, r.get("ManaBox ID") or "",
                        _mix(prev[0], prev[4], qty, paid) if prev else paid)
    return scope, new, {k: v for k, v in skipped.items() if v}


def sold_copies(conn, delta):
    """Entfernte Kopien, die laut Sortier-Plan zum Verkauf standen (Verkaufen oder Bulk), gelten als verkauft. Je Karte
    (oracle_id, Druck egal) netto entfernt, höchstens so viele wie zum Verkauf standen, die teuersten zuerst. Fertige Decks
    zählen nicht: wer eine Karte aus einer Deckliste nimmt, hat sie nicht verkauft. -> [(Schlüssel, Menge, Einzelpreis)]"""
    fest = deck_binders(conn)
    delta = {k: d for k, d in delta.items() if k[0] not in fest}
    if not any(d < 0 for d in delta.values()):
        return []
    ids = json.dumps(sorted({k[1] for k in delta}))
    karte = {r["scryfall_id"]: r for r in conn.execute(
        "SELECT scryfall_id, oracle_id, price_eur, price_eur_foil FROM cards WHERE scryfall_id IN (SELECT value FROM json_each(?))", (ids,))}
    netto, weg = defaultdict(int), defaultdict(list)
    for k, d in delta.items():
        c = karte.get(k[1])
        if c:
            netto[c["oracle_id"]] += d
            if d < 0:
                weg[c["oracle_id"]].append((unit_price(c, k[2]), k, -d))
    zum_verkauf = defaultdict(int)
    for r in plan(conn):
        if r["stack"] in ("sell", "bulk"):
            zum_verkauf[r["oracle_id"]] += r["qty"]
    out = []
    for oid, items in weg.items():
        rest = min(-netto[oid], zum_verkauf[oid])
        for p, k, n in sorted(items, key=lambda t: (-t[0], t[1])):
            if rest <= 0:
                break
            out.append((k, min(n, rest), p))
            rest -= min(n, rest)
    return out


def apply_snapshot(conn, raw, filename, scope, new, skipped=None, dry_run=False, force=False, fetch=None, archive=None, now=None):
    """Schnappschuss anwenden: Bereich „*“ ersetzt den ganzen Bestand (außer importierten Decklisten, die der Export nicht enthält),
    sonst nur diesen Binder. Schutzregel (> 25 % weg nur mit force), Diff, entfernte Kopien von der Verkaufsliste als verkauft
    buchen, Datei archivieren. Scan-Binder (E18) bleiben, wie sie sind: der Sammlungsexport lässt sie aus (gleichnamige Binder der Datei
    werden übersprungen), ein Import in einen Scan-Binder bricht ab."""
    scan = scan_binders(conn)
    if scope in scan:
        raise ValueError(f"„{scope}“ ist ein Scan-Binder: den führt die App selbst, ein Import ersetzt ihn nicht. "
                         f"Soll die Datei ein eigener Binder werden, gib ihr einen anderen Namen.")
    if scope == "*" and scan:
        aus = sum(v[0] for k, v in new.items() if k[0] in scan and v[1] != "list")
        new = {k: v for k, v in new.items() if k[0] not in scan}
        if aus:
            skipped = {**(skipped or {}), "in Scan-Bindern (führt die App)": aus}
    sql = "SELECT binder, scryfall_id, foil, condition, language, qty, binder_type, added, mbid, paid FROM collection"
    listen = json.dumps(sorted((list_decks(conn) - {k[0] for k in new}) | scan) if scope == "*" else [])
    if scope == "*":
        old = {tuple(r[:5]): tuple(r[5:]) for r in conn.execute(sql + " WHERE binder NOT IN (SELECT value FROM json_each(?))", (listen,))}
    else:
        old = {tuple(r[:5]): tuple(r[5:]) for r in conn.execute(sql + " WHERE binder = ?", (scope,))}
    delta = {k: new.get(k, (0,))[0] - old.get(k, (0,))[0] for k in new.keys() | old.keys()}
    delta = {k: d for k, d in delta.items() if d}
    eigen = {k: d for k, d in delta.items() if (new.get(k) or old.get(k))[1] != "list"}  # Wunschlisten zählen nicht zum Bestand
    added, removed = sum(d for d in eigen.values() if d > 0), -sum(d for d in eigen.values() if d < 0)
    bestand = sum(v[0] for v in old.values() if v[1] != "list")
    res = {"scope": scope, "added": added, "removed": removed, "bestand": bestand, "lines": [], "value": 0.0,
           "skipped": skipped or {}, "missing": [], "import_id": None, "sold": {"cards": 0, "value": 0.0}, "doppelt": None}
    if old == new:
        return {**res, "status": "keine Änderung"}
    res["doppelt"] = scan_doppelt(conn, eigen) if scan else None
    verkauft = sold_copies(conn, eigen)
    res["sold"] = {"cards": sum(n for _, n, _ in verkauft), "value": sum(n * p for _, n, p in verkauft)}
    if bestand and removed > MAX_LOSS * bestand and not force:
        res["lines"], res["value"] = diff_lines(conn, eigen)
        return {**res, "status": "abgebrochen"}
    res["missing"] = ensure_cards(conn, {k[1] for k, d in delta.items() if d > 0}, fetch or sources.scryfall_cards)
    res["lines"], res["value"] = diff_lines(conn, eigen)
    if dry_run:
        return {**res, "status": "probelauf"}
    sha, ts = hashlib.sha256(raw).hexdigest(), now_iso()
    deckmeta = conn.execute("SELECT value FROM meta WHERE key = ?", ("deckbinder:" + scope,)).fetchone()
    aenderung = deck_aenderungen(conn, delta, {k[0] for k in old})
    with conn:  # eine Transaktion: Bestand ersetzen, Import, Änderungen und Verkäufe festhalten
        if scope == "*":
            conn.execute("DELETE FROM collection WHERE binder NOT IN (SELECT value FROM json_each(?))", (listen,))
        else:
            conn.execute("DELETE FROM collection WHERE binder = ?", (scope,))
        conn.executemany(COLL_INSERT, [(k[0], v[1], k[1], k[2], k[3], k[4], v[0], v[2], v[3], v[4]) for k, v in new.items()])
        if added or removed:
            res["import_id"] = conn.execute("INSERT INTO imports(file, sha256, scope, added, removed, at) VALUES (?,?,?,?,?,?)",
                                            (filename, sha, scope, added, removed, ts)).lastrowid
            per_card = defaultdict(int)
            for k, d in eigen.items():
                per_card[k[1]] += d
            conn.executemany("INSERT INTO changes VALUES (?,?,?)", [(res["import_id"], sid, d) for sid, d in per_card.items() if d])
            conn.executemany("INSERT INTO sales VALUES (?,?,?,?,?,?,?,?,?)",
                             [(res["import_id"], *k, n, p, ts) for k, n, p in verkauft])
            conn.executemany("INSERT INTO deck_log(deck, at, import_id, rein, raus) VALUES (?,?,?,?,?)",
                             [(b, ts, res["import_id"], json.dumps(r, ensure_ascii=False), json.dumps(w, ensure_ascii=False)) for b, (r, w) in aenderung.items()])
        # alter Stand für „Rückgängig“ (nur die letzte Änderung; undo_import)
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('undo', ?)", (json.dumps({
            "import_id": res["import_id"], "scope": scope, "listen": json.loads(listen), "file": filename, "at": ts,
            "added": added, "removed": removed, "deckmeta": deckmeta[0] if deckmeta else None,
            "rows": [[k[0], v[1], k[1], k[2], k[3], k[4], v[0], v[2], v[3], v[4]] for k, v in old.items()]}, ensure_ascii=False),))
    if archive and res["import_id"]:
        Path(archive).mkdir(parents=True, exist_ok=True)
        endung = Path(filename or "").suffix.lower() if Path(filename or "").suffix.lower() in (".csv", ".txt") else ".csv"
        (Path(archive) / f"{(now or datetime.now()).strftime('%Y-%m-%d')}-{sha[:8]}{endung}").write_bytes(raw)
    return {**res, "status": "importiert"}


def scan_doppelt(conn, delta):
    """Neue Kopien aus einer Datei, deren Druck schon in einem Scan-Binder liegt: in der Übergangszeit vielleicht doppelt erfasst (mit der App
    und in ManaBox). Nur ein Hinweis in der Vorschau. -> {"cards", "names"} oder None"""
    neu = defaultdict(int)
    for k, d in delta.items():
        if d > 0:
            neu[k[1]] += d
    da = conn.execute("SELECT DISTINCT col.scryfall_id, c.name FROM collection col JOIN cards c USING (scryfall_id) WHERE col.binder_type = 'scan' "
                      "AND col.scryfall_id IN (SELECT value FROM json_each(?))", (json.dumps(sorted(neu)),)).fetchall()
    return {"cards": sum(neu[r[0]] for r in da), "names": sorted({r[1] for r in da})} if da else None


def binder_erkennen(conn, new):
    """Abgleich für Binder-Exporte mit neuem Dateinamen (z. B. „packs neu.csv“): steckt ein vorhandener Binder fast ganz in der Datei
    (höchstens so viel fehlt, wie die Schutzregel erlaubt) und macht er einen guten Teil davon aus, ist die Datei sein neuer Stand und kein
    zweiter Binder mit denselben Karten. Fertige Decks, Wunschlisten und Scan-Binder zählen nicht. -> {"binder", "gleich", "von"} (größter Treffer) oder None"""
    datei = defaultdict(int)
    for k, v in new.items():
        datei[k[1:]] += v[0]
    fest, je = deck_binders(conn), defaultdict(lambda: [0, 0])  # Binder -> [Karten, davon gleich in der Datei]
    for b, typ, sid, foil, cond, lang, qty in conn.execute("SELECT binder, binder_type, scryfall_id, foil, condition, language, qty FROM collection"):
        if b not in fest and typ not in ("list", "scan"):
            je[b][0] += qty
            je[b][1] += min(qty, datei.get((sid, foil, cond, lang), 0))
    treffer = [(gleich, b, von) for b, (von, gleich) in je.items()
               if gleich and gleich >= (1 - MAX_LOSS) * von and gleich >= UPDATE_DATEI * sum(datei.values())]
    if not treffer:
        return None
    gleich, b, von = max(treffer)
    return {"binder": b, "gleich": gleich, "von": von}


def _ziel_binder(conn, scope, new, binder):
    """Ohne angegebenen Binder und mit einem Namen, den es noch nicht gibt: Datei per Abgleich einem vorhandenen Binder zuordnen.
    -> (Bereich, Zeilen, erkannt oder None)"""
    if binder or scope == "*" or conn.execute("SELECT 1 FROM collection WHERE binder = ? LIMIT 1", (scope,)).fetchone():
        return scope, new, None
    e = binder_erkennen(conn, new)
    if not e:
        return scope, new, None
    return e["binder"], {(e["binder"], *k[1:]): v for k, v in new.items()}, e | {"datei": scope}


def import_csv(conn, raw, filename, binder=None, dry_run=False, force=False, fetch=None, archive=None, now=None):
    """ManaBox-CSV (bytes) als Schnappschuss importieren: Sammlungsexport ersetzt den Bestand, Binder-Export nur den Binder
    (bei neuem Dateinamen der per Abgleich erkannte Binder, siehe binder_erkennen)."""
    scope, new, skipped = read_manabox(raw, filename, binder)
    scope, new, erkannt = _ziel_binder(conn, scope, new, binder)
    return apply_snapshot(conn, raw, filename, scope, new, skipped, dry_run, force, fetch, archive, now) | {"erkannt": erkannt}


# --- Decklisten und CSVs anderer Apps (Phase 8) -------------------------------------------------------------------

DECK_LINE = re.compile(r"^(?:SB:\s*)?(\d{1,3})\s*[xX]?\s+(\S.*?)\s*$")
DECK_TAIL = re.compile(r"^(?P<name>.+?)(?:\s+\((?P<set>[A-Za-z0-9]{2,6})\)(?:\s+(?P<num>[^\s*\[\^#]+))?)?"
                       r"(?P<flags>(?:\s+(?:\*[A-Za-z]+\*|\[[^\]]*\]|\^[^^]*\^|#\S+))*)$")
DECK_HEAD = re.compile(r"^(?://\s*)?([A-Za-z][A-Za-z ]{0,30}?)\s*(?:\(\d+\))?:?$")
DECK_SKIP = ("side", "maybe", "consider", "token", "wish", "attraction", "sticker")  # Abschnitte, die nicht zum Deck gehören
CSV_ALIAS = {  # Spaltennamen anderer Apps (klein, ohne Leer- und Satzzeichen), bevorzugte zuerst
    "sid": ("scryfallid",),
    "name": ("name", "cardname", "englishname", "card", "kartenname"),
    "qty": ("quantity", "count", "qty", "amount", "anzahl", "menge"),
    "set": ("setcode", "editioncode", "expansioncode", "set", "edition", "exp", "expansion"),
    "number": ("collectornumber", "cardnumber", "number", "cn"),
    "foil": ("foil", "printing", "finish", "isfoil", "foiling"),
    "condition": ("condition", "zustand", "cond"),
    "language": ("language", "lang", "sprache"),
    "binder": ("bindername", "foldername", "folder", "binder"),
    "type": ("bindertype",),
    "proxy": ("proxy",),
    "paid": ("purchaseprice", "pricebought", "buyprice", "pricepaid", "kaufpreis", "einkaufspreis"),
}
CONDITIONS = {"m": "mint", "mint": "mint", "nm": "near_mint", "nearmint": "near_mint", "ex": "excellent", "excellent": "excellent",
              "gd": "good", "good": "good", "lp": "light_played", "lightplayed": "light_played", "lightlyplayed": "light_played",
              "pl": "played", "played": "played", "mp": "played", "moderatelyplayed": "played", "hp": "poor",
              "heavilyplayed": "poor", "po": "poor", "poor": "poor", "damaged": "poor", "dmg": "poor"}
LANGUAGES = {"english": "en", "deutsch": "de", "german": "de", "french": "fr", "francais": "fr", "italian": "it", "italiano": "it",
             "spanish": "es", "espanol": "es", "portuguese": "pt", "japanese": "ja", "jp": "ja", "korean": "ko", "russian": "ru",
             "chinesesimplified": "zh_CN", "zhs": "zh_CN", "chinesetraditional": "zh_TW", "zht": "zh_TW"}


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def name_key(name):
    """Vergleichsschlüssel für Kartennamen: Vorderseite, ohne Akzente, klein."""
    s = unicodedata.normalize("NFKD", (name or "").split(" // ")[0]).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def read_text(raw):
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:  # Excel-Exporte unter Windows
        return raw.decode("cp1252")


def parse_decklist(text):
    """Deckliste: ManaBox-Text „1 Name (SET) 123 *F*“ mit // COMMANDER, Arena/Moxfield mit Commander/Deck, reine Liste.
    -> {"name", "cards": [{qty, name, set, number, foil, commander}], "skipped": {Abschnitt: Karten}}"""
    name, section, about, heads = None, "", False, False
    cards, skipped, groups = [], defaultdict(int), [[]]
    for line in (z.strip() for z in text.splitlines()):
        if not line:
            if section.startswith(("commander", "companion")):
                section = ""  # Commander-Abschnitt endet an der Leerzeile, danach folgt das Deck (auch ohne eigenen Kopf)
            if groups[-1]:
                groups.append([])
            continue
        if line.startswith("#"):
            continue
        m = DECK_LINE.match(line)
        if not m:
            if about and line.lower().startswith("name "):
                name = line[5:].strip()
            elif h := DECK_HEAD.match(line):
                section, heads = h.group(1).strip().lower(), True
                about = section == "about"
            continue
        t = DECK_TAIL.match(m.group(2))
        flags = (t.group("flags") or "").lower()
        teil = "sideboard" if line[:3].upper() == "SB:" else section
        if any(s in teil for s in DECK_SKIP):
            skipped[teil] += int(m.group(1))
            continue
        card = {"qty": int(m.group(1)), "name": t.group("name").strip(), "set": (t.group("set") or "").lower(), "number": t.group("num") or "",
                "foil": "etched" if "*e*" in flags else "foil" if "*f*" in flags else "normal",
                "commander": teil.startswith("commander") or "[commander" in flags}
        cards.append(card)
        groups[-1].append(card)
    groups = [g for g in groups if g]
    # ohne Köpfe (MTGO-Art): eine kleine letzte Gruppe nach einer Leerzeile ist der Commander
    if not heads and not any(c["commander"] for c in cards) and len(groups) >= 2 and sum(c["qty"] for c in groups[-1]) <= 2:
        for c in groups[-1]:
            c["commander"] = True
    return {"name": name, "cards": cards, "skipped": dict(skipped)}


def _ident(item, genau=True):
    if genau and item.get("sid"):
        return {"id": item["sid"]}
    if genau and item.get("set") and item.get("number"):
        return {"set": item["set"], "collector_number": item["number"]}
    if genau and item.get("set"):
        return {"name": item["name"], "set": item["set"]}
    return {"name": item["name"]} if item.get("name") else None


def _match(ident, found):
    """Scryfall-Antwort einer Kennung zuordnen (die Antwort kommt ohne Zuordnung zurück)."""
    if "id" in ident:
        return found["id"].get(ident["id"])
    if "collector_number" in ident:
        return found["num"].get((ident["set"].lower(), ident["collector_number"].lower()))
    if "set" in ident:
        return found["name_set"].get((name_key(ident["name"]), ident["set"].lower()))
    return found["name"].get(name_key(ident["name"]))


def _local(conn, it):
    """Karte aus der eigenen Datenbank (spart Scryfall-Anfragen bei erneutem Import) -> Zeile oder None."""
    if it.get("sid"):
        return conn.execute("SELECT scryfall_id, name FROM cards WHERE scryfall_id = ?", (it["sid"],)).fetchone()
    if it.get("set") and it.get("number"):
        return conn.execute("SELECT scryfall_id, name FROM cards WHERE set_code = ? COLLATE NOCASE AND number = ? COLLATE NOCASE "
                            "LIMIT 1", (it["set"], it["number"])).fetchone()
    if it.get("name"):
        n = it["name"].split(" // ")[0].strip()
        return conn.execute("SELECT scryfall_id, name FROM cards WHERE (name = ? COLLATE NOCASE OR name LIKE ? || ' // %') "
                            "AND (? = '' OR set_code = ? COLLATE NOCASE) ORDER BY scryfall_id IN (SELECT scryfall_id FROM collection) DESC "
                            "LIMIT 1", (n, n, it.get("set") or "", it.get("set") or "")).fetchone()
    return None


def resolve(conn, items, lookup):
    """Einträge ({sid | name, set, number}) -> Scryfall-ID je Eintrag (None = nicht gefunden). Erst die eigene Datenbank,
    dann Scryfall; was genau (Edition und Nummer) nicht klappt oder einen anderen Namen trägt, noch einmal nur nach Name.
    Gefundene Karten landen in cards."""
    out, vorbehalt = [None] * len(items), {}
    stimmt = lambda it, name: not it.get("name") or name_key(it["name"]) == name_key(name)
    for i, it in enumerate(items):
        r = _local(conn, it)
        if r and stimmt(it, r["name"]):
            out[i] = r["scryfall_id"]
    for genau in (True, False):
        offen = {i: _ident(it, genau) for i, it in enumerate(items) if out[i] is None}
        idents = list({json.dumps(x, sort_keys=True): x for x in offen.values() if x}.values())
        if idents:
            cards, _ = lookup(idents)
            store_cards(conn, cards)
            found = {"id": {}, "num": {}, "name_set": {}, "name": {}}
            for c in cards:
                found["id"][c["id"]] = c
                found["num"][(c["set"].lower(), c["collector_number"].lower())] = c
                found["name_set"][(name_key(c["name"]), c["set"].lower())] = c
                found["name"].setdefault(name_key(c["name"]), c)
            for i, x in offen.items():
                c = _match(x, found) if x else None
                if c and stimmt(items[i], c["name"]):
                    out[i] = c["id"]
                elif c:  # andere Karte unter dieser Nummer: erst nach Name suchen, sonst doch diese (z. B. Name auf Deutsch)
                    vorbehalt.setdefault(i, c["id"])
    return [sid or vorbehalt.get(i) for i, sid in enumerate(out)]


def _csv_rows(text):
    """CSV-Text -> (Spalten, Zeilen); Trennzeichen , ; oder Tab, Dragon-Shield-Zeile „sep=,“ wird beachtet."""
    lines = text.splitlines()
    sep = None
    if lines and lines[0].lower().startswith("sep="):
        sep, text = lines[0][4:5] or ",", "\n".join(lines[1:])
    head = next((z for z in text.splitlines() if z.strip()), "")
    sep = sep or max(",;\t", key=head.count)
    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=sep)
    return reader.fieldnames or [], list(reader)


def read_any_csv(conn, text, filename, binder=None, lookup=None, now=None):
    """CSV einer anderen App (Moxfield, Deckbox, Dragon Shield, TCGplayer, Archidekt, Cardmarket …): Spalten per Name,
    Karten per Scryfall. Mit Binder-/Ordner-Spalte gilt sie als ganze Sammlung. -> (Bereich, Zeilen, Übersprungenes, nicht erkannt)"""
    cols, rows = _csv_rows(text)
    da = {_norm(c): c for c in cols}
    spalte = {feld: next((da[n] for n in namen if n in da), None) for feld, namen in CSV_ALIAS.items()}
    if not (spalte["name"] or spalte["sid"]):
        raise ValueError("Pflichtspalten fehlen: Scryfall ID (ManaBox) oder Name und Anzahl (andere Apps)")
    full = spalte["binder"] is not None
    scope = "*" if full else scope_name(filename, binder)
    wert = lambda r, f: (r.get(spalte[f]) or "").strip() if spalte[f] else ""
    items, skipped = [], defaultdict(int)
    for n, r in enumerate(rows, 2):
        if not (wert(r, "name") or wert(r, "sid")):
            continue
        try:
            qty = int(float(wert(r, "qty").replace(",", ".") or 1))
        except ValueError:
            raise ValueError(f"Zeile {n}: Anzahl „{wert(r, 'qty')}“ ist keine Zahl") from None
        if qty <= 0:
            skipped["Anzahl 0"] += 1
            continue
        if wert(r, "proxy").lower() in ("true", "yes", "1", "ja"):
            skipped["Proxy"] += 1
            continue
        ed = wert(r, "set")
        foil = _norm(wert(r, "foil"))
        items.append({"qty": qty, "name": wert(r, "name"), "sid": wert(r, "sid"), "set": ed.lower() if re.fullmatch(r"[A-Za-z0-9]{2,6}", ed) else "",
                      "number": wert(r, "number"), "foil": "etched" if "etched" in foil else "foil" if foil in ("foil", "true", "yes", "1", "ja", "y") else "normal",
                      "condition": CONDITIONS.get(_norm(wert(r, "condition")), wert(r, "condition").lower() or "near_mint"),
                      "language": LANGUAGES.get(_norm(wert(r, "language")), wert(r, "language") or "en"),
                      "binder": wert(r, "binder") or "Sammlung", "type": wert(r, "type").lower() or "binder", "paid": _preis(wert(r, "paid"))})
    ids = resolve(conn, items, lookup or sources.scryfall_lookup)
    alt = {tuple(r[:5]): r[5] for r in conn.execute("SELECT binder, scryfall_id, foil, condition, language, added FROM collection")}
    ts, new, unknown = (now or datetime.now(timezone.utc)).strftime(TS), {}, []
    for it, sid in zip(items, ids):
        if not sid:
            unknown.append(it["name"] or it["sid"])
            continue
        k = (it["binder"] if full else scope, sid, it["foil"], it["condition"], it["language"])
        prev = new.get(k)
        new[k] = (it["qty"] + (prev[0] if prev else 0), it["type"] if full else "binder", alt.get(k, ts), "",
                  _mix(prev[0], prev[4], it["qty"], it["paid"]) if prev else it["paid"])
    if unknown:
        skipped["nicht erkannt"] = len(unknown)
    return scope, new, dict(skipped), unknown


def detect(text):
    """Format am Inhalt erkennen (nicht an der Endung): „manabox“, „csv“ (andere App) oder „deck“ (Deckliste)."""
    lines = [z.strip() for z in text.splitlines() if z.strip()]
    if not lines:
        raise ValueError("Die Datei ist leer")
    first = lines[1] if lines[0].lower().startswith("sep=") and len(lines) > 1 else lines[0]
    cols = {_norm(c) for c in re.split(r"[,;\t]", first)}
    if {_norm(c) for c in REQUIRED} <= cols:
        return "manabox"
    if len(cols) > 1 and cols & set(CSV_ALIAS["name"] + CSV_ALIAS["sid"]):
        return "csv"
    karten = sum(bool(DECK_LINE.match(z)) for z in lines)
    rest = sum(not DECK_LINE.match(z) and not DECK_HEAD.match(z) and not z.startswith("#") for z in lines)
    if karten and rest <= karten // 4:
        return "deck"
    if re.search(r"[,;\t]", first):
        raise ValueError("Pflichtspalten fehlen: Scryfall ID (ManaBox) oder Name und Anzahl (andere Apps)")
    raise ValueError("Format nicht erkannt: weder CSV mit Kartennamen noch Deckliste wie „1 Sol Ring“")


def commander_ok(card):
    t, txt = card["type_line"] or "", card["oracle_text"] or ""
    return ("Legendary" in t and "Creature" in t) or "can be your commander" in txt or "Background" in t


def import_deck(conn, raw, text, filename, name=None, commander=None, dry_run=False, force=False, fetch=None, lookup=None,
                archive=None, now=None):
    """Deckliste als fertiges Deck: eigener Binder (Binder Type „deck“), Karten im Stapel Deck, nicht für neue Decks verfügbar.
    Erneut importiert ersetzt sie das Deck. commander: oracle_id oder Name, sonst aus der Liste (// COMMANDER)."""
    d = parse_decklist(text)
    if not d["cards"]:
        raise ValueError("Keine Karten in der Deckliste")
    scope = scope_name(filename, name or d["name"])
    ids = resolve(conn, d["cards"], lookup or sources.scryfall_lookup)
    alt = {tuple(r[:5]): r[5] for r in conn.execute(
        "SELECT binder, scryfall_id, foil, condition, language, added FROM collection WHERE binder = ?", (scope,))}
    ts, new, unknown, cmd = (now or datetime.now(timezone.utc)).strftime(TS), {}, [], []
    for c, sid in zip(d["cards"], ids):
        if not sid:
            unknown.append(c["name"])
            continue
        k = (scope, sid, c["foil"], "near_mint", "en")
        prev = new.get(k)
        new[k] = (c["qty"] + (prev[0] if prev else 0), "deck", alt.get(k, ts), "", None)
        if c["commander"]:
            cmd.append(sid)
    info = {r["scryfall_id"]: r for r in conn.execute(
        "SELECT scryfall_id, oracle_id, name, type_line, oracle_text FROM cards WHERE scryfall_id IN (SELECT value FROM json_each(?))",
        (json.dumps([s for s in ids if s]),))}
    kandidaten = sorted({info[s]["oracle_id"]: info[s]["name"] for s in ids if s and commander_ok(info[s])}.items(), key=lambda t: t[1])
    if commander:
        cmd_oids = [o for o, n in kandidaten if commander == o or name_key(n) == name_key(commander)]
    else:  # höchstens zwei (Partner, Background); fehlt der Kopf hinter // COMMANDER, nicht das ganze Deck
        cmd_oids = [o for o in dict.fromkeys(info[s]["oracle_id"] for s in cmd) if o in dict(kandidaten)][:2]
    if not cmd_oids:  # Liste ohne Commander: die frühere Wahl (Oberfläche) bleibt, auch wenn sync die Datei erneut liest
        alt = conn.execute("SELECT value FROM meta WHERE key = ?", ("deckbinder:" + scope,)).fetchone()
        cmd_oids = [o for o in (json.loads(alt[0]).get("commanders", []) if alt else []) if o in dict(kandidaten)]
    skipped = {k.capitalize(): v for k, v in d["skipped"].items()} | ({"nicht erkannt": len(unknown)} if unknown else {})
    res = apply_snapshot(conn, raw, filename, scope, new, skipped, dry_run, force, fetch, archive, now)
    if not dry_run and res["status"] != "abgebrochen":
        with conn:
            conn.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", ("deckbinder:" + scope, json.dumps({"commanders": cmd_oids, "file": filename})))
    namen = dict(kandidaten)
    return {**res, "unknown": unknown, "deck": {"name": scope, "cards": sum(v[0] for v in new.values()),
                                               "commanders": [{"oracle_id": o, "name": namen.get(o, "")} for o in cmd_oids],
                                               "candidates": [{"oracle_id": o, "name": n} for o, n in kandidaten]}}


FORMATS = {"manabox": "ManaBox-CSV", "csv": "CSV einer anderen App", "deck": "Deckliste"}


def import_file(conn, raw, filename, binder=None, commander=None, dry_run=False, force=False, fetch=None, lookup=None, archive=None, now=None):
    """Universal-Import, Format am Inhalt erkannt: ManaBox-CSV und CSVs anderer Apps als Schnappschuss eines Binders (mit
    Binder-Spalte: der ganzen Sammlung), Decklisten als fertiges Deck. binder = Ziel-Binder bzw. Deckname statt Dateiname.
    Liegt die Beispielsammlung (Phase 47, E33), ist jeder Import ein echter: Die Vorschau rechnet auf einer Kopie ohne das Beispiel und nennt es
    (Feld „beispiel“), der Import entfernt es vorher, nachdem dieselbe Rechnung auf der Kopie gelungen ist (eine kaputte Datei lässt das Beispiel stehen)."""
    if not beispiel_marker(conn):
        return _import_file(conn, raw, filename, binder, commander, dry_run, force, fetch, lookup, archive, now)
    info = beispiel_info(conn)
    kopie = connect(":memory:")
    try:
        conn.backup(kopie)
        beispiel_entfernen(kopie)
        probe = _import_file(kopie, raw, filename, binder, commander, True, force, fetch, lookup, None, now)
        bekannt = {r[0] for r in conn.execute("SELECT scryfall_id FROM cards")}  # was die Probe bei Scryfall geholt hat, behält das Original (über store_cards)
        store_cards(conn, [json.loads(r[1]) for r in kopie.execute("SELECT scryfall_id, json FROM cards") if r[0] not in bekannt])
    finally:
        kopie.close()
    hinweis = {"binder": info["binder"], "karten": info["karten"], "entfernt": not dry_run}
    if dry_run or probe["status"] == "abgebrochen":  # abgebrochen: Die Schutzregel greift auch hier, das Beispiel bleibt, bis sie nicht mehr greift
        return {**probe, "beispiel": hinweis | {"entfernt": False}}
    beispiel_entfernen(conn)
    return {**_import_file(conn, raw, filename, binder, commander, False, force, fetch, lookup, archive, now), "beispiel": hinweis}


def _import_file(conn, raw, filename, binder=None, commander=None, dry_run=False, force=False, fetch=None, lookup=None, archive=None, now=None):
    text = read_text(raw)
    fmt = detect(text)
    if fmt == "manabox":
        res = import_csv(conn, raw, filename, binder, dry_run, force, fetch, archive, now)
    elif fmt == "csv":
        scope, new, skipped, unknown = read_any_csv(conn, text, filename, binder, lookup, now)
        scope, new, erkannt = _ziel_binder(conn, scope, new, binder)
        res = apply_snapshot(conn, raw, filename, scope, new, skipped, dry_run, force, fetch, archive, now) | {"unknown": unknown, "erkannt": erkannt}
    else:
        res = import_deck(conn, raw, text, filename, binder, commander, dry_run, force, fetch, lookup, archive, now)
    return {"unknown": [], "erkannt": None, **res, "format": fmt}


def delete_binder(conn, name):
    """Binder aus dem Bestand nehmen (z. B. ein importiertes Deck). -> Anzahl entfernter Karten"""
    with conn:
        n = conn.execute("SELECT COALESCE(SUM(qty), 0) FROM collection WHERE binder = ?", (name,)).fetchone()[0]
        conn.execute("DELETE FROM collection WHERE binder = ?", (name,))
        conn.execute("DELETE FROM meta WHERE key IN (?, 'undo')", ("deckbinder:" + name,))  # danach passt der gemerkte alte Stand nicht mehr
    return n


def deck_aenderungen(conn, delta, schon_da):
    """Was ein Import an fertigen Decks ändert, die es vorher schon gab (neu hochgeladene Decks sind keine Änderung):
    Binder -> ([[Menge, Name] rein], [[Menge, Name] raus]), je Kartenname netto (andere Edition derselben Karte ist kein Tausch)."""
    fest = deck_binders(conn) & schon_da
    netto = defaultdict(lambda: defaultdict(int))
    for k, d in delta.items():
        if k[0] in fest:
            netto[k[0]][k[1]] += d
    namen = {r[0]: r[1] for r in conn.execute("SELECT scryfall_id, name FROM cards WHERE scryfall_id IN (SELECT value FROM json_each(?))",
                                              (json.dumps([sid for je in netto.values() for sid in je]),))}
    out = {}
    for b, je in netto.items():
        nach_name = defaultdict(int)
        for sid, d in je.items():
            nach_name[namen.get(sid, sid)] += d
        rein = sorted([d, n] for n, d in nach_name.items() if d > 0)
        raus = sorted([-d, n] for n, d in nach_name.items() if d < 0)
        if rein or raus:
            out[b] = (sorted(rein, key=lambda t: t[1]), sorted(raus, key=lambda t: t[1]))
    return out


def deck_log(conn, deck):
    """Änderungen eines fertigen Decks, neueste zuerst."""
    return [{"id": r["id"], "at": r["at"], "rein": json.loads(r["rein"]), "raus": json.loads(r["raus"]), "grund": r["grund"] or ""}
            for r in conn.execute("SELECT * FROM deck_log WHERE deck = ? ORDER BY id DESC", (deck,))]


def deck_log_grund(conn, log_id, grund):
    """Notiz, warum sich das Deck geändert hat."""
    with conn:
        if not conn.execute("UPDATE deck_log SET grund = ? WHERE id = ?", ((grund or "").strip()[:500], log_id)).rowcount:
            raise ValueError("Unbekannter Eintrag")


def undo_info(conn):
    """Was „Rückgängig“ zurücknehmen würde: {file, at, scope, added, removed} oder None."""
    r = conn.execute("SELECT json_extract(value, '$.file'), json_extract(value, '$.at'), json_extract(value, '$.scope'), "
                     "json_extract(value, '$.added'), json_extract(value, '$.removed') FROM meta WHERE key = 'undo'").fetchone()
    return dict(zip(("file", "at", "scope", "added", "removed"), r)) if r else None


def undo_import(conn):
    """Letzten Import zurücknehmen: alter Stand seines Bereichs (Binder, Deck oder Sammlung), Import, Änderungen und erkannte Verkäufe weg.
    Gemerkt wird nur die letzte Änderung, jeder neue Import ersetzt sie. -> undo_info des zurückgenommenen Imports"""
    r = conn.execute("SELECT value FROM meta WHERE key = 'undo'").fetchone()
    if not r:
        raise ValueError("Es gibt keinen Import, der sich rückgängig machen lässt")
    u, info = json.loads(r[0]), undo_info(conn)
    scan = scan_binders(conn)  # Scan-Binder (E18) bleiben, auch die nach dem Import erfassten
    if u["scope"] in scan:
        raise ValueError(f"„{u['scope']}“ führt inzwischen die App (Scan-Binder), der gemerkte alte Stand passt nicht mehr")
    with conn:
        if u["scope"] == "*":
            conn.execute("DELETE FROM collection WHERE binder NOT IN (SELECT value FROM json_each(?)) AND binder_type IS NOT 'scan'", (json.dumps(u["listen"]),))
        else:
            conn.execute("DELETE FROM collection WHERE binder = ?", (u["scope"],))
            if u["deckmeta"] is None:
                conn.execute("DELETE FROM meta WHERE key = ?", ("deckbinder:" + u["scope"],))
            else:
                conn.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", ("deckbinder:" + u["scope"], u["deckmeta"]))
        conn.executemany(COLL_INSERT, [r + [None] * (10 - len(r)) for r in u["rows"] if r[0] not in scan])  # Zeilen von vor Phase 14 ohne Kaufpreis
        if u["import_id"]:
            conn.execute("DELETE FROM deck_log WHERE import_id = ?", (u["import_id"],))
            conn.execute("DELETE FROM changes WHERE import_id = ?", (u["import_id"],))
            conn.execute("DELETE FROM sales WHERE import_id = ?", (u["import_id"],))
            conn.execute("DELETE FROM imports WHERE id = ?", (u["import_id"],))
        conn.execute("DELETE FROM meta WHERE key = 'undo'")
    return info


# --- Beispielsammlung zum Ausprobieren (Phase 47, PLAN E33) --------------------------------------------------------------

# Im Repository liegen nur zwei Kartenlisten (beispiel/sammlung.csv im ManaBox-Format, beispiel/deck.txt) mit Kennungen und Namen, erfundenen
# Kaufpreisen und Daten: keine Kartendaten von Scryfall (E26). Die Kartendaten holt der normale Import bei Scryfall, beim ersten Laden und nie
# vorher. meta „beispiel“ merkt, was dazugehört; ohne diesen Eintrag gibt es kein Beispiel, und die Binder gelten als echte Daten.
BEISPIEL = "beispiel"
BEISPIEL_ORDNER = ROOT / "beispiel"
BEISPIEL_BINDER = "Beispiel"
BEISPIEL_DECK = "Beispiel-Deck"
_beispiel_laeuft = threading.Lock()  # ein Prozess lädt das Beispiel nur einmal zugleich (das Laden braucht Netz und dauert einige Sekunden)


def beispiel_marker(conn):
    """meta „beispiel“ als Wörterbuch (liegt ein Beispiel?), sonst None."""
    r = conn.execute("SELECT value FROM meta WHERE key = ?", (BEISPIEL,)).fetchone()
    try:
        m = json.loads(r[0]) if r else None
    except ValueError:
        m = None
    return m if isinstance(m, dict) else None


def beispiel_leer(conn):
    """Hat die Sammlung keine Karten? Wunschlisten gehören nicht zum Bestand (OWNED); Karten auf einer Scan-Liste noch nicht."""
    return not conn.execute(f"SELECT 1 FROM collection col WHERE {OWNED} LIMIT 1").fetchone()


def _beispiel_binder(m):
    return [m.get("binder") or BEISPIEL_BINDER, m.get("deck") or BEISPIEL_DECK]


def beispiel_info(conn):
    """Für die Oberfläche: {"da", "angebot", "karten", "binder"}. da = das Beispiel liegt (karten = Karten darin, binder = seine Binder);
    angebot = die Sammlung ist leer und das Beispiel nicht geladen (nur dann wird „Beispielsammlung ansehen“ angeboten)."""
    m = beispiel_marker(conn)
    if not m:
        return {"da": False, "angebot": beispiel_leer(conn), "karten": 0, "binder": []}
    binder = _beispiel_binder(m)
    n = conn.execute("SELECT COALESCE(SUM(qty), 0) FROM collection WHERE binder IN (SELECT value FROM json_each(?)) AND binder_type IS NOT 'scan'",
                     (json.dumps(binder),)).fetchone()[0]
    return {"da": True, "angebot": False, "karten": n, "binder": binder}


def beispiel_dateien():
    """Die Kartenlisten des Beispiels (Bytes) -> (Sammlung als ManaBox-CSV, Deckliste)."""
    try:
        return (BEISPIEL_ORDNER / "sammlung.csv").read_bytes(), (BEISPIEL_ORDNER / "deck.txt").read_bytes()
    except OSError as e:
        raise ValueError(f"Die Dateien der Beispielsammlung fehlen ({BEISPIEL_ORDNER}). Sie gehören zur App, vielleicht wurde sie unvollständig kopiert.") from e


def _karten_weg(conn, ids):
    """Zwischengespeicherte Karten (und ihren Preisverlauf) entfernen, soweit nichts anderes sie braucht: Bestand, Wünsche, Scan-Liste, Scan-Protokoll,
    Messbilder, gespeicherte Decks. Ihre Rulings und Wächter-Meldungen gehen mit, wenn keine andere Karte derselben Karte mehr da ist."""
    if not ids:
        return
    j = json.dumps(sorted(ids))
    gebraucht = ("SELECT scryfall_id FROM collection WHERE scryfall_id IS NOT NULL UNION SELECT scryfall_id FROM wishlist WHERE scryfall_id IS NOT NULL "
                 "UNION SELECT scryfall_id FROM scan_liste WHERE scryfall_id IS NOT NULL UNION SELECT scryfall_id FROM scan_log WHERE scryfall_id IS NOT NULL "
                 "UNION SELECT scryfall_id FROM messbilder WHERE scryfall_id IS NOT NULL")
    weg = [r[0] for r in conn.execute(
        f"SELECT scryfall_id FROM cards WHERE scryfall_id IN (SELECT value FROM json_each(?)) AND scryfall_id NOT IN ({gebraucht}) "
        f"AND (oracle_id IS NULL OR oracle_id NOT IN (SELECT oracle_id FROM deck_cards WHERE oracle_id IS NOT NULL))", (j,))]
    wj = json.dumps(weg)
    oids = [r[0] for r in conn.execute("SELECT DISTINCT oracle_id FROM cards WHERE scryfall_id IN (SELECT value FROM json_each(?)) AND oracle_id IS NOT NULL", (wj,))]
    conn.execute("DELETE FROM cards WHERE scryfall_id IN (SELECT value FROM json_each(?))", (wj,))
    conn.execute("DELETE FROM price_history WHERE scryfall_id IN (SELECT value FROM json_each(?))", (wj,))
    rest = json.dumps(oids)
    for tabelle in ("rulings", "waechter"):
        conn.execute(f"DELETE FROM {tabelle} WHERE oracle_id IN (SELECT value FROM json_each(?)) AND oracle_id NOT IN "
                     f"(SELECT oracle_id FROM cards WHERE oracle_id IS NOT NULL)", (rest,))


def beispiel_entfernen(conn):
    """Das Beispiel restlos entfernen: seine beiden Binder, ihre Importe, Änderungen, Verkäufe und Deck-Änderungen, die Notizen und Spiele dazu, die
    Entscheidungen „behalten/verkaufen“ für Karten, die sonst nicht mehr da sind, den Wertverlauf seit dem Laden, die vom Beispiel geholten Karten
    samt Preisverlauf und den Eintrag in meta. Scan-Binder und alles andere bleiben, wie sie sind (auch bei gleichem Namen: gelöscht wird nie ein
    Scan-Binder). Ohne Beispiel ValueError. -> Karten, die damit aus dem Bestand gingen"""
    m = beispiel_marker(conn)
    if not m:
        raise ValueError("Es liegt keine Beispielsammlung.")
    binder = _beispiel_binder(m)
    bj = json.dumps(binder)
    imports = json.dumps([i for i in m.get("imports") or [] if isinstance(i, int)])
    seit = m.get("at") or ""
    with conn:
        kopien = conn.execute("SELECT COALESCE(SUM(qty), 0) FROM collection WHERE binder IN (SELECT value FROM json_each(?)) AND binder_type IS NOT 'scan'", (bj,)).fetchone()[0]
        oids = [r[0] for r in conn.execute(
            "SELECT DISTINCT c.oracle_id FROM collection col JOIN cards c USING (scryfall_id) WHERE col.binder IN (SELECT value FROM json_each(?)) "
            "AND col.binder_type IS NOT 'scan' AND c.oracle_id IS NOT NULL", (bj,))]
        conn.execute("DELETE FROM collection WHERE binder IN (SELECT value FROM json_each(?)) AND binder_type IS NOT 'scan'", (bj,))
        conn.execute("DELETE FROM notizen WHERE binder IN (SELECT value FROM json_each(?))", (bj,))
        conn.execute("DELETE FROM meta WHERE key IN (SELECT 'deckbinder:' || value FROM json_each(?))", (bj,))
        for tabelle, spalte in (("changes", "import_id"), ("sales", "import_id"), ("deck_log", "import_id"), ("imports", "id")):
            conn.execute(f"DELETE FROM {tabelle} WHERE {spalte} IN (SELECT value FROM json_each(?))", (imports,))
        conn.execute("DELETE FROM deck_log WHERE deck IN (SELECT value FROM json_each(?))", (bj,))
        conn.execute("DELETE FROM games WHERE deck = ?", (binder[1],))
        u = conn.execute("SELECT value FROM meta WHERE key = 'undo'").fetchone()  # „Rückgängig“ zeigte auf das Beispiel: gilt nicht mehr
        if u:
            try:
                gemerkt = json.loads(u[0])
            except ValueError:
                gemerkt = {}
            if gemerkt.get("import_id") in json.loads(imports) or gemerkt.get("scope") in binder:
                conn.execute("DELETE FROM meta WHERE key = 'undo'")
        # Entscheidungen zu Karten, die jetzt nirgends mehr liegen, nur wenn sie seit dem Laden entstanden sind
        conn.execute("DELETE FROM card_status WHERE oracle_id IN (SELECT value FROM json_each(?)) AND updated_at >= ? AND oracle_id NOT IN "
                     "(SELECT c.oracle_id FROM collection col JOIN cards c USING (scryfall_id) WHERE c.oracle_id IS NOT NULL)", (json.dumps(oids), seit))
        conn.execute("DELETE FROM value_history WHERE day >= ?", (m.get("tag") or "",))  # seit dem Laden stand das Beispiel darin
        if m.get("wert_tag"):  # ein Eintrag desselben Tages von vor dem Laden (leere Sammlung) kommt zurück
            conn.execute("INSERT OR REPLACE INTO value_history VALUES (?,?,?,?,?)", m["wert_tag"])
        _karten_weg(conn, m.get("karten") or [])
        conn.execute("DELETE FROM meta WHERE key = ?", (BEISPIEL,))
    if not beispiel_leer(conn):  # Scan-Binder sind geblieben: der Wert von heute stimmt wieder
        record_value(conn)
    return kopien


def beispiel_laden(conn, fetch=None, lookup=None, now=None):
    """Die Beispielsammlung laden, nur in eine leere Sammlung: ValueError mit klarer Meldung sonst. Alles, was Netz braucht, kommt zuerst (die Karten
    der Sammlung nach ihrer Scryfall-ID, die des Decks nach Edition und Nummer); scheitert es, ist nichts angelegt und nichts zwischengespeichert.
    Danach laufen die beiden normalen Importe (Binder „Beispiel“ und Deck „Beispiel-Deck“) ohne Netz, meta „beispiel“ merkt die Importe, die neuen
    Karten und den Wertverlauf von vorher. Jeder Fehler danach nimmt alles wieder zurück. -> {"karten", "deck", "unbekannt", "fehlend"}"""
    if not _beispiel_laeuft.acquire(blocking=False):
        raise ValueError("Die Beispielsammlung wird gerade geladen.")
    try:
        if beispiel_marker(conn):
            raise ValueError("Die Beispielsammlung liegt schon da.")
        if not beispiel_leer(conn):
            raise ValueError("Die Sammlung hat schon Karten. Die Beispielsammlung gibt es nur in einer leeren Sammlung.")
        csv_roh, deck_roh = beispiel_dateien()
        fetch = fetch or sources.scryfall_cards
        lookup = lookup or sources.scryfall_lookup
        zeit = now or datetime.now(timezone.utc)
        tag = zeit.date().isoformat()
        vorher = {r[0] for r in conn.execute("SELECT scryfall_id FROM cards")}
        _, zeilen, _ = read_manabox(csv_roh, "sammlung.csv", BEISPIEL_BINDER)
        liste = parse_decklist(read_text(deck_roh))
        try:
            fehlend = ensure_cards(conn, {k[1] for k in zeilen}, fetch)
            resolve(conn, liste["cards"], lookup)
        except BaseException:
            with conn:
                _karten_weg(conn, {r[0] for r in conn.execute("SELECT scryfall_id FROM cards")} - vorher)
            raise
        neu = sorted({r[0] for r in conn.execute("SELECT scryfall_id FROM cards")} - vorher)
        wert = conn.execute("SELECT * FROM value_history WHERE day = ?", (tag,)).fetchone()
        marker = {"binder": BEISPIEL_BINDER, "deck": BEISPIEL_DECK, "at": zeit.strftime(TS), "tag": tag, "imports": [], "karten": neu,
                  "wert_tag": list(wert) if wert else None}
        with conn:
            conn.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (BEISPIEL, json.dumps(marker)))  # vor den Importen: bricht etwas ab, räumt entfernen auf
        def merken(res):  # jeder Import steht gleich im Eintrag, damit „entfernen“ ihn findet, auch wenn der nächste scheitert
            if res["import_id"]:
                marker["imports"].append(res["import_id"])
                with conn:
                    conn.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (BEISPIEL, json.dumps(marker)))
            return res
        try:
            a = merken(_import_file(conn, csv_roh, "sammlung.csv", BEISPIEL_BINDER, fetch=fetch, lookup=lookup, now=zeit))
            b = merken(_import_file(conn, deck_roh, "deck.txt", BEISPIEL_DECK, fetch=fetch, lookup=lookup, now=zeit))
            record_value(conn, tag)
            with conn:
                conn.execute("DELETE FROM meta WHERE key = 'undo'")  # „Rückgängig“ für das Beispiel ist „entfernen“
        except BaseException:
            beispiel_entfernen(conn)
            raise
        return {"karten": a["added"], "deck": b["added"], "unbekannt": b["unknown"], "fehlend": fehlend + a["missing"] + b["missing"]}
    finally:
        _beispiel_laeuft.release()


def sync(conn, inbox=None, fetch=None, archive=None, now=None, lookup=None):
    """Alle CSVs und Decklisten (.txt) aus inbox/ importieren (der Schnappschuss-Diff macht das beliebig oft wiederholbar),
    dann Preise auffrischen. -> ([(Datei, Ergebnis oder Fehlertext)], Anzahl aufgefrischter Preise)"""
    fetch = fetch or sources.scryfall_cards
    out = []
    dateien = [p for p in Path(inbox or INBOX).glob("*") if p.suffix.lower() in (".csv", ".txt")]
    for f in sorted(dateien, key=lambda p: p.stat().st_mtime):
        try:
            out.append((f.name, import_file(conn, f.read_bytes(), f.name, fetch=fetch, lookup=lookup, archive=archive, now=now)))
        except ValueError as e:
            out.append((f.name, f"übersprungen: {e}"))
    return out, refresh_prices(conn, fetch)


POSTEINGANG_TAGE = 7  # so lange steht das Ergebnis des Posteingangs in den Neuigkeiten
POSTEINGANG_JUNG_S = 60  # jüngere Dateien schreibt der Sync-Ordner vielleicht noch: beim nächsten Mal


def inbox_fuer(db):
    """Posteingang einer Sammlung: inbox/ im Projektordner fürs Hauptkonto, data/konten/<name>/inbox für Unterkonten (wie mit --konto)."""
    return INBOX if db is None or Path(db).resolve() == Path(DB).resolve() else Path(db).parent / "inbox"


def posteingang_an(conn, an=None):
    """Schalter für den Posteingang im täglichen Lauf (Phase 27, Standard aus); an=True/False setzt ihn. -> an?"""
    if an is not None:
        with conn:
            conn.execute("INSERT OR REPLACE INTO meta VALUES ('posteingang', ?)", ("1" if an else "0",))
    r = conn.execute("SELECT value FROM meta WHERE key = 'posteingang'").fetchone()
    return bool(r and r[0] == "1")


def posteingang(conn, inbox=None, fetch=None, lookup=None, archive=None, now=None):
    """Posteingang (Phase 27): neue Dateien aus inbox/ übernehmen wie `mtg sync`, aber jede Datei nur einmal (sha256 gemerkt, sonst holte eine
    alte Datei, die noch im Sync-Ordner liegt, einen alten Stand zurück) und nie mit force: würde sie mehr als 25 % entfernen, bleibt sie liegen,
    wird beim nächsten Mal wieder geprüft und steht als Warnung in den Neuigkeiten. Ohne Netz (oder bei gesperrter Datenbank): Abbruch, der Rest
    kommt beim nächsten Lauf. Nichts hier darf den täglichen Lauf aufhalten: Jeder andere Fehler gilt nur für seine Datei.
    Gemerkt: der letzte Lauf (at, items) und die Meldungen der letzten POSTEINGANG_TAGE Tage für die Neuigkeiten; liegen gebliebene Dateien
    nur aus dem letzten Lauf, weil jeder Lauf sie neu prüft. -> [{datei, status, added, removed, text, at}] dieses Laufs
    (status: importiert, keine Änderung, abgebrochen, fehler, wartet, später)"""
    ordner, jetzt = Path(inbox or INBOX), now or datetime.now(timezone.utc)
    ts = jetzt.strftime(TS)
    r = conn.execute("SELECT value FROM meta WHERE key = 'posteingang:gesehen'").fetchone()
    gesehen, items = set(json.loads(r[0])) if r else set(), []
    def mtime(p):  # eine Datei, die der Sync-Ordner gerade wegnimmt, sortiert vorn ein und meldet sich unten als Fehler
        try:
            return p.stat().st_mtime
        except OSError:
            return 0
    dateien = sorted((p for p in ordner.glob("*") if p.suffix.lower() in (".csv", ".txt")), key=mtime) if ordner.is_dir() else []
    eintrag = lambda f, status, text, res=None: {"datei": f.name, "status": status, "added": res["added"] if res else 0,
                                                 "removed": res["removed"] if res else 0, "text": text, "at": ts}
    for f in dateien:
        sha = None
        try:
            if abs(time.time() - f.stat().st_mtime) < POSTEINGANG_JUNG_S:
                items.append(eintrag(f, "wartet", "gerade erst gespeichert"))
                continue
            raw = f.read_bytes()
            sha = hashlib.sha256(raw).hexdigest()
            if sha in gesehen:
                continue
            res = import_file(conn, raw, f.name, fetch=fetch, lookup=lookup, archive=archive, now=now)
        except (urllib.error.URLError, TimeoutError, ConnectionError, sqlite3.OperationalError) as e:  # vorübergehend
            items.append(eintrag(f, "später", str(getattr(e, "reason", e))))
            break
        except Exception as e:  # kaputte Datei, Scan-Binder oder Unerwartetes: gemeldet, nicht jeden Tag wieder
            items.append(eintrag(f, "fehler", str(e) if isinstance(e, ValueError) else f"{type(e).__name__}: {e}"))
            if sha:
                gesehen.add(sha)
            continue
        items.append(eintrag(f, res["status"], format_import(res), res))
        if res["status"] != "abgebrochen":
            gesehen.add(sha)
    r = conn.execute("SELECT value FROM meta WHERE key = 'posteingang:ergebnis'").fetchone()
    alt = [i for i in (json.loads(r[0]).get("meldungen", []) if r else []) if i["status"] in ("importiert", "fehler")
           and jetzt - datetime.strptime(i["at"], TS).replace(tzinfo=timezone.utc) <= timedelta(days=POSTEINGANG_TAGE)]
    with conn:
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('posteingang:gesehen', ?)", (json.dumps(sorted(gesehen)),))
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('posteingang:ergebnis', ?)", (json.dumps(
            {"at": ts, "items": items, "meldungen": alt + items}, ensure_ascii=False),))
    return items


def posteingang_news(conn, now=None):
    """Was der Posteingang in den letzten POSTEINGANG_TAGE Tagen übernommen hat (jüngstes zuerst), Warnungen für liegen gebliebene und
    unlesbare Dateien."""
    r = conn.execute("SELECT value FROM meta WHERE key = 'posteingang:ergebnis'").fetchone()
    jetzt, out = now or datetime.now(timezone.utc), []
    for it in reversed(json.loads(r[0]).get("meldungen", []) if r else []):
        if jetzt - datetime.strptime(it["at"], TS).replace(tzinfo=timezone.utc) > timedelta(days=POSTEINGANG_TAGE):
            continue
        if it["status"] == "importiert":
            out.append({"kind": "posteingang", "icon": "↓", "text": f"Posteingang: „{it['datei']}“ übernommen", "sub": f"+{zahl(it['added'])} / −{zahl(it['removed'])} Karten"})
        elif it["status"] == "abgebrochen":
            out.append({"kind": "posteingang_warn", "icon": "!", "text": f"Posteingang: „{it['datei']}“ nicht übernommen",
                        "sub": f"Es würden {zahl(it['removed'])} Karten fehlen, mehr als ein Viertel. Prüf die Datei und lade sie von Hand hoch."})
        elif it["status"] == "fehler":
            out.append({"kind": "posteingang_warn", "icon": "!", "text": f"Posteingang: „{it['datei']}“ nicht lesbar", "sub": it["text"]})
    return out


def format_import(res):
    wo = "Sammlung" if res["scope"] == "*" else (f"Deck „{res['scope']}“" if res.get("format") == "deck" else f"Binder „{res['scope']}“")
    if res["status"] == "keine Änderung":
        return f"{wo}: keine Änderung" + (f" (Abgleich: „{res['erkannt']['datei']}“ ist dieser Binder)" if res.get("erkannt") else "")
    wert = ("+" if res["value"] >= 0 else "−") + eur(abs(res["value"]))
    if res["status"] == "abgebrochen":
        status = f"ABGEBROCHEN: {pct(res['removed'] / res['bestand'])} des Bestands würden entfernt, nur mit --force"
    else:
        status = {"importiert": "importiert", "probelauf": "Probelauf, nichts gespeichert"}[res["status"]]
    out = [f"{wo}: +{zahl(res['added'])} / −{zahl(res['removed'])} Karten, Wert {wert} – {status}"]
    if res.get("beispiel") and res["status"] != "abgebrochen":
        b = res["beispiel"]
        out.append(f"  Die Beispielsammlung ({zahl(b['karten'])} Karten) {'wurde vorher entfernt' if b['entfernt'] else 'wird vorher entfernt'}.")
    if res.get("erkannt"):
        e = res["erkannt"]
        out.append(f"  Abgleich: „{e['datei']}“ ist der neue Stand von „{e['binder']}“ ({zahl(e['gleich'])} von {zahl(e['von'])} Karten schon da), "
                   f"übernommen werden nur die Unterschiede; als eigener Binder: --binder \"{e['datei']}\"")
    out += ["  " + ln for ln in res["lines"]]
    if res.get("doppelt"):
        d = res["doppelt"]
        out.append(f"  Achtung: {zahl(d['cards'])} neue Karten liegen schon in einem Scan-Binder ({', '.join(d['names'][:5])}{' …' if len(d['names']) > 5 else ''}). "
                   f"Doppelt erfasst? Was die App scannt, nicht zusätzlich in ManaBox scannen.")
    if res.get("sold", {}).get("cards"):
        out.append(f"  davon verkauft (standen auf der Verkaufsliste): {zahl(res['sold']['cards'])} Karten, {eur(res['sold']['value'])}")
    if res["skipped"]:
        out.append("  übersprungen: " + ", ".join(f"{n}× {k}" for k, n in res["skipped"].items()))
    if res.get("unknown"):
        out.append(f"  nicht erkannt: {', '.join(res['unknown'][:5])}{' …' if len(res['unknown']) > 5 else ''}")
    if res["missing"]:
        out.append(f"  bei Scryfall nicht gefunden: {len(res['missing'])} IDs")
    return "\n".join(out)


# --- Auswertung --------------------------------------------------------------------------------------------------

# --- Wunschliste (Phase 16): eigene Wünsche mit Zielpreis, dazu die Wunschlisten aus ManaBox (Binder Type „list“) -----------------

def wunsch_setzen(conn, scryfall_id, qty=1, max_eur=None, note=None):
    """Karte (ein Druck, für den Preis) auf die Wunschliste oder Eintrag ändern; je Karte (oracle_id) ein Eintrag."""
    c = conn.execute("SELECT oracle_id FROM cards WHERE scryfall_id = ?", (scryfall_id,)).fetchone()
    if not c:
        raise ValueError("Unbekannte Karte")
    if max_eur is not None and (not isinstance(max_eur, (int, float)) or max_eur < 0):
        raise ValueError("Zielpreis muss eine Zahl ab 0 sein")
    with conn:
        alt = conn.execute("SELECT added FROM wishlist WHERE oracle_id = ?", (c[0],)).fetchone()
        conn.execute("INSERT OR REPLACE INTO wishlist VALUES (?,?,?,?,?,?)", (c[0], scryfall_id, max(1, int(qty or 1)), max_eur,
                                                                              (note or "").strip()[:300], alt[0] if alt else now_iso()))


def wunsch_weg(conn, oracle_id):
    with conn:
        return conn.execute("DELETE FROM wishlist WHERE oracle_id = ?", (oracle_id,)).rowcount


def wuensche(conn):
    """Eigene Wünsche und ManaBox-Wunschlisten (Binder Type „list“) mit Preis (Scryfall-Trend des Drucks, Foil mit Foil-Preis), Cardmarket „ab“,
    Kopien im Besitz und ob der Zielpreis erreicht ist (günstigster der beiden Preise). Einen Zielpreis setzt man in der App, auch für ManaBox-Wünsche."""
    besitz = {r[0]: r[1] for r in conn.execute(f"SELECT c.oracle_id, SUM(col.qty) FROM collection col JOIN cards c USING (scryfall_id) WHERE {OWNED} GROUP BY c.oracle_id")}
    preis = "CASE WHEN {f} THEN COALESCE(c.price_eur_foil, c.price_eur) ELSE COALESCE(c.price_eur, c.price_eur_foil) END"
    ab = "CASE WHEN {f} THEN cm.low_foil ELSE cm.low END"
    sql = ("SELECT c.oracle_id, c.scryfall_id, c.name, c.set_code, c.number, c.image_url image, {preis} price, {ab} cm_low, {rest} FROM {von} "
           "LEFT JOIN cm_price cm ON cm.id_product = json_extract(c.json, '$.cardmarket_id') {wo}")
    felder = ("oracle_id", "scryfall_id", "name", "set_code", "number", "image", "price", "cm_low")
    eigen = {r["oracle_id"]: dict(r) | {"quelle": "app", "listen": []} for r in conn.execute(sql.format(
        preis=preis.format(f="0"), ab=ab.format(f="0"), rest="w.qty, w.max_eur, w.note, w.added", von="wishlist w JOIN cards c USING (scryfall_id)", wo=""))}
    for r in conn.execute(sql.format(preis=preis.format(f="col.foil != 'normal'"), ab=ab.format(f="col.foil != 'normal'"), rest="col.qty, col.binder",
                                     von="collection col JOIN cards c USING (scryfall_id)", wo="WHERE col.binder_type = 'list'")):
        e = eigen.setdefault(r["oracle_id"], {k: r[k] for k in felder} | {"qty": 0, "max_eur": None, "note": "", "added": None, "quelle": "manabox", "listen": []})
        if e["quelle"] == "manabox":
            e["qty"] += r["qty"]
        if r["binder"] not in e["listen"]:
            e["listen"].append(r["binder"])
    out = []
    for e in eigen.values():
        p = min((x for x in (e["price"], e["cm_low"]) if x is not None), default=None)
        out.append(e | {"have": besitz.get(e["oracle_id"], 0), "best": p, "reached": e["max_eur"] is not None and p is not None and p <= e["max_eur"]})
    return sorted(out, key=lambda e: (not e["reached"], e["name"].lower()))


# --- Wächter (Phase 19): Bann, Game Changer, Reprints in neuen Sets -------------------------------------------------------------

WAECHTER_TAGE = 30        # so lange stehen Meldungen in den Neuigkeiten
SET_FENSTER = 60          # Sets, die vor höchstens so vielen Tagen erschienen sind oder in so vielen Tagen erscheinen
SET_TYPEN = ("core", "expansion", "masters", "draft_innovation", "commander", "funny", "starter")  # Papier-Sets, die Karten neu auflegen
REPRINT_AB = 5.0          # Reprint-Hinweis für Karten im Besitz ab diesem Preis


def neue_sets(conn, sets=None, suche=None, heute=None):
    """Sets der letzten und nächsten SET_FENSTER Tage einmal ansehen: Karten, die du ab REPRINT_AB besitzt, bekommen den Hinweis „Reprint in …“
    (wichtig fürs Verkaufen: Neuauflagen drücken den Preis). -> Zahl neuer Hinweise"""
    heute = date.fromisoformat(heute) if isinstance(heute, str) else (heute or date.today())
    r = conn.execute("SELECT value FROM meta WHERE key = 'sets:geprueft'").fetchone()
    geprueft = set(json.loads(r[0])) if r else set()
    wert = {name_key(n): o for n, o in conn.execute(f"SELECT c.name, c.oracle_id FROM collection col JOIN cards c USING (scryfall_id) WHERE {OWNED} "
                                                     f"GROUP BY c.oracle_id HAVING MAX({PRICE}) >= ?", (REPRINT_AB,))}
    eigene_sets = defaultdict(set)  # aus einem Set, das du schon hast (z. B. dem Precon), ist die Karte für dich kein Reprint
    for o, st in conn.execute(f"SELECT DISTINCT c.oracle_id, lower(c.set_code) FROM collection col JOIN cards c USING (scryfall_id) WHERE {OWNED}"):
        eigene_sets[o].add(st)
    n, liste = 0, (sets or sources.scryfall_sets)()
    _sets_merken(conn, liste, heute.isoformat())  # Set-Größen für den Set-Stand (Phase 20) und die Set-Wahl beim Erfassen (Phase 25)
    for st in liste:
        tag = st.get("released_at") or ""
        if st["code"] in geprueft or st.get("set_type") not in SET_TYPEN or not tag or abs((date.fromisoformat(tag) - heute).days) > SET_FENSTER:
            continue
        for karte in (suche or sources.scryfall_search)(f"e:{st['code']}"):
            o = wert.get(name_key(karte["name"]))
            if o and karte.get("set") == st["code"] and st["code"] not in eigene_sets[o]:
                n += conn.execute("INSERT OR IGNORE INTO waechter(day, oracle_id, art, info) VALUES (?,?,?,?)",
                                  (heute.isoformat(), o, "reprint", f"{st['name']} ({st['code'].upper()}, {tag})")).rowcount
        geprueft.add(st["code"])
        with conn:
            conn.execute("INSERT OR REPLACE INTO meta VALUES ('sets:geprueft', ?)", (json.dumps(sorted(geprueft)),))
    return n


def reprints(conn, tage=90):
    """oracle_id -> Set-Angaben der Reprints, die der Wächter in den letzten Tagen gefunden hat."""
    out = defaultdict(list)
    for o, info in conn.execute("SELECT oracle_id, info FROM waechter WHERE art = 'reprint' AND day >= ?", ((date.today() - timedelta(days=tage)).isoformat(),)):
        out[o].append(info)
    return dict(out)


# --- Sammler-Bibel (Phase 20): Lagerort, Verleih, Notiz je Kopie; Set-Stand; Rückblick; Wert-Bericht -------------------------------

NOTIZ_JOIN = ("LEFT JOIN notizen n ON n.binder = col.binder AND n.scryfall_id = col.scryfall_id AND n.foil = col.foil "
              "AND n.condition = col.condition AND n.language = col.language")


def notiz_setzen(conn, schluessel, ort="", verliehen="", notiz=""):
    """Lagerort, „verliehen an“ und Notiz zu einer Sammlungszeile (binder, scryfall_id, foil, condition, language). Eigene Tabelle: übersteht
    jeden Re-Import (der Bestand selbst kommt aus ManaBox, E7). Alles leer = Eintrag weg."""
    werte = [(x or "").strip()[:200] for x in (ort, verliehen, notiz)]
    if len(schluessel) != 5:
        raise ValueError("Unbekannte Kopie")
    with conn:
        if any(werte):
            conn.execute("INSERT OR REPLACE INTO notizen VALUES (?,?,?,?,?,?,?,?,?)", (*schluessel, *werte, now_iso()))
        else:
            conn.execute("DELETE FROM notizen WHERE binder = ? AND scryfall_id = ? AND foil = ? AND condition = ? AND language = ?", schluessel)


def verliehen(conn):
    """Was gerade verliehen ist (nur Kopien, die noch im Bestand sind)."""
    return [dict(r) for r in conn.execute(
        f"SELECT c.oracle_id, c.name, c.image_url image, col.qty, col.binder, n.verliehen, n.updated FROM collection col JOIN cards c USING (scryfall_id) "
        f"{NOTIZ_JOIN} WHERE {OWNED} AND COALESCE(n.verliehen, '') != '' ORDER BY n.verliehen COLLATE NOCASE, c.name")]


def arena_drucke(conn):
    """Kopien im Bestand, die als reiner Arena-Druck eingetragen sind. Auf Papier gibt es die nicht, ManaBox hat beim Scannen wohl den
    Druck mit gleichem Bild erwischt; ohne Euro-Preis zählen sie auch nicht zum Wert."""
    return [dict(r) for r in conn.execute(
        f"SELECT c.oracle_id, c.name, c.set_code, c.number, col.binder, SUM(col.qty) qty FROM collection col JOIN cards c USING (scryfall_id) "
        f"WHERE {OWNED} AND {ARENA} GROUP BY c.scryfall_id, col.binder ORDER BY c.name")]


def sets_info(conn):
    """Set-Größen aus der Scryfall-Set-Liste, die der tägliche Lauf (`neue_sets`) mitmerkt: Kürzel -> {name, size, typ, datum, digital}.
    Vor dem ersten Lauf leer."""
    r = conn.execute("SELECT value FROM meta WHERE key = 'sets:liste'").fetchone()
    return json.loads(r[0]) if r else {}


def _sets_merken(conn, liste, tag):
    """Scryfall-Set-Liste merken (card_count zählt jeden Druck mit, printed_size fehlt bei neuen Sets)."""
    with conn:
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('sets:liste', ?)", (json.dumps(
            {x["code"].upper(): {"name": x["name"], "size": x.get("card_count") or 0, "typ": x.get("set_type") or "", "datum": x.get("released_at") or "",
                                 "digital": bool(x.get("digital"))} for x in liste}, ensure_ascii=False),))
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('sets:liste:tag', ?)", (tag,))


def set_karten(conn, code, suche=None, now=None):
    """Alle Drucke eines Sets in Sammlernummer-Reihenfolge (Scryfall, 30 Tage gemerkt) für die Binder-Ansicht. -> [{number, name, image, rarity, id}]"""
    code = code.upper()
    now = now or datetime.now(timezone.utc)
    r = conn.execute("SELECT json, fetched_at FROM set_karten WHERE set_code = ?", (code,)).fetchone()
    if r and datetime.strptime(r["fetched_at"], TS).replace(tzinfo=timezone.utc) > now - timedelta(days=30):
        return json.loads(r["json"])
    karten = [{"id": k["id"], "number": k["collector_number"], "name": k["name"], "rarity": k.get("rarity"),
               "image": (k.get("image_uris") or (k.get("card_faces") or [{}])[0].get("image_uris") or {}).get("normal")}
              for k in (suche or (lambda q: sources.scryfall_search(q, unique="prints")))(f"e:{code.lower()}")]
    karten.sort(key=lambda k: (int(re.match(r"\d*", k["number"]).group() or 0), k["number"]))
    with conn:
        conn.execute("INSERT OR REPLACE INTO set_karten VALUES (?,?,?)", (code, json.dumps(karten, ensure_ascii=False), now.strftime(TS)))
    return karten


def rueckblick(conn, jahr=None):
    """Ein Jahr in Zahlen: wann du wie viel eingescannt hast (Spalte „Added“ von ManaBox), die wertvollsten Neuzugänge, erkannte Verkäufe."""
    jahr = str(jahr or date.today().year)
    jahre = [r[0] for r in conn.execute(f"SELECT DISTINCT substr(col.added, 1, 4) j FROM collection col WHERE {OWNED} AND col.added != '' ORDER BY j DESC")]
    monate = [dict(r) for r in conn.execute(
        f"SELECT substr(col.added, 1, 7) monat, SUM(col.qty) karten, SUM(col.qty * {PRICE}) wert FROM collection col JOIN cards c USING (scryfall_id) "
        f"WHERE {OWNED} AND substr(col.added, 1, 4) = ? GROUP BY monat ORDER BY monat", (jahr,))]
    funde = [dict(r) for r in conn.execute(
        f"SELECT c.oracle_id, c.name, c.image_url image, {PRICE} price, MIN(col.added) added FROM collection col JOIN cards c USING (scryfall_id) "
        f"WHERE {OWNED} AND substr(col.added, 1, 4) = ? GROUP BY c.oracle_id ORDER BY price DESC LIMIT 5", (jahr,))]
    verkauft = conn.execute("SELECT COALESCE(SUM(qty), 0), COALESCE(SUM(qty * price), 0) FROM sales WHERE substr(at, 1, 4) = ?", (jahr,)).fetchone()
    gespielt = [dict(r) for r in conn.execute("SELECT deck, COUNT(*) spiele, SUM(won) siege FROM games WHERE substr(at, 1, 4) = ? GROUP BY deck "
                                              "ORDER BY spiele DESC, siege DESC, deck", (jahr,))]
    return {"jahr": jahr, "jahre": jahre, "monate": monate, "karten": sum(m["karten"] for m in monate), "wert": sum(m["wert"] for m in monate),
            "funde": funde, "verkauft": {"karten": verkauft[0], "wert": verkauft[1]},
            "spiele": sum(g["spiele"] for g in gespielt), "meist": gespielt[0] if gespielt else None,
            "decks": conn.execute("SELECT COUNT(*) FROM decks WHERE substr(saved_at, 1, 4) = ?", (jahr,)).fetchone()[0]}


def bericht(conn, kaufpreise=False, top=50):
    """Wert-Bericht zum Drucken (Versicherung, Nachlass): Stichtag, Summe, Anzahl, die wertvollsten Karten, Summen je Binder; Kaufpreise wahlweise."""
    s = stats(conn)
    karten = [dict(r) for r in conn.execute(
        f"SELECT c.name, c.set_code, c.number, col.foil, col.language, col.condition, SUM(col.qty) qty, {PRICE} price, SUM(col.qty * {PRICE}) summe, "
        f"MAX(col.paid) paid FROM collection col JOIN cards c USING (scryfall_id) WHERE {OWNED} GROUP BY col.scryfall_id, col.foil, col.language, col.condition "
        f"ORDER BY price DESC, c.name LIMIT ?", (top,))]
    binder = [dict(r) for r in conn.execute(
        f"SELECT col.binder, SUM(col.qty) karten, SUM(col.qty * {PRICE}) wert FROM collection col JOIN cards c USING (scryfall_id) WHERE {OWNED} "
        f"GROUP BY col.binder ORDER BY wert DESC")]
    if not kaufpreise:
        for k in karten:
            k.pop("paid")
    return {"stichtag": now_iso(), "wert": s["value"], "karten": s["cards"], "unique": s["unique"], "paid": s["paid"] if kaufpreise else None,
            "top": karten, "binder": binder, "quelle": "Cardmarket-Trend laut Scryfall, Foils mit Foil-Preis, ohne Zustand und Sprache"}


def refresh_cardmarket(conn, holen, day=None):
    """Cardmarket-Preise höchstens einmal am Tag übernehmen (holen() liefert den Text der Preisliste). -> Anzahl oder None (heute schon)"""
    day = day or date.today().isoformat()
    r = conn.execute("SELECT value FROM meta WHERE key = 'cardmarket_tag'").fetchone()
    if r and r[0] == day:
        return None
    n = cardmarket_store(conn, holen(), day)
    with conn:
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('cardmarket_tag', ?)", (day,))
    return n


def stats(conn):
    k = conn.execute(
        f"SELECT COALESCE(SUM(col.qty), 0) cards, COUNT(DISTINCT c.oracle_id) uniq, COALESCE(SUM(col.qty * {PRICE}), 0) value "
        f"FROM collection col LEFT JOIN cards c USING (scryfall_id) WHERE {OWNED}").fetchone()
    top = conn.execute(
        f"SELECT c.name, c.set_code, col.foil, SUM(col.qty) qty, {PRICE} price FROM collection col JOIN cards c USING (scryfall_id) "
        f"WHERE {OWNED} GROUP BY col.scryfall_id, col.foil ORDER BY price DESC, c.name LIMIT 10").fetchall()
    return {"cards": k["cards"], "unique": k["uniq"], "value": k["value"], "available": sum(available(conn).values()),
            "top": [dict(r) for r in top], "paid": paid_stats(conn)}


def format_stats(s):
    out = [f"Karten: {zahl(s['cards'])} (verfügbar {zahl(s['available'])}) · Unikate: {zahl(s['unique'])} · Wert: {eur(s['value'])}"]
    p = s["paid"]
    if p["cards"]:
        out.append(f"Kaufpreis: {eur(p['paid'])} für {zahl(p['cards'])} von {zahl(p['all'])} Karten, heute {eur(p['value'])} "
                   f"({'+' if p['value'] >= p['paid'] else '−'}{eur(abs(p['value'] - p['paid']))})")
    out += [f"{i:>2}. {eur(t['price']):>10}  {t['name']} ({t['set_code']}){' Foil' if t['foil'] != 'normal' else ''} ×{t['qty']}"
            for i, t in enumerate(s["top"], 1)]
    return "\n".join(out)


def card_info(conn, name):
    """Karten zum Namen (exakt, sonst Teiltreffer) mit Besitz, Preis und Decks."""
    ids = [r[0] for r in conn.execute("SELECT DISTINCT oracle_id FROM cards WHERE name = ? COLLATE NOCASE", (name,))]
    if not ids:
        ids = [r[0] for r in conn.execute(
            "SELECT oracle_id FROM cards WHERE name LIKE ? GROUP BY oracle_id ORDER BY MIN(name) LIMIT 5", (f"%{name}%",))]
    have, fest, out = available(conn), deck_binders(conn), []
    for oid in ids:
        c = conn.execute("SELECT * FROM cards WHERE oracle_id = ? ORDER BY updated_at DESC LIMIT 1", (oid,)).fetchone()
        owned = conn.execute(
            f"SELECT col.binder, c.set_code, c.number, col.foil, col.language, col.condition, col.qty, {PRICE} price, col.paid "
            f"FROM collection col JOIN cards c USING (scryfall_id) WHERE c.oracle_id = ? ORDER BY col.binder, c.set_code", (oid,)).fetchall()
        decks = [r[0] for r in conn.execute(
            "SELECT DISTINCT d.name FROM deck_cards dc JOIN decks d ON d.id = dc.deck_id WHERE dc.oracle_id = ?", (oid,))]
        decks += sorted({o["binder"] for o in owned if o["binder"] in fest})  # fertige Decks
        out.append({"card": dict(c), "owned": [dict(r) for r in owned], "available": have.get(oid, 0), "decks": decks})
    return out


def format_card(i):
    c = i["card"]
    foil = f" (Foil {eur(c['price_eur_foil'])})" if c["price_eur_foil"] is not None else ""
    preis = eur(c["price_eur"]) if c["price_eur"] is not None else "kein Preis"
    out = [f"{c['name']} {c['mana_cost']} · {c['type_line']} · EDHREC-Rang {c['edhrec_rank'] or '–'}",
           "  " + (c["oracle_text"] or "").replace("\n", " | "),
           f"Besitz: {sum(o['qty'] for o in i['owned'])} gesamt, {i['available']} verfügbar · Preis {preis}{foil}"]
    bezahlt = lambda o: f" · bezahlt {eur(o['paid'])}" if o["paid"] is not None else ""
    out += [f"  {o['qty']}× {o['set_code']} #{o['number']} {o['language']} {o['condition']}"
            f"{' ' + o['foil'] if o['foil'] != 'normal' else ''} – {o['binder']}{bezahlt(o)}" for o in i["owned"]]
    out.append("Decks: " + (", ".join(i["decks"]) or "–"))
    return "\n".join(out)


# --- Erfassen mit Set-Lock (Phase 25, PLAN E18): Drucke der gewählten Sets, Scan-Binder, Sitzungen ------------------------------

SET_LISTE_TAGE = 7     # so alt darf die gemerkte Set-Liste für die Set-Wahl sein, sonst einmal neu von Scryfall
SET_OHNE = ("alchemy", "memorabilia", "minigame", "treasure_chest", "vanguard")  # beim Erfassen nicht angeboten (digital, Gedenk- und Spielhilfen)
SCAN_DATEI = "Kamera"  # imports.file einer Erfassen-Sitzung: die Karten kamen per Kamera, nicht aus einer Datei
SCAN_MAX = 99          # höchstens so viele Kopien je Buchung
FOILS = ("normal", "foil", "etched")
ZUSTAENDE = ("mint", "near_mint", "excellent", "good", "light_played", "played", "poor")
SPRACHEN = ("en", "de", "fr", "it", "es", "pt", "ja", "ko", "ru", "zh_CN", "zh_TW")


def set_liste(conn, holen=None, heute=None, neu=False):
    """Sets zur Wahl beim Erfassen: Papier-Sets ohne SET_OHNE, neueste zuerst. Aus der Set-Liste des täglichen Laufs (neue_sets); fehlt sie,
    ist sie älter als SET_LISTE_TAGE oder neu=True, einmal von Scryfall. -> [{code, name, datum, typ, size}]"""
    heute = heute or date.today().isoformat()
    tag = (conn.execute("SELECT value FROM meta WHERE key = 'sets:liste:tag'").fetchone() or [""])[0]
    info = sets_info(conn)
    if neu or not tag or (date.fromisoformat(heute) - date.fromisoformat(tag)).days > SET_LISTE_TAGE or any("typ" not in v for v in info.values()):
        _sets_merken(conn, (holen or sources.scryfall_sets)(), heute)
        info = sets_info(conn)
    out = [{"code": k, "name": v["name"], "datum": v["datum"], "typ": v["typ"], "size": v["size"]}
           for k, v in info.items() if not v["digital"] and v["typ"] not in SET_OHNE]
    return sorted(out, key=lambda s: (s["datum"], s["typ"] == "commander", s["code"]), reverse=True)


def set_drucke(conn, codes, suche=None, neu=False, now=None):
    """Drucke der gewählten Sets fürs Erfassen: eine Scryfall-Suche je Set (`unique=prints`), je Set einmal in set_prints gemerkt; neu=True holt
    es noch einmal (neue Sets bekommen oft später Drucke). Mit dem ganzen Scryfall-JSON, damit eine erfasste Karte ohne weitere Anfrage in
    cards kommt. Nicht gleich in cards: Abfragen über den Bestand bleiben unverfälscht. -> {Kürzel: Zahl der Drucke}"""
    ts, out = (now or datetime.now(timezone.utc)).strftime(TS), {}
    for code in dict.fromkeys(c.strip().upper() for c in codes if c.strip()):
        if not re.fullmatch(r"[A-Z0-9]{2,6}", code):
            raise ValueError(f"Unbekanntes Set „{code}“")
        da = conn.execute("SELECT COUNT(*) FROM set_prints WHERE set_code = ?", (code,)).fetchone()[0]
        if da and not neu:
            out[code] = da
            continue
        rows = []
        for k in (suche or (lambda q: sources.scryfall_search(q, unique="prints")))(f"e:{code.lower()}"):
            f0 = (k.get("card_faces") or [{}])[0]
            rows.append((k["id"], k["set"].upper(), k.get("oracle_id") or f0.get("oracle_id"), k["name"], k["collector_number"], k.get("lang"),
                         (k.get("image_uris") or f0.get("image_uris") or {}).get("normal"), k.get("illustration_id") or f0.get("illustration_id"),
                         json.dumps(k.get("finishes") or []), int(bool(k.get("digital"))), json.dumps(k, separators=(",", ":")), ts))
        with conn:
            conn.execute("DELETE FROM set_prints WHERE set_code = ?", (code,))
            conn.executemany("INSERT OR REPLACE INTO set_prints VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        out[code] = len(rows)
    return out


def scan_binder_name(conn, name, deck=False):
    """Name für einen Scan-Binder: nicht leer, kein Binder aus ManaBox, keine hochgeladene Deckliste. Auf der Liste der fertigen Decks nur, wenn er
    schon ein Scan-Binder ist (ein eingescanntes Deck, Phase 60) oder als Deck angelegt wird (deck); sonst ist der Name für ein Deck aus ManaBox
    vorgesehen. -> Name"""
    name = (name or "").strip()
    if not name or name == "*" or len(name) > 80:
        raise ValueError("Bitte einen Namen für den Binder angeben (höchstens 80 Zeichen)")
    r = conn.execute("SELECT binder_type FROM collection WHERE binder = ? LIMIT 1", (name,)).fetchone()
    if (r and r[0] != "scan") or name in list_decks(conn) or (name in fertige_decks(conn) and not r and not deck):
        raise ValueError(f"„{name}“ gibt es schon als Binder aus ManaBox oder als Deck. Bitte einen anderen Namen wählen.")
    return name


def scan_binder_liste(conn):
    """Scan-Binder mit Karten, Wert, letzter Erfassung und ob er ein fertiges Deck ist (deck, Phase 60), zuletzt benutzte zuerst."""
    fest = set(fertige_decks(conn))
    return [dict(r) | {"deck": r["name"] in fest} for r in conn.execute(
        f"SELECT col.binder name, SUM(col.qty) karten, SUM(col.qty * {PRICE}) wert, MAX(col.added) zuletzt FROM collection col JOIN cards c USING (scryfall_id) "
        f"WHERE col.binder_type = 'scan' GROUP BY col.binder ORDER BY zuletzt DESC, col.binder")]


def _werte(foil, condition, language):
    if foil not in FOILS or condition not in ZUSTAENDE or language not in SPRACHEN:
        raise ValueError("Foil, Zustand oder Sprache unbekannt")


def _passend(foil, finishes):
    """Foil-Vorgabe der Sitzung passend zum Druck (Scryfall finishes: nonfoil, foil, etched): gibt es ihn so nicht, die Art, die es gibt."""
    art = {"normal": "nonfoil", "foil": "foil", "etched": "etched"}
    moeglich = [f for f in FOILS if art[f] in finishes]
    return foil if not moeglich or foil in moeglich else moeglich[0]


def katalog_pfad(db=None):
    """data/katalog.db (Phase 31, katalog.py): alle Papier-Drucke, eine Datei für alle Konten. Unterkonten liegen in data/konten/<name>/."""
    ordner = Path(db or DB).parent
    return (ordner.parent.parent if ordner.parent.name == "konten" else ordner) / "katalog.db"


def katalog_von(conn):
    """Pfad des Katalogs neben der Sammlung von conn, None bei einer Datenbank im Speicher."""
    datei = conn.execute("PRAGMA database_list").fetchone()[2]
    return katalog_pfad(datei) if datei else None


def _katalog(conn):
    """Lesende Verbindung zum Katalog neben der Sammlung von conn, None ohne Katalog (auch bei einer Datenbank im Speicher)."""
    pfad = katalog_von(conn)
    return katalog.offen(pfad) if pfad else None


def _katalog_drucke(conn, ids):
    """Drucke aus dem Katalog. -> {scryfall_id: Zeile aus drucke}"""
    k = _katalog(conn) if ids else None
    if not k:
        return {}
    with closing(k):
        return {r["scryfall_id"]: r for r in k.execute("SELECT * FROM drucke WHERE scryfall_id IN (SELECT value FROM json_each(?))", (json.dumps(sorted(set(ids))),))}


def _karte_da(conn, sid, fetch=None, kat=False):
    """Druck für den Bestand: schon in cards, sonst aus set_prints (ohne Anfrage, Preise vom Abruf des Sets), sonst von Scryfall. kat=True
    (Scan-Liste, Phase 31): Ein Druck aus dem Katalog genügt, die volle Karte holt erst liste_uebernehmen."""
    if not re.fullmatch(r"[0-9a-f-]{36}", sid or ""):
        raise ValueError("Unbekannte Karte")
    if conn.execute("SELECT 1 FROM cards WHERE scryfall_id = ?", (sid,)).fetchone():
        return
    r = conn.execute("SELECT json, at FROM set_prints WHERE scryfall_id = ?", (sid,)).fetchone()
    if r:
        store_cards(conn, [json.loads(r[0])], r[1])
    elif not (kat and _katalog_drucke(conn, [sid])) and ensure_cards(conn, [sid], fetch or sources.scryfall_cards):
        raise ValueError("Unbekannte Karte")


def _marktpreis(conn, sid, foil):
    """Kaufpreis beim Erfassen (wie in den ManaBox-Exporten, wo jede Karte außer Tokens einen hat): der Preis des Drucks in dieser Ausführung
    im Moment des Erfassens, Foil-Preis für Foils; fehlt er, der andere; ohne Preis (Tokens) None."""
    r = conn.execute("SELECT price_eur, price_eur_foil FROM cards WHERE scryfall_id = ?", (sid,)).fetchone()
    if not r:
        return None
    a, b = (r[1], r[0]) if foil != "normal" else (r[0], r[1])
    return a if a is not None else b


def _buchen(conn, binder, key, n, ts=None):
    """Kopien in einem Scan-Binder zu- (n > 0) oder abbuchen; key = (scryfall_id, foil, condition, language). Neue Kopien bekommen den
    Marktpreis als Kaufpreis (mit vorhandenen nach Menge gemittelt). Eine Zeile ohne Kopien verschwindet (Ort und Notiz bleiben in notizen
    stehen und gelten wieder, wenn die Kopie zurückkommt)."""
    w = "binder = ? AND scryfall_id = ? AND foil = ? AND condition = ? AND language = ?"
    r = conn.execute(f"SELECT qty, paid FROM collection WHERE {w}", (binder, *key)).fetchone()
    preis = _marktpreis(conn, key[0], key[1]) if n > 0 else None
    if r and r[0] + n <= 0:
        conn.execute(f"DELETE FROM collection WHERE {w}", (binder, *key))
    elif r:
        conn.execute(f"UPDATE collection SET qty = qty + ?, paid = ?, added = CASE WHEN ? > 0 THEN MAX(added, ?) ELSE added END WHERE {w}",
                     (n, _mix(r[0], r[1], n, preis) if n > 0 else r[1], n, ts or "", binder, *key))
    elif n > 0:
        conn.execute(COLL_INSERT, (binder, "scan", *key, n, ts or now_iso(), "", preis))


def _sitzung(conn, sitzung):
    s = conn.execute("SELECT * FROM imports WHERE id = ? AND file = ?", (int(sitzung or 0), SCAN_DATEI)).fetchone()
    if not s:
        raise ValueError("Unbekannte Erfassen-Sitzung")
    return s


def _sitzung_rechnen(conn, sitzung):
    """imports.added und changes der Sitzung aus scan_log: so arbeiten „Zuletzt hinzugefügt“ und die Neuigkeiten wie nach einem Import."""
    conn.execute("DELETE FROM changes WHERE import_id = ?", (sitzung,))
    conn.execute("INSERT INTO changes SELECT ?, scryfall_id, SUM(qty) FROM scan_log WHERE sitzung = ? GROUP BY scryfall_id HAVING SUM(qty) != 0", (sitzung, sitzung))
    conn.execute("UPDATE imports SET added = (SELECT COALESCE(SUM(qty), 0) FROM scan_log WHERE sitzung = ?) WHERE id = ?", (sitzung, sitzung))


def scan_add(conn, binder, scryfall_id, foil="normal", condition="near_mint", language="en", qty=1, sitzung=None, zug=None, fetch=None, now=None):
    """Erfassen (Phase 25, E18): Kopien eines Drucks in einen Scan-Binder legen, sofort gespeichert (das Handy kann jederzeit weg sein). Je
    Sitzung ein Eintrag in imports (Datei „Kamera“, Bereich = Binder) mit changes. zug = Kennung der Karte im Rahmen: derselbe Zug zählt einmal,
    auch wenn das Bild zweimal ankommt oder das Netz die Anfrage wiederholt. Foil richtet sich nach dem Druck (gibt es ihn nur als Foil, ist es
    eine). Unbekannte oder fremde Sitzung (anderer Binder): neue Sitzung. -> scan_sitzung"""
    binder = scan_binder_name(conn, binder)
    _werte(foil, condition, language)
    if not 1 <= int(qty) <= SCAN_MAX:
        raise ValueError(f"Menge 1 bis {SCAN_MAX}")
    ts = (now or datetime.now(timezone.utc)).strftime(TS)
    s = conn.execute("SELECT id, scope FROM imports WHERE id = ? AND file = ?", (int(sitzung or 0), SCAN_DATEI)).fetchone()
    s = s["id"] if s and s["scope"] == binder else None
    if s and zug and conn.execute("SELECT 1 FROM scan_log WHERE sitzung = ? AND zug = ?", (s, str(zug))).fetchone():
        return scan_sitzung(conn, s)
    _karte_da(conn, scryfall_id, fetch)
    fin = conn.execute("SELECT json_extract(json, '$.finishes') FROM cards WHERE scryfall_id = ?", (scryfall_id,)).fetchone()[0]
    foil = _passend(foil, json.loads(fin) if fin else [])
    with conn:
        if not s:
            s = conn.execute("INSERT INTO imports(file, sha256, scope, added, removed, at) VALUES (?,?,?,?,?,?)", (SCAN_DATEI, "", binder, 0, 0, ts)).lastrowid
        conn.execute("INSERT INTO scan_log(sitzung, scryfall_id, foil, condition, language, qty, zug, at) VALUES (?,?,?,?,?,?,?,?)",
                     (s, scryfall_id, foil, condition, language, int(qty), str(zug) if zug else None, ts))
        _buchen(conn, binder, (scryfall_id, foil, condition, language), int(qty), ts)
        _sitzung_rechnen(conn, s)
    return scan_sitzung(conn, s)


def scan_zurueck(conn, sitzung):
    """„Letzte zurück“: die zuletzt erfasste Karte der Sitzung wieder aus dem Binder nehmen. -> scan_sitzung mit „weg“ (Name der Karte)"""
    s = _sitzung(conn, sitzung)
    r = conn.execute("SELECT l.*, c.name FROM scan_log l LEFT JOIN cards c USING (scryfall_id) WHERE l.sitzung = ? ORDER BY l.id DESC LIMIT 1", (s["id"],)).fetchone()
    if not r:
        raise ValueError("In dieser Sitzung ist nichts mehr erfasst")
    with conn:
        conn.execute("DELETE FROM scan_log WHERE id = ?", (r["id"],))
        _buchen(conn, s["scope"], (r["scryfall_id"], r["foil"], r["condition"], r["language"]), -r["qty"])
        _sitzung_rechnen(conn, s["id"])
    return scan_sitzung(conn, s["id"]) | {"weg": r["name"]}


def scan_aendern(conn, sitzung, key, foil=None, condition=None, language=None, qty=None, now=None):
    """Zeile der Sitzung ändern: Foil, Zustand oder Sprache (die Kopien wandern in die passende Zeile des Binders) und/oder die Menge
    (0 = Zeile weg). key = (scryfall_id, foil, condition, language) wie in scan_sitzung. -> scan_sitzung"""
    s = _sitzung(conn, sitzung)
    key = tuple(key or ())
    if len(key) != 4:
        raise ValueError("Unbekannte Zeile")
    w = "sitzung = ? AND scryfall_id = ? AND foil = ? AND condition = ? AND language = ?"
    ereignisse = conn.execute(f"SELECT id, qty FROM scan_log WHERE {w} ORDER BY id", (s["id"], *key)).fetchall()
    n = sum(e["qty"] for e in ereignisse)
    if n <= 0:
        raise ValueError("Diese Zeile gibt es in der Sitzung nicht")
    neu = (key[0], foil or key[1], condition or key[2], language or key[3])
    _werte(*neu[1:])
    menge = n if qty is None else int(qty)
    if not 0 <= menge <= SCAN_MAX:
        raise ValueError(f"Menge 0 bis {SCAN_MAX}")
    ts = (now or datetime.now(timezone.utc)).strftime(TS)
    with conn:
        if neu != key:  # die Zeile zieht um, die Reihenfolge der Sitzung bleibt
            conn.execute(f"UPDATE scan_log SET foil = ?, condition = ?, language = ? WHERE {w}", (*neu[1:], s["id"], *key))
            _buchen(conn, s["scope"], key, -n)
            _buchen(conn, s["scope"], neu, n, ts)
        if menge > n:
            conn.execute("INSERT INTO scan_log(sitzung, scryfall_id, foil, condition, language, qty, zug, at) VALUES (?,?,?,?,?,?,?,?)", (s["id"], *neu, menge - n, None, ts))
        weg = n - menge
        for e in reversed(ereignisse):  # weniger: von den jüngsten Ereignissen abziehen
            if weg <= 0:
                break
            if e["qty"] <= weg:
                conn.execute("DELETE FROM scan_log WHERE id = ?", (e["id"],))
            else:
                conn.execute("UPDATE scan_log SET qty = qty - ? WHERE id = ?", (weg, e["id"]))
            weg -= e["qty"]
        if menge != n:
            _buchen(conn, s["scope"], neu, menge - n, ts)
        _sitzung_rechnen(conn, s["id"])
    return scan_sitzung(conn, s["id"])


def scan_sitzung(conn, sitzung):
    """Eine Erfassen-Sitzung: Binder, Beginn, Karten, Wert und Zeilen (Druck, Foil, Zustand, Sprache, Menge, Preis, Kopien im ganzen Bestand),
    zuletzt erfasste zuerst."""
    s = _sitzung(conn, sitzung)
    zeilen = [dict(r) for r in conn.execute(
        "SELECT l.scryfall_id, l.foil, l.condition, l.language, SUM(l.qty) qty, MAX(l.id) zuletzt, c.oracle_id, c.name, c.set_code, c.number, "
        "c.image_url image, CASE WHEN l.foil != 'normal' THEN COALESCE(c.price_eur_foil, c.price_eur) ELSE COALESCE(c.price_eur, c.price_eur_foil) END price "
        "FROM scan_log l JOIN cards c USING (scryfall_id) WHERE l.sitzung = ? GROUP BY l.scryfall_id, l.foil, l.condition, l.language "
        "HAVING SUM(l.qty) > 0 ORDER BY zuletzt DESC", (s["id"],))]
    hat = dict(conn.execute(f"SELECT c.oracle_id, SUM(col.qty) FROM collection col JOIN cards c USING (scryfall_id) WHERE {OWNED} AND c.oracle_id IN "
                            f"(SELECT value FROM json_each(?)) GROUP BY c.oracle_id", (json.dumps(sorted({z["oracle_id"] for z in zeilen if z["oracle_id"]})),)))
    for z in zeilen:
        z["hat"] = hat.get(z["oracle_id"], 0)  # Kopien dieser Karte im ganzen Bestand
    return {"id": s["id"], "binder": s["scope"], "at": s["at"], "karten": sum(z["qty"] for z in zeilen),
            "wert": sum(z["qty"] * (z["price"] or 0) for z in zeilen), "zeilen": zeilen}


# --- Scan-Liste mit Abnahme (Phase 29, wie in ManaBox): erst sammeln und prüfen, dann übernehmen ----------------------------------------
# Erkannte Karten kommen zuerst auf die Scan-Liste (Tabelle scan_liste, je Scan eine Zeile, auf dem Server, damit nichts verloren geht, wenn das
# Handy weg ist). Dort wird geprüft und korrigiert; erst „Übernehmen“ legt alles auf einmal in einen Scan-Binder und macht daraus eine Erfassen-
# Sitzung wie in Phase 25 (imports „Kamera“, scan_log, Kaufpreis). Eine übernommene Sitzung lässt sich zurück auf die Liste holen.

LISTE_WAHL = 6  # so viele andere Kandidaten der Erkennung merkt sich ein Scan (zum Tauschen beim Prüfen)
LISTE_KEY = "scryfall_id = ? AND foil = ? AND condition = ? AND language = ?"


def _finishes(conn, sid):
    fin = conn.execute("SELECT json_extract(json, '$.finishes') FROM cards WHERE scryfall_id = ?", (sid,)).fetchone()
    fin = fin or [k["finishes"] for k in _katalog_drucke(conn, [sid]).values()]
    return json.loads(fin[0]) if fin and fin[0] else []


def liste_add(conn, scryfall_id, foil="normal", condition="near_mint", language="en", qty=1, zug=None, wahl=None, fetch=None, now=None, pruefen=False):
    """Erkannte Karte auf die Scan-Liste, noch nicht in die Sammlung. zug: derselbe Zug zählt einmal (Bild doppelt, Anfrage wiederholt, auch
    nach dem Übernehmen). wahl: die anderen Kandidaten der Erkennung (Ids), zum schnellen Tauschen beim Prüfen. Foil passend zum Druck.
    pruefen (Phase 32): Die Karte ist erkannt, der Druck aber geraten (mehrere mit demselben Bild); wahl nennt dann die anderen Drucke. -> liste"""
    _werte(foil, condition, language)
    if not 1 <= int(qty) <= SCAN_MAX:
        raise ValueError(f"Menge 1 bis {SCAN_MAX}")
    if zug and conn.execute("SELECT 1 FROM scan_liste WHERE zug = ? UNION ALL SELECT 1 FROM scan_log WHERE zug = ?", (str(zug), str(zug))).fetchone():
        return liste(conn)
    _karte_da(conn, scryfall_id, fetch, kat=True)
    andere = [w for w in dict.fromkeys(str(x) for x in wahl or []) if w != scryfall_id and re.fullmatch(r"[0-9a-f-]{36}", w)][:LISTE_WAHL]
    with conn:
        conn.execute("INSERT INTO scan_liste(scryfall_id, foil, condition, language, qty, zug, at, wahl, pruefen) VALUES (?,?,?,?,?,?,?,?,?)",
                     (scryfall_id, _passend(foil, _finishes(conn, scryfall_id)), condition, language, int(qty), str(zug) if zug else None,
                      (now or datetime.now(timezone.utc)).strftime(TS), json.dumps(andere), int(bool(pruefen))))
    return liste(conn)


def _drucke_info(conn, ids):
    """Name, Set, Nummer und Bild zu Druck-Ids, aus den bekannten Karten, den geladenen Sets oder dem Katalog. -> {id: {...}}"""
    j = json.dumps(sorted(set(ids)))
    out = {r[0]: {"id": r[0], "name": r[1], "set_code": r[2], "number": r[3], "image": r[4]} for r in conn.execute(
        "SELECT scryfall_id, name, set_code, number, image_url FROM cards WHERE scryfall_id IN (SELECT value FROM json_each(?)) UNION ALL "
        "SELECT scryfall_id, name, set_code, number, image_url FROM set_prints WHERE scryfall_id IN (SELECT value FROM json_each(?)) "
        "AND scryfall_id NOT IN (SELECT scryfall_id FROM cards)", (j, j))}
    for sid, k in _katalog_drucke(conn, [i for i in set(ids) if i not in out]).items():
        out[sid] = {"id": sid, "name": k["name"], "set_code": k["set_code"], "number": k["number"], "image": k["image"]}
    return out


def liste(conn):
    """Die Scan-Liste zum Prüfen: je Druck, Foil, Zustand und Sprache eine Zeile, zuletzt gescannte zuerst, mit Menge, Zahl der Scans, Preis,
    Kopien schon im Bestand (hat), den anderen Kandidaten der Erkennung (wahl) und pruefen (der Druck ist geraten, Phase 32). Ein Druck, den
    cards noch nicht kennt, zeigt Name, Set, Nummer, Bild und Preis aus dem Katalog (Phase 31). -> {karten, wert, zeilen}"""
    zeilen = [dict(r) for r in conn.execute(
        "SELECT l.scryfall_id, l.foil, l.condition, l.language, SUM(l.qty) qty, COUNT(*) scans, MAX(l.id) zuletzt, MAX(l.at) at, MAX(l.pruefen) pruefen, "
        "c.oracle_id, c.name, "
        "c.set_code, c.number, c.image_url image, CASE WHEN l.foil != 'normal' THEN COALESCE(c.price_eur_foil, c.price_eur) "
        "ELSE COALESCE(c.price_eur, c.price_eur_foil) END price FROM scan_liste l LEFT JOIN cards c USING (scryfall_id) "
        "GROUP BY l.scryfall_id, l.foil, l.condition, l.language ORDER BY zuletzt DESC")]
    kat = _katalog_drucke(conn, [z["scryfall_id"] for z in zeilen if z["name"] is None])
    for z in zeilen:
        k = kat.get(z["scryfall_id"])
        if k:
            a, b = (k["eur_foil"], k["eur"]) if z["foil"] != "normal" else (k["eur"], k["eur_foil"])
            z |= {"oracle_id": k["oracle_id"], "name": k["name"], "set_code": k["set_code"], "number": k["number"], "image": k["image"],
                  "price": a if a is not None else b}
        elif z["name"] is None:  # weder in cards noch im Katalog (der Druck ist dort seit dem Scan verschwunden): tauschen oder entfernen
            z["name"] = "Unbekannte Karte"
    wahl = defaultdict(list)
    for r in conn.execute("SELECT scryfall_id, foil, condition, language, wahl FROM scan_liste ORDER BY id DESC"):
        wahl[tuple(r[:4])] += json.loads(r[4] or "[]")
    info = _drucke_info(conn, [w for v in wahl.values() for w in v])
    hat = dict(conn.execute(f"SELECT c.oracle_id, SUM(col.qty) FROM collection col JOIN cards c USING (scryfall_id) WHERE {OWNED} AND c.oracle_id IN "
                            f"(SELECT value FROM json_each(?)) GROUP BY c.oracle_id", (json.dumps(sorted({z["oracle_id"] for z in zeilen if z["oracle_id"]})),)))
    for z in zeilen:
        key = (z["scryfall_id"], z["foil"], z["condition"], z["language"])
        z["wahl"] = [info[w] for w in dict.fromkeys(wahl[key]) if w in info and w != z["scryfall_id"]][:LISTE_WAHL]
        z["hat"] = hat.get(z["oracle_id"], 0)
    return {"karten": sum(z["qty"] for z in zeilen), "wert": sum(z["qty"] * (z["price"] or 0) for z in zeilen), "zeilen": zeilen}


def liste_aendern(conn, key, scryfall_id=None, foil=None, condition=None, language=None, qty=None, fetch=None, now=None):
    """Zeile der Scan-Liste ändern: andere Karte oder anderer Druck (scryfall_id; die bisherige bleibt als Kandidat), Foil, Zustand, Sprache,
    Menge (0 = von der Liste). key = (scryfall_id, foil, condition, language) wie in liste. Mit scryfall_id gilt der Druck als geprüft, auch
    wenn es derselbe bleibt. -> liste"""
    key = tuple(key or ())
    if len(key) != 4:
        raise ValueError("Unbekannte Zeile")
    ereignisse = conn.execute(f"SELECT id, qty, wahl FROM scan_liste WHERE {LISTE_KEY} ORDER BY id", key).fetchall()
    n = sum(e["qty"] for e in ereignisse)
    if n <= 0:
        raise ValueError("Diese Zeile gibt es auf der Scan-Liste nicht mehr")
    _werte(foil or key[1], condition or key[2], language or key[3])
    sid = scryfall_id or key[0]
    if sid != key[0]:
        _karte_da(conn, sid, fetch, kat=True)
    neu = (sid, _passend(foil or key[1], _finishes(conn, sid)) if sid != key[0] or foil else key[1], condition or key[2], language or key[3])
    menge = n if qty is None else int(qty)
    if not 0 <= menge <= SCAN_MAX:
        raise ValueError(f"Menge 0 bis {SCAN_MAX}")
    with conn:
        for e in ereignisse:  # anderer Druck: die bisherige Karte bleibt als Kandidat, falls es doch die war
            w = json.loads(e["wahl"] or "[]")
            w = [key[0]] + [x for x in w if x not in (sid, key[0])] if sid != key[0] else w
            conn.execute("UPDATE scan_liste SET scryfall_id = ?, foil = ?, condition = ?, language = ?, wahl = ?, pruefen = pruefen AND ? WHERE id = ?",
                         (*neu, json.dumps(w[:LISTE_WAHL]), not scryfall_id, e["id"]))
        if menge > n:
            conn.execute("INSERT INTO scan_liste(scryfall_id, foil, condition, language, qty, zug, at, wahl) VALUES (?,?,?,?,?,?,?,?)",
                         (*neu, menge - n, None, (now or datetime.now(timezone.utc)).strftime(TS), "[]"))
        weg = n - menge
        for e in reversed(ereignisse):  # weniger: von den jüngsten Scans abziehen
            if weg <= 0:
                break
            if e["qty"] <= weg:
                conn.execute("DELETE FROM scan_liste WHERE id = ?", (e["id"],))
            else:
                conn.execute("UPDATE scan_liste SET qty = qty - ? WHERE id = ?", (weg, e["id"]))
            weg -= e["qty"]
        _etiketten(conn)
    return liste(conn)


def liste_zurueck(conn):
    """„Letzte zurück“: den jüngsten Scan von der Liste nehmen. -> liste mit „weg“ (Name der Karte)"""
    r = conn.execute("SELECT id, scryfall_id FROM scan_liste ORDER BY id DESC LIMIT 1").fetchone()
    if not r:
        raise ValueError("Die Scan-Liste ist leer")
    with conn:
        conn.execute("DELETE FROM scan_liste WHERE id = ?", (r["id"],))
        _etiketten(conn)
    return liste(conn) | {"weg": _drucke_info(conn, [r["scryfall_id"]]).get(r["scryfall_id"], {}).get("name")}


def liste_leeren(conn):
    """Die ganze Scan-Liste verwerfen (nichts davon kommt in die Sammlung). -> liste"""
    with conn:
        conn.execute("DELETE FROM scan_liste")
        _etiketten(conn)
    return liste(conn)


def liste_uebernehmen(conn, binder, now=None, fetch=None, deck=False):
    """„Übernehmen“: die geprüfte Scan-Liste in einen Scan-Binder legen, ganz oder gar nicht. deck (Phase 60): Der Binder ist ein fertiges Deck
    (kommt auf die Liste fertige_decks: nie verfügbar, nie im Verkauf, unter Decks zu sehen); ein Deck bleibt ein Deck, auch ohne deck. Daraus wird eine Erfassen-Sitzung wie in Phase 25
    (imports „Kamera“, scan_log, Kaufpreis = Marktpreis jetzt, „Zuletzt hinzugefügt“, Neuigkeiten, Wertverlauf); die Liste ist danach leer.
    Preise, die älter als PRICE_MAX_AGE_H sind (etwa vom Laden des Sets vor Wochen), holt sie vorher neu; ohne Netz gilt der zuletzt bekannte.
    Drucke, die bisher nur der Katalog kennt (Phase 31), bekommen hier ihre vollen Kartendaten, alle auf einmal (75 je Anfrage); das braucht
    Netz. -> scan_sitzung"""
    binder = scan_binder_name(conn, binder, deck)
    ereignisse = conn.execute("SELECT * FROM scan_liste ORDER BY id").fetchall()
    if not ereignisse:
        raise ValueError("Die Scan-Liste ist leer")
    try:
        fehlt = ensure_cards(conn, [e["scryfall_id"] for e in ereignisse], fetch or sources.scryfall_cards)
    except (urllib.error.URLError, TimeoutError):
        raise ValueError("Scryfall ist gerade nicht erreichbar, von dort kommen die Kartendaten der neuen Karten. Die Scan-Liste bleibt, bitte später noch einmal übernehmen.")
    if fehlt:
        raise ValueError(f"{len(fehlt)} Karten der Scan-Liste kennt Scryfall nicht (mehr). Bitte dort tauschen oder entfernen, dann noch einmal übernehmen.")
    jetzt = now or datetime.now(timezone.utc)
    ts = jetzt.strftime(TS)
    alt = [r[0] for r in conn.execute("SELECT scryfall_id FROM cards WHERE updated_at < ? AND scryfall_id IN (SELECT scryfall_id FROM scan_liste)",
                                      ((jetzt - timedelta(hours=PRICE_MAX_AGE_H)).strftime(TS),))]
    if alt:
        try:
            store_cards(conn, (fetch or sources.scryfall_cards)(alt)[0], ts)
        except (urllib.error.URLError, TimeoutError):
            pass
    if deck and binder not in fertige_decks(conn):
        set_fertige_decks(conn, fertige_decks(conn) + [binder])
    with conn:
        s = conn.execute("INSERT INTO imports(file, sha256, scope, added, removed, at) VALUES (?,?,?,?,?,?)", (SCAN_DATEI, "", binder, 0, 0, ts)).lastrowid
        for e in ereignisse:
            key = (e["scryfall_id"], e["foil"], e["condition"], e["language"])
            conn.execute("INSERT INTO scan_log(sitzung, scryfall_id, foil, condition, language, qty, zug, at) VALUES (?,?,?,?,?,?,?,?)", (s, *key, e["qty"], e["zug"], e["at"]))
            _buchen(conn, binder, key, e["qty"], ts)
        _sitzung_rechnen(conn, s)
        conn.execute("DELETE FROM scan_liste")
    return scan_sitzung(conn, s)


def _sitzung_kopien(conn, s):
    """Was eine übernommene Sitzung in ihren Binder gelegt hat, und ob es dort noch liegt. -> ({Schlüssel: Menge}, alles noch da?)"""
    braucht = defaultdict(int)
    for e in conn.execute("SELECT scryfall_id, foil, condition, language, qty FROM scan_log WHERE sitzung = ?", (s["id"],)):
        braucht[tuple(e[:4])] += e[4]
    da = all((conn.execute(f"SELECT qty FROM collection WHERE {ZEILE}", (s["scope"], *k)).fetchone() or [0])[0] >= n for k, n in braucht.items())
    return braucht, da


LETZTE_SITZUNG = ("SELECT * FROM imports i WHERE file = ? AND (? IS NULL OR id = ?) AND EXISTS (SELECT 1 FROM scan_log l WHERE l.sitzung = i.id) "
                  "ORDER BY id DESC LIMIT 1")  # leere Sitzungen (alles zurückgenommen) zählen nicht


def letzte_sitzung(conn):
    """Die zuletzt übernommene Erfassen-Sitzung (für „Zurücknehmen“), None ohne. -> {id, binder, karten, at, zuruecknehmbar}"""
    s = conn.execute(LETZTE_SITZUNG, (SCAN_DATEI, None, None)).fetchone()
    if not s:
        return None
    braucht, da = _sitzung_kopien(conn, s)
    return {"id": s["id"], "binder": s["scope"], "karten": sum(braucht.values()), "at": s["at"], "zuruecknehmbar": da and bool(braucht)}


def sitzung_zuruecknehmen(conn, sitzung=None):
    """Eine übernommene Erfassen-Sitzung zurücknehmen (Standard: die letzte): ihre Kopien kommen aus dem Binder zurück auf die Scan-Liste, zum
    Korrigieren und erneut Übernehmen. Nur solange der Binder sie noch hat (sonst im Kartendetail ändern). -> liste"""
    s = conn.execute(LETZTE_SITZUNG, (SCAN_DATEI, sitzung, sitzung)).fetchone()
    if not s:
        raise ValueError("Es gibt keine übernommene Erfassung zum Zurücknehmen")
    braucht, da = _sitzung_kopien(conn, s)
    if not da:
        raise ValueError(f"In „{s['scope']}“ hat sich seitdem etwas geändert (verkauft, verschoben oder geändert). Ändere die Karten im Kartendetail.")
    with conn:
        for key, n in braucht.items():
            _buchen(conn, s["scope"], key, -n)
        conn.execute("INSERT INTO scan_liste(scryfall_id, foil, condition, language, qty, zug, at, wahl) "
                     "SELECT scryfall_id, foil, condition, language, qty, zug, at, '[]' FROM scan_log WHERE sitzung = ? ORDER BY id", (s["id"],))
        for tabelle, spalte in (("scan_log", "sitzung"), ("changes", "import_id"), ("imports", "id")):
            conn.execute(f"DELETE FROM {tabelle} WHERE {spalte} = ?", (s["id"],))
    return liste(conn)


DRUCK = ("id", "oid", "name", "set_code", "number", "image")  # ein Druck zum Tauschen auf der Scan-Liste


def drucke_karte(conn, oid):
    """Alle Papier-Drucke einer Karte (oracle_id) zum Tauschen auf der Scan-Liste (Phase 60), auch die mit anderem Bild: aus dem Katalog (neueste
    zuerst), dahinter bekannte Karten und geladene Sets, die er nicht kennt (ohne Katalog nur die). -> [{id, oid, name, set_code, number, image}]"""
    out = {}
    k = _katalog(conn)
    if k:
        with closing(k):
            for r in k.execute("SELECT scryfall_id, oracle_id, name, set_code, number, image FROM drucke WHERE oracle_id = ? "
                               "ORDER BY released DESC, set_code, CAST(number AS INTEGER), number", (oid,)):
                out[r[0]] = dict(zip(DRUCK, r))
    for r in conn.execute("SELECT scryfall_id, oracle_id, name, set_code, number, image_url FROM cards WHERE oracle_id = ?1 "
                          "AND COALESCE(json_extract(json, '$.digital'), 0) = 0 UNION SELECT scryfall_id, oracle_id, name, set_code, number, image_url "
                          "FROM set_prints WHERE oracle_id = ?1 AND digital = 0 ORDER BY 4, 5", (oid,)):
        out.setdefault(r[0], dict(zip(DRUCK, r)))
    return list(out.values())


def drucke_suchen(conn, q, limit=24):
    """Andere Karte für eine Zeile der Scan-Liste: Drucke, deren Name den Text enthält. Je Name zuerst die aus den geladenen Sets und den
    bekannten Karten (nach Set und Nummer), dann alle übrigen Papier-Drucke aus dem Katalog (Phase 31, neueste zuerst); Scryfall wird nicht
    mehr gefragt. -> [{id, oid, name, set_code, number, image}]"""
    q = (q or "").strip()
    if len(q) < 2:
        raise ValueError("Mindestens zwei Buchstaben")
    muster = f"%{q}%"
    out = {r[0]: dict(zip(DRUCK, r)) for r in conn.execute(
        "SELECT scryfall_id, oracle_id, name, set_code, number, image_url FROM set_prints WHERE name LIKE ? AND digital = 0 UNION "
        "SELECT scryfall_id, oracle_id, name, set_code, number, image_url FROM cards WHERE name LIKE ? AND COALESCE(json_extract(json, '$.digital'), 0) = 0 "
        "ORDER BY 3, 4, 5 LIMIT ?", (muster, muster, limit * 4))}
    k = _katalog(conn)
    if k:
        with closing(k):  # genaue Namen und Anfänge zuerst, damit die Grenze nicht die gesuchte Karte abschneidet
            for r in k.execute("SELECT scryfall_id, oracle_id, name, set_code, number, image FROM drucke WHERE name LIKE ?1 ORDER BY lower(name) != lower(?2), "
                               "name NOT LIKE ?2 || '%', name, released DESC, set_code, number LIMIT ?3", (muster, q, limit)):
                out.setdefault(r[0], dict(zip(DRUCK, r)))
    genau = q.casefold()
    return sorted(out.values(), key=lambda d: (d["name"].casefold() != genau, not d["name"].casefold().startswith(genau), d["name"]))[:limit]


# --- Messbilder (Phase 30, PLAN E20): echte Kamerabilder mit Etikett, zum Messen der Erkennung ---------------------------------------------
# Testdaten, kein Bestand: Die Dateien liegen neben der Datenbank der Sammlung (messbild_ordner) und fehlen in der Sicherung. Das Etikett (Druck,
# Foil, Sprache) eines Bilds mit Zug-Kennung ist der Stand der Scan-Liste: Tauschen dort zieht es nach, Entfernen löst es (Druck None = noch
# zuordnen). Bilder vom Auslöser haben keinen Zug und bekommen ihr Etikett von Hand (messbild_setzen).

MESSBILD_MAX = 2 * 1024 * 1024  # Bytes je Bild; 1280 px als JPEG lagen bei 110 KB, 1920 px brauchen rund das Doppelte
MESSBILD_PX = 1920              # lange Seite höchstens: das volle Kamerabild, damit die Messung dieselbe Schrift sieht wie die Kamera (Phase 35)
MERKMALE = ("huelle", "schraeg", "frei")  # zum Ankreuzen (Hülle, schräg, frei im Bild); Foil und Sprache stehen im Etikett


def messbild_ordner(db=None):
    """Ablage der Messbilder einer Sammlung: data/messbilder/ fürs Hauptkonto, data/konten/<name>/messbilder/ für Unterkonten."""
    return Path(db or DB).parent / "messbilder"


def _jpeg_mass(b):
    """Breite und Höhe aus dem Kopf eines JPEG (SOF-Segment). Das Bild selbst kann Python nicht lesen, den Kopf schon."""
    i = 2
    while b[:3] == b"\xff\xd8\xff" and i + 9 <= len(b) and b[i] == 0xFF:
        if 0xC0 <= b[i + 1] <= 0xCF and b[i + 1] not in (0xC4, 0xC8, 0xCC):  # SOF0 bis SOF15 ohne Huffman-Tabelle, JPG und DAC
            return int.from_bytes(b[i + 7:i + 9], "big"), int.from_bytes(b[i + 5:i + 7], "big")
        i += 2 + int.from_bytes(b[i + 2:i + 4], "big")
    raise ValueError("Das ist kein JPEG-Bild")


def _etiketten(conn):
    """Etiketten der Messbilder mit Zug-Kennung auf den Stand von Scan-Liste und Sitzungen bringen: getauscht heißt neuer Druck, entfernt heißt
    ohne Druck und ohne Zug (ab dann gilt, was messbild_setzen sagt)."""
    conn.execute("UPDATE messbilder SET (scryfall_id, foil, language) = (SELECT scryfall_id, foil, language FROM (SELECT zug, scryfall_id, foil, language "
                 "FROM scan_liste UNION ALL SELECT zug, scryfall_id, foil, language FROM scan_log) z WHERE z.zug = messbilder.zug) WHERE zug IS NOT NULL")
    conn.execute("UPDATE messbilder SET zug = NULL WHERE zug IS NOT NULL AND scryfall_id IS NULL")


def _merkmale(m):
    m = m.split(",") if isinstance(m, str) else m or ()
    return ",".join(x for x in MERKMALE if x in m)


def messbild_neu(conn, ordner, jpeg, zug=None, merkmale=None, rahmen=None, now=None):
    """Kamerabild als Messbild ablegen: JPEG, höchstens MESSBILD_MAX Bytes und MESSBILD_PX an der langen Seite (Breite und Höhe aus dem Kopf der
    Datei, nicht vom Absender). zug = Kennung der gezählten Karte: Das Etikett kommt von der Scan-Liste, derselbe Zug zählt einmal. Ohne zug
    (Auslöser) bleibt es leer, bis messbild_setzen es zuordnet. rahmen = (x, y, Breite, Höhe) des Rahmens im Bild. -> Eintrag wie in messbilder"""
    if len(jpeg) > MESSBILD_MAX:
        raise ValueError(f"Das Bild ist größer als {MESSBILD_MAX // 1024 // 1024} MB")
    breite, hoehe = _jpeg_mass(jpeg)
    if not 0 < max(breite, hoehe) <= MESSBILD_PX:
        raise ValueError(f"Das Bild ist größer als {MESSBILD_PX} Pixel")
    rahmen = [round(float(x), 1) for x in rahmen or ()]
    if len(rahmen) not in (0, 4) or any(not 0 <= x <= MESSBILD_PX for x in rahmen):
        raise ValueError("Rahmen: x, y, Breite und Höhe im Bild")
    mid = (conn.execute("SELECT id FROM messbilder WHERE zug = ?", (str(zug),)).fetchone() or [None])[0] if zug else None
    if mid is None:
        Path(ordner).mkdir(parents=True, exist_ok=True)
        with conn:
            mid = conn.execute("INSERT INTO messbilder(at, merkmale, breite, hoehe, rahmen, zug) VALUES (?,?,?,?,?,?)",
                               ((now or datetime.now(timezone.utc)).strftime(TS), _merkmale(merkmale), breite, hoehe, json.dumps(rahmen),
                                str(zug) if zug else None)).lastrowid
            _etiketten(conn)
            (Path(ordner) / f"{mid}.jpg").write_bytes(jpeg)
    return next(m for m in messbilder(conn, ordner)["items"] if m["id"] == mid)


def messbilder(conn, ordner):
    """Alle Messbilder, jüngste zuerst, mit Name, Set, Nummer und Scryfall-Bild des Etiketts. -> {zahl, bytes, ohne (noch zuordnen), items}"""
    da = {int(p.stem): p.stat().st_size for p in Path(ordner).glob("*.jpg") if p.stem.isdigit()}
    rows = conn.execute("SELECT * FROM messbilder ORDER BY id DESC").fetchall()
    # ponytail: Einträge ohne Datei fallen weg (nach dem Zurückspielen einer Sicherung: die Bilder sind nicht drin)
    fehlt = [(r["id"],) for r in rows if r["id"] not in da]
    if fehlt:
        with conn:
            conn.executemany("DELETE FROM messbilder WHERE id = ?", fehlt)
    info = _drucke_info(conn, [r["scryfall_id"] for r in rows if r["scryfall_id"]])
    leer = {"name": None, "set_code": None, "number": None, "image": None}
    items = [dict(r) | {"merkmale": [x for x in (r["merkmale"] or "").split(",") if x], "rahmen": json.loads(r["rahmen"] or "[]"), "bytes": da[r["id"]]}
             | {k: v for k, v in info.get(r["scryfall_id"], leer).items() if k != "id"} for r in rows if r["id"] in da]
    return {"zahl": len(items), "bytes": sum(m["bytes"] for m in items), "ohne": sum(not m["scryfall_id"] for m in items), "items": items}


def messbild_setzen(conn, mid, scryfall_id=None, foil=None, language=None, merkmale=None, fetch=None):
    """Etikett von Hand (None lässt den Wert): Druck, Foil, Sprache, Merkmale. Für Bilder vom Auslöser und solche, deren Scan von der Liste
    genommen wurde. Ein Bild, das noch an der Scan-Liste hängt, löst sich damit von ihr: Deine Angabe gilt."""
    r = conn.execute("SELECT * FROM messbilder WHERE id = ?", (int(mid or 0),)).fetchone()
    if not r:
        raise ValueError("Dieses Messbild gibt es nicht mehr")
    sid = scryfall_id or r["scryfall_id"]
    if not sid:
        raise ValueError("Bitte die Karte wählen")
    neu = (sid, foil or r["foil"] or "normal", language or r["language"] or "en")
    _werte(neu[1], "near_mint", neu[2])
    if scryfall_id:
        _karte_da(conn, scryfall_id, fetch)
    with conn:
        conn.execute("UPDATE messbilder SET scryfall_id = ?, foil = ?, language = ?, merkmale = ?, zug = CASE WHEN ? THEN zug END WHERE id = ?",
                     (*neu, r["merkmale"] if merkmale is None else _merkmale(merkmale), neu == tuple(r[k] for k in ("scryfall_id", "foil", "language")), r["id"]))


def messbild_weg(conn, ordner, mid=None):
    """Ein Messbild löschen, ohne mid alle (auch Dateien ohne Eintrag). -> Zahl der gelöschten Einträge"""
    mid = None if mid is None else int(mid)
    with conn:
        n = conn.execute("DELETE FROM messbilder WHERE ? IS NULL OR id = ?", (mid, mid)).rowcount
    for p in Path(ordner).glob(f"{'*' if mid is None else mid}.jpg"):
        p.unlink()
    return n


# --- Bestand ohne ManaBox (Phase 26, PLAN E18): Scan-Binder ändern, als verkauft buchen, ManaBox-Binder übernehmen ------------------------

VERKAUF_DATEI = "Verkauf"  # imports.file einer Buchung „als verkauft“
ZEILE = "binder = ? AND scryfall_id = ? AND foil = ? AND condition = ? AND language = ?"


def _scan_zeile(conn, key):
    """Sammlungszeile eines Scan-Binders; key = (binder, scryfall_id, foil, condition, language). ManaBox-Binder ändert man in ManaBox."""
    key = tuple(key or ())
    if len(key) != 5:
        raise ValueError("Unbekannte Kopie")
    r = conn.execute(f"SELECT * FROM collection WHERE {ZEILE}", key).fetchone()
    if not r:
        raise ValueError("Diese Kopie gibt es nicht mehr")
    if r["binder_type"] != "scan":
        raise ValueError(f"„{key[0]}“ kommt aus ManaBox: dort ändern und neu exportieren, oder den Binder übernehmen (mtg uebernehmen)")
    return key, r


def kopie_aendern(conn, key, qty=None, binder=None, foil=None, condition=None, language=None):
    """Kopien eines Scan-Binders ändern (Phase 26). Bleibt das Ziel gleich, setzt qty die Menge (0 = Zeile weg, samt Ort und Notiz). Mit anderem
    Binder (Scan-Binder oder neuer Name), Foil, Zustand oder Sprache wandern qty Kopien (Standard: alle) dorthin; eine vorhandene Zeile bekommt
    sie dazu (Kaufpreis gemittelt), Ort und Notiz ziehen mit, wenn die ganze Zeile umzieht. -> Schlüssel der Zeile danach"""
    key, r = _scan_zeile(conn, key)
    ziel = (scan_binder_name(conn, binder) if (binder or "").strip() not in ("", key[0]) else key[0], key[1], foil or key[2], condition or key[3], language or key[4])
    _werte(*ziel[2:])
    n = r["qty"] if qty is None else int(qty)
    with conn:
        if ziel == key:
            if not 0 <= n <= 9999:
                raise ValueError("Menge 0 bis 9999")
            if n:
                conn.execute(f"UPDATE collection SET qty = ? WHERE {ZEILE}", (n, *key))
            else:
                conn.execute(f"DELETE FROM collection WHERE {ZEILE}", key)
                conn.execute(f"DELETE FROM notizen WHERE {ZEILE}", key)
            return key
        if not 1 <= n <= r["qty"]:
            raise ValueError(f"1 bis {r['qty']} Kopien")
        da = conn.execute(f"SELECT qty, paid FROM collection WHERE {ZEILE}", ziel).fetchone()
        if da:
            conn.execute(f"UPDATE collection SET qty = qty + ?, paid = ? WHERE {ZEILE}", (n, _mix(da["qty"], da["paid"], n, r["paid"]), *ziel))
        else:
            conn.execute(COLL_INSERT, (ziel[0], "scan", *ziel[1:], n, r["added"], r["mbid"], r["paid"]))
        if n < r["qty"]:
            conn.execute(f"UPDATE collection SET qty = qty - ? WHERE {ZEILE}", (n, *key))
        else:
            conn.execute(f"DELETE FROM collection WHERE {ZEILE}", key)
            if not conn.execute(f"SELECT 1 FROM notizen WHERE {ZEILE}", ziel).fetchone():
                conn.execute(f"UPDATE notizen SET binder = ?, foil = ?, condition = ?, language = ? WHERE {ZEILE}", (ziel[0], *ziel[2:], *key))
    return ziel


def binder_umbenennen(conn, alt, neu):
    """Scan-Binder umbenennen (Phase 26): Kopien, Orte und Notizen, Erfassen-Sitzungen und gebuchte Verkäufe ziehen mit, bei einem eingescannten
    Deck auch der Eintrag unter den fertigen Decks und sein Commander. -> neuer Name"""
    if alt not in scan_binders(conn):
        raise ValueError(f"„{alt}“ ist kein Scan-Binder")
    neu = scan_binder_name(conn, neu)
    if neu == alt:
        return neu
    if conn.execute("SELECT 1 FROM collection WHERE binder = ?", (neu,)).fetchone():
        raise ValueError(f"„{neu}“ gibt es schon. Karten verschiebst du einzeln im Kartendetail.")
    with conn:
        conn.execute("DELETE FROM notizen WHERE binder = ?", (neu,))  # Reste eines früheren Binders gleichen Namens
        for tabelle in ("collection", "notizen", "sales"):
            conn.execute(f"UPDATE {tabelle} SET binder = ? WHERE binder = ?", (neu, alt))
        conn.execute("UPDATE imports SET scope = ? WHERE scope = ? AND file IN (?, ?)", (neu, alt, SCAN_DATEI, VERKAUF_DATEI))
        fest = fertige_decks(conn)
        if alt in fest:  # ein eingescanntes Deck (Phase 60) bleibt eins, mit seinem Commander
            conn.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (FERTIGE_DECKS, json.dumps([neu if n == alt else n for n in fest], ensure_ascii=False)))
            conn.execute("UPDATE OR REPLACE meta SET key = ? WHERE key = ?", ("deckbinder:" + neu, "deckbinder:" + alt))
    return neu


def verkauf_buchen(conn, zeilen, erloes=None, now=None):
    """Als verkauft buchen (Phase 26, E18): Kopien aus Scan-Bindern nehmen und wie die Verkauft-Erkennung beim Import (E7) in sales schreiben,
    je Kopie mit dem Trendpreis; mit erloes (was du insgesamt bekommen hast) im Verhältnis der Trendpreise verteilt. Ein Eintrag in imports
    (Datei „Verkauf“) hält die Buchung zusammen (Jahresüberblick, Zurücknehmen). zeilen = [(Schlüssel, Menge)]. Karten aus ManaBox-Bindern
    bucht weiter der nächste Import. -> {import_id, karten, wert}"""
    posten = defaultdict(int)
    for key, n in zeilen or []:
        posten[tuple(key)] += int(n)
    if not posten or min(posten.values()) < 1:
        raise ValueError("Welche Karten? Je Zeile mindestens eine Kopie")
    rows, vorher = [], []  # vorher: Kaufpreis, Datum und ManaBox-ID je Zeile, damit „Zurücknehmen“ sie wiederherstellt
    for key, n in posten.items():
        key, r = _scan_zeile(conn, key)
        if n > r["qty"]:
            raise ValueError(f"In „{key[0]}“ liegen nur {r['qty']} Kopien davon")
        c = conn.execute("SELECT price_eur, price_eur_foil FROM cards WHERE scryfall_id = ?", (key[1],)).fetchone()
        rows.append([key, n, unit_price(c, key[2]) if c else 0.0, r["qty"]])
        vorher.append([r["paid"], r["added"], r["mbid"]])
    if erloes not in (None, ""):
        erloes, trend, stueck = float(erloes), sum(n * p for _, n, p, _ in rows), sum(n for _, n, _, _ in rows)
        if erloes < 0:
            raise ValueError("Der Erlös kann nicht negativ sein")
        for z in rows:  # ohne Trendpreise gleichmäßig je Karte
            z[2] = round(z[2] * erloes / trend if trend else erloes / stueck, 4)
    ts = (now or datetime.now(timezone.utc)).strftime(TS)
    binder = {z[0][0] for z in rows}
    with conn:
        iid = conn.execute("INSERT INTO imports(file, sha256, scope, added, removed, at) VALUES (?,?,?,?,?,?)",
                           (VERKAUF_DATEI, "", binder.pop() if len(binder) == 1 else "Scan-Binder", 0, sum(z[1] for z in rows), ts)).lastrowid
        je = defaultdict(int)
        for key, n, p, qty in rows:
            if n < qty:
                conn.execute(f"UPDATE collection SET qty = qty - ? WHERE {ZEILE}", (n, *key))
            else:
                conn.execute(f"DELETE FROM collection WHERE {ZEILE}", key)
                conn.execute(f"DELETE FROM notizen WHERE {ZEILE}", key)
            conn.execute("INSERT INTO sales VALUES (?,?,?,?,?,?,?,?,?)", (iid, *key, n, p, ts))
            je[key[1]] -= n
        conn.executemany("INSERT INTO changes VALUES (?,?,?)", [(iid, sid, d) for sid, d in je.items()])
        conn.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (f"verkauf:{iid}", json.dumps(vorher)))
    return {"import_id": iid, "karten": sum(z[1] for z in rows), "wert": sum(z[1] * z[2] for z in rows)}


def verkauf_zuruecknehmen(conn, import_id=None):
    """Eine Buchung „als verkauft“ zurücknehmen (Standard: die letzte): die Kopien kommen in ihre Scan-Binder zurück, mit Kaufpreis und Datum
    von vorher (ohne Ort und Notiz, die gingen mit dem Verkauf), Buchung und Verkäufe verschwinden. -> {import_id, karten, wert}"""
    i = conn.execute("SELECT id FROM imports WHERE file = ? AND (? IS NULL OR id = ?) ORDER BY id DESC LIMIT 1",
                     (VERKAUF_DATEI, import_id, import_id)).fetchone()
    if not i:
        raise ValueError("Es gibt keine Buchung „als verkauft“ zum Zurücknehmen")
    verkauft = conn.execute("SELECT * FROM sales WHERE import_id = ? ORDER BY rowid", (i[0],)).fetchall()  # in der Reihenfolge der Buchung
    for s in verkauft:
        typ = conn.execute("SELECT binder_type FROM collection WHERE binder = ? LIMIT 1", (s["binder"],)).fetchone()
        if typ and typ[0] != "scan":
            raise ValueError(f"„{s['binder']}“ ist inzwischen ein Binder aus ManaBox, dorthin bucht die App nichts zurück")
    r = conn.execute("SELECT value FROM meta WHERE key = ?", (f"verkauf:{i[0]}",)).fetchone()
    vorher = json.loads(r[0]) if r else []
    if len(vorher) != len(verkauft):  # Buchung von vor diesem Stand: nichts gemerkt, die Kopien kommen ohne Kaufpreis zurück
        vorher = [[None, None, ""]] * len(verkauft)
    with conn:
        for s, (paid, added, mbid) in zip(verkauft, vorher):
            key = (s["binder"], s["scryfall_id"], s["foil"], s["condition"], s["language"])
            da = conn.execute(f"SELECT qty, paid FROM collection WHERE {ZEILE}", key).fetchone()
            if da:
                conn.execute(f"UPDATE collection SET qty = qty + ?, paid = ? WHERE {ZEILE}", (s["qty"], _mix(da["qty"], da["paid"], s["qty"], paid), *key))
            else:
                conn.execute(COLL_INSERT, (key[0], "scan", *key[1:], s["qty"], added or s["at"], mbid or "", paid))
        conn.execute("DELETE FROM meta WHERE key = ?", (f"verkauf:{i[0]}",))
        for tabelle, spalte in (("sales", "import_id"), ("changes", "import_id"), ("imports", "id")):
            conn.execute(f"DELETE FROM {tabelle} WHERE {spalte} = ?", (i[0],))
    return {"import_id": i[0], "karten": sum(s["qty"] for s in verkauft), "wert": sum(s["qty"] * s["price"] for s in verkauft)}


def uebernahme_pruefen(conn, binder):
    """Kann dieser Binder in die App übernommen werden? Nur gewöhnliche ManaBox-Binder (keine Decks, Wunschlisten oder Scan-Binder). -> Karten"""
    typen = dict(conn.execute("SELECT binder_type, SUM(qty) FROM collection WHERE binder = ? GROUP BY binder_type", (binder,)).fetchall())
    if not typen:
        raise ValueError(f"Kein Binder „{binder}“ (mtg stats bzw. die Binder-Liste unter Karten zeigt alle)")
    if set(typen) == {"scan"}:
        raise ValueError(f"„{binder}“ führt die App schon")
    if set(typen) != {"binder"} or binder in deck_binders(conn):
        raise ValueError(f"„{binder}“ ist ein Deck oder eine Wunschliste, die bleiben bei ManaBox")
    return sum(typen.values())


def binder_uebernehmen(conn, binder):
    """ManaBox-Binder in einen Scan-Binder umwandeln (Phase 26, einmalig; vorher eine Sicherung anlegen): ab dann schreibt nur die App, ein
    ManaBox-Export mit diesem Binder ändert ihn nicht mehr. Der gemerkte Stand für „Rückgängig“ passt danach nicht mehr und verfällt. -> Karten"""
    n = uebernahme_pruefen(conn, binder)
    with conn:
        conn.execute("UPDATE collection SET binder_type = 'scan' WHERE binder = ?", (binder,))
        conn.execute("DELETE FROM meta WHERE key = 'undo'")
    return n


# --- CLI ---------------------------------------------------------------------------------------------------------

def _progress(done, total):
    print(f"\rScryfall: {done}/{total}", end="\n" if done >= total else "", file=sys.stderr, flush=True)


def _fetch(ids):
    return sources.scryfall_cards(ids, progress=_progress)


def _lookup(idents):
    return sources.scryfall_lookup(idents, progress=_progress)


def cmd_import(a):
    raw = Path(a.csv).read_bytes()
    res = import_file(connect(), raw, Path(a.csv).name, binder=a.binder, commander=a.commander, dry_run=a.dry_run, force=a.force,
                      fetch=_fetch, lookup=_lookup, archive=ARCHIVE)
    print(f"Erkannt: {FORMATS[res['format']]}")
    print(format_import(res))
    return 1 if res["status"] == "abgebrochen" else 0


def cmd_prices(a):
    conn = connect()
    print(f"Preise aktualisiert: {zahl(refresh_prices(conn, _fetch))} Karten")
    try:
        n = refresh_cardmarket(conn, sources.cardmarket_guide)
    except sources.QuelleAus as e:  # Phase 44: Preise von Scryfall sind schon da, nur die Preisliste fehlt
        print(f"Cardmarket-Preisliste: übersprungen ({e})")
        return
    print("Cardmarket-Preisliste: heute schon übernommen" if n is None else f"Cardmarket-Preisliste: {zahl(n)} Produkte")


def cmd_stats(a):
    print(format_stats(stats(connect())))


def cmd_card(a):
    treffer = card_info(connect(), a.name)
    print("\n\n".join(format_card(i) for i in treffer) if treffer else f"Keine Karte „{a.name}“ gefunden.")
    return 0 if treffer else 1


def cmd_sell(a):
    conn = connect()
    minimum = rules(conn)["sell_min"] if a.min is None else a.min
    alle = plan(conn, sell_min=minimum)
    rows = sorted((r for r in alle if r["stack"] == "sell"), key=lambda r: (-r["price"], r["name"], r["binder"]))
    bulk = [r for r in alle if r["stack"] == "bulk"]
    print(f"Verkaufen ab {eur(minimum)}: {zahl(sum(r['qty'] for r in rows))} Karten, "
          f"Summe {eur(sum(r['qty'] * r['price'] for r in rows))}")
    for i, r in enumerate(rows[:30], 1):
        print(f"{i:>2}. {eur(r['price']):>10}  {r['qty']}×  {r['name']} ({r['set']}){' ' + r['foil'] if r['foil'] != 'normal' else ''} – {r['binder']}")
    if len(rows) > 30:
        print(f"    … und {len(rows) - 30} weitere Zeilen")
    print(f"Bulk (unter {eur(minimum)}): {zahl(sum(r['qty'] for r in bulk))} Karten, Summe {eur(sum(r['qty'] * r['price'] for r in bulk))}")


def cmd_rules(a):
    conn = connect()
    r = set_rules(conn, a.keep, a.staples, a.min) if (a.keep, a.staples, a.min) != (None, None, None) else rules(conn)
    print(f"Behalten: {r['keep']} je Karte, {max(r['keep'], r['staples'])} je Staple (EDHREC-Rang bis {RANK_STAPLE} oder Top-10-Commander), "
          f"Basics alle · Verkaufen ab {eur(r['sell_min'])}, darunter Bulk")


def _tags(conn, deckbuild):
    if deckbuild.ensure_tags(conn, progress=lambda n, t: print(f"\rRollen-Tags laden: {n}/{t}", end="", file=sys.stderr)):
        print(file=sys.stderr)


def _edhrec_progress(i, n, name):
    print(f"\rEDHREC {i}/{n}  {name[:40]:<40}", end="\n" if i == n else "", file=sys.stderr, flush=True)


def cmd_commanders(a):
    import deckbuild
    conn = connect()
    _tags(conn, deckbuild)
    rank, pending = deckbuild.ranking(conn, progress=_edhrec_progress, only_cached=a.cached)
    n = deckbuild.mark_top10(conn, rank)  # immer aus dem Ranking nach Abdeckung, egal welcher Modus angezeigt wird
    mind = deckbuild.MODE_MIN_DECKS.get(a.mode, 0) if a.min_decks is None else a.min_decks
    print(deckbuild.format_ranking(deckbuild.rank_modes(conn, rank, a.mode, mind, sources.scryfall_names), pending, a.top))
    print(f"Top-10-Listen: {zahl(n)} Karten gelten im Sortier-Plan als Staple (doppelt behalten)")


def cmd_build(a):
    import deckbuild
    conn = connect()
    _tags(conn, deckbuild)
    d = deckbuild.build(conn, a.name, a.bracket, fetch_names=sources.scryfall_names, theme=a.theme)
    if a.save:
        d["id"] = deckbuild.save_deck(conn, d)
    print(deckbuild.export_text(d) if a.text else deckbuild.format_deck(d) + (f"\n  gespeichert als Deck {d['id']}" if a.save else ""))


def cmd_plan_decks(a):
    import deckbuild
    conn = connect()
    _tags(conn, deckbuild)
    decks = deckbuild.plan_decks(conn, a.count, a.bracket, a.save, fetch_names=sources.scryfall_names, progress=_edhrec_progress)
    print(f"Diese {len(decks)} Decks kannst du gleichzeitig bauen{' (gespeichert)' if a.save else ''}:")
    for d in decks:
        print(deckbuild.format_deck(d))


def format_movers(m):
    if not m["ready"]:
        return (f"Noch kein Preisverlauf ({m['span']} Tage): Bei jeder Preis-Aktualisierung merkt sich die App den Preis jeder Karte, "
                f"nach {MOVE_MIN_SPAN} Tagen stehen hier Veränderungen.")
    out = [f"Preisbewegung gegen den Stand von vor {m['days']} Tagen oder früher (ab {pct(MOVE_PCT)} Änderung, Karte ab {eur(MOVE_EUR)}):"]
    for titel, k in (("Gestiegen", "up"), ("Gefallen", "down")):
        out.append(f"{titel}:" + ("" if m[k] else " nichts"))
        out += [f"  {e['pct'] * 100:+.0f} %  {eur(e['old'])} → {eur(e['price'])}  {e['name']}{' (Foil)' if e['foil'] else ''} ×{e['qty']}" for e in m[k]]
    return "\n".join(out)


def cmd_movers(a):
    print(format_movers(movers(connect(), a.days)))


def cmd_gaps(a):
    import deckbuild
    g = deckbuild.gaps(connect(), a.top, fetch_names=sources.scryfall_names)
    if not g["commanders"]:
        print("Noch keine Commander-Daten: erst `mtg commanders`.")
        return 1
    print(f"Fehlt auf den Listen deiner {len(g['commanders'])} besten Commander ({', '.join(g['commanders'][:3])} …), nach Zahl der Listen:")
    for e in g["items"]:
        print(f"{e['n']:>2}×  {eur(e['price']) if e['price'] is not None else 'kein Preis':>9}  {e['name']}")


def cmd_bracket(a):
    import deckbuild
    print(deckbuild.format_bracket(deckbuild.bracket_check(read_text(Path(a.datei).read_bytes()), sources.spellbook_bracket)))


def cmd_missing(a):
    import deckbuild
    cmd, liste, summe = deckbuild.shopping_list(connect(), a.name, a.budget, fetch_names=sources.scryfall_names)
    print(f"Einkaufsliste für {cmd['name']} (Budget {eur(a.budget)}): {len(liste)} Karten, Summe {eur(summe)}")
    for m in liste:
        print(f"{m['w']:.2f}  {eur(m['price']):>9}  {m['name']}")


def cmd_decks(a):
    import deckbuild
    conn = connect()
    if a.id is None:
        for d in deckbuild.decks_list(conn):
            print(f"{d['id']:>3}  {d['name']} · Bracket {d['bracket']} · {d['cards']} Karten ({d['basics']} Basics) · {eur(d['value'])}")
        for d in deckbuild.binder_decks(conn):
            cmd = d["commander"]["name"] if d["commander"] else "Commander unbekannt"
            print(f"  –  {d['name']} (fertig, {cmd}) · {d['cards']} Karten · {eur(d['value'])}")
        return
    if a.delete:
        print("gelöscht" if deckbuild.delete_deck(conn, a.id) else "kein solches Deck")
        return
    d = deckbuild.deck_detail(conn, a.id)
    if not d:
        print("kein solches Deck")
        return 1
    print(deckbuild.export_text(d) if a.text else deckbuild.format_deck(d))


def _news(conn):
    import deckbuild
    z = sources.zustand()["quellen"]  # Phase 44: abgeschaltete Quellen fragt niemand, die Neuigkeiten aus Datenbank und Cache bleiben
    for k in ("edhrec", "spellbook"):
        if not z[k]:
            print(f"Hinweis: {sources.QUELLEN[k]['name']} ist abgeschaltet, dazu gibt es keine neuen Neuigkeiten.", file=sys.stderr)
    try:
        print(deckbuild.format_news(posteingang_news(conn) + deckbuild.news(conn, edhrec=sources.edhrec_commander if z["edhrec"] else None,
                                                                            spellbook=sources.spellbook_combos if z["spellbook"] else None) + deckbuild.radar_news(conn)))
    except urllib.error.URLError as e:
        print(f"Neuigkeiten: Netz nicht erreichbar ({e})", file=sys.stderr)


def cmd_news(a):
    _news(connect())


def cmd_sync(a):
    conn = connect()
    results, n = sync(conn, fetch=_fetch, archive=ARCHIVE, lookup=_lookup)
    for name, r in results:
        print(r if isinstance(r, str) else format_import(r))
    print(f"Preise aktualisiert: {zahl(n)} Karten")
    m = movers(conn)
    if m["up"]:
        print("Preise gestiegen: " + ", ".join(f"{e['name']} {e['pct'] * 100:+.0f} %" for e in m["up"][:3]) + " (mtg movers: alle)")
    _news(conn)
    return 1 if any(not isinstance(r, str) and r["status"] == "abgebrochen" for _, r in results) else 0


UI_PROZESS = re.compile(r"mtg\.py.*\sui(\s|$)")  # ponytail: jede Oberfläche (python … mtg.py … ui), auch aus einer anderen Kopie des Ordners


def _prozesse():
    """Laufende Python-Prozesse und Browser (Edge, Chrome: das App-Fenster, Phase 55) als [(pid, Befehlszeile)]: Windows über PowerShell, sonst ps."""
    import subprocess
    befehl = (["powershell", "-NoProfile", "-Command", "Get-CimInstance Win32_Process -Filter \"Name LIKE 'python%' OR Name = 'msedge.exe' OR Name = 'chrome.exe'\" | "
               "ForEach-Object { \"$($_.ProcessId) $($_.CommandLine)\" }"] if os.name == "nt" else ["ps", "-eo", "pid=,args="])
    out = subprocess.run(befehl, capture_output=True, text=True, errors="replace", check=False).stdout
    return [(int(p), rest) for p, _, rest in (z.strip().partition(" ") for z in out.splitlines()) if p.isdigit()]


def ui_stoppen(prozesse=_prozesse, warten=5.0):
    """Laufende Oberflächen beenden, egal auf welchem Port und auch ohne offenes Fenster, dazu ihr App-Fenster (Phase 55: der Browser mit dem
    Profil aus fenster_profil; bliebe er offen, ginge das Fenster eines neuen Starts in ihm auf, und der neue Server endete sofort). Wartet,
    bis alle weg sind. -> [(pid, port)] der Oberflächen"""
    laufend, profil = prozesse(), str(fenster_profil()).lower()
    ziele = [(pid, int(m.group(1)) if (m := re.search(r"--port[= ](\d+)", cl)) else 8765) for pid, cl in laufend
             if pid != os.getpid() and UI_PROZESS.search(cl)]
    fenster = [pid for pid, cl in laufend if "--app=" in cl and profil in cl.lower()]  # nur der Hauptprozess trägt --app, die übrigen enden mit ihm
    for pid in [pid for pid, _ in ziele] + fenster:
        try:
            os.kill(pid, signal.SIGTERM)  # Windows: sofort beendet; die Datenbank übersteht das (SQLite-Transaktionen)
        except OSError:
            pass  # schon weg, etwa zusammen mit dem Starter der venv
    offen, ende = {pid for pid, _ in ziele} | set(fenster), time.monotonic() + warten
    while offen and time.monotonic() < ende:
        offen &= {pid for pid, _ in prozesse()}
        if offen:
            time.sleep(0.3)
    return ziele


def cmd_stop(a):
    ports = sorted({port for _, port in ui_stoppen()})
    print(f"Oberfläche beendet (Port {', '.join(map(str, ports))})." if ports else "Es läuft keine Oberfläche.")


STARTER = f"{version.NAME} starten.cmd"
VERKNUEPFUNG_ALT = "MTG Commander.lnk"  # so hieß die Verknüpfung vor Phase 37 (PLAN E22); steht hier nur, um sie zu entfernen
# Je Ordner (Desktop, Startmenü): eine alte Verknüpfung entfernen, wenn sie ins Leere oder in diesen Ordner zeigt; die neue anlegen, wenn sie fehlt oder
# ins Leere zeigt, und neu schreiben, wenn sie in diesen Ordner zeigt, ihr Symbol aber nicht (Ordner umbenannt: Windows zieht nur das Ziel nach)
VERKNUEPFUNG = ("$w = New-Object -ComObject WScript.Shell; "
                "$ordner = if ($env:MTG_ORDNER) { $env:MTG_ORDNER -split ';' } else { 'Desktop', 'Programs' | ForEach-Object { [Environment]::GetFolderPath($_) } }; "
                "foreach ($d in $ordner) { "
                "$alt = Join-Path $d $env:MTG_ALT; "
                "if (Test-Path -LiteralPath $alt) { $t = $w.CreateShortcut($alt).TargetPath; "
                "if (-not $t -or -not (Test-Path -LiteralPath $t) -or (Split-Path -Parent $t) -eq $env:MTG_DIR) { Remove-Item -LiteralPath $alt; \"- $alt\" } }; "
                "$p = Join-Path $d $env:MTG_LNK; "
                "if (Test-Path -LiteralPath $p) { $s = $w.CreateShortcut($p); $t = $s.TargetPath; if ($t -and (Test-Path -LiteralPath $t) -and "
                "((Split-Path -Parent $t) -ne $env:MTG_DIR -or $s.IconLocation.StartsWith($env:MTG_ICON, [StringComparison]::OrdinalIgnoreCase))) { continue } }; "
                "$s = $w.CreateShortcut($p); $s.TargetPath = $env:MTG_ZIEL; $s.WorkingDirectory = $env:MTG_DIR; $s.IconLocation = $env:MTG_ICON; "
                "$s.WindowStyle = 7; $s.Description = $env:MTG_NAME; $s.Save(); \"+ $p\" }")


def cmd_verknuepfung(a, ordner=None):
    """Windows: Verknüpfung mit dem Namen der App und Kartensymbol (ui/mtg.ico) auf Desktop und Startmenü, startet den Starter minimiert; die alte
    Verknüpfung (VERKNUEPFUNG_ALT) verschwindet dabei. Nur wenn sie fehlt oder ins Leere zeigt (Ordner verschoben). ordner: statt Desktop und
    Startmenü diese Ordner (für Tests)."""
    # ponytail: eine gelöschte Verknüpfung kommt beim nächsten Start wieder; Merker in data/, falls das stört
    if os.name != "nt":
        return
    import subprocess
    pfad = Path(__file__).resolve().parent
    env = os.environ | {"MTG_ZIEL": str(pfad / STARTER), "MTG_DIR": str(pfad), "MTG_ICON": str(pfad / "ui" / "mtg.ico"),
                        "MTG_LNK": f"{version.NAME}.lnk", "MTG_ALT": VERKNUEPFUNG_ALT, "MTG_NAME": version.NAME}
    if ordner:
        env["MTG_ORDNER"] = ";".join(map(str, ordner))
    out = subprocess.run(["powershell", "-NoProfile", "-Command", VERKNUEPFUNG], env=env, capture_output=True, text=True, errors="replace", check=False).stdout
    for z in out.splitlines():
        print(f"Verknüpfung {'angelegt' if z.startswith('+') else 'entfernt'}: {z[2:]}")


FENSTER_BROWSER = ("Microsoft/Edge/Application/msedge.exe", "Google/Chrome/Application/chrome.exe")  # können --app; Edge hat jedes Windows (im EWR entfernbar)


def fenster_profil():
    """Eigenes Browser-Profil des App-Fensters (Phase 55), neben der Sammlung; steht nicht in der Sicherung."""
    return Path(DB).parent / "fenster"


def fenster_browser(basen=None):
    """Edge oder Chrome für das App-Fenster, gesucht in den Programmordnern von Windows. -> Pfad oder None (auch außerhalb von Windows)"""
    basen = [os.environ.get(v) for v in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA")] if basen is None else basen
    return next((str(p) for rel in FENSTER_BROWSER for b in basen if b and (p := Path(b) / rel).is_file()), None)


def _ui_im_hintergrund(a):
    """mtg ui --fenster ohne schwarzes Fenster: dieselbe Oberfläche noch einmal starten, ohne Konsole (Ausgaben nach data/fenster.log), und
    sofort zurück, damit sich der Starter schließt. Ist der Port belegt, sagt es dieses Fenster, statt dass still nichts aufgeht."""
    import socket
    import subprocess
    with socket.socket() as s:
        try:
            s.bind((a.host, a.port))
        except OSError as e:
            print(f"Port {a.port} nicht nutzbar: {e}", file=sys.stderr)
            return 2
    argv = [*(["--konto", a.konto] if a.konto else []), "ui", "--fenster", "--port", str(a.port), "--host", a.host,
            *(["--no-daily"] if a.no_daily else []), *(["--log"] if a.log else [])]
    fenster_profil().parent.mkdir(parents=True, exist_ok=True)
    with open(fenster_profil().parent / "fenster.log", "w", encoding="utf-8") as log:
        subprocess.Popen([sys.executable, str(Path(__file__).resolve()), *argv], stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                         env=os.environ | {"MTG_IM_HINTERGRUND": "1", "PYTHONIOENCODING": "utf-8"},
                         creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    print(f"{version.NAME} öffnet sich in einem eigenen Fenster.")
    return 0


def cmd_ui(a):
    import server  # erst hier, server importiert mtg
    fenster = None
    if a.fenster:
        exe = fenster_browser()
        if not exe:
            print("Kein Edge und kein Chrome gefunden: Die Seite öffnet sich im Browser, dieses Fenster offen lassen.", file=sys.stderr)
        elif not os.environ.get("MTG_IM_HINTERGRUND"):
            return _ui_im_hintergrund(a)
        else:
            fenster = [exe, f"--user-data-dir={fenster_profil()}", "--no-first-run", "--no-default-browser-check"]
    try:
        return server.serve(a.port, not a.no_open, a.host, not a.no_daily, a.log, fenster)
    except OSError as e:
        print(f"Port {a.port} nicht nutzbar: {e}", file=sys.stderr)
        return 2


def cmd_suche(a):
    import server  # erst hier, server importiert mtg
    conn = connect()
    r = server.api_cards(conn, {"q": a.text, "sort": "price", "per_page": str(a.top)})
    for h in r["hinweise"]:
        print(f"Hinweis: {h}", file=sys.stderr)
    print(f"{zahl(r['total'])} Karten ({zahl(r['copies'])} Exemplare){', die teuersten ' + str(len(r['items'])) if r['total'] > len(r['items']) else ''}:")
    for c in r["items"]:
        print(f"{eur(c['price']):>10}  {c['qty']}×  {c['name']} ({c['set']})")
    return 0 if r["total"] else 1


def cmd_dossier(a):
    import deckbuild
    if a.datei:
        print(f"Dossier gespeichert: {deckbuild.dossier_speichern(a.commander, Path(a.datei).read_text(encoding='utf-8'))}")
    else:
        print(deckbuild.dossier(a.commander) or f"Kein Dossier zu {a.commander} (Skill mtg-recherche legt eins an).")


def cmd_radar(a):
    import deckbuild
    if a.datei:
        print(f"Radar gespeichert: {deckbuild.radar_speichern(json.loads(Path(a.datei).read_text(encoding='utf-8')), a.tag)}")
    print(deckbuild.format_news(deckbuild.radar_news(connect())))


def cmd_undo(a):
    u = undo_import(connect())
    print(f"Rückgängig: Import „{u['file']}“ vom {u['at'][:10]} (+{zahl(u['added'])} / −{zahl(u['removed'])} Karten), "
          f"{'die ganze Sammlung' if u['scope'] == '*' else u['scope']} wieder auf dem Stand davor")


def cmd_beispiel(a):
    conn = connect()
    if a.weg:
        n = beispiel_entfernen(conn)
        print(f"Beispielsammlung entfernt ({zahl(n)} Karten). Sonst ist nichts geändert.")
        return 0
    if beispiel_marker(conn):
        i = beispiel_info(conn)
        print(f"Die Beispielsammlung liegt schon da ({zahl(i['karten'])} Karten in {', '.join(i['binder'])}). Entfernen: mtg beispiel --weg")
        return 0
    r = beispiel_laden(conn, _fetch, _lookup)
    print(f"Beispielsammlung geladen: {zahl(r['karten'])} Karten im Binder „{BEISPIEL_BINDER}“ und das Deck „{BEISPIEL_DECK}“ ({zahl(r['deck'])} Karten). "
          f"Entfernen: mtg beispiel --weg")
    if r["unbekannt"] or r["fehlend"]:
        print(f"  Bei Scryfall nicht gefunden: {zahl(len(r['unbekannt']) + len(r['fehlend']))} Einträge")
    return 0


def cmd_uebernehmen(a):
    import konten
    conn = connect()
    n = uebernahme_pruefen(conn, a.binder)
    ziel = konten.sicherung_vor("uebernahme")
    binder_uebernehmen(conn, a.binder)
    print(f"„{a.binder}“ führt jetzt die App ({zahl(n)} Karten). Sicherung davor: {ziel}")
    print("Diesen Binder in ManaBox nicht mehr ändern: Ein Export mit ihm wird ab jetzt übersprungen. Neue Karten: Scannen, Erfassen.")


def cmd_katalog(a):
    pfad = katalog_pfad()
    if a.neu:
        t = time.monotonic()
        with closing(connect()) as conn:
            kuerzel = katalog.kandidaten(sets_info(conn))
        katalog.bauen(sources.scryfall_bulk(), pfad, kuerzel)
        print(f"Katalog neu geladen in {time.monotonic() - t:.0f} s")
    if a.namen:
        t = time.monotonic()
        n = katalog.namen_bauen(sources.scryfall_bulk("all_cards"), pfad)
        print(f"{zahl(n)} deutsche Kartennamen geladen in {time.monotonic() - t:.0f} s")
    s = katalog.stand(pfad)
    print(f"Katalog: {zahl(s['drucke'])} Papier-Drucke, {zahl(s['aussehen'])} Aussehen, {zahl(len(s['sets']))} Sets, {s['bytes'] / 1e6:.0f} MB, "
          f"Stand {s['gebaut']} ({pfad})" if s else "Noch kein Katalog. Die Oberfläche lädt ihn, sobald jemand unter Scannen „Erfassen“ öffnet; sofort geht es mit: mtg katalog --neu")
    if s:
        f = katalog.fp_stand(pfad)
        print(f"Erkennung ohne Set-Wahl: {zahl(f['fertig'])} von {zahl(f['gesamt'])} Bildern vorbereitet (in der Oberfläche unter Scannen, Erfassen)")
        n = katalog.namen_stand(pfad)
        print(f"Namen lesen: {zahl(n['zahl'])} deutsche Kartennamen, Stand {n['gebaut']}" if n else "Namen lesen: noch keine deutschen Kartennamen (Schalter „Deutsche Kartennamen laden“ in den Einstellungen des Scanners, sofort: mtg katalog --namen)")


def cmd_backup(a):
    import konten
    ziel = Path(a.ziel) if a.ziel else konten.daten() / "sicherungen" / f"mtg-{datetime.now():%Y-%m-%d-%H%M%S}.zip"
    ziel.parent.mkdir(parents=True, exist_ok=True)
    print(f"Sicherung: {ziel} ({konten.sicherung(ziel)} Datenbanken)")


def cmd_wiederherstellen(a):
    """Sicherung zurückspielen (PLAN E30): erst zeigen, was in ihr steckt und was sie ersetzt, dann fragen (--ja: ohne Frage). Geprüft und
    getauscht wird in konten.zurueckspielen; --dry-run prüft nur (konten.pruefen) und schreibt im Datenordner nichts."""
    import konten

    def zeile(s):
        return (f"  {s['konto'] or 'Sammlung':<20} " + (f"{zahl(s['karten']):>7} Karten {eur(s['wert']):>13}" if s["karten"] is not None else
                                                           "Karten und Wert unbekannt (in Benutzung, oder ein Programm wurde hart beendet)"))

    def zeigen(info):
        print(f"Sicherung {info['datei']} vom {info['datum']}:")
        print("  Konten: " + (", ".join(f"{k['name']} ({'Hauptkonto' if k['rolle'] == 'haupt' else 'Unterkonto'}, {'mit' if k['pw'] else 'ohne'} "
                                        f"Passwort)" for k in info["konten"]) or "keine (eine Sammlung, ohne Anmeldung)"))
        for s in info["sammlungen"]:
            print(zeile(s) + (f", {zahl(s['importe'])} archivierte{' Importe' if s['importe'] > 1 else 'r Import'}" if s["importe"] else ""))
        print(f"Ersetzt in {info['ordner']}:" + ("" if info["jetzt"] or info["konten_jetzt"] else " nichts, dort liegt noch keine Sammlung"))
        if info["jetzt"] or info["konten_jetzt"]:
            print("  Konten: " + (", ".join(info["konten_jetzt"]) or "keine"))
        for s in info["jetzt"]:
            print(zeile(s) + ("" if s["drin"] else ", steckt nicht in der Sicherung und entfällt") + ("" if s["gesichert"] else
                  ", gehört zu keinem Konto und wird aufgehoben, nicht gesichert"))
        if info["bleibt"]:
            print("Bleibt liegen: " + ", ".join(info["bleibt"]))
        if info["jetzt"]:
            print("Der jetzige Stand kommt vorher nach sicherungen/vor-wiederherstellung-….zip und lässt sich mit diesem Befehl zurückholen.")
        if info["stand"] < STAND:
            print(f"Die Sicherung hat Stand {info['stand']}: Die App stellt sie beim nächsten Start auf Stand {STAND} um, mit Sicherung davor.")
        if info["laeuft"]:
            print("Die App läuft gerade. Zurückgespielt wird nur, wenn sie beendet ist.")

    def fragen(info):
        zeigen(info)
        if a.ja:
            return True
        try:
            return input("Zurückspielen? [j/N] ").strip().lower() in ("j", "ja")
        except EOFError:  # keine Eingabe möglich (Skript, Container ohne Terminal): dann nur mit --ja
            return False

    if a.dry_run:
        zeigen(konten.pruefen(a.datei))
        print("Probelauf: Die Sicherung ist in Ordnung, geändert ist nichts.")
        return 0
    try:
        info = konten.zurueckspielen(a.datei, fragen)
    except konten.NichtZurueck as e:
        print(f"Fehler: {e}", file=sys.stderr)
        return 3
    if info is None:
        print("Nicht zurückgespielt, nichts geändert (ohne Rückfrage: --ja).")
        return 1
    print(f"Zurückgespielt: {len(info['sammlungen'])} {'Sammlung' if len(info['sammlungen']) == 1 else 'Sammlungen'}, "
          f"{zahl(sum(s['karten'] for s in info['sammlungen']))} Karten, Stand vom {info['datum']}.")
    if info["sicherung"]:
        print(f"Der Stand davor: {info['sicherung']}")
    if info["rest"]:
        print(f"Nicht in der Sicherung des Stands davor und deshalb aufgehoben: {info['rest']}")
    return 0


def _passwort(a):
    """Passwort aus MTG_PASSWORT (Docker, Skripte) oder zweimal eingeben; None = ohne Passwort."""
    if getattr(a, "ohne_passwort", False):
        return None
    if os.environ.get("MTG_PASSWORT"):
        return os.environ["MTG_PASSWORT"]
    import getpass
    pw = getpass.getpass("Passwort: ")
    if pw != getpass.getpass("Noch einmal: "):
        raise ValueError("Die Passwörter sind verschieden")
    return pw


def cmd_konto(a):
    import konten
    conn = konten.connect()
    if a.aktion == "list":
        for k in konten.liste(conn):
            print(f"{k['name']:<20} {'Hauptkonto' if k['rolle'] == 'haupt' else 'Unterkonto'} · {'mit' if k['pw'] else 'ohne'} Passwort · {k['db']}")
        print(f"Modus: {konten.modus()}")
        return
    if not a.name:
        raise ValueError("Name fehlt, z. B. mtg konto add betreiber --haupt")
    if a.aktion == "add":
        n = konten.anlegen(conn, a.name, _passwort(a), a.haupt)
        print(f"Konto „{n}“ angelegt ({'Hauptkonto' if a.haupt else 'Unterkonto'}, Sammlung {konten.db_pfad(n, 'haupt' if a.haupt else 'unter')})")
    elif a.aktion == "passwort":
        konten.passwort(conn, konten.kurz(a.name), _passwort(a))
        print("Passwort geändert, alte Anmeldungen gelten nicht mehr")
    elif a.aktion == "del":
        konten.entfernen(conn, konten.kurz(a.name))
        print("Konto entfernt, seine Datenbank bleibt liegen")


def cmd_einrichtung(a):
    """Den Einrichtungs-Code zeigen (PLAN E28): Er entsteht, wenn die Oberfläche ohne Hauptkonto auf einer anderen Adresse als 127.0.0.1
    startet, steht einmal in deren Protokoll und gilt bis zum ersten Hauptkonto. Der Befehl liest ihn nur."""
    import konten
    if konten.modus() != "einfach":
        print("Die Einrichtung ist abgeschlossen: Es gibt ein Hauptkonto (mtg konto list). Ein Einrichtungs-Code gilt nicht mehr.")
        return 0
    code = konten.einrichtung_code()
    if not code:
        print("Kein Einrichtungs-Code offen. Er entsteht, wenn die Oberfläche ohne Hauptkonto auf einer anderen Adresse als 127.0.0.1 startet "
              "(Docker, mtg ui --host 0.0.0.0). Am eigenen Rechner geht es ohne: „Konten und Sicherung“ oder mtg konto add NAME --haupt.")
        return 1
    print(f"Einrichtung: Code {code}")
    print("Im Browser auf der Einrichtungsseite eingeben. Er gilt, bis das Hauptkonto angelegt ist.")
    return 0


def _konto_waehlen(name):
    """CLI für die Sammlung eines anderen Kontos: Datenbank, Archiv und inbox/ liegen dann in dessen Ordner."""
    global DB, ARCHIVE, INBOX
    import konten
    if not konten.pfad().exists():
        raise ValueError("Es gibt noch keine Konten (mtg konto add NAME --haupt)")
    k = konten.konto(konten.connect(), konten.kurz(name))
    if not k:
        raise ValueError(f"Kein Konto „{name}“ (mtg konto list)")
    DB = konten.db_pfad(k["name"], k["rolle"])
    if k["rolle"] != "haupt":
        ARCHIVE, INBOX = DB.parent / "imports", DB.parent / "inbox"


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser(prog="mtg", description=f"{version.NAME} – Sammlung, Sortier-Plan, Deckbau.")
    p.add_argument("--version", action="version", version=f"{version.NAME} {version.VERSION}")
    p.add_argument("--konto", help="Sammlung eines Unterkontos statt der eigenen (siehe mtg konto list)")
    sub = p.add_subparsers(dest="cmd")
    s = sub.add_parser("import", help="Datei importieren: ManaBox-CSV, CSV anderer Apps oder Deckliste (Schnappschuss)")
    s.add_argument("csv", help="Datei (.csv oder .txt)")
    s.add_argument("--binder", help="Binder- bzw. Deckname (sonst Dateiname)")
    s.add_argument("--commander", help="Commander einer Deckliste (sonst aus // COMMANDER)")
    s.add_argument("--dry-run", action="store_true", help="nur Diff zeigen")
    s.add_argument("--force", action="store_true", help="auch bei mehr als 25%% Verlust")
    sub.add_parser("prices", help="Preise neu laden (älter als 24 h)")
    sub.add_parser("stats", help="Karten, Unikate, Wert, Top 10")
    s = sub.add_parser("card", help="Besitz, Preis und Text einer Karte")
    s.add_argument("name")
    s = sub.add_parser("sell", help="Verkaufsliste: Top 30 und Summe, dazu Bulk")
    s.add_argument("--min", type=float, help="Mindestpreis für Einzelverkauf in Euro (sonst Regel, Standard 1)")
    s = sub.add_parser("rules", help="Regeln des Sortier-Plans zeigen oder ändern")
    s.add_argument("--keep", type=int, help="Kopien je Karte behalten (Standard 1)")
    s.add_argument("--staples", type=int, help="Kopien je Staple behalten (Standard 2)")
    s.add_argument("--min", type=float, help="ab diesem Preis einzeln verkaufen, darunter Bulk (Standard 1)")
    s = sub.add_parser("commanders", help="Commander nach Abdeckung (lädt EDHREC, erster Lauf dauert)")
    s.add_argument("--top", type=int, default=20)
    s.add_argument("--cached", action="store_true", help="nur schon geladene Daten")
    s.add_argument("--mode", choices=("machbar", "beliebt", "geheimtipp", "guenstig"), default="machbar",
                   help="machbar: Abdeckung (Standard) · beliebt: meiste EDHREC-Decks · geheimtipp: gut machbar, wenig gespielt · guenstig: kleinster Zukauf")
    s.add_argument("--min-decks", type=int, help="nur Commander mit so vielen EDHREC-Decks (Standard 0, bei geheimtipp 30)")
    s = sub.add_parser("build", help="Deck aus der Sammlung bauen")
    s.add_argument("name", help="Commander")
    s.add_argument("--bracket", type=int, default=3, help="1-5, Standard 3")
    s.add_argument("--theme", default="auto", help="EDHREC-Thema, z. B. Landfall (Standard auto: das gängige Thema mit der besten Abdeckung; none: allgemeine Liste)")
    s.add_argument("--save", action="store_true", help="Deck speichern, Karten gelten dann als verplant")
    s.add_argument("--text", action="store_true", help="Textliste für Moxfield/Archidekt ausgeben")
    s = sub.add_parser("plan-decks", help="Mehrere Decks gleichzeitig planen")
    s.add_argument("--count", type=int, default=5)
    s.add_argument("--bracket", type=int, default=3)
    s.add_argument("--save", action="store_true")
    s = sub.add_parser("movers", help="Preisbewegung der Karten im Besitz (gestiegen und gefallen)")
    s.add_argument("--days", type=int, default=MOVE_DAYS, help="Vergleich gegen vor so vielen Tagen (Standard 14)")
    s = sub.add_parser("gaps", help="Karten, die auf den Listen mehrerer deiner besten Commander stehen und dir fehlen")
    s.add_argument("--top", type=int, default=10, help="so viele beste Commander vergleichen (Standard 10)")
    s = sub.add_parser("bracket", help="Bracket einer Deckliste (Textdatei) über Commander Spellbook einschätzen")
    s.add_argument("datei", help="Deckliste als Textdatei")
    s = sub.add_parser("missing", help="Einkaufsliste für einen Commander")
    s.add_argument("name")
    s.add_argument("--budget", type=float, default=20.0, help="Euro, Standard 20")
    s = sub.add_parser("decks", help="Gespeicherte Decks auflisten, anzeigen, exportieren, löschen")
    s.add_argument("id", nargs="?", type=int)
    s.add_argument("--text", action="store_true")
    s.add_argument("--delete", action="store_true")
    sub.add_parser("news", help="Neuigkeiten zum letzten Import: Upgrades, neue Commander, Verkäufe, Combos")
    sub.add_parser("sync", help="inbox/ (CSVs und Decklisten) importieren, Preise auffrischen, Neuigkeiten (beliebig oft ausführbar)")
    s = sub.add_parser("ui", help="Oberfläche starten (Standard nur 127.0.0.1)")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--host", default="127.0.0.1", help="z. B. 0.0.0.0 auf dem Server (ohne Hauptkonto: Einrichtung im Browser mit dem Code aus dem Protokoll)")
    s.add_argument("--no-open", action="store_true", help="Browser nicht öffnen")
    s.add_argument("--fenster", action="store_true", help="eigenes Fenster (Windows, Edge oder Chrome) ohne Konsole; schließt es, endet die Oberfläche")
    s.add_argument("--no-daily", action="store_true", help="kein täglicher Lauf (Preise, Wertverlauf, Sicherung)")
    s.add_argument("--log", action="store_true", help="jede Anfrage protokollieren (Zeit, Adresse, Methode, Pfad, Status, Dauer); auf einer anderen Adresse als 127.0.0.1 ohnehin an")
    sub.add_parser("undo", help="Letzten Import rückgängig machen")
    s = sub.add_parser("beispiel", help="Beispielsammlung zum Ausprobieren laden (nur in einer leeren Sammlung, einmal Netz zu Scryfall) oder mit --weg entfernen")
    s.add_argument("--weg", action="store_true", help="die Beispielsammlung restlos entfernen (sonst bleibt alles, wie es ist)")
    s = sub.add_parser("uebernehmen", help="ManaBox-Binder in die App übernehmen: ab dann ein Scan-Binder ohne ManaBox (Sicherung davor)")
    s.add_argument("binder")
    sub.add_parser("stop", help="Laufende Oberfläche beenden (jede, egal auf welchem Port; neu starten mit dem Starter der App)")
    sub.add_parser("verknuepfung", help="Windows: Verknüpfung mit dem Namen der App und Kartensymbol auf Desktop und Startmenü (macht der Starter selbst)")
    s = sub.add_parser("dossier", help="Recherche-Dossier zu einem Commander zeigen oder speichern (Skill mtg-recherche)")
    s.add_argument("commander")
    s.add_argument("datei", nargs="?", help="Markdown-Datei mit festen Abschnitten und Quellen")
    s = sub.add_parser("radar", help="Markt-Radar gegen den Bestand zeigen oder speichern (JSON, Skill mtg-recherche)")
    s.add_argument("datei", nargs="?", help="JSON-Liste [{name, richtung, grund, quelle}]")
    s.add_argument("--tag", help="Datum der Recherche (JJJJ-MM-TT), Standard heute")
    s = sub.add_parser("suche", help="Sammlung durchsuchen: t:vampire c:r mv<=3, o:\"draw a card\", id:bg otag:ramp, fn:landfall, is:foil, -, or, (…)")
    s.add_argument("text")
    s.add_argument("--top", type=int, default=30)
    s = sub.add_parser("katalog", help="Katalog aller Papier-Drucke (Scryfall-Gesamtdaten, data/katalog.db): Stand zeigen")
    s.add_argument("--neu", action="store_true", help="jetzt neu laden (rund 75 MB von Scryfall; sonst macht das die Oberfläche, wenn jemand erfasst)")
    s.add_argument("--namen", action="store_true", help="deutsche Kartennamen jetzt laden (rund 378 MB von Scryfall; fürs Lesen des Namens beim Scannen, die Oberfläche lädt sie nur mit dem Schalter)")
    s = sub.add_parser("backup", help="Sicherung aller Sammlungen als ZIP (Standard data/sicherungen/)")
    s.add_argument("ziel", nargs="?")
    s = sub.add_parser("wiederherstellen", help="Sicherung (ZIP) zurückspielen: ersetzt Konten und alle Sammlungen, nur bei beendeter App; "
                                                "prüft die ZIP und sichert vorher den jetzigen Stand")
    s.add_argument("datei", help="die ZIP aus „Konten und Sicherung“, aus data/sicherungen/ oder von mtg backup")
    s.add_argument("--dry-run", action="store_true", help="nur prüfen und zeigen, was ersetzt würde")
    s.add_argument("--ja", action="store_true", help="nicht nachfragen")
    sub.add_parser("einrichtung", help="Einrichtungs-Code zeigen (Server ohne Hauptkonto: damit legt man es im Browser an oder spielt eine Sicherung ein)")
    s = sub.add_parser("konto", help="Konten: Hauptkonto und Unterkonten mit eigener Sammlung (Login für den Server)")
    s.add_argument("aktion", choices=("list", "add", "passwort", "del"))
    s.add_argument("name", nargs="?")
    s.add_argument("--haupt", action="store_true", help="beim Anlegen: das Hauptkonto (sieht alle Sammlungen)")
    s.add_argument("--ohne-passwort", action="store_true", help="ohne Passwort (Unterkonto, das nur das Hauptkonto verwaltet; Hauptkonto: kein Login)")
    a = p.parse_args(argv)
    if not a.cmd:
        p.print_help()
        return 0
    try:
        if a.konto and a.cmd not in ("ui", "backup", "wiederherstellen", "konto", "einrichtung", "stop", "verknuepfung"):  # die arbeiten mit allen Sammlungen
            _konto_waehlen(a.konto)
        return {"import": cmd_import, "prices": cmd_prices, "stats": cmd_stats, "card": cmd_card, "sell": cmd_sell, "rules": cmd_rules, "ui": cmd_ui,
                "news": cmd_news, "sync": cmd_sync, "movers": cmd_movers, "gaps": cmd_gaps, "bracket": cmd_bracket, "undo": cmd_undo, "beispiel": cmd_beispiel,
                "backup": cmd_backup, "wiederherstellen": cmd_wiederherstellen, "katalog": cmd_katalog, "konto": cmd_konto, "einrichtung": cmd_einrichtung, "uebernehmen": cmd_uebernehmen, "suche": cmd_suche, "dossier": cmd_dossier, "radar": cmd_radar, "stop": cmd_stop, "verknuepfung": cmd_verknuepfung,
                "commanders": cmd_commanders, "build": cmd_build, "plan-decks": cmd_plan_decks, "missing": cmd_missing, "decks": cmd_decks}[a.cmd](a) or 0
    except (urllib.error.URLError, ValueError, FileNotFoundError, PermissionError, EOFError) as e:  # EOFError: gzip-Strom abgebrochen (Katalog)
        print(f"Fehler: {e} – nichts geändert.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
