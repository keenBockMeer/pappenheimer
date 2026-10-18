"""HTTP-Server: ui/ statisch + JSON unter /api/. Ohne Konten nur 127.0.0.1; mit Hauptkonto und Passwort auch auf dem eigenen Server
(PLAN E13, E14). Die api_*-Funktionen laufen ohne Server (Tests)."""
import base64
import csv
import gzip
import hashlib
import http.cookies
import io
import ipaddress
import json
import mimetypes
import os
import re
import secrets
import shlex
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import webbrowser
from contextlib import closing
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import deckbuild
import katalog
import konten
import llm
import mtg
import qr
import sources
import suche
import version

UI = Path(__file__).parent / "ui"
PORT = 8765
MAX_IMPORT = 20 * 1024 * 1024
PER_PAGE = 120
SORT_PER_PAGE = 200
SELL_MAX_ROWS = 1000
ARCHIVE = mtg.ARCHIVE
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".svg": "image/svg+xml", ".ico": "image/x-icon", ".woff2": "font/woff2", ".txt": "text/plain; charset=utf-8",
         ".png": "image/png", ".webmanifest": "application/manifest+json"}  # Web-App fürs Handy (Phase 27)
# Farb-Eimer wie im Mockup: eine Farbe, Mehrfarbig, Farblos (inkl. Länder und Tokens)
BUCKET = ("CASE WHEN c.type_line LIKE '%Land%' OR c.color_identity = '' THEN 'C' "
          "WHEN length(c.color_identity) = 1 THEN c.color_identity ELSE 'M' END")
COLORS = [("W", "Weiß"), ("U", "Blau"), ("B", "Schwarz"), ("R", "Rot"), ("G", "Grün"), ("M", "Mehrfarbig"), ("C", "Farblos")]
# Serienname und Erscheinungsdatum stehen nur im Scryfall-JSON. Ein Vertreter je Serie (kleinste scryfall_id, bleibt bei Preis-Updates
# gleich) genügt und erspart das Parsen aller Karten. Als Join im Teil-Select, damit SQLite die Abfrage nicht in die Hauptabfrage
# faltet und das JSON je Sammlungszeile neu liest (gemessen: 450 statt 120 ms bei 8.000 Drucken).
SET_META = ("SELECT m.set_code, json_extract(s.json, '$.set_name') AS set_name, json_extract(s.json, '$.released_at') AS released "
            "FROM (SELECT set_code, MIN(scryfall_id) AS id FROM cards GROUP BY set_code) m JOIN cards s ON s.scryfall_id = m.id")
# nach Serie: neueste zuerst bzw. A–Z, innerhalb der Serie nach Sammlernummer ("2" vor "10", "17s" nach "17")
SET_SORTS = {"set": "released DESC, set_name COLLATE NOCASE, set_code, CAST(number AS INTEGER), number, name COLLATE NOCASE",
             "setaz": "set_name COLLATE NOCASE, set_code, CAST(number AS INTEGER), number, name COLLATE NOCASE"}
SORTS = {"name": "name COLLATE NOCASE", "price": "price DESC, name COLLATE NOCASE", "qty": "total DESC, name COLLATE NOCASE",
         "added": "last_added DESC, name COLLATE NOCASE", "rank": "rank IS NULL, rank, name COLLATE NOCASE", **SET_SORTS}
SETS_SORTS = {"new": "released DESC, name COLLATE NOCASE, code", "added": "last_added DESC, name COLLATE NOCASE, code",
              "name": "name COLLATE NOCASE, code", "cards": "copies DESC, name COLLATE NOCASE, code", "value": "value DESC, name COLLATE NOCASE, code"}


def api_cards(conn, q, plan_rows=None):
    """Galerie: eine Kachel je Karte (oracle_id), Bild und Preis vom teuersten Druck, Menge über alle Drucke.
    Mit Serienfilter (set=KÜRZEL) oder Sortierung nach Serie zählt jeder Druck für sich: sonst fiele dieselbe Karte aus mehreren Serien
    unter die Serie ihres teuersten Drucks. Nur dann sind set_name und der Join auf SET_META dabei (sonst set_name None)."""
    where, args = [mtg.OWNED], []
    je_druck = bool(q.get("set")) or q.get("sort") in SET_SORTS
    gruppe = "c.scryfall_id" if je_druck else "c.oracle_id"
    if je_druck:
        verbund, set_name, released = f"LEFT JOIN ({SET_META}) sm ON sm.set_code = c.set_code", "COALESCE(sm.set_name, c.set_code)", "sm.released"
    else:
        verbund, set_name, released = "", "NULL", "NULL"
    stapel = mtg.stacks_by_card(mtg.plan(conn) if plan_rows is None else plan_rows)
    if q.get("status") in mtg.STACKS:
        where.append("c.oracle_id IN (SELECT value FROM json_each(?))")
        args.append(json.dumps([o for o, st in stapel.items() if st[q["status"]]]))
    hinweise = []
    if q.get("q") and suche.ist_syntax(q["q"]):  # Suchsyntax (Phase 18): t:, o:, c:, id:, mv, r:, set:, lang:, is:, otag:, fn:, eur, -, or, Klammern
        suche.registrieren(conn)
        sql_, p, hinweise = suche.sql(q["q"], mtg.PRICE)
        where.append(f"({sql_})")
        args += p
    elif q.get("q"):
        where.append("c.name LIKE ?")
        args.append(f"%{q['q']}%")
    if q.get("fn"):  # Funktion wie beim Deckbau (Landfall, Spielsteine …), am Kartentext erkannt
        suche.registrieren(conn)
        where.append("funktion(c.oracle_text, c.type_line, ?)")
        args.append(q["fn"])
    farben = [x for x in q.get("color", "").split(",") if x in "WUBRGMC" and x]
    if farben:
        where.append(f"{BUCKET} IN ({','.join('?' * len(farben))})")
        args += farben
    if q.get("set"):
        where.append("c.set_code = ?")
        args.append(q["set"].upper())
    for feld, spalte in (("type", "c.type_line LIKE ?"), ("rarity", "c.rarity = ?"), ("binder", "col.binder = ?")):
        if q.get(feld):
            where.append(spalte)
            args.append(f"%{q[feld]}%" if feld == "type" else q[feld])
    mind = ""
    if q.get("min"):
        mind = " AND price >= ?"
        args.append(float(q["min"]))
    cte = (f"WITH r AS (SELECT c.oracle_id, c.name, c.image_url AS image, c.set_code, c.number, {set_name} AS set_name, "
           f"{released} AS released, c.rarity, c.type_line, c.mana_cost, c.edhrec_rank AS rank, col.foil, {mtg.PRICE} AS price, "
           f"ROW_NUMBER() OVER (PARTITION BY {gruppe} ORDER BY {mtg.PRICE} DESC, col.added DESC) AS rn, "
           f"SUM(col.qty) OVER (PARTITION BY {gruppe}) AS total, MAX(col.added) OVER (PARTITION BY {gruppe}) AS last_added "
           f"FROM collection col JOIN cards c USING (scryfall_id) {verbund} WHERE {' AND '.join(where)}) ")
    n, exemplare = conn.execute(cte + f"SELECT COUNT(*), COALESCE(SUM(total), 0) FROM r WHERE rn = 1{mind}", args).fetchone()
    pro = max(1, min(int(q.get("per_page") or PER_PAGE), PER_PAGE))
    seite = max(1, int(q.get("page") or 1))
    treffer = conn.execute(cte + f"SELECT * FROM r WHERE rn = 1{mind} ORDER BY {SORTS.get(q.get('sort'), SORTS['name'])} LIMIT ? OFFSET ?",
                           args + [pro, (seite - 1) * pro]).fetchall()
    leer = {"deck": [], "keep": 0, "sell": 0, "bulk": 0}
    items = [{"oracle_id": r["oracle_id"], "name": r["name"], "image": r["image"], "set": r["set_code"], "set_name": r["set_name"],
              "number": r["number"], "rarity": r["rarity"],
              "type": r["type_line"], "mana_cost": r["mana_cost"], "rank": r["rank"], "foil": r["foil"] != "normal",
              "price": r["price"], "qty": r["total"], "added": r["last_added"], "stacks": stapel.get(r["oracle_id"], leer)}
             for r in treffer]
    return {"items": items, "total": n, "copies": exemplare, "page": seite, "per_page": pro, "pages": max(1, -(-n // pro)), "hinweise": hinweise}


def api_sets(conn, q):
    """Serien im Besitz (alle Binder, ohne Wunschlisten): verschiedene Drucke, Exemplare, Wert, zuletzt hinzugefügt und das Bild
    des teuersten Drucks. q = Suchtext (Serienname oder Kürzel), sort = new|added|name|cards|value."""
    where, args = [mtg.OWNED], []
    if q.get("q"):
        where.append("(COALESCE(sm.set_name, c.set_code) LIKE ? OR c.set_code LIKE ?)")
        args += [f"%{q['q']}%"] * 2
    treffer = conn.execute(
        f"WITH r AS (SELECT c.set_code AS code, COALESCE(sm.set_name, c.set_code) AS name, sm.released, c.scryfall_id, c.image_url AS image, "
        f"col.qty, col.added, {mtg.PRICE} AS price, "
        f"ROW_NUMBER() OVER (PARTITION BY c.set_code ORDER BY {mtg.PRICE} DESC, c.scryfall_id) AS rn "
        f"FROM collection col JOIN cards c USING (scryfall_id) LEFT JOIN ({SET_META}) sm ON sm.set_code = c.set_code "
        f"WHERE {' AND '.join(where)}) "
        f"SELECT code, name, released, COUNT(DISTINCT scryfall_id) AS prints, SUM(qty) AS copies, SUM(qty * price) AS value, "
        f"MAX(added) AS last_added, MAX(CASE WHEN rn = 1 THEN image END) AS image FROM r GROUP BY code "
        f"ORDER BY {SETS_SORTS.get(q.get('sort'), SETS_SORTS['new'])}", args).fetchall()
    items = [dict(r) for r in treffer]
    groesse = mtg.sets_info(conn)
    for i in items:  # Set-Stand (Phase 20): verschiedene Drucke gegen die Kartenzahl des Sets bei Scryfall (mit Varianten), aus dem täglichen Lauf
        g = (groesse.get(i["code"]) or {}).get("size")
        if g:
            i["size"], i["have"] = g, min(i["prints"], g)
    return {"items": items, "total": len(items), "copies": sum(i["copies"] for i in items)}


def set_meta(conn):
    """Kürzel -> (Serienname, Erscheinungsdatum)."""
    return {r["set_code"]: (r["set_name"], r["released"]) for r in conn.execute(SET_META)}


def _serie(code, meta, neueste_zuerst):
    """Sortierschlüssel einer Serie wie in SET_SORTS: Datum (neueste zuerst oder gar nicht), Name, Kürzel."""
    name, released = meta.get(code, (None, None))
    return (-int(re.sub(r"\D", "", released or "")[:8] or 0) if neueste_zuerst else 0, (name or code).lower(), code)


def _nummer(n):
    """Sammlernummer als Sortierschlüssel (Text wie "17s" oder "S8"): erst die führende Zahl, dann der Text."""
    m = re.match(r"\d+", n or "")
    return (int(m.group()) if m else 0, n or "")


def api_summary(conn):
    if not conn.execute("SELECT 1 FROM value_history WHERE day = ?", (date.today().isoformat(),)).fetchone():
        mtg.record_value(conn)  # Wertverlauf: heute fehlt noch (z. B. ohne laufenden täglichen Lauf)
    s = mtg.stats(conn)
    zeilen = mtg.plan(conn)
    farben = {r["b"]: r for r in conn.execute(
        f"SELECT {BUCKET} b, SUM(col.qty * {mtg.PRICE}) value, SUM(col.qty) n FROM collection col JOIN cards c USING (scryfall_id) "
        f"WHERE {mtg.OWNED} GROUP BY b")}
    imp = conn.execute("SELECT * FROM imports WHERE added > 0 OR removed > 0 ORDER BY id DESC LIMIT 1").fetchone()
    delta = conn.execute(
        "SELECT COALESCE(SUM(ch.delta * COALESCE(c.price_eur, c.price_eur_foil, 0)), 0) FROM changes ch JOIN cards c USING (scryfall_id) "
        "WHERE ch.import_id = ?", (imp["id"],)).fetchone()[0] if imp else 0  # ponytail: Foil-Aufschlag der Änderungen unberücksichtigt
    preise = conn.execute("SELECT MIN(updated_at) FROM cards WHERE scryfall_id IN (SELECT scryfall_id FROM collection)").fetchone()[0]
    decks = deckbuild.decks_list(conn) + deckbuild.binder_decks(conn)
    bew = api_prices(conn, rows=zeilen)
    alarm = [{"kind": "price", "oracle_id": e["oracle_id"], "text": f"{e['name']} ist in {e['days']} Tagen um {e['pct'] * 100:.0f} % gestiegen, jetzt {mtg.eur(e['price'])}",
              "sub": f"Du hast {n} davon zum Verkaufen (vorher {mtg.eur(e['old'])})"} for e in bew["up"] if (n := e["stacks"]["sell"] + e["stacks"]["bulk"])][:3]
    return {"cards": s["cards"], "unique": s["unique"], "value": s["value"], "available": s["available"],
            "colors": [{"key": k, "label": lab, "value": farben[k]["value"] if k in farben else 0,
                        "cards": farben[k]["n"] if k in farben else 0} for k, lab in COLORS],
            "binders": api_binders(conn), "beispiel": mtg.beispiel_info(conn), "plan": mtg.stack_totals(zeilen), "rules": mtg.rules(conn), "sell_min": mtg.rules(conn)["sell_min"],
            "decks": len(decks), "deck_tiles": decks[:4], "news": konten.ordner_news(conn) + mtg.posteingang_news(conn) + deckbuild.waechter_news(conn) + deckbuild.radar_news(conn) + deckbuild.news(conn, rows=zeilen) + alarm,
            "movers": bew | {"up": bew["up"][:3], "down": bew["down"][:3]},
            "setup": {"edhrec": conn.execute("SELECT COUNT(*) FROM edhrec").fetchone()[0],
                      "tags": bool(conn.execute("SELECT 1 FROM tags WHERE tag = 'ramp' LIMIT 1").fetchone())},
            "top": api_cards(conn, {"sort": "price", "per_page": "6"}, zeilen)["items"],
            "recent": api_cards(conn, {"sort": "added", "per_page": "6"}, zeilen)["items"],
            "last_import": dict(imp) | {"value": delta} if imp else None, "prices_at": preise, "undo": mtg.undo_info(conn),
            "paid": s["paid"], "history": mtg.value_history(conn), "wuensche": [w["name"] for w in mtg.wuensche(conn) if w["reached"]],
            "verliehen": mtg.verliehen(conn), "arena": mtg.arena_drucke(conn),
            "sicherung": konten.aussen() | {"scan_karten": conn.execute("SELECT COALESCE(SUM(qty), 0) FROM collection WHERE binder_type = 'scan'").fetchone()[0]}}


def api_beispiel(conn, d=None, fetch=None, lookup=None):
    """Beispielsammlung zum Ausprobieren (Phase 47, E33). GET: Stand für die Oberfläche (mtg.beispiel_info). POST {"aktion": "laden"}: lädt sie
    (nur in einer leeren Sammlung, sonst ValueError, die Prüfung steht in mtg.beispiel_laden und gilt damit für jeden Weg); {"aktion": "entfernen"}."""
    if d is None:
        return mtg.beispiel_info(conn)
    if d.get("aktion") == "laden":
        return mtg.beispiel_laden(conn, fetch or mtg._fetch, lookup or mtg._lookup) | {"beispiel": mtg.beispiel_info(conn)}
    if d.get("aktion") == "entfernen":
        return {"entfernt": mtg.beispiel_entfernen(conn), "beispiel": mtg.beispiel_info(conn)}
    raise ValueError("Erwartet: aktion laden oder entfernen")


def api_binders(conn):
    """Binder im Bestand mit Typ und Kartenzahl (für Filter und Import-Ziel); fertige Decks markiert."""
    fest = mtg.deck_binders(conn)
    return [dict(r) | {"deck": r["name"] in fest} for r in conn.execute(
        f"SELECT col.binder name, col.binder_type type, SUM(col.qty) cards FROM collection col WHERE {mtg.OWNED} "
        f"GROUP BY col.binder ORDER BY col.binder")]


def api_card(conn, oracle_id):
    c = conn.execute("SELECT * FROM cards WHERE oracle_id = ? ORDER BY updated_at DESC LIMIT 1", (oracle_id,)).fetchone()
    if not c:
        return None
    owned = conn.execute(
        f"SELECT col.binder, col.binder_type, col.scryfall_id, c.set_code, c.number, c.image_url image, col.foil, col.language, col.condition, col.qty, {mtg.PRICE} price, col.paid, "
        f"cm.low, cm.trend, cm.avg30, cm.low_foil, cm.trend_foil, cm.avg30_foil, cm.day cm_day, n.ort, n.verliehen, n.notiz "
        f"FROM collection col JOIN cards c USING (scryfall_id) LEFT JOIN cm_price cm ON cm.id_product = json_extract(c.json, '$.cardmarket_id') {mtg.NOTIZ_JOIN} "
        f"WHERE c.oracle_id = ? AND {mtg.OWNED} ORDER BY price DESC, col.binder", (oracle_id,)).fetchall()
    cm = lambda r: None if not r["cm_day"] else ({"low": r["low_foil"], "trend": r["trend_foil"], "avg30": r["avg30_foil"], "day": r["cm_day"]}
                                                  if r["foil"] != "normal" else {"low": r["low"], "trend": r["trend"], "avg30": r["avg30"], "day": r["cm_day"]})
    eigen = ("binder", "scryfall_id", "set_code", "number", "image", "foil", "language", "condition", "qty", "price", "paid", "ort", "verliehen", "notiz")
    decks = [dict(r) for r in conn.execute(
        "SELECT d.id, d.name FROM decks d WHERE d.id IN (SELECT deck_id FROM deck_cards WHERE oracle_id = ?) ORDER BY d.name", (oracle_id,))]
    fest = mtg.deck_binders(conn)
    decks += [{"binder": b, "name": b} for b in sorted({o["binder"] for o in owned} & fest)]
    j = json.loads(c["json"] or "{}")
    links = {"scryfall": j.get("scryfall_uri"), "cardmarket": (j.get("purchase_uris") or {}).get("cardmarket"),
             "edhrec": (j.get("related_uris") or {}).get("edhrec")}
    return {"oracle_id": oracle_id, "name": c["name"], "image": c["image_url"], "mana_cost": c["mana_cost"], "type": c["type_line"],
            "set_name": j.get("set_name"), "links": {k: v for k, v in links.items() if v},
            "text": c["oracle_text"], "rarity": c["rarity"], "rank": c["edhrec_rank"], "legal": bool(c["legal_commander"]),
            "game_changer": bool(c["game_changer"]), "price": c["price_eur"], "price_foil": c["price_eur_foil"], "reserved": bool(j.get("reserved")),
            "owned": [{k: r[k] for k in eigen} | {"cm": cm(r), "scan": r["binder_type"] == "scan"} for r in owned], "available": mtg.available(conn).get(oracle_id, 0), "decks": decks,
            "want": deckbuild.demand(conn).get(oracle_id, []), "reprints": mtg.reprints(conn).get(oracle_id, []),
            "wunsch": dict(w) if (w := conn.execute("SELECT qty, max_eur, note FROM wishlist WHERE oracle_id = ?", (oracle_id,)).fetchone()) else None,
            "stacks": mtg.stacks_by_card([r for r in mtg.plan(conn) if r["oracle_id"] == oracle_id]).get(
                oracle_id, {"deck": [], "keep": 0, "sell": 0, "bulk": 0}),
            "status": dict(m) if (m := conn.execute("SELECT status, keep FROM card_status WHERE oracle_id = ?", (oracle_id,)).fetchone()) else None}


def api_status(conn, body):
    d = json.loads(body or b"{}")
    mtg.set_status(conn, d.get("oracle_id"), d.get("status") or None, d.get("keep") or 0)
    return {"ok": True}


def _zeile(r):
    """Eine Sammlungszeile (Druck, Binder); id ist stabil, damit die Oberfläche Zeilen abwählen kann."""
    return {"id": f"{r['scryfall_id']}-{r['foil']}-{r['condition']}-{r['language']}-{hashlib.md5(r['binder'].encode()).hexdigest()[:6]}",
            "oracle_id": r["oracle_id"], "name": r["name"], "set": r["set"], "number": r["number"], "foil": r["foil"],
            "condition": r["condition"], "language": r["language"], "binder": r["binder"], "image": r["image"], "price": r["price"],
            "rarity": r.get("rarity"), "added": r["added"], "stacks": []}


def api_sort(conn, q):
    """Ohne binder: alle Binder mit Zähler je Stapel. Mit binder: dessen Zeilen (order=scan|name) mit Ziel-Stapel."""
    zeilen = mtg.plan(conn)
    if not q.get("binder"):
        je = {}
        for r in zeilen:
            je.setdefault(r["binder"], dict.fromkeys(mtg.STACKS, 0))[r["stack"]] += r["qty"]
        return {"binders": [{"name": b, "cards": sum(c.values()), "stacks": c} for b, c in sorted(je.items())]}
    karten, zaehler = {}, dict.fromkeys(mtg.STACKS, 0)
    for r in zeilen:
        if r["binder"] != q["binder"]:
            continue
        k = karten.setdefault((r["scryfall_id"], r["foil"], r["condition"], r["language"]), _zeile(r))
        k["stacks"].append({"stack": r["stack"], "deck": r["deck"], "qty": r["qty"]})
        zaehler[r["stack"]] += r["qty"]
    reihenfolge = q.get("order")
    if reihenfolge in SET_SORTS:
        meta = set_meta(conn)
        schluessel = lambda k: (_serie(k["set"], meta, reihenfolge == "set"), _nummer(k["number"]), k["name"].lower())
    elif reihenfolge == "name":
        schluessel = lambda k: (k["name"].lower(), k["set"])
    else:
        schluessel = lambda k: (k["added"], k["name"].lower())
    items = sorted(karten.values(), key=schluessel)
    seite, pages = max(1, int(q.get("page") or 1)), max(1, -(-len(items) // SORT_PER_PAGE))
    return {"binder": q["binder"], "counts": zaehler, "total": len(items), "page": seite, "pages": pages,
            "rows": items[(seite - 1) * SORT_PER_PAGE:seite * SORT_PER_PAGE]}


def sell_min(conn, q):
    return float(q["min"]) if q.get("min") not in (None, "") else mtg.rules(conn)["sell_min"]


# Verkaufen 2.0 (Phase 17). Belegt am 2026-10-08, vor einer Änderung neu nachsehen:
# Cardmarket behält bei Privatverkäufern 5 % des Kartenpreises, das Porto zahlt der Käufer (tcg-pricetracker.com/en/blog/cardmarket-fees vom
# 29.07.2026 und flipzi.io; die offizielle Tabelle cardmarket.com/en/Policies/Fees war hinter einer Bot-Prüfung nicht abrufbar).
CM_PROVISION = 0.05
# KEEPSEVEN-Bulkankauf je Karte (sammelkartenankauf.de/Bulk-Sammelkarten-Ankauf/), Schlüssel (Seltenheit, Foil); „basic“ = Standardländer.
# Tokens und Specials stehen nicht auf der Liste. Versand übernimmt KEEPSEVEN ab K7_VERSAND_AB Ankaufswert. Gekauft wird Englisch und Deutsch.
K7_BULK = {("mythic", False): 0.12, ("rare", False): 0.10, ("uncommon", False): 0.005, ("common", False): 0.003, ("basic", False): 0.002,
           ("mythic", True): 0.15, ("rare", True): 0.10, ("uncommon", True): 0.007, ("common", True): 0.005, ("basic", True): 0.004}
K7_VERSAND_AB = 50.0
K7_SPRACHEN = ("en", "de")


def _sprachen(q):
    """lang=en,de -> nur diese Sprachen (KEEPSEVEN kauft nur Englisch und Deutsch); leer = alle."""
    return {x for x in (q or {}).get("lang", "").split(",") if x}


def sell_rows(conn, minimum, group="single", langs=None):
    """Zum Verkauf: single = einzeln (ab Mindestpreis), bulk = darunter, all = beides; teuerste zuerst. langs: nur diese Sprachen."""
    stacks = {"single": ("sell",), "bulk": ("bulk",), "all": ("sell", "bulk")}.get(group, ("sell",))
    rows = [r for r in mtg.plan(conn, sell_min=minimum) if r["stack"] in stacks and (not langs or r["language"] in langs)]
    rows.sort(key=lambda r: (-r["price"], r["name"], r["binder"]))
    return rows


def k7_bulk(rows):
    """Was KEEPSEVEN laut Bulk-Preisliste für diese Zeilen zahlt: nur Englisch und Deutsch, Tokens und Specials gar nicht.
    -> {"value", "cards" (gekauft), "ohne" (nicht gekauft), "frei_ab"}"""
    wert = karten = ohne = 0
    for r in rows:
        k = ("basic" if r.get("basic") else r["rarity"], r["foil"] != "normal")
        if r["language"] in K7_SPRACHEN and k in K7_BULK and not r.get("token"):
            wert, karten = wert + r["qty"] * K7_BULK[k], karten + r["qty"]
        else:
            ohne += r["qty"]
    return {"value": round(wert, 2), "cards": karten, "ohne": ohne, "frei_ab": K7_VERSAND_AB}


def sales_summary(conn):
    """Verkäufe, die Importe erkannt haben: letzter Import mit Verkäufen (mit Karten), Summe über alle und je Jahr."""
    total = conn.execute("SELECT COALESCE(SUM(qty), 0), COALESCE(SUM(qty * price), 0) FROM sales").fetchone()
    last = conn.execute("SELECT s.import_id, MAX(s.at) at, SUM(s.qty) cards, SUM(s.qty * s.price) value, i.file FROM sales s LEFT JOIN imports i ON i.id = s.import_id "
                        "GROUP BY s.import_id ORDER BY s.import_id DESC LIMIT 1").fetchone()  # file „Verkauf“: als verkauft gebucht (Phase 26)
    karten = [dict(r) for r in conn.execute(
        "SELECT c.oracle_id, c.name, c.set_code \"set\", c.image_url image, s.foil, SUM(s.qty) qty, s.price FROM sales s "
        "JOIN cards c USING (scryfall_id) WHERE s.import_id = ? GROUP BY s.scryfall_id, s.foil ORDER BY s.price DESC, c.name LIMIT 50",
        (last["import_id"],))] if last else []
    jahre = [dict(r) for r in conn.execute("SELECT substr(at, 1, 4) jahr, SUM(qty) cards, SUM(qty * price) value FROM sales GROUP BY jahr ORDER BY jahr DESC")]
    return {"cards": total[0], "value": total[1], "last": dict(last) | {"items": karten} if last else None, "jahre": jahre}


def api_sell(conn, q):
    minimum, langs = sell_min(conn, q), _sprachen(q)
    alle = mtg.plan(conn, sell_min=minimum)
    rows = [r for r in alle if not langs or r["language"] in langs]
    gefragt = deckbuild.demand(conn)  # Konfliktkarten: stehen auf den Listen von mindestens zwei der besten Commander
    neuauflage, scan = mtg.reprints(conn), mtg.scan_binders(conn)
    extra = {r[0]: r for r in conn.execute(  # Cardmarket „ab“ und Reserved List je Druck der Verkaufszeilen
        "SELECT c.scryfall_id, cm.low, cm.low_foil, json_extract(c.json, '$.reserved') reserved FROM cards c "
        "LEFT JOIN cm_price cm ON cm.id_product = json_extract(c.json, '$.cardmarket_id') WHERE c.scryfall_id IN (SELECT value FROM json_each(?))",
        (json.dumps(sorted({r["scryfall_id"] for r in rows if r["stack"] in ("sell", "bulk")})),))}

    def zeile(r):
        e = extra.get(r["scryfall_id"])
        ab = e and (e["low_foil"] if r["foil"] != "normal" else e["low"])
        return {**_zeile(r), "qty": r["qty"], "want": gefragt.get(r["oracle_id"], []), "cm_low": ab, "reserved": bool(e and e["reserved"]),
                "reprint": neuauflage.get(r["oracle_id"], []), "scryfall_id": r["scryfall_id"], "scan": r["binder"] in scan}

    def gruppe(stack):
        rs = sorted((r for r in rows if r["stack"] == stack), key=lambda r: (-r["price"], r["name"], r["binder"]))
        value = sum(r["qty"] * r["price"] for r in rs)
        return {"cards": sum(r["qty"] for r in rs), "value": value, "netto_cm": round(value * (1 - CM_PROVISION), 2), "total_rows": len(rs),
                "rows": [zeile(r) for r in rs[:SELL_MAX_ROWS]]}
    single, bulk = gruppe("sell"), gruppe("bulk")
    bulk["k7"] = k7_bulk([r for r in rows if r["stack"] == "bulk"])
    selten = {}
    for r in rows:
        if r["stack"] == "bulk":
            k = r["rarity"] if r["rarity"] in ("common", "uncommon", "rare", "mythic") else "other"
            selten.setdefault(k, {"rarity": k, "cards": 0, "value": 0.0})
            selten[k]["cards"] += r["qty"]
            selten[k]["value"] += r["qty"] * r["price"]
    bulk["rarity"] = [selten[k] for k in ("common", "uncommon", "rare", "mythic", "other") if k in selten]
    andere = sum(r["qty"] for r in alle if r["stack"] in ("sell", "bulk") and r["language"] not in K7_SPRACHEN)
    return {"min": minimum, "rules": mtg.rules(conn), "single": single, "bulk": bulk, "sold": sales_summary(conn), "langs": sorted(langs),
            "andere_sprachen": andere, "provision": CM_PROVISION}


MANABOX = ["Name", "Set code", "Set name", "Collector number", "Foil", "Rarity", "Quantity", "ManaBox ID", "Scryfall ID", "Purchase price",
           "Misprint", "Altered", "Signed", "Condition", "Language", "Proxy", "Purchase price currency", "Added"]
# Liste zum Anbieten (z. B. Sammlungsankauf bei KEEPSEVEN): öffnet sich im deutschen Excel direkt (Semikolon, Komma, BOM)
EXCEL = ["Anzahl", "Name", "Edition", "Set", "Nr.", "Sprache", "Zustand", "Foil", "Seltenheit", "Preis (€)", "Summe (€)", "Binder"]
SPRACHE = {"en": "Englisch", "de": "Deutsch", "fr": "Französisch", "it": "Italienisch", "es": "Spanisch", "pt": "Portugiesisch",
           "ja": "Japanisch", "ko": "Koreanisch", "ru": "Russisch", "zh_CN": "Chinesisch (vereinfacht)", "zh_TW": "Chinesisch (traditionell)"}
ZUSTAND = {"mint": "Near Mint (NM)",  # KEEPSEVEN kennt kein Mint, es zählt als NM (Phase 9)
           "near_mint": "Near Mint (NM)", "excellent": "Excellent (EX)", "good": "Good (GD)",
           "light_played": "Light Played (LP)", "played": "Played (PL)", "poor": "Poor (PO)"}


def sell_export(conn, q):
    """Verkaufsliste als Datei: format manabox (CSV, in ManaBox als Liste importierbar), excel (zum Anbieten) oder text
    („1 Name (SET) 123 *F*“); group single, bulk oder all; skip = abgewählte Zeilen-IDs, kommagetrennt. -> (Content-Type, Bytes)"""
    skip = {x for x in q.get("skip", "").split(",") if x}
    rows = [r for r in sell_rows(conn, sell_min(conn, q), q.get("group") or "single", _sprachen(q)) if _zeile(r)["id"] not in skip]
    fmt = q.get("format") or "manabox"
    if fmt == "text":
        return "text/plain; charset=utf-8", "".join(
            f"{r['qty']} {r['name']} ({r['set']}) {r['number']}{' *F*' if r['foil'] == 'foil' else ' *E*' if r['foil'] == 'etched' else ''}\n"
            for r in rows).encode()
    extra = {(r["scryfall_id"], r["foil"], r["condition"], r["language"], r["binder"]): r for r in conn.execute(
        "SELECT col.scryfall_id, col.foil, col.condition, col.language, col.binder, col.mbid, c.rarity, json_extract(c.json, '$.set_name') set_name "
        "FROM collection col JOIN cards c USING (scryfall_id)")}
    out = io.StringIO()
    if fmt == "excel":
        komma = lambda x: f"{x:.2f}".replace(".", ",")
        w = csv.writer(out, delimiter=";", lineterminator="\r\n")
        w.writerow(EXCEL)
        for r in rows:
            e = extra[(r["scryfall_id"], r["foil"], r["condition"], r["language"], r["binder"])]
            w.writerow([r["qty"], r["name"], e["set_name"] or "", r["set"], r["number"], SPRACHE.get(r["language"], r["language"]),
                        ZUSTAND.get(r["condition"], r["condition"]), "" if r["foil"] == "normal" else r["foil"].capitalize(),
                        (e["rarity"] or "").capitalize(), komma(r["price"]), komma(r["price"] * r["qty"]), r["binder"]])
        return "text/csv; charset=utf-8", ("\ufeff" + out.getvalue()).encode()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(MANABOX)
    for r in rows:
        e = extra[(r["scryfall_id"], r["foil"], r["condition"], r["language"], r["binder"])]
        w.writerow([r["name"], r["set"], e["set_name"], r["number"], r["foil"], e["rarity"], r["qty"], e["mbid"], r["scryfall_id"],
                    f"{r['price']:.2f}", "false", "false", "false", r["condition"], r["language"], "false", "EUR", r["added"]])
    return "text/csv; charset=utf-8", out.getvalue().encode()


def sell_csv(conn, q):
    """Verkaufsliste im ManaBox-Format (wie bisher)."""
    return sell_export(conn, q | {"format": "manabox"})[1].decode()


def api_settings(conn, body=None):
    if body is not None:
        d = json.loads(body or b"{}")
        mtg.set_rules(conn, d.get("keep"), d.get("staples"), d.get("sell_min"))
    return mtg.rules(conn) | {"rank_staple": mtg.RANK_STAPLE}


def api_fertige_decks(conn, d=None):
    """Binder, die fertige Decks sind, auch wenn der Export keinen Binder Type nennt (Einstellung dieser Sammlung, PLAN E33): GET zeigt die Namen
    und die Binder im Bestand, POST {namen: [...]} ersetzt die Liste. Gilt sofort für Sortier-Plan und „verfügbar“."""
    if d is not None:
        mtg.set_fertige_decks(conn, d.get("namen"))
    return {"namen": mtg.fertige_decks(conn), "binder": [{"name": b["name"], "type": b["type"], "deck": b["deck"]} for b in api_binders(conn)]}


PROXY_AUS = ("Das Proxy-Blatt ist ausgeschaltet. Das Hauptkonto kann es unter „Konten und Sicherung“ einschalten. Es ist zum Ausprobieren "
             "vor dem Kauf gedacht.")


def _proxy_blatt(method, d, haupt):
    """GET /api/proxy-blatt: ist das Proxy-Blatt eingeschaltet (für die ganze Installation, standardmäßig aus)? POST {an: bool} schaltet es ein
    oder aus, nur das Hauptkonto. Die Einstellung steht in meta der Hauptsammlung, auch wenn das Hauptkonto gerade die eines Unterkontos offen hat."""
    if method == "POST":
        if not haupt:
            raise PermissionError("Das Proxy-Blatt schaltet nur das Hauptkonto ein")
        if not isinstance(d.get("an"), bool):
            raise ValueError("Erwartet: {an: true oder false}")
        with closing(mtg.connect()) as conn:
            mtg.proxy_blatt_setzen(conn, d["an"])
    return {"an": mtg.proxy_blatt(), "haupt": haupt}


SCAN_FP_MAX = 4096  # Bytes je Fingerabdruck (die App schickt deutlich weniger); mehr ist keiner
SCAN_SETS_MAX = 6   # so viele Sets auf einmal beim Erfassen (etwa Precon mit Spielsteinen, Booster mit Specials)


def _scan_eigen(conn):
    """Eigene Drucke für den Scanner. Arena-Drucke (nur digital, etwa KLR) haben dasselbe Bild wie ein Papier-Druck: Besitzt du den auch,
    fehlen sie (der Scan trifft dann den Papier-Druck). -> scryfall_id -> (id, oracle_id, Name, Bild, Preis, illustration_id, Arena, Set, Nummer)"""
    eigen = {r[0]: r for r in conn.execute(
        f"SELECT DISTINCT c.scryfall_id, c.oracle_id, c.name, c.image_url, COALESCE(c.price_eur, c.price_eur_foil), "
        f"json_extract(c.json, '$.illustration_id'), {mtg.ARENA}, c.set_code, c.number FROM collection col JOIN cards c USING (scryfall_id) WHERE {mtg.OWNED}")}
    papier = {r[5] for r in eigen.values() if not r[6]}
    return {s: r for s, r in eigen.items() if not (r[6] and r[5] in papier)}


def api_scan(conn, q=None, body=None, set_suche=None):
    """Scanner (Phase 24, PLAN E17): Bild-Fingerabdrücke der eigenen Drucke. Der Browser rechnet sie aus dem Scryfall-Bild (Python kann
    kein JPEG lesen) und schickt sie her (body: {v, fp: {scryfall_id: base64}}, ältere Versionen fliegen raus; erlaubt sind eigene Drucke und
    die der Sets fürs Erfassen). GET (q: v) liefert alle der Version v mit Preis, Bild und Set samt Nummer je Druck (gezeigt wird der erkannte
    Druck, nicht irgendein Druck mit demselben Namen), die noch fehlenden Drucke mit Bild und je Karte Name, Bild und Stapel aus dem
    Sortier-Plan, damit der Scan ohne weitere Anfrage antwortet; ein Arena-Druck ohne Preis bekommt den des günstigsten Papier-Drucks mit
    gleichem Bild. Mit set=KÜRZEL[,…] (Erfassen, Phase 25): der Index der Drucke dieser Sets (scan_set)."""
    q = q or {}
    if body is not None:
        d = json.loads(body or b"{}")
        v, fps = d.get("v"), d.get("fp")
        if not isinstance(v, int) or v < 1 or not isinstance(fps, dict):
            raise ValueError("Fingerabdrücke: v und fp fehlen")
        erlaubt = set(_scan_eigen(conn)) | {r[0] for r in conn.execute("SELECT scryfall_id FROM set_prints WHERE NOT digital")}
        soll = (conn.execute("SELECT length(fp) FROM scan_fp WHERE v = ? LIMIT 1", (v,)).fetchone() or [None])[0]  # eine Länge je Version
        rows = []
        for sid, b64 in fps.items():
            fp = base64.b64decode(b64 if isinstance(b64, str) else "", validate=True)
            soll = soll or len(fp)
            if sid not in erlaubt or not 0 < len(fp) <= SCAN_FP_MAX or len(fp) != soll:
                raise ValueError(f"Fingerabdruck für {sid} passt nicht")
            rows.append((sid, v, fp))
        with conn:
            conn.execute("DELETE FROM scan_fp WHERE v != ?", (v,))
            conn.executemany("INSERT OR REPLACE INTO scan_fp VALUES (?,?,?)", rows)
        return {"ok": len(rows)}
    if q.get("set"):
        return scan_set(conn, int(q.get("v") or 0), q["set"], q.get("neu") == "1", set_suche)
    eigen = _scan_eigen(conn)
    bildpreis = dict(conn.execute(f"SELECT json_extract(c.json, '$.illustration_id'), MIN(COALESCE(c.price_eur, c.price_eur_foil)) FROM cards c "
                                  f"WHERE NOT {mtg.ARENA} AND COALESCE(c.price_eur, c.price_eur_foil) IS NOT NULL GROUP BY 1"))
    v = int(q.get("v") or 0)
    fp = {sid: b for sid, b in conn.execute("SELECT scryfall_id, fp FROM scan_fp WHERE v = ?", (v,)) if sid in eigen}
    ids = sorted(fp)
    stapel, leer = mtg.stacks_by_card(mtg.plan(conn)), {"deck": [], "keep": 0, "sell": 0, "bulk": 0}
    return {"v": v, "ids": ids, "oids": [eigen[s][1] for s in ids], "preise": [eigen[s][4] if eigen[s][4] is not None else bildpreis.get(eigen[s][5]) for s in ids],
            "bilder": [eigen[s][3] for s in ids], "drucke": [f"{eigen[s][7]} {eigen[s][8]}" for s in ids],
            "fp":base64.b64encode(b"".join(fp[s] for s in ids)).decode(), "len": len(fp[ids[0]]) if ids else 0,
            "karten": {r[1]: {"name": r[2], "image": r[3], "stacks": stapel.get(r[1], leer)} for r in eigen.values()},
            "fehlt": [{"id": s, "image": r[3]} for s, r in eigen.items() if s not in fp and r[3]]}


SCAN_PAKET = 2000  # so viele fehlende Aussehen nennt eine Anfrage; der Browser rechnet sie und fragt nach den nächsten
SUCHE_SETS = 12    # so viele Kürzel je Suche (bevorzugte Sets bzw. Sets der letzten Karten)
SUCHE_KARTEN = katalog.NAMEN_ZAHL * katalog.NAMEN_KARTEN  # so viele Kennungen je Suche höchstens (was api_scan_titel nennen kann)


def api_scan_katalog(conn, q=None, body=None):
    """Erkennung ohne Set-Wahl vorbereiten (Phase 32, PLAN E20): Fingerabdrücke je Aussehen im Katalog aller Papier-Drucke, gemeinsam für alle
    Konten. GET (q: v): Stand {gesamt, fertig, titel: der Server kann Namen lesen (Phase 35)}, mit fehlt=1 dazu die nächsten SCAN_PAKET fehlenden mit Bild (die Sets der eigenen Sammlung zuerst),
    mit probe=N stattdessen N vorbereitete Aussehen für die Messung. POST {v, fp: {aussehen: base64}} speichert, was der Browser gerechnet hat
    (katalog.fp_speichern: nur Aussehen aus dem Katalog, nichts überschreiben)."""
    kat = mtg.katalog_von(conn)
    if body is not None:
        d = json.loads(body or b"{}")
        v, fps = d.get("v"), d.get("fp")
        if not isinstance(v, int) or v < 1 or not isinstance(fps, dict):
            raise ValueError("Fingerabdrücke: v und fp fehlen")
        roh = {a: base64.b64decode(b if isinstance(b, str) else "", validate=True) for a, b in fps.items()}
        if any(len(fp) > SCAN_FP_MAX for fp in roh.values()):
            raise ValueError("Fingerabdruck zu groß")
        return {"ok": katalog.fp_speichern(kat, v, roh)}
    q = q or {}
    v = int(q.get("v") or 0)
    if q.get("probe"):  # Messung von Hand (tests/suche_eval.js; mit lang=de gedruckte Namen für tests/titel_eval.js)
        n = min(int(q["probe"]), 5000)
        return {"v": v, "probe": katalog.namen_probe(kat, n, q["lang"]) if q.get("lang") else katalog.fp_probe(kat, n)}
    eigen = [r[0] for r in conn.execute("SELECT DISTINCT c.set_code FROM collection col JOIN cards c USING (scryfall_id)")]
    return {"v": v, "titel": bool(titel_programm())} | katalog.fp_stand(kat, v, eigen, SCAN_PAKET if q.get("fehlt") else 0)


def api_scan_suche(conn, body):
    """Erkennung ohne Set-Wahl (Phase 32): {v, fp: [base64 je Lage, höchstens katalog.SUCHE_LAGEN], sets: [bevorzugte Kürzel], kontext: [Sets der
    zuletzt gezählten Karten, jüngstes zuerst], karten und sicher: [Kennungen aus api_scan_titel (Phase 35): alle Karten, deren Name gelesen
    wurde, und die Karte des sicher gelesenen Namens; dann stehen nur ihre Bilder zur Wahl]}. Unter gleich aussehenden Drucken gehen die vor, die
    die Sammlung hat oder die auf der Scan-Liste liegen (Phase 60, katalog.druckwahl).
    -> katalog.suche: die besten drei Bilder mit Wert, Abstand, gewähltem Druck und anderen Drucken."""
    d = json.loads(body or b"{}")
    v, fps = d.get("v"), d.get("fp")
    if not isinstance(v, int) or v < 1 or not isinstance(fps, list) or not 1 <= len(fps) <= katalog.SUCHE_LAGEN:
        raise ValueError(f"Suche: v und fp (1 bis {katalog.SUCHE_LAGEN} Lagen) fehlen")
    kuerzel = lambda x: [s.upper() for s in (x if isinstance(x, list) else []) if isinstance(s, str)][:SUCHE_SETS]
    lagen = [base64.b64decode(b if isinstance(b, str) else "", validate=True) for b in fps]
    karten, sicher = d.get("karten"), d.get("sicher")
    for k in (karten, sicher):
        if k is not None and not (isinstance(k, list) and len(k) <= SUCHE_KARTEN and all(isinstance(x, str) for x in k)):
            raise ValueError(f"Suche: karten und sicher sind Listen von höchstens {SUCHE_KARTEN} Kennungen")
    eigen = {r[0] for r in conn.execute("SELECT scryfall_id FROM collection UNION SELECT scryfall_id FROM scan_liste")}  # Phase 60: rund 4 ms
    return katalog.suche(mtg.katalog_von(conn), v, lagen, kuerzel(d.get("sets")), kuerzel(d.get("kontext")), d.get("pruef"), karten, sicher, eigen)


# --- Namen lesen (Phase 35, PLAN E21) ---------------------------------------------------------------------------------------------------------
# Die App schickt Streifen mit der Namenszeile (erst eng geschnitten, dann großzügig), Tesseract liest sie nebeneinander, katalog.namen_suche
# gleicht mit allen Kartennamen ab. Tesseract ist ein eigenes Programm (im Docker-Image dabei, am Rechner freiwillig): Ohne es gibt es die
# Funktion nicht, alles andere läuft. Die Streifen werden nicht gespeichert.

TITEL_MAX = 200 * 1024     # Bytes je Streifen
TITEL_STREIFEN = 2         # so viele Streifen je Anfrage, und so viele liest der Server zugleich
TITEL_SEKUNDEN = 5         # länger darf ein Aufruf nicht dauern
TITEL_ZEILEN = 4           # so viele gelesene Zeilen werden abgeglichen (der Streifen ist großzügig geschnitten: Rand und Bildkante geben Unsinn)
# Seitenmodus (6 = ein Block Text) und Sprachmodell von Tesseract, aus der Messung (PLAN Phase 35): Das englische Modell liest deutsche Namen
# so gut wie das deutsche (ä kommt als a an, der Abgleich löst Umlaute ohnehin auf), beide zusammen kosten die doppelte Zeit.
TITEL_PSM, TITEL_SPRACHE = "6", "eng"
TITEL_PSMS, TITEL_SPRACHEN = ("6", "7", "11", "13"), ("eng", "deu", "deu+eng")  # was die Messung (tests/titel_eval.js) noch wählen darf; deu nur, wo es installiert ist
_titel_sperre = threading.BoundedSemaphore(TITEL_STREIFEN)


def titel_programm():
    """Aufruf von Tesseract als Liste, None ohne: MTG_TESSERACT (Pfad zum Programm oder ein ganzer Aufruf wie „docker exec -i NAME tesseract“),
    sonst tesseract aus dem Suchpfad."""
    eigen = os.environ.get("MTG_TESSERACT", "").strip()
    if eigen:
        return [eigen] if Path(eigen).is_file() else shlex.split(eigen)
    return [shutil.which("tesseract")] if shutil.which("tesseract") else None


def titel_lesen(bild, psm=TITEL_PSM, sprache=TITEL_SPRACHE):
    """Streifen (JPEG oder PNG) -> gelesene Zeilen. Feste Argumente, das Bild über die Standardeingabe, nichts auf der Platte."""
    programm = titel_programm()
    if not programm:
        raise ValueError("Namen lesen geht nur mit Tesseract (im Docker-Image dabei)")
    try:
        with _titel_sperre:  # ponytail: eine Karte zur Zeit; mehr nebeneinander, wenn mehrere Handys zugleich scannen und es stört
            r = subprocess.run([*programm, "stdin", "stdout", "--psm", psm, "-l", sprache], input=bild, capture_output=True, timeout=TITEL_SEKUNDEN,
                               env=os.environ | {"OMP_THREAD_LIMIT": "1"})  # eine Zeile: mehrere Rechenkerne machen Tesseract langsamer
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ValueError(f"Tesseract antwortet nicht ({type(e).__name__})") from e
    if r.returncode:
        raise ValueError("Tesseract: " + r.stderr.decode("utf-8", "replace").strip()[-200:])
    return [z.strip() for z in r.stdout.decode("utf-8", "replace").splitlines() if z.strip()]


def api_scan_titel(conn, body, lesen=None):
    """POST /api/scan/titel {streifen: [base64 je Streifen, JPEG oder PNG, höchstens TITEL_STREIFEN zu je TITEL_MAX]} -> {text: gelesene Zeilen,
    namen: die besten Namen dazu (katalog.namen_suche), sicher: der erste ist sicher gelesen, karten: Kennungen aller Karten mit einem Namen ab
    katalog.NAMEN_AB (für api_scan_suche), ms}. Die Streifen liest Tesseract nebeneinander; es gilt der erste, der einen Namen ab NAMEN_AB
    ergibt, sonst der beste. psm und sprache wählt nur die Messung."""
    d = json.loads(body or b"{}")
    roh = d.get("streifen")
    if not isinstance(roh, list) or not 1 <= len(roh) <= TITEL_STREIFEN:
        raise ValueError(f"Namen lesen: streifen (1 bis {TITEL_STREIFEN}) fehlt")
    bilder = [base64.b64decode(s if isinstance(s, str) else "", validate=True) for s in roh]
    if any(not (b[:2] == b"\xff\xd8" or b[:8] == b"\x89PNG\r\n\x1a\n") or len(b) > TITEL_MAX for b in bilder):
        raise ValueError(f"Namen lesen: je Streifen ein JPEG oder PNG bis {TITEL_MAX // 1024} KB")
    psm, sprache = d.get("psm") or TITEL_PSM, d.get("sprache") or TITEL_SPRACHE
    if psm not in TITEL_PSMS or sprache not in TITEL_SPRACHEN:
        raise ValueError("Namen lesen: psm oder sprache unbekannt")
    t0, kat, gelesen = time.perf_counter(), mtg.katalog_von(conn), [None] * len(bilder)

    def lies(i):
        try:
            gelesen[i] = (lesen or titel_lesen)(bilder[i], psm, sprache)
        except ValueError as e:
            gelesen[i] = e
    faeden = [threading.Thread(target=lies, args=(i,)) for i in range(len(bilder))]
    for f in faeden:
        f.start()
    for f in faeden:
        f.join()
    for g in gelesen:
        if isinstance(g, ValueError):
            raise g
    wert = lambda n: n[0]["wert"] if n else 0
    je = [(zeilen, max((katalog.namen_suche(kat, z) for z in zeilen[:TITEL_ZEILEN]), key=wert, default=[])) for zeilen in gelesen]
    zeilen, namen = next((x for x in je if wert(x[1]) >= katalog.NAMEN_AB), max(je, key=lambda x: wert(x[1])))
    return {"text": zeilen, "namen": namen, "sicher": katalog.namen_sicher(namen),
            "karten": list(dict.fromkeys(k for n in namen if n["wert"] >= katalog.NAMEN_AB for k in n["karten"])), "ms": round((time.perf_counter() - t0) * 1000, 1)}


def scan_set(conn, v, codes, neu=False, suche=None):
    """Index fürs Erfassen mit Set-Lock (Phase 25, E18): Fingerabdrücke der Version v für die Papier-Drucke der Sets (set_prints, beim ersten
    Mal von Scryfall, neu holt sie noch einmal), die noch fehlenden Drucke mit Bild und je Druck Name, Kürzel, Nummer, Bild, Bild-Kennung
    (dasselbe Bild in zwei Sets: nie raten), Foil-Arten, Preis und wie viele Kopien der Karte du schon hast."""
    codes = list(dict.fromkeys(c.strip().upper() for c in codes.split(",") if c.strip()))[:SCAN_SETS_MAX]
    mtg.set_drucke(conn, codes, suche, neu)
    rows = conn.execute(
        "SELECT scryfall_id, oracle_id, name, set_code, number, image_url, illustration_id, finishes, json_extract(json, '$.set_name'), "
        "json_extract(json, '$.prices.eur'), COALESCE(json_extract(json, '$.prices.eur_foil'), json_extract(json, '$.prices.eur_etched')), "
        "json_extract(json, '$.rarity') FROM set_prints WHERE set_code IN (SELECT value FROM json_each(?)) AND NOT digital", (json.dumps(codes),)).fetchall()
    fp = {sid: b for sid, b in conn.execute("SELECT scryfall_id, fp FROM scan_fp WHERE v = ? AND scryfall_id IN (SELECT value FROM json_each(?))",
                                            (v, json.dumps([r[0] for r in rows])))}
    ids = sorted(fp)
    hat = dict(conn.execute(f"SELECT c.oracle_id, SUM(col.qty) FROM collection col JOIN cards c USING (scryfall_id) WHERE {mtg.OWNED} "
                            f"AND c.oracle_id IN (SELECT value FROM json_each(?)) GROUP BY c.oracle_id", (json.dumps(sorted({r[1] for r in rows if r[1]})),)))
    zahl = lambda x: float(x) if x else None
    sets = {c: {"code": c, "name": c, "drucke": 0} for c in codes}
    for r in rows:
        sets[r[3]] |= {"name": r[8] or r[3], "drucke": sets[r[3]]["drucke"] + 1}
    return {"v": v, "sets": list(sets.values()), "ids": ids, "fp": base64.b64encode(b"".join(fp[s] for s in ids)).decode(), "len": len(fp[ids[0]]) if ids else 0,
            "drucke": {r[0]: {"oid": r[1], "name": r[2], "set": r[3], "number": r[4], "image": r[5], "ill": r[6], "finishes": json.loads(r[7] or "[]"),
                              "eur": zahl(r[9]), "eur_foil": zahl(r[10]), "rarity": r[11], "hat": hat.get(r[1], 0)} for r in rows},
            "fehlt": [{"id": r[0], "image": r[5]} for r in rows if r[0] not in fp and r[5]]}


def api_bestand(conn, path, d):
    """Bestand ohne ManaBox (Phase 26): Kopie eines Scan-Binders ändern oder verschieben, Scan-Binder umbenennen, als verkauft buchen und
    zurücknehmen, ManaBox-Binder übernehmen (vorher eine Sicherung aller Sammlungen)."""
    if path == "/api/kopie":
        return {"key": mtg.kopie_aendern(conn, d.get("key"), d.get("qty"), d.get("binder"), d.get("foil"), d.get("condition"), d.get("language"))}
    if path == "/api/binder-name":
        return {"name": mtg.binder_umbenennen(conn, d.get("alt") or "", d.get("neu") or "")}
    if path == "/api/verkauft":
        return mtg.verkauf_buchen(conn, [(z.get("key"), z.get("qty")) for z in d.get("zeilen") or []], d.get("erloes"))
    if path == "/api/verkauft-zurueck":
        return mtg.verkauf_zuruecknehmen(conn, d.get("import_id"))
    binder = d.get("binder") or ""
    mtg.uebernahme_pruefen(conn, binder)
    ziel = konten.sicherung_vor("uebernahme")
    return {"karten": mtg.binder_uebernehmen(conn, binder), "sicherung": ziel.name}


def bestand_export(conn, binder=None):
    """Bestand als ManaBox-CSV (Phase 26): ein Binder im Format des Binder-Exports, ohne binder alles im Format des Sammlungsexports (mit Binder
    Name und Binder Type; Scan-Binder stehen dort als „binder“, andere Arten kennt ManaBox nicht). In ManaBox importierbar, in eine leere Sammlung
    dieser App importiert wieder derselbe Bestand. Purchase price ist der gespeicherte Kaufpreis (leer ohne). -> Bytes"""
    rows = conn.execute(
        "SELECT col.*, COALESCE(c.name, '') name, COALESCE(c.set_code, '') set_code, COALESCE(c.number, '') number, COALESCE(c.rarity, '') rarity, "
        "COALESCE(json_extract(c.json, '$.set_name'), '') set_name FROM collection col LEFT JOIN cards c USING (scryfall_id) "
        f"{'WHERE col.binder = ? ' if binder else ''}ORDER BY col.binder, c.set_code, CAST(c.number AS INTEGER), c.number, col.foil",
        (binder,) if binder else ()).fetchall()
    if binder and not rows:
        raise ValueError(f"Kein Binder „{binder}“")
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(([] if binder else ["Binder Name", "Binder Type"]) + MANABOX)
    for r in rows:
        w.writerow(([] if binder else [r["binder"], "binder" if r["binder_type"] == "scan" else r["binder_type"]])
                   + [r["name"], r["set_code"], r["set_name"], r["number"], r["foil"], r["rarity"], r["qty"], r["mbid"] or "", r["scryfall_id"],
                      "" if r["paid"] is None else str(round(r["paid"], 4)), "false", "false", "false", r["condition"], r["language"], "false", "EUR", r["added"] or ""])
    return out.getvalue().encode()


def api_erfassen(conn, q, body=None, fetch=None):
    """Erfassen (Phase 25, mit Scan-Liste aus Phase 29): GET mit sitzung=ID die Sitzung, mit suche=TEXT Drucke zum Tauschen (auch aus dem Katalog,
    Phase 31), mit drucke=ORACLE_ID alle Drucke dieser Karte (Phase 60), ohne all das Scan-Binder, Namensvorschlag, ManaBox-Binder, die Scan-Liste und
    die zuletzt übernommene Sitzung. POST {aktion: liste (id, foil, condition, language, qty, zug, wahl, pruefen) | liste-aendern (key, id, foil,
    condition, language, qty) | liste-zurueck | liste-leeren | uebernehmen (binder, deck: als fertiges Deck, Phase 60) | sitzung-zurueck (sitzung)};
    direkt in den Binder (Phase 25): add | zurueck | aendern."""
    if body is None:
        if q.get("sitzung"):
            return mtg.scan_sitzung(conn, q["sitzung"])
        if q.get("suche") is not None:
            return {"items": mtg.drucke_suchen(conn, q["suche"])}
        if q.get("drucke"):
            return {"items": mtg.drucke_karte(conn, q["drucke"])}
        fest = mtg.deck_binders(conn)  # ManaBox-Binder, die sich übernehmen lassen (Phase 26)
        manabox = [{"name": b, "karten": n} for b, n in conn.execute("SELECT binder, SUM(qty) FROM collection WHERE binder_type = 'binder' GROUP BY binder "
                                                                       "ORDER BY binder COLLATE NOCASE") if b not in fest]
        return {"binder": mtg.scan_binder_liste(conn), "vorschlag": f"Scan {date.today().isoformat()}", "manabox": manabox,
                "liste": mtg.liste(conn), "zuletzt": mtg.letzte_sitzung(conn)}
    d = json.loads(body or b"{}")
    a = d.get("aktion")
    if a == "liste":
        return mtg.liste_add(conn, d.get("id"), d.get("foil") or "normal", d.get("condition") or "near_mint", d.get("language") or "en",
                             d.get("qty") or 1, d.get("zug"), d.get("wahl"), fetch=fetch, pruefen=d.get("pruefen"))
    if a == "liste-aendern":
        return mtg.liste_aendern(conn, d.get("key"), d.get("id"), d.get("foil"), d.get("condition"), d.get("language"), d.get("qty"), fetch=fetch)
    if a == "liste-zurueck":
        return mtg.liste_zurueck(conn)
    if a == "liste-leeren":
        return mtg.liste_leeren(conn)
    if a == "uebernehmen":
        s = mtg.liste_uebernehmen(conn, d.get("binder"), fetch=fetch, deck=bool(d.get("deck")))
        return {"sitzung": s, "liste": mtg.liste(conn), "zuletzt": mtg.letzte_sitzung(conn)}
    if a == "sitzung-zurueck":
        return {"liste": mtg.sitzung_zuruecknehmen(conn, d.get("sitzung")), "zuletzt": mtg.letzte_sitzung(conn)}
    if a == "add":
        return mtg.scan_add(conn, d.get("binder"), d.get("id"), d.get("foil") or "normal", d.get("condition") or "near_mint", d.get("language") or "en",
                            d.get("qty") or 1, d.get("sitzung"), d.get("zug"), fetch=fetch)
    if a == "zurueck":
        return mtg.scan_zurueck(conn, d.get("sitzung"))
    if a == "aendern":
        return mtg.scan_aendern(conn, d.get("sitzung"), d.get("key"), d.get("foil"), d.get("condition"), d.get("language"), d.get("qty"))
    raise ValueError("Unbekannte Aktion")


def api_messbild(conn, method, path, q, body=b"", db=None, fetch=None):
    """Messbilder (Phase 30): echte Kamerabilder mit Etikett, zum Messen der Erkennung; je Sammlung in mtg.messbild_ordner. POST /api/messbild
    mit dem JPEG als Body (q: zug, merkmale, rahmen=x,y,b,h) legt eins ab, GET /api/messbild/ID.jpg liefert es, GET /api/messbilder die Liste
    mit Zahl und Platz, POST /api/messbilder {aktion: setzen (id, scryfall_id, foil, language, merkmale) | weg (id) | leeren} ändert sie.
    -> (Statuscode, Content-Type, Bytes)"""
    ordner = mtg.messbild_ordner(db)
    bild = re.fullmatch(r"/api/messbild/(\d+)\.jpg", path)
    if bild and method == "GET":
        datei = ordner / f"{int(bild[1])}.jpg"
        return (200, "image/jpeg", datei.read_bytes()) if datei.is_file() else _json({"error": "nicht gefunden"}, 404)
    if path == "/api/messbild" and method == "POST":
        return _json(mtg.messbild_neu(conn, ordner, body, q.get("zug"), q.get("merkmale"), q["rahmen"].split(",") if q.get("rahmen") else None))
    if path == "/api/messbilder":
        d = json.loads(body or b"{}") if method == "POST" else {}
        if d.get("aktion") == "setzen":
            mtg.messbild_setzen(conn, d.get("id"), d.get("scryfall_id"), d.get("foil"), d.get("language"), d.get("merkmale"), fetch)
        elif d.get("aktion") in ("weg", "leeren"):
            mtg.messbild_weg(conn, ordner, int(d.get("id") or 0) if d["aktion"] == "weg" else None)
        elif method == "POST":
            raise ValueError("Unbekannte Aktion")
        return _json(mtg.messbilder(conn, ordner))
    return _json({"error": "nicht gefunden"}, 404)


def api_commanders(conn, q=None, names=None):
    """Ranking aus den schon geladenen EDHREC-Daten; fehlende lädt der Job „commanders“ bzw. `mtg commanders`. mode: machbar, beliebt, geheimtipp oder
    guenstig (rechnet den Zukauf, braucht beim ersten Mal Scryfall); min_decks: nur Commander mit so vielen EDHREC-Decks (Standard je Modus)."""
    q = q or {}
    rank, pending = deckbuild.ranking(conn, only_cached=True)
    tags = bool(conn.execute("SELECT 1 FROM tags WHERE tag = 'ramp' LIMIT 1").fetchone())
    mode = q.get("mode") if q.get("mode") in deckbuild.MODES else "machbar"
    mind = max(0, int(q["min_decks"])) if q.get("min_decks") not in (None, "") else deckbuild.MODE_MIN_DECKS.get(mode, 0)
    items = deckbuild.rank_modes(conn, rank, mode, mind, names or sources.scryfall_names)
    return {"items": items[:100], "total": len(items), "all": len(rank), "pending": pending, "tags": tags, "mode": mode, "min_decks": mind}


def api_prices(conn, q=None, rows=None):
    """Preisbewegung der Karten im Besitz (mtg.movers), jede mit den Stapeln ihrer Kopien (rows: schon berechneter Sortier-Plan)."""
    m = mtg.movers(conn, int((q or {}).get("days") or mtg.MOVE_DAYS))
    stapel = mtg.stacks_by_card(mtg.plan(conn) if rows is None else rows)
    leer = {"deck": [], "keep": 0, "sell": 0, "bulk": 0}
    return m | {k: [e | {"stacks": stapel.get(e["oracle_id"], leer)} for e in m[k]] for k in ("up", "down")}


def api_gaps(conn, names=None):
    """Karten, die auf den Listen mehrerer deiner besten Commander stehen und dir fehlen (deckbuild.gaps)."""
    return deckbuild.gaps(conn, fetch_names=names or sources.scryfall_names)


def api_set_binder(conn, code, suche=None):
    """Binder-Ansicht eines Sets: alle Drucke in Sammlernummer-Reihenfolge, je mit deinen Kopien (0 = fehlt)."""
    if not code:
        raise ValueError("Welches Set?")
    karten = mtg.set_karten(conn, code, suche)
    hat = {r[0]: r[1] for r in conn.execute(f"SELECT col.scryfall_id, SUM(col.qty) FROM collection col JOIN cards c USING (scryfall_id) WHERE {mtg.OWNED} "
                                             f"AND c.set_code = ? GROUP BY col.scryfall_id", (code.upper(),))}
    oids = {r[0]: r[1] for r in conn.execute("SELECT scryfall_id, oracle_id FROM cards WHERE set_code = ?", (code.upper(),))}
    info = mtg.sets_info(conn).get(code.upper()) or {}
    return {"set": code.upper(), "name": info.get("name") or code.upper(), "size": info.get("size") or len(karten),
            "karten": [k | {"qty": hat.get(k["id"], 0), "oracle_id": oids.get(k["id"])} for k in karten]}


RULINGS_MAX_AGE_TAGE = 30


def api_rulings(conn, oracle_id, holen=None):
    """Rulings einer Karte (Scryfall, 30 Tage gemerkt). Die App zeigt sie nur an, sie schreibt keine Regeln selbst."""
    r = conn.execute("SELECT json, fetched_at FROM rulings WHERE oracle_id = ?", (oracle_id,)).fetchone()
    if r and r["fetched_at"][:10] >= (date.today() - timedelta(days=RULINGS_MAX_AGE_TAGE)).isoformat():
        return {"items": json.loads(r["json"]), "at": r["fetched_at"]}
    c = conn.execute("SELECT scryfall_id FROM cards WHERE oracle_id = ? LIMIT 1", (oracle_id,)).fetchone()
    if not c:
        raise ValueError("Unbekannte Karte")
    items = [{"date": x.get("published_at"), "source": x.get("source"), "text": x.get("comment")} for x in (holen or sources.scryfall_rulings)(c[0])]
    with conn:
        conn.execute("INSERT OR REPLACE INTO rulings VALUES (?,?,?)", (oracle_id, json.dumps(items, ensure_ascii=False), mtg.now_iso()))
    return {"items": items, "at": mtg.now_iso()}


def api_wunsch(conn, body, names=None):
    """Wunschliste: {scryfall_id | oracle_id | name, qty, max_eur, note} setzt einen Eintrag (Name: Karte über Scryfall suchen), {oracle_id, weg: true} entfernt ihn."""
    d = json.loads(body or b"{}")
    if d.get("weg"):
        return {"weg": mtg.wunsch_weg(conn, d.get("oracle_id") or "")}
    sid = d.get("scryfall_id")
    if not sid and d.get("oracle_id"):
        r = conn.execute("SELECT scryfall_id FROM cards WHERE oracle_id = ? ORDER BY updated_at DESC LIMIT 1", (d["oracle_id"],)).fetchone()
        sid = r and r[0]
    if not sid and (d.get("name") or "").strip():
        r = deckbuild.card_rows(conn, [d["name"].strip()], names or sources.scryfall_names)[d["name"].strip()]
        sid = r and r["scryfall_id"]
        if not sid:
            raise ValueError(f"Keine Karte „{d['name'].strip()}“ gefunden")
    if not sid:
        raise ValueError("Welche Karte? Name angeben")
    m = d.get("max_eur")
    mtg.wunsch_setzen(conn, sid, d.get("qty") or 1, float(str(m).replace(",", ".")) if m not in (None, "") else None, d.get("note"))
    return {"ok": True}


def api_bracket(conn, body, spellbook=None):
    """Bracket-Einschätzung einer Deckliste: body {"text": Deckliste}."""
    text = (json.loads(body or b"{}").get("text") or "").strip()
    if not text:
        raise ValueError("Keine Deckliste angegeben")
    return deckbuild.bracket_check(text, spellbook or sources.spellbook_bracket)


def api_decks(conn):
    """In der App gebaute Decks (items) und fertige Decks aus Binder bzw. Deckliste (fertig)."""
    return {"items": deckbuild.decks_list(conn), "fertig": deckbuild.binder_decks(conn)}


def api_binder_deck(conn, name, body=None):
    """Fertiges Deck anzeigen; mit body {"commander": oracle_id} den Commander festlegen."""
    if body is not None:
        d = json.loads(body or b"{}")
        if d.get("commander") is not None:
            alt = conn.execute("SELECT value FROM meta WHERE key = ?", ("deckbinder:" + name,)).fetchone()
            neu = (json.loads(alt[0]) if alt else {}) | {"commanders": [d["commander"]] if d["commander"] else []}
            with conn:
                conn.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", ("deckbinder:" + name, json.dumps(neu)))
    return deckbuild.binder_deck(conn, name)


def api_plan_decks(conn, body, edhrec=None, names=None):
    """Mehrere Decks gleichzeitig aus freien Karten (nur Commander mit geladenen EDHREC-Daten); save speichert alle."""
    d = json.loads(body or b"{}")
    n = max(1, min(int(d.get("count") or 3), 8))
    decks = deckbuild.plan_decks(conn, n, int(d.get("bracket") or 3), bool(d.get("save")), fetch=edhrec,
                                 fetch_names=names or sources.scryfall_names, only_cached=True)
    return {"items": decks}


def api_build(conn, body, edhrec=None, names=None):
    d = json.loads(body or b"{}")
    deck = deckbuild.build(conn, d.get("commander") or "", int(d.get("bracket") or 3), fetch=edhrec, fetch_names=names or sources.scryfall_names,
                           theme=d.get("theme") or "auto")
    if d.get("save"):
        deck["id"] = deckbuild.save_deck(conn, deck)
    return deck


def api_import(conn, raw, filename, q, fetch=None, lookup=None, archive=None):
    """Universal-Import (Format am Inhalt erkannt). dry=1: Vorschau ohne Speichern; binder: Ziel-Binder bzw. Deckname;
    commander: oracle_id für Decklisten; force=1: auch bei mehr als 25 % Verlust."""
    if len(raw) > MAX_IMPORT:
        raise ValueError("Datei ist größer als 20 MB")
    res = mtg.import_file(conn, raw, filename or "Import.csv", binder=q.get("binder") or None, commander=q.get("commander") or None,
                          dry_run=q.get("dry") == "1", force=q.get("force") == "1", fetch=fetch or mtg._fetch,
                          lookup=lookup or mtg._lookup, archive=archive or ARCHIVE)
    return {**res, "format_label": mtg.FORMATS[res["format"]], "text": mtg.format_import(res)}


# --- Hintergrund-Jobs: Commander-Daten (Rollen-Tags + EDHREC) und Preise, Fortschritt per GET /api/jobs -------------

JOBS = {}
_jobs_lock = threading.Lock()


def job_commanders(conn, job, edhrec=None, search=None):
    """Rollen-Tags (Scryfall) und EDHREC-Seiten aller Commander-Kandidaten laden (1 Seite/s), dann Top-10 markieren."""
    job["label"] = "Rollen-Tags (Ramp, Draw …)"
    deckbuild.ensure_tags(conn, fetch=search, progress=lambda n, t: job.update(done=n, total=t))
    rank, _ = deckbuild.ranking(conn, fetch=edhrec, progress=lambda i, n, name: job.update(done=i, total=n, label=name))
    deckbuild.mark_top10(conn, rank)
    job.update(done=job["total"], label=f"{len(rank)} Commander bewertet")


def job_prices(conn, job, fetch=None):
    """Preise der Karten im Besitz auffrischen (älter als 24 h)."""
    job["label"] = "Preise von Scryfall"
    n = mtg.refresh_prices(conn, fetch or (lambda ids: sources.scryfall_cards(ids, progress=lambda d, t: job.update(done=d, total=t))))
    job.update(label=f"{n} Preise aktualisiert")


def job_combos(conn, job, karten=None, combos=None):
    """Combos der ganzen Sammlung (Spellbook): erst die Liste der Combo-Karten (einmal im Monat, ca. 75 Seiten), dann je drei Farben eine Anfrage."""
    job["label"] = "Combo-Karten von Commander Spellbook"
    r = deckbuild.sammlung_combos(conn, karten or (lambda: sources.spellbook_combo_karten(progress=lambda n: job.update(done=n, total=0, label=f"{n} Combo-Karten"))),
                                  combos, progress=lambda i, n: job.update(done=i, total=n, label="Combos je drei Farben"))
    job.update(label=f"{len(r['fertig'])} Combos fertig, {len(r['fast'])} fehlt eine Karte")


def job_vektoren(conn, job, embed=None):
    """Embeddings aller Karten im Besitz über das lokale Ollama (für „Ähnliche Karten“, PLAN E15)."""
    job["label"] = "Ähnlichkeit berechnen (lokales Ollama)"
    n = llm.vektoren_laden(conn, embed, progress=lambda d, t: job.update(done=d, total=t))
    job.update(label=f"{n} Karten berechnet")


JOB_TYPES = {"commanders": job_commanders, "prices": job_prices, "combos": job_combos, "vektoren": job_vektoren}


def start_job(name, connect=None, scope=""):
    """Job im Hintergrund starten, je Sammlung (scope) und Name höchstens einer gleichzeitig. -> Status"""
    if name not in JOB_TYPES:
        raise ValueError("unbekannter Job")
    with _jobs_lock:
        if JOBS.get((scope, name), {}).get("running"):
            return dict(JOBS[(scope, name)])
        job = JOBS[(scope, name)] = {"name": name, "running": True, "done": 0, "total": 0, "label": "", "error": None, "started": mtg.now_iso(), "finished": None}

    def run():
        conn = (connect or mtg.connect)()
        try:
            JOB_TYPES[name](conn, job)
        except sources.QuelleAus as e:  # Phase 44: abgeschaltet, kein Abruf
            job["error"] = str(e)
        except (urllib.error.URLError, TimeoutError) as e:  # im Status zeigen statt still abbrechen
            job["error"] = f"Keine Verbindung ({getattr(e, 'reason', e)})"
        except ValueError as e:  # eigene, lesbare Meldungen (wie in dispatch)
            job["error"] = str(e)
        except Exception:  # unerwartet (PLAN E29): fester Satz mit Nummer, das Übrige nur auf stderr
            job["error"] = unerwartet(f"Job {name}")
        finally:
            conn.close()
            job.update(running=False, finished=mtg.now_iso())
    threading.Thread(target=run, daemon=True).start()
    return dict(job)


def api_jobs(scope=""):
    with _jobs_lock:
        return {n: dict(v) for (sc, n), v in JOBS.items() if sc == scope}


def _json(obj, code=200):
    return code, "application/json; charset=utf-8", json.dumps(obj, ensure_ascii=False).encode()


# --- Fehler, Protokoll, Proxy (Phase 40, PLAN E29) --------------------------------------------------------------------

FEHLER_500 = "Unerwarteter Fehler (Nummer {}). Unter dieser Nummer steht er im Protokoll des Servers."
HSTS = ("Strict-Transport-Security", "max-age=31536000")  # ein Jahr, ohne includeSubDomains; nur auf Antworten zu https-Anfragen
PROTOKOLL = False  # eine Zeile je Anfrage und je fehlgeschlagener Anmeldung; serve schaltet es ein (nicht auf 127.0.0.1 oder mit --log)


def _zeit():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def unerwartet(wo=""):
    """Unerwarteter Fehler, aufgerufen im except-Zweig: Klassenname, Text und Aufrufliste gehen nur auf stderr, unter einer zufälligen Nummer.
    -> der feste Satz mit derselben Nummer, das Einzige, was nach außen geht."""
    nr = secrets.token_hex(4)
    print(f"Fehler {nr} {_zeit()} {wo}\n{traceback.format_exc()}", file=sys.stderr, flush=True)
    return FEHLER_500.format(nr)


def hinter_proxy():
    """Sagt der Betreiber, dass ein Proxy davor steht (MTG_PROXY=1; compose.yaml und deploy/pappenheimer.service setzen es)? Nur dann glaubt
    der Server X-Forwarded-For und X-Forwarded-Proto: Ohne Proxy schreibt diese Köpfe der Absender selbst. Der Proxy muss beide selbst
    setzen und darf die des Absenders nicht durchreichen (Caddy tut das laut seiner Dokumentation, tailscale serve laut seinem Quelltext:
    docs/PLAN.md, Phase 40). Schickt er nichts, zählt die Gegenstelle der Verbindung (Handler._adresse)."""
    return os.environ.get("MTG_PROXY", "").strip() == "1"


def protokoll(adresse, text):
    """Eine Zeile ins Protokoll (stdout): Zeit, Absender-Adresse, Text. Nie Abfrage, Cookie oder Passwort."""
    if PROTOKOLL:
        print(f"{_zeit()} {adresse or '-'} {text}", flush=True)


def dispatch(conn, method, path, q, body=b"", filename="", fetch=None, edhrec=None, names=None, lookup=None, spellbook=None, db=None, archive=None, rulings=None,
             set_suche=None, sets=None, lesen=None):
    """-> (Statuscode, Content-Type, Bytes). db: Pfad der aktiven Sammlung (für Hintergrund-Jobs), archive: deren Import-Archiv."""
    try:
        if path == "/api/erfassen":
            return _json(api_erfassen(conn, q, body if method == "POST" else None, fetch))
        if path.startswith("/api/messbild"):
            return api_messbild(conn, method, path, q, body, db, fetch)
        if path == "/api/beispiel" and method in ("GET", "POST"):
            try:
                return _json(api_beispiel(conn, json.loads(body or b"{}") if method == "POST" else None, fetch, lookup))
            except urllib.error.URLError as e:  # ohne Netz: nichts angelegt (mtg.beispiel_laden holt zuerst alles, was Netz braucht)
                return _json({"error": f"Keine Verbindung zu Scryfall ({getattr(e, 'reason', e)}). Die Beispielsammlung braucht einmal Netz, damit die App die Kartendaten "
                                       f"holen kann. Es wurde nichts angelegt."}, 502)
        if path == "/api/set-liste" and method == "GET":
            return _json({"items": mtg.set_liste(conn, sets, neu=q.get("neu") == "1")})
        if path in ("/api/kopie", "/api/binder-name", "/api/verkauft", "/api/verkauft-zurueck", "/api/uebernehmen") and method == "POST":
            return _json(api_bestand(conn, path, json.loads(body or b"{}")))
        if path == "/api/posteingang":  # Phase 27: Schalter, Ordner, letztes Ergebnis; jetzt=1 prüft sofort
            d = json.loads(body or b"{}") if method == "POST" else {}
            if "an" in d:
                mtg.posteingang_an(conn, bool(d["an"]))
            if d.get("jetzt"):
                mtg.posteingang(conn, mtg.inbox_fuer(db), fetch or mtg._fetch, lookup or mtg._lookup, archive or ARCHIVE)
            r = conn.execute("SELECT value FROM meta WHERE key = 'posteingang:ergebnis'").fetchone()
            return _json({"an": mtg.posteingang_an(conn), "ordner": str(mtg.inbox_fuer(db)), "ergebnis": json.loads(r[0]) if r else None})
        if path == "/api/bestand.csv" and method == "GET":
            return 200, "text/csv; charset=utf-8", bestand_export(conn, q.get("binder") or None)
        if path == "/api/undo" and method == "POST":
            return _json(mtg.undo_import(conn))
        if path == "/api/commanders" and method == "GET":
            return _json(api_commanders(conn, q, names))
        if path == "/api/prices" and method == "GET":
            return _json(api_prices(conn, q))
        if path == "/api/gaps" and method == "GET":
            return _json(api_gaps(conn, names))
        if path == "/api/bracket" and method == "POST":
            return _json(api_bracket(conn, body, spellbook))
        if path == "/api/decks" and method == "GET":
            return _json(api_decks(conn))
        if path == "/api/build" and method == "POST":
            return _json(api_build(conn, body, edhrec, names))
        if path == "/api/plan-decks" and method == "POST":
            return _json(api_plan_decks(conn, body, edhrec, names))
        if path == "/api/notiz" and method == "POST":
            d = json.loads(body or b"{}")
            mtg.notiz_setzen(conn, tuple(d.get("key") or ()), d.get("ort"), d.get("verliehen"), d.get("notiz"))
            return _json({"ok": True})
        if path == "/api/set-binder" and method == "GET":
            return _json(api_set_binder(conn, q.get("set") or "", set_suche))
        if path == "/api/rueckblick" and method == "GET":
            return _json(mtg.rueckblick(conn, q.get("jahr")))
        if path == "/api/bericht" and method == "GET":
            return _json(mtg.bericht(conn, q.get("kaufpreise") == "1"))
        if path == "/api/dossier" and method == "GET":
            text = deckbuild.dossier(q.get("name") or "")
            return _json({"html": deckbuild.dossier_html(text) if text else None})
        if path == "/api/spiele" and method == "GET":
            return _json(deckbuild.spiele(conn))
        if path == "/api/spiel" and method == "POST":
            d = json.loads(body or b"{}")
            return _json({"id": deckbuild.spiel_neu(conn, d.get("deck"), d.get("won"), d.get("pod"), d.get("players"), d.get("turns"), d.get("notes"))})
        if path == "/api/spiel-weg" and method == "POST":
            with conn:
                conn.execute("DELETE FROM games WHERE id = ?", (int(json.loads(body or b"{}").get("id") or 0),))
            return _json({"ok": True})
        if path == "/api/gruppe" and method == "POST":
            d = json.loads(body or b"{}")
            return _json({"id": deckbuild.gruppe_neu(conn, d.get("pod"), d.get("spieler"), d.get("deck"), d.get("bracket"), d.get("farben"),
                                                     names or sources.scryfall_names)})
        if path == "/api/gruppe-weg" and method == "POST":
            with conn:
                conn.execute("DELETE FROM gruppe WHERE id = ?", (int(json.loads(body or b"{}").get("id") or 0),))
            return _json({"ok": True})
        if path == "/api/deck-bracket" and method == "POST":
            d = json.loads(body or b"{}")
            deckbuild.deck_bracket_setzen(conn, d.get("name") or "", int(d["bracket"]) if d.get("bracket") else None)
            return _json({"ok": True})
        if path == "/api/tisch" and method == "GET":
            return _json(deckbuild.tisch(conn, [i for i in (q.get("ids") or "").split(",") if i.isdigit()]))
        if path == "/api/rulings" and method == "GET":
            return _json(api_rulings(conn, q.get("oracle_id") or "", rulings))
        if path == "/api/llm" and method == "GET":
            return _json(llm.status(conn))
        if path in ("/api/aehnlich", "/api/frage"):  # lokales Ollama: eigene Meldung, wenn es nicht läuft
            try:
                if path == "/api/aehnlich" and method == "GET":
                    return _json({"items": llm.aehnlich(conn, q.get("oracle_id") or "")})
                if method == "POST":
                    return _json(llm.frage(json.loads(body or b"{}").get("text")))
            except (urllib.error.URLError, TimeoutError) as e:
                return _json({"error": f"Das lokale Ollama antwortet nicht ({getattr(e, 'reason', e)}). Läuft es? Der Rest der App geht weiter."}, 502)
        if path == "/api/combos" and method == "GET":
            return _json(deckbuild.sammlung_combos_cached(conn) or {"fertig": [], "fast": [], "at": None})
        if path == "/api/funktionen" and method == "GET":
            return _json({"items": [[k, label] for k, (label, _, _) in deckbuild.FUNCTIONS.items()]})
        if path == "/api/wuensche" and method == "GET":
            return _json({"items": mtg.wuensche(conn)})
        if path == "/api/wuensche.txt" and method == "GET":  # Textliste, zum Beispiel zum Einfügen bei Händlern
            return 200, "text/plain; charset=utf-8", "".join(f"{w['qty']} {w['name']}\n"
                                                              for w in mtg.wuensche(conn)).encode()
        if path == "/api/wunsch" and method == "POST":
            return _json(api_wunsch(conn, body, names))
        if path == "/api/bedarf" and method == "GET":
            return _json(deckbuild.bedarf(conn, edhrec, names or sources.scryfall_names))
        if path == "/api/deck-log" and method == "POST":
            d = json.loads(body or b"{}")
            mtg.deck_log_grund(conn, int(d.get("id") or 0), d.get("grund"))
            return _json({"ok": True})
        if path == "/api/improve" and method == "GET":  # Upgrade-Leiter: gespeichertes Deck (id) oder fertiges (binder)
            d = deckbuild.deck_detail(conn, int(q["id"])) if q.get("id") else deckbuild.binder_deck(conn, q.get("binder") or "")
            if not d:
                return _json({"error": "unbekanntes Deck"}, 404)
            return _json(deckbuild.improve(conn, d, names or sources.scryfall_names, fetch=edhrec))
        if path == "/api/pick" and method == "GET":
            r = deckbuild.pick_list(conn, int(q.get("id") or 0), q.get("order") or "set")
            return _json(r) if r else _json({"error": "unbekanntes Deck"}, 404)
        if path == "/api/zerlegen" and method == "GET":
            r = deckbuild.zerlegen(conn, int(q["id"]) if (q.get("id") or "").isdigit() else q.get("binder") or "")
            return _json(r) if r else _json({"error": "unbekanntes Deck"}, 404)
        if path == "/api/proxy" and method == "POST":
            if not mtg.proxy_blatt():  # E23: aus, bis das Hauptkonto es einschaltet; die Ansicht erklärt es, die Schnittstelle antwortet nicht
                return _json({"error": PROXY_AUS, "aus": "proxy"}, 403)
            return _json(deckbuild.proxy_liste(conn, json.loads(body or b"{}").get("text"), names or sources.scryfall_names))
        if path in ("/api/binder-deck", "/api/binder-deck.txt"):
            if method == "POST" and q.get("delete") == "1":
                return _json({"deleted": mtg.delete_binder(conn, q.get("name") or "")})
            d = api_binder_deck(conn, q.get("name") or "", body if method == "POST" else None)
            if not d:
                return _json({"error": "unbekanntes Deck"}, 404)
            if path.endswith(".txt"):
                return 200, "text/plain; charset=utf-8", deckbuild.export_text(d).encode()
            return _json(d)
        if path == "/api/jobs":
            scope = str(db or "")
            return _json(start_job(q.get("start"), (lambda: mtg.connect(db)) if db else None, scope) if method == "POST" else api_jobs(scope))
        if path == "/api/scan":
            return _json(api_scan(conn, q, body if method == "POST" else None, set_suche))
        if path == "/api/scan/katalog":
            return _json(api_scan_katalog(conn, q, body if method == "POST" else None))
        if path == "/api/scan/suche" and method == "POST":
            return _json(api_scan_suche(conn, body))
        if path == "/api/scan/titel" and method == "POST":
            return _json(api_scan_titel(conn, body, lesen))
        if path == "/api/settings":
            return _json(api_settings(conn, body if method == "POST" else None))
        if path == "/api/fertige-decks":
            return _json(api_fertige_decks(conn, json.loads(body or b"{}") if method == "POST" else None))
        if method == "GET" and path == "/api/binders":
            return _json({"items": api_binders(conn)})
        if path.startswith("/api/deck/"):
            teil = path[len("/api/deck/"):]
            if method == "POST" and teil.endswith("/delete"):
                return _json({"deleted": deckbuild.delete_deck(conn, int(teil[:-len("/delete")]))})
            d = deckbuild.deck_detail(conn, int(teil[:-4] if teil.endswith(".txt") else teil))
            if not d:
                return _json({"error": "unbekanntes Deck"}, 404)
            if teil.endswith(".txt"):
                return 200, "text/plain; charset=utf-8", deckbuild.export_text(d).encode()
            return _json(d)
        if method == "GET" and path == "/api/summary":
            return _json(api_summary(conn))
        if method == "GET" and path == "/api/cards":
            return _json(api_cards(conn, q))
        if method == "GET" and path == "/api/sets":
            return _json(api_sets(conn, q))
        if method == "GET" and path.startswith("/api/card/"):
            karte = api_card(conn, path[len("/api/card/"):])
            return _json(karte) if karte else _json({"error": "unbekannte Karte"}, 404)
        if method == "GET" and path == "/api/sort":
            return _json(api_sort(conn, q))
        if method == "GET" and path == "/api/sell":
            return _json(api_sell(conn, q))
        if method == "GET" and path in ("/api/sell.csv", "/api/sell.txt"):
            return 200, *sell_export(conn, q | ({"format": "text"} if path.endswith(".txt") else {}))
        if method == "POST" and path == "/api/status":
            return _json(api_status(conn, body))
        if method == "POST" and path == "/api/import":
            return _json(api_import(conn, body, filename, q, fetch, lookup, archive))
    except ValueError as e:
        return _json({"error": str(e)}, 400)
    except sources.QuelleAus as e:  # Phase 44: vom Betreiber abgeschaltet, nichts wurde abgerufen; quelle lässt die Oberfläche auf die Seite „Quellen“ zeigen
        return _json({"error": str(e), "quelle": e.quelle}, 409)
    except urllib.error.URLError as e:  # Scryfall, EDHREC oder Spellbook nicht erreichbar
        return _json({"error": f"Keine Verbindung zu Scryfall/EDHREC ({getattr(e, 'reason', e)}). Ist der Rechner online? Es wurde nichts geändert."}, 502)
    return _json({"error": "nicht gefunden"}, 404)


# --- Konten, Anmeldung, Sammlungen (Phase 13, PLAN E14) ------------------------------------------------------------

KONTO_PFADE = ("/api/session", "/api/login", "/api/logout", "/api/konten", "/api/backup.zip", "/api/sicherung", "/api/quellen", "/api/katalog", "/api/proxy-blatt", "/api/update", "/api/qr")


def _cookie(token, sicher):
    """Sitzungs-Cookie: nur für diese Seite (SameSite=Strict), nicht für Skripte lesbar; hinter HTTPS nur verschlüsselt. token None = löschen."""
    teile = [f"mtg={token or ''}", "Path=/", "HttpOnly", "SameSite=Strict", f"Max-Age={konten.SITZUNG_S if token else 0}"]
    return "; ".join(teile + (["Secure"] if sicher else []))


def _lokal_haupt(kc):
    """Modus „lokal“ ohne Sitzung: wer auf 127.0.0.1 fragt, ist das Hauptkonto in seiner eigenen Sammlung."""
    h = konten.haupt(kc)
    return {"konto": h["name"], "rolle": "haupt", "anzeige": h["anzeige"], "aktiv": h["name"], "aktiv_rolle": "haupt"}


def sammlung(m, token):
    """Sitzung und Datenbank der aktiven Sammlung. -> (Sitzung oder None, Pfad oder None)"""
    if m == "einfach":
        return None, Path(mtg.DB)
    with closing(konten.connect()) as kc:
        s = konten.sitzung(kc, token) or (_lokal_haupt(kc) if m == "lokal" else None)
    return s, (konten.db_pfad(s["aktiv"], s["aktiv_rolle"]) if s else None)


def _bestand(p):
    """Karten und Wert einer Sammlung, ohne sie anzulegen."""
    if not Path(p).exists():
        return 0, 0.0
    with closing(sqlite3.connect(f"file:{Path(p).as_posix()}?mode=ro", uri=True)) as c:
        try:
            return tuple(c.execute(f"SELECT COALESCE(SUM(col.qty), 0), COALESCE(SUM(col.qty * {mtg.PRICE}), 0) FROM collection col "
                                   f"LEFT JOIN cards c USING (scryfall_id) WHERE {mtg.OWNED}").fetchone())
        except sqlite3.OperationalError:  # leere Datei
            return 0, 0.0


def _info(kc, m, s):
    return {"version": version.VERSION, "modus": m, "angemeldet": bool(s), "quellen": sources.zustand()["quellen"], "proxy": mtg.proxy_blatt(), "konto": s and s["konto"], "anzeige": s and s["anzeige"], "rolle": s and s["rolle"],
            "aktiv": s and s["aktiv"], "sammlungen": [{"name": k["name"], "anzeige": k["anzeige"], "rolle": k["rolle"]} for k in konten.sichtbar(kc, s)] if s else []}


def _backup():
    buf = io.BytesIO()
    konten.sicherung(buf)
    konten.sicherung_geladen()  # zählt als Sicherung außer Haus (Phase 27): sie liegt danach auch auf dem Gerät, das sie geladen hat
    return 200, "application/zip", buf.getvalue(), {"Content-Disposition": f'attachment; filename="mtg-sicherung-{date.today()}.zip"'}


def _sicherung(method, d):
    """GET /api/sicherung: wann zuletzt eine Sicherung das Haus verlassen hat (konten.aussen) und der zweite Ordner (konten.ordner_info).
    POST {ordner: {an, pfad}} stellt ihn ein (Phase 42); beides nur fürs Hauptkonto (der Aufrufer prüft das). Die Einstellung gehört der ganzen
    Installation und steht in der Hauptsammlung, auch wenn das Hauptkonto gerade die eines Unterkontos offen hat."""
    with closing(mtg.connect()) as conn:
        if method == "POST":
            o = d.get("ordner")
            if not isinstance(o, dict) or not isinstance(o.get("pfad", ""), str):
                raise ValueError("Erwartet: {ordner: {an, pfad}}")
            konten.ordner_setzen(conn, o.get("an") is True, o.get("pfad", ""))
        return konten.aussen() | {"ordner": konten.ordner_info(conn)}


def _quellen(method, d, haupt):
    """GET /api/quellen: je Quelle Zweck, was hingeschickt wird, wie oft, Link und ob sie an ist (sources.beschreibung). POST {edhrec, spellbook,
    cardmarket: bool} stellt die Schalter (PLAN E25), nur das Hauptkonto und nur ohne MTG_QUELLEN. Die Schalter gelten für die ganze Installation und
    stehen in meta der Hauptsammlung, auch wenn das Hauptkonto gerade die Sammlung eines Unterkontos offen hat."""
    if method == "POST":
        if not haupt:
            raise PermissionError("Die Quellen stellt nur das Hauptkonto ein")
        with closing(mtg.connect()) as conn:
            sources.setzen(conn, d)
    return sources.beschreibung() | {"haupt": haupt}


UPDATE_KEY = "update:letzte"  # meta der Hauptsammlung: das letzte Ergebnis von „Nach Updates suchen“ (Phase 50)


def api_update(method, haupt):
    """Phase 50 (PLAN E31): Nach Updates suchen, nur auf Knopfdruck und nur das Hauptkonto; nichts davon läuft im täglichen Lauf. GET: das letzte
    Ergebnis. POST: fragt GitHub nach der neuesten Veröffentlichung und merkt sie mit Zeit in meta der Hauptsammlung. Erreicht die Anfrage GitHub nicht
    oder bremst es, steht das als „fehler“ in der Antwort (kein Fehlercode), und das letzte Ergebnis bleibt stehen. „neu“ rechnet jedes Lesen neu: Nach
    einem Update zeigt ein altes Ergebnis nicht mehr „ist da“."""
    if not haupt:
        raise PermissionError("Nach Updates sucht nur das Hauptkonto")
    fehler = None
    with closing(mtg.connect()) as conn:
        if method == "POST":
            try:
                neu = sources.neueste_version()
                with conn:
                    conn.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (UPDATE_KEY, json.dumps({"at": mtg.now_iso(), **(neu or {})}, ensure_ascii=False)))
            except urllib.error.HTTPError as e:
                fehler = ("GitHub bremst gerade (zu viele Anfragen von dieser Adresse). Versuch es später noch einmal." if e.code in (403, 429)
                          else f"GitHub antwortet mit einem Fehler (HTTP {e.code}).")
            except (OSError, ValueError):  # kein Netz, Zeitüberschreitung oder keine lesbare Antwort
                fehler = "Keine Verbindung zu GitHub oder keine lesbare Antwort. Ist der Rechner online?"
        zeile = conn.execute("SELECT value FROM meta WHERE key = ?", (UPDATE_KEY,)).fetchone()
    try:
        letzte = json.loads(zeile[0]) if zeile else None
    except ValueError:
        letzte = None
    if isinstance(letzte, dict):
        neuer = sources.nummern(letzte.get("version"))
        letzte["neu"] = bool(neuer and neuer > sources.nummern(version.VERSION))
        letzte["sicherheit"] = letzte["neu"] and "sicherheit" in str(letzte.get("titel") or "").lower()
    else:
        letzte = None
    return {"eigene": version.VERSION, "letzte": letzte, "fehler": fehler}


def api_qr(d, haupt):
    """POST /api/qr {text}: der QR-Code zu einer Adresse als SVG (qr.svg: ohne Skript und Verweise), damit sich das Handy mit einem Scan mit der Seite
    verbindet und sie dort installieren lässt. Nur das Hauptkonto; text ist die Adresse der Seite (höchstens 106 Bytes, sonst eine lesbare Meldung)."""
    if not haupt:
        raise PermissionError("Den QR-Code zeigt nur das Hauptkonto")
    text = d.get("text")
    if not isinstance(text, str) or not text.startswith(("http://", "https://")):
        raise ValueError("Erwartet: {text: Adresse der Seite}")
    return {"svg": qr.svg(text)}


def _katalog_job(was, bulk=None):
    """Hintergrund-Job für die Gesamtdaten (Phase 45): „katalog“ lädt den Katalog aller Papier-Drucke, „namen“ die deutschen Kartennamen. Der
    Zustand (Fortschritt in Bytes) steht sofort da, sonst sähe die Anzeige im ersten Augenblick nichts. Läuft oder lief heute schon ein Abruf
    (auch der tägliche Lauf, auch von einem anderen Gerät), startet nichts (_abruf_beginnen). -> True, wenn gestartet"""
    kat, heute = mtg.katalog_pfad(), date.today().isoformat()
    zustand = _abruf_beginnen(was, kat, heute)
    if not zustand:
        return False

    def lauf():  # was der Job tut, steht wie beim täglichen Lauf im Protokoll des Servers (stdout)
        try:
            if was == "katalog":
                kuerzel = _katalog_stand_aller()[0]
                s = _abruf_laufen(zustand, was, lambda strom: katalog.bauen(strom, kat, kuerzel, heute), bulk)
                print(f"Hintergrund-Job: Katalog: {s['drucke']} Papier-Drucke, {s['aussehen']} Aussehen (Erfassen geöffnet)", flush=True)
            else:
                n = _abruf_laufen(zustand, was, lambda strom: katalog.namen_bauen(strom, kat, tag=heute), bulk)
                print(f"Hintergrund-Job: Katalog: {n} deutsche Kartennamen (Schalter eingeschaltet)", flush=True)
        except Exception:  # steht im Zustand (error), nie den Server mitreißen
            if not zustand["error"]:
                zustand["error"] = unerwartet(f"Job {was}")
            zustand.update(running=False, finished=zustand["finished"] or mtg.now_iso())
            print(f"Hintergrund-Job: {'Katalog' if was == 'katalog' else 'Kartennamen'} nicht geladen ({zustand['error']})", flush=True)
    threading.Thread(target=lauf, daemon=True).start()
    return True


def _katalog_info(haupt):
    """Stand für die Einstellungen des Scanners: der Katalog (oder None), die deutschen Namen mit Schalter, Größen und beide Abrufe."""
    kat = mtg.katalog_pfad()
    try:
        s, n = katalog.stand(kat), katalog.namen_stand(kat)
    except sqlite3.Error:
        s = n = None
    with closing(mtg.connect()) as conn:
        an, tag = katalog.namen_schalter(conn, kat), katalog.genutzt(conn)
    zeig = lambda was: dict(_abruf[was]) if was in _abruf else None
    return {"katalog": s and {"drucke": s["drucke"], "aussehen": s["aussehen"], "gebaut": s["gebaut"], "mb": round(s["bytes"] / 1e6)},
            "mb": katalog.KATALOG_MB, "job": zeig("katalog"), "genutzt": tag,
            "namen": {"an": an, "darf": bool(haupt), "moeglich": bool(titel_programm()), "mb": katalog.DEUTSCH_MB, "zahl": n and n["zahl"], "gebaut": n and n["gebaut"],
                      "job": zeig("namen")}}


def api_katalog(method, d, haupt, bulk=None):
    """GET /api/katalog: Stand des Katalogs und der deutschen Namen mit Abrufen im Gang (_katalog_info). POST {oeffnen: true}: „Erfassen“ wurde geöffnet
    (Merker für die ganze Installation, katalog.genutzt_merken); fehlt der Katalog, lädt ihn sofort ein Hintergrund-Job. POST {namen: bool}: der Schalter
    „Deutsche Kartennamen laden“, nur das Hauptkonto; an, mit Katalog und Tesseract, lädt sie sofort ein Hintergrund-Job (sonst der tägliche Lauf). Die Merker
    gehören der ganzen Installation und stehen in meta der Hauptsammlung, auch wenn ein Unterkonto sie auslöst (PLAN E26)."""
    if method == "POST":
        kat, heute = mtg.katalog_pfad(), date.today().isoformat()
        namen = d.get("namen")
        if namen is not None and not isinstance(namen, bool):
            raise ValueError("Erwartet: {namen: an oder aus}")
        if namen is not None and not haupt:
            raise PermissionError("Die deutschen Kartennamen stellt nur das Hauptkonto ein")
        with closing(mtg.connect()) as conn:
            if d.get("oeffnen") is True:
                katalog.genutzt_merken(conn, heute)
            if namen is not None:
                katalog.namen_schalter_setzen(conn, namen)
        if d.get("oeffnen") is True and not Path(kat).exists():
            _katalog_job("katalog", bulk)
        if namen and Path(kat).exists() and titel_programm() and katalog.namen_faellig(kat, heute):
            _katalog_job("namen", bulk)
    return _katalog_info(haupt)


def _anmelden(kc, name, pw, adresse):
    """konten.anmelden mit der Adresse des Absenders (Sperre je Adresse und Konto, PLAN E29); was scheitert, steht mit Adresse und Konto im
    Protokoll. Den Namen nur, wenn es das Konto gibt (sonst „-“): Wer sein Passwort ins Namensfeld tippt, soll es dort nicht wiederfinden."""
    try:
        return konten.anmelden(kc, name, pw, adresse=adresse)
    except (ValueError, konten.Gesperrt) as e:
        try:
            n = konten.kurz(name)
        except ValueError:
            n = ""
        art = "abgewiesen, zu viele zugleich" if isinstance(e, konten.Ausgelastet) else "gesperrt" if isinstance(e, konten.Gesperrt) else "fehlgeschlagen"
        protokoll(adresse, f"Anmeldung {art} konto={n if n and konten.konto(kc, n) else '-'}")
        raise


def api_konto(method, path, body, token, sicher=False, adresse=""):
    """Anmeldung, Sitzung, Sammlungswechsel, Konten und Sicherung. adresse: Absender (Handler._adresse), ohne zählt die Sperre je Konto.
    -> (Statuscode, Content-Type, Bytes, zusätzliche Header)"""
    try:
        d = json.loads(body or b"{}") if method == "POST" else {}
        m = konten.modus()
        if m == "einfach":
            if path == "/api/session" and method == "GET":
                return (*_json({"version": version.VERSION, "modus": m, "angemeldet": True, "rolle": "haupt", "sammlungen": [], "quellen": sources.zustand()["quellen"], "proxy": mtg.proxy_blatt()}), {})
            if path == "/api/backup.zip" and method == "GET":
                return _backup()
            if path == "/api/sicherung":
                return (*_json(_sicherung(method, d)), {})
            if path == "/api/quellen":  # ohne Konten ist der Betreiber das Hauptkonto
                return (*_json(_quellen(method, d, True)), {})
            if path == "/api/proxy-blatt":
                return (*_json(_proxy_blatt(method, d, True)), {})
            if path == "/api/update":
                return (*_json(api_update(method, True)), {})
            if path == "/api/qr" and method == "POST":
                return (*_json(api_qr(d, True)), {})
            if path == "/api/katalog":
                return (*_json(api_katalog(method, d, True)), {})
            if path == "/api/konten" and method == "POST" and d.get("aktion") == "add":  # erstes Konto = Hauptkonto, die bisherige Sammlung gehört ihm
                with closing(konten.connect()) as kc:
                    n = konten.anlegen(kc, d.get("name") or "", d.get("passwort") or None, ist_haupt=True)
                    neu = _anmelden(kc, n, d["passwort"], adresse) if d.get("passwort") else None
                    return (*_json(_info(kc, konten.modus(), konten.sitzung(kc, neu) or _lokal_haupt(kc))),
                            {"Set-Cookie": _cookie(neu, sicher)} if neu else {})
            raise ValueError("Erst ein Hauptkonto anlegen")
        with closing(konten.connect()) as kc:
            s = konten.sitzung(kc, token)
            if path == "/api/login" and method == "POST":
                if m != "anmeldung":
                    raise ValueError("Hier ist keine Anmeldung nötig")
                neu = _anmelden(kc, d.get("name") or "", d.get("passwort") or "", adresse)
                return (*_json(_info(kc, m, konten.sitzung(kc, neu))), {"Set-Cookie": _cookie(neu, sicher)})
            if path == "/api/logout" and method == "POST":
                konten.abmelden(kc, token)
                return (*_json({"ok": True}), {"Set-Cookie": _cookie(None, sicher)})
            if not s and m == "lokal":
                s = _lokal_haupt(kc)
            if path == "/api/session" and method == "GET":
                return (*_json(_info(kc, m, s)), {})
            if not s:
                return (*_json({"error": "Bitte anmelden", "login": True}, 401), {})
            haupt, extra = s["rolle"] == "haupt", {}
            if path == "/api/session" and method == "POST":
                if not konten.sitzung(kc, token):  # „lokal“ ohne Cookie: erst eine Sitzung, damit die Wahl bleibt
                    token = konten.ohne_passwort(kc)
                    extra["Set-Cookie"] = _cookie(token, sicher)
                konten.wechseln(kc, token, d.get("aktiv") or "", s)
                return (*_json(_info(kc, m, konten.sitzung(kc, token))), extra)
            if path == "/api/quellen":  # lesen darf jedes Konto (die Seite „Quellen“ ist das Ziel jedes Hinweises), stellen nur das Hauptkonto
                return (*_json(_quellen(method, d, haupt)), {})
            if path == "/api/proxy-blatt":  # lesen darf jedes Konto (die Ansicht erklärt, warum es aus ist), einschalten nur das Hauptkonto
                return (*_json(_proxy_blatt(method, d, haupt)), {})
            if path == "/api/update":  # Phase 50: nur das Hauptkonto, nur auf Knopfdruck
                return (*_json(api_update(method, haupt)), {})
            if path == "/api/qr" and method == "POST":  # QR-Code der Adresse fürs Handy, nur das Hauptkonto
                return (*_json(api_qr(d, haupt)), {})
            if path == "/api/katalog":  # jedes Konto öffnet „Erfassen“, den Schalter der Namen stellt nur das Hauptkonto
                return (*_json(api_katalog(method, d, haupt)), {})
            if path == "/api/backup.zip" and method == "GET" or path == "/api/sicherung":
                if not haupt:
                    raise PermissionError("Die Sicherung verwaltet nur das Hauptkonto")
                return _backup() if path == "/api/backup.zip" else (*_json(_sicherung(method, d)), {})
            if path == "/api/konten" and method == "GET":
                if not haupt:
                    raise PermissionError("Nur das Hauptkonto verwaltet Konten")
                return (*_json({"items": [k | dict(zip(("karten", "wert"), _bestand(k["db"]))) for k in konten.liste(kc)]}), {})
            if path == "/api/konten" and method == "POST":
                aktion, name = d.get("aktion"), d.get("name") or ""
                if aktion == "add":
                    if not haupt:
                        raise PermissionError("Nur das Hauptkonto legt Konten an")
                    return (*_json({"name": konten.anlegen(kc, name, d.get("passwort") or None)}), {})
                ziel = konten.kurz(name) if name else s["konto"]
                if aktion == "del":
                    if not haupt:
                        raise PermissionError("Nur das Hauptkonto entfernt Konten")
                    konten.entfernen(kc, ziel)
                    return (*_json({"ok": True}), {})
                if aktion == "passwort":
                    k = konten.konto(kc, ziel)
                    if not k:
                        raise ValueError(f"Kein Konto „{ziel}“")
                    if ziel != s["konto"] and not haupt:
                        raise PermissionError("Das Passwort eines anderen Kontos ändert nur das Hauptkonto")
                    if ziel == s["konto"] and k["pw"] and not konten.pw_ok(d.get("alt") or "", k["pw"]):
                        raise ValueError("Das bisherige Passwort stimmt nicht")
                    if not d.get("passwort") and k["rolle"] == "haupt":
                        raise ValueError("Das Hauptkonto braucht ein Passwort (entfernen nur auf dem Rechner selbst: mtg konto passwort NAME --ohne-passwort)")
                    konten.passwort(kc, ziel, d.get("passwort") or None)
                    if ziel == s["konto"]:  # die eigenen Sitzungen sind damit beendet: gleich wieder anmelden
                        neu = _anmelden(kc, ziel, d["passwort"], adresse)
                        return (*_json(_info(kc, konten.modus(), konten.sitzung(kc, neu))), {"Set-Cookie": _cookie(neu, sicher)})
                    return (*_json({"ok": True}), {})
            return (*_json({"error": "nicht gefunden"}, 404), {})
    except konten.Gesperrt as e:
        return (*_json({"error": str(e)}, 429), {})
    except PermissionError as e:
        return (*_json({"error": str(e)}, 403), {})
    except ValueError as e:
        return (*_json({"error": str(e)}, 400), {})


# --- Erste Einrichtung im Browser (Phase 43, PLAN E28) -----------------------------------------------------------------
# Ohne Hauptkonto auf einer anderen Adresse als 127.0.0.1 wartet der Server auf die Einrichtung. Dann gilt eine Positivliste
# (Handler._einrichtung): die Seite mit ihren Dateien (EINRICHTUNG_DATEIEN) und EINRICHTUNG_API, alles andere 403. Wer den Code nicht kennt,
# liest und schreibt nichts (E13); der Code steht einmal im Protokoll (serve) und kommt nur im Körper einer Anfrage, nie in der Adresse.

EINRICHTUNG_DATEIEN = {"/": "index.html", "/zaehler.js": "zaehler.js", "/app.js": "app.js", "/style.css": "style.css", "/favicon.svg": "favicon.svg",
                       "/grain.svg": "grain.svg", "/fonts/Geist-Variable.woff2": "fonts/Geist-Variable.woff2"}
# genau was die Seite braucht: index.html lädt zaehler.js vor app.js (nur Rechenregeln des Scanners, Phase 56), favicon.svg ruft auch Docker ab
EINRICHTUNG_API = ("/api/einrichtung", "/api/einrichtung/sicherung")
EINRICHTUNG_JSON = 4096           # so viele Bytes höchstens hat eine Anfrage an /api/einrichtung (Code, Name, Passwort)
VERWERFEN = 4096                  # so viele Bytes Körper liest der Server noch, bevor er eine Anfrage ablehnt (Handler._verwerfen)
MAX_SICHERUNG = 2 * 1024 ** 3    # so groß darf die ZIP sein, die die Einrichtung einspielt (eigene Grenze statt MAX_IMPORT); größere: mtg wiederherstellen
CODE_ZEILE = 64                   # die erste Zeile beim Hochladen ist der Code, höchstens so viele Bytes; dahinter beginnt die ZIP
EINSPIEL_WARTEN_S = 60            # kommt beim Hochladen so lange nichts, bricht der Server ab (sonst hielte eine hängende Verbindung den Weg besetzt)
EINRICHTUNG_S = 5                 # so oft sieht der tägliche Lauf nach, ob die Einrichtung vorbei ist
EINRICHTUNG = {"offen": False, "sperre": None}  # serve: offen = so gestartet; sperre = die Sperre des Datenordners (konten.belegen), die das Einspielen braucht
_einrichtung, _hochladen = threading.Lock(), threading.Lock()  # ein Schritt der Einrichtung zur Zeit; eine ZIP zur Zeit
FERTIG = "Die Einrichtung ist abgeschlossen. Bitte die Seite neu laden."
NICHT_LEER = ("Im Datenordner liegen schon Dateien, deshalb spielt die Einrichtung hier keine Sicherung ein. Auf dem Server geht es mit "
              "mtg wiederherstellen DATEI.zip.")
ZU_GROSS = f"Die Datei ist größer als {MAX_SICHERUNG // 1024 ** 2} MB. So eine Sicherung spielt auf dem Server mtg wiederherstellen DATEI.zip ein."
ABGELEHNT = ("Diese Datei spielt die App nicht ein: Sie ist keine Sicherung dieser App, beschädigt, verschlüsselt (dann erst mit gpg "
             "entschlüsseln) oder aus einer neueren Version. Der genaue Grund steht im Protokoll des Servers. Geändert ist nichts.")
UNVOLLSTAENDIG = "Die Datei kam nicht vollständig an oder ließ sich nicht speichern. Bitte noch einmal. Geändert ist nichts."
GESCHEITERT = "Das Einspielen ist gescheitert, geändert ist nichts. Der Grund steht im Protokoll des Servers."
HALB = ("Das Einspielen ist mittendrin gescheitert, im Datenordner liegen jetzt Teile der Sicherung. Was zu tun ist, steht im Protokoll "
        "des Servers.")
NICHT_OFFEN = "Die Daten im Datenordner lassen sich mit dieser Version der App nicht öffnen. Der Grund steht im Protokoll des Servers."


class Fertig(PermissionError):
    """Die Einrichtung ist vorbei (es gibt ein Hauptkonto) oder der Code gilt nicht mehr."""


def einrichtung_offen():
    """Wartet dieser Server auf die erste Einrichtung? Dann hat serve ihn so gestartet, und der Code liegt noch im Datenordner (er
    verschwindet mit dem ersten Hauptkonto, auch wenn es die Kommandozeile anlegt). Liest nur diese eine Datei und keine Datenbank: Solange
    die Einrichtung offen ist, öffnet keine Anfrage eine Datenbank, außer dem einen Schritt der Einrichtung, der gerade läuft (_einrichtung)."""
    return EINRICHTUNG["offen"] and konten.einrichtung_code() is not None


def einrichtung_starten(sperre):
    """Modus „Einrichtung“ einschalten (serve): Code anlegen oder den vorhandenen nehmen, den Rest eines abgebrochenen Hochladens
    wegräumen. sperre: die Sperre des Datenordners oder None (dann spielt die Einrichtung keine Sicherung ein). -> Code"""
    code = konten.einrichtung_beginnen()
    (konten.daten() / konten.EINRICHTUNG_ZIP).unlink(missing_ok=True)
    EINRICHTUNG.update(offen=True, sperre=sperre)
    return code


def _einrichtung_ende():
    EINRICHTUNG["offen"] = False
    konten.einrichtung_ende()


def _sauber(text):
    """Text fürs Protokoll: eine Zeile, ohne Steuerzeichen, höchstens 1.000 Zeichen (er kann Namen aus einer hochgeladenen ZIP enthalten)."""
    return re.sub(r"[\x00-\x1f\x7f-\x9f]", "?", str(text))[:1000]


def _code_pruefen(code, adresse):
    """konten.code_pruefen; ein falscher Code und die Sperre stehen mit der Adresse im Protokoll, der Versuch selbst nie. Ist die
    Einrichtung inzwischen vorbei (ein anderer war schneller, der Code ist weg), heißt es Fertig statt „falsch“."""
    try:
        konten.code_pruefen(code, adresse)
    except (ValueError, konten.Gesperrt) as e:
        if not einrichtung_offen():
            raise Fertig(FERTIG) from None
        protokoll(adresse, f"Einrichtung: Code {'gesperrt' if isinstance(e, konten.Gesperrt) else 'falsch'}")
        raise


def _noch_offen():
    """Unter _einrichtung, vor jedem Schritt (der Code ist da schon geprüft): Die Einrichtung ist noch offen (ein anderer Schritt kann sie
    inzwischen abgeschlossen haben, dann ist der Code weg), und es gibt kein Hauptkonto. Sonst Fertig."""
    if not einrichtung_offen():
        raise Fertig(FERTIG)
    if konten.modus() != "einfach":  # ein Hauptkonto ist da, der Code ließ sich nur nicht löschen
        _einrichtung_ende()
        raise Fertig(FERTIG)


def sicherung_moeglich():
    """Spielt die Einrichtung eine Sicherung ein? Nur in einen leeren Datenordner (konten.leer), und nur wenn dieser Server ihn belegt hält."""
    return EINRICHTUNG["sperre"] is not None and konten.leer()


def api_einrichtung(body, adresse="", sicher=False):
    """POST /api/einrichtung, nur solange die Einrichtung offen ist (Handler._einrichtung). Jede Aktion braucht den Code:
    {aktion: "code", code} prüft ihn und sagt, ob eine Sicherung eingespielt werden kann (das erfährt nur, wer ihn kennt);
    {aktion: "neu", code, name, passwort} legt das Hauptkonto an (immer mit Passwort), löscht den Code und meldet an.
    -> (Statuscode, Content-Type, Bytes, zusätzliche Header)"""
    try:
        d = json.loads(body or b"{}")
    except ValueError:
        d = None
    if not isinstance(d, dict) or d.get("aktion") not in ("code", "neu"):
        raise ValueError("Die Anfrage ist nicht lesbar")
    _code_pruefen(d.get("code"), adresse)  # zählt den Versuch, ohne auf einen laufenden Schritt zu warten
    with _einrichtung:
        _noch_offen()
        if d["aktion"] == "code":
            return (*_json({"ok": True, "sicherung": sicherung_moeglich(), "max_mb": MAX_SICHERUNG // 1024 ** 2}), {})
        name, pw = d.get("name"), d.get("passwort")
        if not isinstance(name, str) or not isinstance(pw, str):
            raise ValueError("Bitte Name und Passwort angeben")
        konten.kurz(name)  # beides prüfen, bevor konten.db entsteht: Nach einem abgelehnten Versuch ist der Datenordner so leer wie vorher
        konten._pruefe(pw)
        with closing(konten.connect()) as kc:
            n = konten.anlegen(kc, name, pw, ist_haupt=True)  # löscht den Code (konten.einrichtung_ende)
            _einrichtung_ende()
            protokoll(adresse, f"Einrichtung: Hauptkonto angelegt konto={n}")
            neu = _anmelden(kc, n, pw, adresse)
            return (*_json(_info(kc, konten.modus(), konten.sitzung(kc, neu))), {"Set-Cookie": _cookie(neu, sicher)})


# --- Täglicher Lauf (PLAN E16): Sicherung, dann Preise je Sammlung ------------------------------------------------------

TAEGLICH_S = 3600  # so oft prüft der Server, ob heute schon gelaufen
_katalog_versuch = {}  # ponytail: Pfad -> Tag des letzten Abrufs, im Speicher: höchstens ein Abruf der Gesamtdaten (80 MB) je Tag und Serverstart
_abruf = {}            # was ("katalog", "namen") -> Zustand des Abrufs für die Anzeige {running, done, total (Bytes), label, error, started, finished}
_abruf_sperre = threading.Lock()


def _abruf_beginnen(was, kat, heute):
    """Der einzige Weg zu den Scryfall-Gesamtdaten (PLAN E26): Der tägliche Lauf und der Hintergrund-Job beim ersten Öffnen von „Erfassen“ laufen
    beide hier durch, also gilt die Regel aus Phase 31 für beide zusammen: höchstens ein Abruf je Tag und Datei (auch ein gescheiterter zählt), und
    keiner, solange einer läuft (zwei Geräte öffnen zugleich: ein Abruf). -> der Zustand zum Fortschreiben, None = heute schon, nichts zu tun"""
    schluessel = kat if was == "katalog" else (kat, was)
    with _abruf_sperre:
        if _katalog_versuch.get(schluessel) == heute or _abruf.get(was, {}).get("running"):
            return None
        _katalog_versuch[schluessel] = heute
        _abruf[was] = {"running": True, "done": 0, "total": 0, "label": "", "error": None, "started": mtg.now_iso(), "finished": None}
        return _abruf[was]


def _abruf_laufen(zustand, was, laden, bulk=None):
    """Den begonnenen Abruf ausführen: laden(strom) baut aus dem Strom der Gesamtdaten (default_cards bzw. all_cards, bulk ersetzt sources.scryfall_bulk
    in Tests) und gibt ein Ergebnis zurück. Fehler gehen weiter und stehen im Zustand (nur lesbare Sätze, sonst die Nummer aus unerwartet)."""
    typ = "default_cards" if was == "katalog" else "all_cards"
    try:
        return laden(bulk(typ) if bulk else sources.scryfall_bulk(typ, progress=lambda d, t: zustand.update(done=d, total=t)))
    except (OSError, EOFError, ValueError, KeyError) as e:  # Netz weg, Strom abgebrochen oder Format geändert: der alte Stand bleibt
        zustand["error"] = str(getattr(e, "reason", e))
        raise
    except Exception:
        zustand["error"] = unerwartet(f"Abruf {was}")
        raise
    finally:
        zustand.update(running=False, finished=mtg.now_iso())


def _katalog_stand_aller():
    """Was alle Sammlungen der Installation über den Katalog sagen: -> (Papier-Sets der Set-Listen, liegt irgendwo etwas auf einer Scan-Liste)."""
    kuerzel, liste = set(), False
    for _, db in konten.sammlungen():  # die Set-Liste von heute hat neue_sets im täglichen Lauf in jeder Sammlung gemerkt
        if db.exists():
            try:
                with closing(mtg.connect(db)) as conn:
                    kuerzel |= katalog.kandidaten(mtg.sets_info(conn))
                    liste = liste or conn.execute("SELECT 1 FROM scan_liste LIMIT 1").fetchone() is not None
            except mtg.NichtMigriert:
                pass  # steht beim Öffnen der Sammlung im Protokoll
    return kuerzel, liste


def _katalog_merker(kat, heute):
    """Die Merker der ganzen Installation aus meta der Hauptsammlung (katalog.py, Phase 45). -> (Tag, an dem „Erfassen“ zuletzt geöffnet wurde, oder
    None; Schalter der deutschen Namen). Übergang für eine Installation von vor Phase 45: Hat sie schon einen Katalog und noch keinen Merker, gilt er
    als heute benutzt (und das wird eingetragen, sonst liefe die Frist nie ab); der Schalter der Namen steht dort an, wo der Katalog schon Namen hat."""
    if str(mtg.DB) == ":memory:" or not Path(mtg.DB).exists():
        return None, False
    try:
        with closing(mtg.connect()) as conn:
            tag = katalog.genutzt(conn)
            if tag is None and kat and Path(kat).exists():
                tag = katalog.genutzt_merken(conn, heute)
            return tag, katalog.namen_schalter(conn, kat)
    except mtg.NichtMigriert:
        return None, False  # steht beim Öffnen der Sammlung im Protokoll


def _zweiter_ordner(heute):
    """konten.ordner_kopie mit der Hauptsammlung. -> Protokollzeile oder None"""
    if not Path(mtg.DB).exists():
        return None
    try:
        with closing(mtg.connect()) as conn:
            return konten.ordner_kopie(conn, heute)
    except mtg.NichtMigriert:
        return None  # steht beim Öffnen der Sammlung unten im Protokoll
    except Exception as e:  # nie den täglichen Lauf aufhalten
        return f"Sicherung im zweiten Ordner gescheitert: {type(e).__name__}: {e}"


def taeglich(fetch=None, heute=None, cardmarket=None, sets=None, set_suche=None, salt=None, lookup=None, bulk=None, titel=None):
    """Einmal am Tag: Sicherung aller Sammlungen, dann je Sammlung der Posteingang (nur mit Schalter, Phase 27), Preise auffrischen (nur ältere
    als 24 h, dabei Wertverlauf) und die Cardmarket-Preisliste übernehmen (einmal geladen für alle Sammlungen). Zum Schluss der Katalog aller
    Papier-Drucke (Phase 31), wenn er fällig ist (katalog.faellig), und die deutschen Kartennamen (Phase 35, katalog.namen_faellig), aber nur
    wo der Server Namen lesen kann (titel_programm). Beides seit Phase 45 nur bei Bedarf (katalog.gebraucht: in den letzten 30 Tagen „Erfassen“
    geöffnet oder etwas auf einer Scan-Liste), die Namen zusätzlich nur mit dem Schalter (katalog.namen_schalter). Wiederholbar: was heute schon lief, wird übersprungen; ohne Netz bleibt
    der Tag offen und der nächste Versuch holt ihn nach. -> Protokollzeilen"""
    heute = heute or date.today().isoformat()
    zip_ = konten.taegliche_sicherung(heute)
    out, liste = [f"Sicherung {zip_.name}"] if zip_ else [], []
    zweit = _zweiter_ordner(heute)  # Phase 42: die ZIP zusätzlich in den vom Hauptkonto eingestellten Ordner, ein Fehler hält nichts auf
    if zweit:
        out.append(zweit)

    def holen():  # die Preisliste nur einmal laden, auch bei mehreren Sammlungen
        if not liste:
            liste.append((cardmarket or sources.cardmarket_guide)())
        return liste[0]
    salz = []
    for name, db in konten.sammlungen():
        if not db.exists():
            continue
        try:
            conn = mtg.connect(db)
        except mtg.NichtMigriert as e:  # neuer als die App oder nicht umstellbar (PLAN E27): Sie bleibt liegen, die anderen laufen
            out.append(f"{name or 'Sammlung'}: {e}")
            continue
        with closing(conn):
            schon = conn.execute("SELECT value FROM meta WHERE key = 'taeglich'").fetchone()
            if schon and schon[0] == heute:
                continue
            if mtg.posteingang_an(conn):  # wie mtg sync, aber jede Datei nur einmal und nie mit force
                try:
                    neu = mtg.posteingang(conn, mtg.inbox_fuer(db), fetch or sources.scryfall_cards, lookup, db.parent / "imports")
                except Exception as e:  # etwa ein nicht lesbarer Ordner: die Preise laufen trotzdem
                    neu = [{"datei": "Ordner", "status": f"nicht geprüft ({type(e).__name__}: {e})"}]
                if neu:
                    teile = ", ".join(f"{i['datei']} {i['status']}" for i in neu)
                    out.append(f"{name or 'Sammlung'}: Posteingang {teile}")
            n = mtg.refresh_prices(conn, fetch or sources.scryfall_cards)
            try:
                mtg.neue_sets(conn, sets, set_suche, heute)
            except (urllib.error.URLError, KeyError, ValueError) as e:  # Zusatz wie die Preisliste: fehlt er, läuft der Rest
                out.append(f"{name or 'Sammlung'}: neue Sets nicht geprüft ({getattr(e, 'reason', e)})")
            try:  # Salt-Liste von EDHREC (Phase 21), einmal je Lauf geladen
                if not salz:
                    salz.append((salt or sources.edhrec_salt)())
                deckbuild.salt_merken(conn, salz[0])
            except sources.QuelleAus:  # Phase 44: abgeschaltet, kein Abruf
                out.append(f"{name or 'Sammlung'}: Salt übersprungen (EDHREC ist abgeschaltet)")
            except (urllib.error.URLError, KeyError, ValueError) as e:
                out.append(f"{name or 'Sammlung'}: Salt nicht geladen ({getattr(e, 'reason', e)})")
            try:
                cm = mtg.refresh_cardmarket(conn, holen, heute)
            except sources.QuelleAus:  # Phase 44: abgeschaltet, kein Abruf; die Scryfall-Preise sind da
                cm = "übersprungen (Cardmarket ist abgeschaltet)"
            except (urllib.error.URLError, ValueError, TimeoutError) as e:  # Zusatz: fehlt sie, bleiben Scryfall-Preise und der Rest
                cm = f"nicht übernommen ({getattr(e, 'reason', e)})"
            with conn:
                conn.execute("INSERT OR REPLACE INTO meta VALUES ('taeglich', ?)", (heute,))
            out.append(f"{name or 'Sammlung'}: {n} Preise aufgefrischt, Cardmarket {cm if isinstance(cm, str) else f'{cm or 0} Produkte'}")
    kat = mtg.katalog_pfad()
    kuerzel, liste_da = _katalog_stand_aller()
    genutzt, namen_an = _katalog_merker(kat, heute)
    bedarf = katalog.gebraucht(genutzt, heute, liste_da)  # PLAN E26: ohne Scannen kein Abruf der Gesamtdaten
    grund = katalog.faellig(kat, kuerzel, heute) if bedarf else None
    if grund:
        zustand = _abruf_beginnen("katalog", kat, heute)
        if zustand:
            try:
                s = _abruf_laufen(zustand, "katalog", lambda strom: katalog.bauen(strom, kat, kuerzel, heute), bulk)
                out.append(f"Katalog: {s['drucke']} Papier-Drucke, {s['aussehen']} Aussehen ({grund})")
            except (OSError, EOFError, ValueError, KeyError) as e:  # Netz weg, Strom abgebrochen oder Format geändert: der alte Stand bleibt
                out.append(f"Katalog nicht geladen ({getattr(e, 'reason', e)})")
    grund = katalog.namen_faellig(kat, heute) if bedarf and namen_an and (titel or titel_programm)() else None
    if grund:
        zustand = _abruf_beginnen("namen", kat, heute)
        if zustand:
            try:
                n = _abruf_laufen(zustand, "namen", lambda strom: katalog.namen_bauen(strom, kat, tag=heute), bulk)
                out.append(f"Katalog: {n} deutsche Kartennamen ({grund})")
            except (OSError, EOFError, ValueError, KeyError) as e:
                out.append(f"Kartennamen nicht geladen ({getattr(e, 'reason', e)})")
    return out


def _taeglich_schleife():
    while True:
        if einrichtung_offen():  # Phase 43: vor der Einrichtung kein Netz, keine Sicherung und kein zweiter Schreiber im Datenordner
            time.sleep(EINRICHTUNG_S)
            continue
        try:
            for z in taeglich():
                print(f"Täglicher Lauf: {z}", flush=True)
        except urllib.error.URLError as e:
            print(f"Täglicher Lauf: kein Netz ({getattr(e, 'reason', e)}), nächster Versuch in einer Stunde", file=sys.stderr, flush=True)
        except Exception as e:  # nie den Server mitreißen
            print(f"Täglicher Lauf: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        time.sleep(TAEGLICH_S)


# --- HTTP --------------------------------------------------------------------------------------------------------------

def _csp():
    """Content-Security-Policy: Skripte nur von hier (das kleine Darstellungs-Skript in index.html per Hash), Bilder von hier und Scryfall."""
    inline = re.findall(r"<script>(.*?)</script>", (UI / "index.html").read_text(encoding="utf-8"), re.S)
    hashes = " ".join(f"'sha256-{base64.b64encode(hashlib.sha256(x.encode()).digest()).decode()}'" for x in inline)
    return ("default-src 'self'; img-src 'self' data: https://cards.scryfall.io; style-src 'self' 'unsafe-inline'; "
            f"script-src 'self' {hashes}; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")


SICHERHEIT = (("X-Content-Type-Options", "nosniff"), ("X-Frame-Options", "DENY"), ("Referrer-Policy", "same-origin"), ("Content-Security-Policy", _csp()))


# --- Laden: ETag und gzip (Phase 48, PLAN E32) -------------------------------------------------------------------------
# Statische Dateien: ETag aus dem Inhalt, Cache-Control: no-cache (der Browser fragt jedes Mal nach und bekommt 304, solange die Datei gleich ist; nach
# einem Update läuft sofort der neue Code), gzip für Text, einmal je Dateiversion gepackt. Die API bleibt no-store (Sitzung, persönlicher Inhalt: nie in
# einen gemeinsamen Zwischenspeicher) und wird ab GZIP_API_AB gepackt. Schrift, PNG, ICO und ZIP werden nie gepackt (sie sind es schon).

GZIP_API_AB = 1024  # so viele Bytes muss eine API-Antwort haben, damit sie gepackt wird; gemessen (tests/lade_messung.py): darunter spart es höchstens ~0,2 KB
GZIP_API_STUFE = 6  # 45 KB (/api/cards, die größte Seite der Beispielsammlung) brauchen auf Stufe 6 unter 1 ms
PACKBAR = ("text/", "application/json", "application/manifest+json", "image/svg+xml")
_statisch = {}      # Pfad -> [(mtime_ns, Größe), ETag-Kern, Inhalt, gepackter Inhalt oder None, gepackt schon versucht]; neu, sobald sich die Datei ändert


def packbar(ctype):
    """Ist das Text, der sich zu packen lohnt (nach dem Content-Type)? Bilder außer SVG, Schrift und ZIP nie."""
    return str(ctype).split(";")[0].strip().lower().startswith(PACKBAR)


def nimmt_gzip(kopf):
    """Nimmt der Browser gzip an (Accept-Encoding)? Gewicht q=0 heißt nein; ein ausdrücklich genanntes gzip (oder x-gzip) geht dem „*“ vor; ein
    Gewicht, das keine Zahl ist, gilt als nein."""
    q = {}
    for teil in str(kopf or "").split(","):
        name, _, rest = teil.partition(";")
        name, gewicht = name.strip().lower(), 1.0
        if not name:
            continue
        for par in rest.split(";"):
            k, _, v = par.partition("=")
            if k.strip().lower() == "q":
                try:
                    gewicht = float(v.strip())
                except ValueError:
                    gewicht = 0.0
        q[name] = gewicht
    return q.get("gzip", q.get("x-gzip", q.get("*", 0.0))) > 0


_INM = re.compile(r'\s*(\*|(?:W/)?"[^"]*")\s*(,|$)')


def etag_passt(kopf, etag):
    """If-None-Match: trifft einer der genannten Werte (oder „*“) auf den ETag? Schwache Marken (W/"…") zählen mit, denn für 304 gilt der schwache
    Vergleich. Eine Liste, die nicht der Form folgt, passt auf nichts (die Datei kommt dann ganz)."""
    kopf, i = str(kopf or ""), 0
    while (m := _INM.match(kopf, i)):
        if m[1] == "*" or (m[1][2:] if m[1].startswith("W/") else m[1]) == etag:
            return True
        if not m[2]:
            break
        i = m.end()
    return False


def statische_datei(p, packen):
    """Inhalt einer Datei aus ui/ -> (ETag, Inhalt, Content-Encoding oder None). ETag aus dem Inhalt (SHA-256); die Datei wird nur neu gelesen und
    gepackt, wenn sich Änderungszeit oder Größe ändern. Die gepackte Fassung hat einen eigenen ETag (-gz): Sie ist eine andere Antwort."""
    st = p.stat()
    e = _statisch.get(p)
    if e is None or e[0] != (st.st_mtime_ns, st.st_size):
        roh = p.read_bytes()
        e = _statisch[p] = [(st.st_mtime_ns, st.st_size), hashlib.sha256(roh).hexdigest()[:24], roh, None, False]
    if packen and not e[4]:
        gz = gzip.compress(e[2], 9, mtime=0)  # mtime=0: dieselben Bytes bei jedem Packen
        e[3], e[4] = (gz if len(gz) < len(e[2]) else None), True
    return (f'"{e[1]}-gz"', e[3], "gzip") if packen and e[3] else (f'"{e[1]}"', e[2], None)


class Handler(BaseHTTPRequestHandler):
    port = PORT
    lokal = True  # lauscht nur auf 127.0.0.1 (serve setzt es)

    def parse_request(self):
        self._t0 = time.monotonic()
        return super().parse_request()

    def log_message(self, *a):  # die Meldungen von http.server bleiben aus; das Protokoll schreibt log_request
        pass

    def log_request(self, code="-", size="-"):
        """Eine Zeile je Antwort (PLAN E29): Zeit, Adresse, Methode, Pfad ohne Abfrage, Status, Dauer bis zum Beginn der Antwort. http.server ruft
        das aus send_response, also auch für seine eigenen Fehlerantworten (unlesbare Anfrage, unbekannte Methode)."""
        if PROTOKOLL:
            ms = (time.monotonic() - self._t0) * 1000 if getattr(self, "_t0", None) else 0
            protokoll(self._adresse(), f"{getattr(self, 'command', None) or '-'} {self._pfad() or '-'} {int(code) if isinstance(code, int) else code} {ms:.0f}ms")

    def _pfad(self):
        """Pfad der Anfrage fürs Protokoll: ohne Abfrage, nur druckbare ASCII-Zeichen, höchstens 200."""
        return re.sub(r"[^\x21-\x7e]", "?", (getattr(self, "path", "") or "").split("?")[0])[:200]

    def _vom_proxy(self, kopf):
        """Letzter Eintrag eines X-Forwarded-Kopfs, aber nur wenn der Betreiber einen Proxy angibt (hinter_proxy), sonst „“. Den letzten
        Eintrag hat der Proxy selbst geschrieben; alles davor kann der Absender erfunden haben."""
        k = getattr(self, "headers", None)
        return ",".join(k.get_all(kopf) or []).split(",")[-1].strip() if k is not None and hinter_proxy() else ""

    def _adresse(self):
        """Absender-Adresse für Sperre und Protokoll: die Gegenstelle der Verbindung (die kann niemand vortäuschen, der eine Antwort will).
        Mit Proxy der letzte Eintrag von X-Forwarded-For; fehlt er oder ist er keine Adresse, bleibt es bei der Gegenstelle, also beim
        Proxy: Dann teilen sich alle eine Adresse, und die Sperre gilt je Konto wie vor Phase 40."""
        try:
            return str(ipaddress.ip_address(self._vom_proxy("X-Forwarded-For")))
        except ValueError:
            return self.client_address[0]

    def _https(self):
        """Kam die Anfrage über https? Das weiß nur ein Proxy davor (X-Forwarded-Proto); ohne ihn spricht der Server selbst nur http."""
        return self._vom_proxy("X-Forwarded-Proto").lower() == "https"

    def _reply(self, code, ctype, body, extra=None):
        """Eine Antwort senden: Standard no-store und die Sicherheits-Header (auf jeder Antwort, auch auf 304), HSTS nur bei https; extra ergänzt
        oder ersetzt (Cache-Control bei statischen Dateien). Ein 304 hat weder Content-Type noch Content-Length noch Körper."""
        self.send_response(code)
        kopf = {} if code == 304 else {"Content-Type": ctype, "Content-Length": str(len(body))}
        kopf.update({"Cache-Control": "no-store", **dict(SICHERHEIT), **dict((HSTS,) if self._https() else ()), **(extra or {})})
        for k, v in kopf.items():
            self.send_header(k, v)
        self.end_headers()
        if code != 304:
            self.wfile.write(body)

    def _nimmt_gzip(self):
        return nimmt_gzip(",".join(self.headers.get_all("Accept-Encoding") or []))

    def _gepackt(self, antwort):
        """Antwort der API -> dieselbe, gepackt, wenn der Browser gzip annimmt, der Inhalt Text ist und mindestens GZIP_API_AB Bytes hat (und das
        Packen etwas spart). Bleibt no-store. Vary nennt Accept-Encoding bei jedem Text, auch wenn nicht gepackt wurde."""
        code, ctype, body, *rest = antwort
        extra = dict(rest[0]) if rest else {}
        if not packbar(ctype) or code == 304:
            return antwort
        extra["Vary"] = "Accept-Encoding"
        if len(body) >= GZIP_API_AB and "Content-Encoding" not in extra and self._nimmt_gzip():
            gz = gzip.compress(body, GZIP_API_STUFE, mtime=0)
            if len(gz) < len(body):
                body, extra["Content-Encoding"] = gz, "gzip"
        return code, ctype, body, extra

    def _senden(self, antwort, api=False):
        """Antwort von antwort() senden (die der API gepackt, E32). Wirft sie unerwartet, geht nur der feste Satz mit Nummer hinaus (PLAN E29)."""
        try:
            a = antwort()
            if api:
                a = self._gepackt(a)
        except Exception:
            a = _json({"error": unerwartet(f"{self.command} {self._pfad()}")}, 500)
        self._reply(*a)

    def _token(self):
        try:
            c = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))
        except http.cookies.CookieError:
            return None
        return c["mtg"].value if "mtg" in c else None

    def _erlaubt(self, m):
        """Mit Anmeldung schützt die Sitzung (das Cookie gilt nur für die eigene Adresse). Ohne: nur 127.0.0.1 und nur die eigene Adresse im
        Host-Kopf (gegen DNS-Rebinding); lauscht der Server woanders, bleibt alles zu (E13)."""
        return m == "anmeldung" or (self.lokal and self.headers.get("Host", "") in (f"127.0.0.1:{self.port}", f"localhost:{self.port}"))

    def _api(self, method, u, body=b""):
        """-> Antwort (Statuscode, Content-Type, Bytes[, zusätzliche Header])"""
        try:
            m = konten.modus()
            if not self._erlaubt(m):
                return 403, "text/plain", b"nicht erlaubt"
            if u.path in EINRICHTUNG_API:  # gibt es nur, solange die Einrichtung offen ist (_einrichtung)
                return _json({"error": FERTIG, "fertig": True}, 403)
            token = self._token()
            if u.path in KONTO_PFADE:
                return api_konto(method, u.path, body, token, self._https(), self._adresse())
            s, db = sammlung(m, token)
            if db is None:
                return _json({"error": "Bitte anmelden", "login": True}, 401)
            conn = mtg.connect(db)
        except mtg.NichtMigriert as e:  # Datenbank neuer als die App oder nicht umstellbar (PLAN E27): lesbare Meldung, nichts ist geändert
            return _json({"error": str(e)}, 503)
        with closing(conn):
            return dispatch(conn, method, u.path, dict(urllib.parse.parse_qsl(u.query)), body,
                            urllib.parse.unquote(self.headers.get("X-Filename", "")), db=db, archive=Path(db).parent / "imports")

    def _datei(self, u):
        try:
            m = konten.modus()
        except mtg.NichtMigriert as e:  # konten.db neuer als die App: Ohne sie weiß der Server nicht, wer die Seite sehen darf
            return 503, "text/plain; charset=utf-8", str(e).encode()
        if not self._erlaubt(m):
            return 403, "text/plain", b"Host nicht erlaubt"
        p = (UI / ("index.html" if u.path == "/" else u.path.lstrip("/"))).resolve()
        if UI.resolve() not in p.parents or not p.is_file():
            return 404, "text/plain", b"nicht gefunden"
        ctype = TYPES.get(p.suffix) or mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        text = packbar(ctype)
        etag, body, kodierung = statische_datei(p, text and self._nimmt_gzip())
        extra = {"ETag": etag, "Cache-Control": "no-cache", **({"Vary": "Accept-Encoding"} if text else {})}  # no-cache: immer nachfragen (E32)
        if etag_passt(",".join(self.headers.get_all("If-None-Match") or []), etag):
            return 304, ctype, b"", extra
        return 200, ctype, body, {**extra, **({"Content-Encoding": kodierung} if kodierung else {})}

    def _einrichtung(self, method, u, laenge=0):
        """Jede Anfrage, solange die Einrichtung offen ist (PLAN E28): die Positivliste an einer Stelle. Die Seite und genau ihre Dateien,
        GET /api/einrichtung (sagt nur, dass die Einrichtung offen ist), POST /api/einrichtung (api_einrichtung) und
        POST /api/einrichtung/sicherung (_einspielen); alles andere 403, auch /api/session und jede Sammlungs-API. Der Körper einer Anfrage
        wird erst gelesen, wenn Pfad und Größe passen. Was eine hochgeladene ZIP an Namen und Pfaden mitbringt, geht nur ins Protokoll."""
        try:
            if method == "GET" and u.path in EINRICHTUNG_DATEIEN:
                p = UI / EINRICHTUNG_DATEIEN[u.path]
                return 200, TYPES.get(p.suffix) or mimetypes.guess_type(p.name)[0] or "application/octet-stream", p.read_bytes()
            if method == "GET" and u.path == "/api/einrichtung":
                return _json({"modus": "einrichtung"})
            if method == "POST" and u.path == "/api/einrichtung":
                if laenge > EINRICHTUNG_JSON:
                    return _json({"error": "Die Anfrage ist zu groß"}, 413)
                return api_einrichtung(self.rfile.read(laenge), self._adresse(), self._https())
            if method == "POST" and u.path == "/api/einrichtung/sicherung":
                return self._einspielen(laenge)
            if method == "POST":
                self._verwerfen(laenge)
            return 403, "text/plain", b"nicht erlaubt"
        except Fertig as e:
            return _json({"error": str(e), "fertig": True}, 403)
        except konten.Gesperrt as e:
            return _json({"error": str(e)}, 429)
        except mtg.NichtMigriert as e:  # der Text nennt den Pfad der Datenbank
            protokoll(self._adresse(), f"Einrichtung: {_sauber(e)}")
            return _json({"error": NICHT_OFFEN}, 503)
        except ValueError as e:  # nur eigene Sätze: falscher Code, Name, Passwort, Datenordner nicht leer
            return _json({"error": str(e)}, 400)

    def _einspielen(self, laenge):
        """POST /api/einrichtung/sicherung: Sicherung in eine leere Installation einspielen. Der Körper ist eine Zeile mit dem Code, dahinter
        die ZIP. Reihenfolge: (1) Größe nach Content-Length, sonst 413, nichts gelesen. (2) Die erste Zeile lesen (höchstens CODE_ZEILE
        Bytes) und den Code prüfen, mit Sperre: Ohne den Code nimmt der Server kein Byte der Datei an. (3) Eine ZIP zur Zeit. (4) Die
        Einrichtung ist noch offen, der Datenordner leer (konten.leer), und der Server hält ihn belegt. (5) Erst jetzt die Datei annehmen:
        auf die Platte (einrichtung.zip im Datenordner, nur für den Nutzer der App lesbar), nie mehr als Content-Length, das unter der
        Grenze liegt. (6) Unter _einrichtung noch einmal (4), dann konten.zurueckspielen mit der Sperre dieses Servers und streng: prüfen
        wie mtg wiederherstellen und einsetzen. (7) Bringt die Sicherung ein Hauptkonto mit Passwort, ist die Einrichtung vorbei und der
        Code weg; sonst (eine Sicherung ohne Konten) bleibt er, bis das Hauptkonto angelegt ist. Die ZIP verschwindet in jedem Fall."""
        adresse = self._adresse()

        def fest(satz, status, grund):  # nach außen ein fester Satz, der Grund (mit Namen aus der ZIP und Pfaden) nur ins Protokoll
            protokoll(adresse, f"Einrichtung: {_sauber(grund)}")
            return _json({"error": satz}, status)
        if laenge > MAX_SICHERUNG + CODE_ZEILE:
            return _json({"error": ZU_GROSS}, 413)
        kopf = self.rfile.readline(min(CODE_ZEILE, laenge))
        code = kopf[:-1].decode("ascii", "replace") if kopf.endswith(b"\n") else None  # ohne Zeilenende kein Code: ein Fehlversuch
        _code_pruefen(code, adresse)
        if not _hochladen.acquire(blocking=False):
            raise konten.Gesperrt("Gerade wird schon eine Sicherung eingespielt. Bitte warten.")
        ziel, rest, grund = konten.daten() / konten.EINRICHTUNG_ZIP, laenge - len(kopf), []
        try:
            with _einrichtung:
                _noch_offen()
                if not sicherung_moeglich():
                    raise ValueError(NICHT_LEER)
            try:
                self.connection.settimeout(EINSPIEL_WARTEN_S)
                with os.fdopen(os.open(ziel, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_BINARY", 0), 0o600), "wb") as f:
                    while rest:
                        block = self.rfile.read(min(1 << 16, rest))
                        if not block:
                            raise EOFError("Verbindung endet vor dem Ende der Datei")
                        f.write(block)
                        rest -= len(block)
            except (OSError, EOFError) as e:
                return fest(UNVOLLSTAENDIG, 400, f"Sicherung nicht angenommen ({type(e).__name__}: {e})")
            finally:
                self.connection.settimeout(None)

            def fragen(info):  # die geprüfte Sicherung, bevor etwas eingesetzt wird
                if info["jetzt"]:
                    grund.append(NICHT_LEER)
                elif any(k["rolle"] == "haupt" and not k["pw"] for k in info["konten"]):
                    grund.append("Das Hauptkonto dieser Sicherung hat kein Passwort. So eine Sicherung spielt nur die Kommandozeile ein: "
                                 "mtg wiederherstellen DATEI.zip, danach mtg konto passwort NAME.")
                return not grund
            with _einrichtung:
                _noch_offen()
                if not sicherung_moeglich():
                    raise ValueError(NICHT_LEER)
                try:
                    info = konten.zurueckspielen(ziel, fragen, EINRICHTUNG["sperre"], streng=True)
                except konten.KeineSicherung as e:
                    return fest(ABGELEHNT, 400, f"Sicherung abgelehnt: {e}")
                except konten.NichtZurueck as e:
                    return fest(HALB, 500, f"Sicherung halb eingespielt: App beenden, den Datenordner leeren (was dort von der Sicherung "
                                           f"liegt, steckt in der ZIP), dann mtg wiederherstellen DATEI.zip. {e}")
                except ValueError as e:
                    return fest(GESCHEITERT, 500, f"Sicherung nicht eingespielt: {e}")
                if info is None:
                    raise ValueError(grund[0])
                try:
                    fertig = konten.modus() == "anmeldung"  # öffnet konten.db; eine ältere stellt das um, mit Sicherung davor (Phase 39)
                except mtg.NichtMigriert as e:
                    return fest(NICHT_OFFEN, 500, f"Sicherung eingespielt, aber: {e}")
                if fertig:
                    _einrichtung_ende()
                protokoll(adresse, f"Einrichtung: Sicherung eingespielt ({len(info['konten'])} Konten, {len(info['sammlungen'])} Sammlungen)")
                return _json({"ok": True, "anmeldung": fertig, "datum": info["datum"], "konten": len(info["konten"]),
                              "sammlungen": len(info["sammlungen"]), "karten": sum(s["karten"] for s in info["sammlungen"])})
        finally:
            try:
                ziel.unlink(missing_ok=True)
            except OSError:
                pass
            _hochladen.release()

    def _ziel(self):
        try:
            return urllib.parse.urlsplit(self.path)
        except ValueError:  # etwa „http://[“: keine Adresse
            return None

    def do_GET(self):
        u = self._ziel()
        if u is None:
            return self._reply(400, "text/plain", b"Adresse nicht lesbar")
        if einrichtung_offen():
            return self._senden(lambda: self._einrichtung("GET", u))
        if u.path.startswith("/api/"):
            return self._senden(lambda: self._api("GET", u), api=True)
        self._senden(lambda: self._datei(u))

    def _verwerfen(self, laenge):
        """Den kleinen Körper einer Anfrage lesen, die abgelehnt wird (bis VERWERFEN Bytes). Schließt der Server mit ungelesenen Daten, reißt
        unter Windows die Verbindung ab, bevor der Absender die Antwort hat: Er sähe einen Netzfehler statt „nicht erlaubt“. Große Körper
        bleiben ungelesen."""
        n = str(laenge or "").strip()
        if re.fullmatch(r"[0-9]{1,6}", n) and 0 < int(n) <= VERWERFEN:
            self.rfile.read(int(n))

    def do_POST(self):  # eigener Header: fremde Webseiten können ihn ohne Vorabfrage nicht senden
        if self.headers.get("X-Mtg") != "1":
            self._verwerfen(self.headers.get("Content-Length"))
            return self._reply(403, "text/plain", b"nicht erlaubt")
        u, laenge = self._ziel(), (self.headers.get("Content-Length") or "0").strip()
        if u is None or not re.fullmatch(r"[0-9]{1,15}", laenge):
            return self._reply(*_json({"error": "Die Anfrage ist nicht lesbar (Adresse oder Content-Length)"}, 400))
        if einrichtung_offen():  # Phase 43: nur die Positivliste, und sie liest den Körper selbst (erst nach Pfad, Größe und Code)
            return self._senden(lambda: self._einrichtung("POST", u, int(laenge)))
        if u.path in EINRICHTUNG_API:  # die Einrichtung ist vorbei (oder war hier nie offen): nichts lesen, _api sagt es
            return self._senden(lambda: self._api("POST", u), api=True)
        if int(laenge) > MAX_IMPORT:
            return self._reply(*_json({"error": "Datei ist größer als 20 MB"}, 413))
        self._senden(lambda: self._api("POST", u, self.rfile.read(int(laenge))), api=True)


def serve(port=PORT, open_browser=True, host="127.0.0.1", daily=True, log=False, fenster=None):
    """Oberfläche starten. Auf einer anderen Adresse als 127.0.0.1 (Server) nur mit Anmeldung (E13) oder, solange es kein Hauptkonto gibt,
    im Modus „Einrichtung“ (E28): Dann antwortet der Server nur auf die Einrichtungsseite, und der Code dafür steht einmal im Protokoll.
    Ein Hauptkonto ohne Passwort reicht dort weiter nicht. Auf 127.0.0.1 ändert das nichts. Das Protokoll (eine Zeile je Anfrage,
    PLAN E29) läuft nur auf dem Server oder mit log. fenster: Befehl eines Browsers für ein eigenes App-Fenster (Phase 55, mtg.fenster_befehl);
    endet sein Prozess (Fenster zu), endet der Server. -> Rückgabewert fürs CLI"""
    global PROTOKOLL
    lokal = host in ("127.0.0.1", "localhost")
    m = None if lokal else konten.modus()
    if m == "lokal":
        print("Auf einer anderen Adresse als 127.0.0.1 nur mit Anmeldung, und das Hauptkonto hat noch kein Passwort. "
              "Erst eins setzen: mtg konto passwort NAME", file=sys.stderr)
        return 2
    Handler.port, Handler.lokal, PROTOKOLL = port, lokal, bool(log or not lokal)
    EINRICHTUNG.update(offen=False, sperre=None)
    srv = ThreadingHTTPServer((host, port), Handler)
    try:  # Phase 41: Solange die Oberfläche läuft, hält sie den Datenordner belegt; daran erkennt „mtg wiederherstellen“ sie
        sperre = konten.belegen()  # None: Eine zweite Oberfläche auf demselben Ordner hält sie schon
    except OSError:
        sperre = None
    code = None
    try:
        if m == "einfach":  # Phase 43: kein Hauptkonto, also Einrichtung im Browser, nur mit dem Code
            code = einrichtung_starten(sperre)
        elif m:
            konten.einrichtung_ende()  # ein liegen gebliebener Code gilt ohnehin nicht mehr
    except OSError as e:
        print(f"Der Einrichtungs-Code lässt sich nicht im Datenordner {konten.daten()} speichern ({e.strerror or e}). Der Ordner muss dem "
              f"Nutzer der App gehören (mit Docker: sudo chown 1000:1000 data).", file=sys.stderr)
        srv.server_close()
        if sperre:
            sperre.close()
        return 2
    if daily:
        threading.Thread(target=_taeglich_schleife, daemon=True).start()
    url = f"http://127.0.0.1:{port}"
    print(f"{version.NAME} {version.VERSION} läuft auf {url if lokal else f'{host}:{port}, ' + ('Einrichtung offen' if code else 'Anmeldung an')}"
          f"{', Proxy davor (MTG_PROXY)' if hinter_proxy() else ''} (Strg+C beendet)", flush=True)
    if code:  # die einzige Stelle, an der der Code im Protokoll steht
        print(f"Einrichtung: Code {code}\nNoch gibt es kein Hauptkonto. Die Adresse der App im Browser öffnen und dort diesen Code eingeben; "
              f"er gilt, bis das Hauptkonto angelegt ist. Noch einmal zeigen: mtg einrichtung", flush=True)
    if fenster:  # mit eigenem Profil ist der gestartete Prozess das Fenster selbst und endet, sobald es zu ist (am Rechner geprüft)
        app = subprocess.Popen([*fenster, f"--app={url}"])
        threading.Thread(target=lambda: (app.wait(), srv.shutdown()), daemon=True).start()
    elif open_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        EINRICHTUNG.update(offen=False, sperre=None)
        if sperre:
            sperre.close()
