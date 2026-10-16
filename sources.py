"""Einziges Modul mit Netz: Scryfall, EDHREC, Commander Spellbook, Cardmarket-Preisliste (die drei letzten mit Schalter, siehe QUELLEN).
Tests ersetzen diese Funktionen, nie echtes Netz."""
import gzip
import json
import os
import re
import sqlite3
import time
import urllib.error
import urllib.parse
import urllib.request
from contextlib import closing
from pathlib import Path

import version

# Name, Version und Adresse des Projekts stehen in version.py (Scryfall verlangt Name und Version der Anwendung)
HEADERS = {"User-Agent": version.USER_AGENT, "Accept": "application/json"}
# Sekunden Abstand je Host. Scryfall erlaubt für /cards/search und /cards/collection (alles, was wir nutzen) 2 Anfragen pro Sekunde
# und sperrt nach einem 429 für 30 Sekunden (scryfall.com/docs/api/rate-limits); das Bild-CDN *.scryfall.io hat kein Limit.
GAP = {"api.scryfall.com": 0.5, "json.edhrec.com": 1.0, "backend.commanderspellbook.com": 0.5, "downloads.s3.cardmarket.com": 1.0, "data.scryfall.io": 1.0, "api.github.com": 1.0}
SPERRE = 31  # Sekunden Pause nach HTTP 429
_last = {}

# --- Schalter je Quelle (Phase 44, PLAN E25) ----------------------------------------------------------------------------------
# Jede Quelle außer Scryfall (ohne Scryfall gibt es keinen Import) lässt sich für die ganze Installation abschalten: auch für Unterkonten, den
# täglichen Lauf, Hintergrund-Jobs und die Kommandozeile. Geprüft wird an genau einer Stelle, pruefen(): _call für alle Hosts mit Schalter und
# cardmarket_guide, das nicht über _call läuft. Abgeschaltet heißt: kein Aufruf, stattdessen QuelleAus (eine URLError wie „kein Netz“, damit
# jede bestehende Stelle weiterläuft; wer will, sagt „abgeschaltet“).
# Ein Ja von EDHREC dreht den Standard um (E25: bis dahin ist EDHREC für neue Installationen aus; bestehende Sammlungen mit EDHREC-Daten
# behalten es über die Migration auf Stand 2, mtg._stand_2).
EDHREC_STANDARD = False
QUELLEN = {
    "edhrec": {
        "name": "EDHREC", "hosts": ("json.edhrec.com",), "standard": EDHREC_STANDARD, "link": "https://edhrec.com/terms",
        "zweck": "Beliebte Karten und Themen je Commander (Ranking, Deckbau, Lücken, Staples der besten Commander) und die Salt-Liste.",
        "schickt": "Nur den Namen des Commanders oder Themas in der Adresse. Dazu sieht EDHREC die Adresse des Rechners und den Programmnamen mit Version.",
        "wie_oft": "Beim Laden der Commander-Daten eine Seite je Commander und Thema, höchstens eine pro Sekunde; jede Seite bleibt 30 Tage gemerkt. Die Salt-Liste einmal am Tag.",
        "hinweis": "EDHREC bietet keine offizielle Schnittstelle. Die Nutzungsbedingungen von EDHREC untersagen laut Stand vom 2026-10-12 automatische Anfragen und das Kopieren der Inhalte. Wer einschaltet, hat sie gelesen und entscheidet selbst.",
    },
    "spellbook": {
        "name": "Commander Spellbook", "hosts": ("backend.commanderspellbook.com",), "standard": True, "link": "https://commanderspellbook.com/",
        "zweck": "Combos in der Sammlung, Bracket-Prüfung einer Deckliste und Combo-Hinweise in mtg news.",
        "schickt": "Kartennamen: bei den Combos die Namen deiner Karten, die in Combos vorkommen (höchstens 600 je Anfrage); bei der Bracket-Prüfung und mtg news die Namen der Karten des Decks. Dazu Adresse und Programmname mit Version.",
        "wie_oft": "Nur auf Knopfdruck (Combos suchen, Bracket prüfen) oder mit den Befehlen mtg news und mtg sync. Die Liste der Combo-Karten (rund 75 Seiten) höchstens einmal im Monat.",
        "hinweis": "Bedingungen für die Schnittstelle fand die Durchsicht vom 2026-10-12 nicht: Es gibt ein öffentliches Schema, aber keine Nutzungsbedingungen. Die Anfragen sind wenige und gebremst (höchstens zwei pro Sekunde).",
    },
    "cardmarket": {
        "name": "Cardmarket-Preisliste", "hosts": ("downloads.s3.cardmarket.com",), "standard": True, "link": "https://help.cardmarket.com/en/cardmarket-api",
        "zweck": "Niedrigster Angebotspreis (ab), Trend und Schnitt je Karte, fürs Verkaufen und die Wünsche.",
        "schickt": "Nichts außer der Adresse des Rechners und dem Programmnamen mit Version: Die App lädt eine öffentliche Datei (rund 26 MB), ohne Namen oder Kennungen.",
        "wie_oft": "Einmal am Tag im täglichen Lauf oder mit mtg prices.",
        "hinweis": "Bedingungen für diese Dateien fand die Durchsicht vom 2026-10-12 nicht (die Seite zur Schnittstelle nennt nur die geschlossene Schnittstelle). Die Datei steht öffentlich zum Herunterladen.",
    },
}
HOST_QUELLE = {h: k for k, q in QUELLEN.items() for h in q["hosts"]}
ENV_QUELLEN = "MTG_QUELLEN"   # Umgebung: Liste der eingeschalteten Quellen (edhrec,spellbook,cardmarket), „alle“ oder „keine“; sperrt die Schalter
KEY = "quellen"               # meta der Hauptsammlung: {Quelle: bool} (die Schalter der Oberfläche)
KEY_ALT = "quellen:alt"       # meta jeder Sammlung: {Quelle: true} = die Migration fand dort Daten dieser Quelle (bleibt an, solange nichts gespeichert ist)


class QuelleAus(urllib.error.URLError):
    """Die Quelle ist abgeschaltet; es wurde nichts abgerufen. quelle: der Schlüssel in QUELLEN."""
    def __init__(self, quelle):
        self.quelle = quelle
        super().__init__(f"{QUELLEN[quelle]['name']} ist abgeschaltet. Einschalten geht auf der Seite „Quellen“ (Konten und Sicherung).")

    def __str__(self):
        return self.reason


def _umgebung():
    """MTG_QUELLEN -> Menge der eingeschalteten Quellen, oder None, wenn nicht gesetzt (leer zählt als nicht gesetzt; „keine“ schaltet alle ab)."""
    roh = (os.environ.get(ENV_QUELLEN) or "").strip().lower()
    if not roh:
        return None
    worte = {w for w in roh.replace(";", ",").replace(" ", ",").split(",") if w}
    return set(QUELLEN) if "alle" in worte else worte & set(QUELLEN)


def gespeichert():
    """Die Schalter aus meta der Hauptsammlung (die Datei mtg.DB), nur lesend und ohne sie anzulegen oder zu migrieren. -> ({Quelle: bool}, {Quelle: true})
    Ohne Datei, ohne Eintrag oder bei einem Lesefehler: leer, dann gelten die Standards."""
    import mtg  # erst hier: mtg importiert sources
    pfad = Path(mtg.DB)
    if str(mtg.DB) == ":memory:" or not pfad.is_file():
        return {}, {}
    try:
        with closing(sqlite3.connect(f"file:{urllib.parse.quote(pfad.as_posix(), safe='/:')}?mode=ro", uri=True, timeout=5)) as c:
            zeilen = dict(c.execute("SELECT key, value FROM meta WHERE key IN (?, ?)", (KEY, KEY_ALT)).fetchall())
    except sqlite3.Error:
        return {}, {}

    def lesen(roh):
        try:
            d = json.loads(roh) if roh else {}
        except ValueError:
            d = {}
        return {k: v for k, v in d.items() if k in QUELLEN and isinstance(v, bool)} if isinstance(d, dict) else {}
    return lesen(zeilen.get(KEY)), lesen(zeilen.get(KEY_ALT))


def zustand():
    """Welche Quellen sind an? -> {"quellen": {Quelle: bool}, "gesperrt": bool}; gesperrt: MTG_QUELLEN legt es fest, die Oberfläche stellt nichts."""
    env = _umgebung()
    if env is not None:
        return {"quellen": {k: k in env for k in QUELLEN}, "gesperrt": True}
    werte, alt = gespeichert()
    return {"quellen": {k: werte.get(k, alt.get(k, q["standard"])) for k, q in QUELLEN.items()}, "gesperrt": False}


def an(quelle):
    return zustand()["quellen"][quelle]


def pruefen(quelle):
    """Die einzige Stelle, die über einen Abruf entscheidet: wirft QuelleAus, wenn die Quelle abgeschaltet ist."""
    if not an(quelle):
        raise QuelleAus(quelle)


def setzen(conn, neu):
    """Schalter speichern (conn: Hauptsammlung). neu: {Quelle: bool}; was fehlt, behält den heutigen Stand. Gespeichert wird immer der ganze Satz, damit
    ein späterer anderer Standard nichts umstellt. Mit MTG_QUELLEN ValueError. -> zustand()"""
    if not isinstance(neu, dict) or not neu or any(k not in QUELLEN or not isinstance(v, bool) for k, v in neu.items()):
        raise ValueError("Erwartet: {Quelle: an oder aus} für edhrec, spellbook oder cardmarket")
    z = zustand()
    if z["gesperrt"]:
        raise ValueError(f"Die Quellen sind in der Umgebung festgelegt ({ENV_QUELLEN}). Dort ändern, nicht hier.")
    with conn:
        conn.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (KEY, json.dumps(z["quellen"] | neu)))
    return zustand()


def beschreibung():
    """Für die Seite „Quellen“: Scryfall (ohne Schalter) und die drei anderen mit Zweck, Inhalt der Anfragen, Rhythmus, Link und Stand."""
    z = zustand()
    scryfall = {"key": "scryfall", "name": "Scryfall", "an": True, "schaltbar": False, "link": "https://scryfall.com/docs/api",
                "zweck": "Karten, Bilder, Preise und Sets. Ohne Scryfall gibt es keinen Import, deshalb hat diese Quelle keinen Schalter.",
                "schickt": "Kartennamen und Kennungen der Karten, die du importierst oder erfasst, dazu Adresse und Programmname mit Version.",
                "wie_oft": "Beim Import, beim Erfassen und einmal am Tag für Preise und neue Sets (höchstens zwei Anfragen pro Sekunde); Gesamtdaten nur, wenn jemand scannt: der Katalog aller Karten (rund 75 MB) beim ersten Öffnen von „Erfassen“ und danach höchstens einmal am Tag, solange er gebraucht wird (in den letzten 30 Tagen geöffnet oder etwas auf einer Scan-Liste); die deutschen Kartennamen (rund 378 MB) nur mit dem Schalter in den Einstellungen des Scanners.",
                "hinweis": ""}
    github = {"key": "github", "name": "GitHub", "an": True, "schaltbar": False, "link": f"{version.REPO}/releases",
              "zweck": "Nachsehen, ob es eine neue Version von Pappenheimer gibt.",
              "schickt": "Nichts aus deiner Sammlung. GitHub sieht die Adresse des Rechners und den Programmnamen mit Version; gefragt wird nur nach der neuesten Veröffentlichung dieses Projekts.",
              "wie_oft": "Nur auf Knopfdruck („Nach Updates suchen“ unter Konten und Sicherung, nur für das Hauptkonto), eine Anfrage. Nie von selbst, auch nicht im täglichen Lauf. Dafür gibt es keinen Schalter.",
              "hinweis": ""}
    return {"gesperrt": z["gesperrt"], "env": ENV_QUELLEN,
            "items": [scryfall] + [{"key": k, "name": q["name"], "an": z["quellen"][k], "schaltbar": True, "link": q["link"], "zweck": q["zweck"],
                                    "schickt": q["schickt"], "wie_oft": q["wie_oft"], "hinweis": q["hinweis"]} for k, q in QUELLEN.items()] + [github]}


def _call(url, body=None, missing=(404,)):
    """GET, mit body POST (JSON). Statuscodes in missing -> None. Abstand je Host, bei 429/5xx bis zu 3 Versuche (429: SPERRE warten)."""
    host = urllib.parse.urlsplit(url).netloc
    if host in HOST_QUELLE:
        pruefen(HOST_QUELLE[host])
    headers = dict(HEADERS)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    for versuch in range(3):
        time.sleep(max(0.0, _last.get(host, 0) + GAP.get(host, 0.5) - time.monotonic()))
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in missing:
                return None
            if e.code not in (429, 500, 502, 503, 504) or versuch == 2:
                raise
            time.sleep(SPERRE if e.code == 429 else 2 * (versuch + 1))
        finally:
            _last[host] = time.monotonic()


# --- GitHub: neueste Veröffentlichung (Phase 50, PLAN E31) --------------------------------------------------------------------
# Kein Eintrag in QUELLEN und kein Schalter: Der Abruf geht nur durch den Knopf „Nach Updates suchen“ (server.api_update), nie von selbst.
RELEASE_URL = f"https://api.github.com/repos/{version.REPO.removeprefix('https://github.com/')}/releases/latest"


def nummern(v):
    """„0.9.1“ oder „v0.9.1“ -> (0, 9, 1); alles andere (Vorabversion „0.9.1-rc1“, Unsinn) -> None."""
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", v) if isinstance(v, str) else None
    return tuple(map(int, m.groups())) if m else None


def neueste_version():
    """Die neueste Veröffentlichung dieses Projekts bei GitHub -> {"version", "titel", "url"}, oder None, wenn es noch keine gibt. Vorabversionen,
    Entwürfe und Tags ohne Versionsnummer zählen nicht. Die Adresse baut die App selbst aus Repository und Version, aus der Antwort kommt nur der Titel."""
    r = _call(RELEASE_URL)
    if not isinstance(r, dict) or r.get("prerelease") or r.get("draft") or not nummern(r.get("tag_name")):
        return None
    v = r["tag_name"].lstrip("v")
    return {"version": v, "titel": str(r.get("name") or "")[:200], "url": f"{version.REPO}/releases/tag/v{v}"}


def scryfall_cards(ids, progress=None):
    """Karten per Scryfall-ID (75 je Anfrage). -> (Karten, nicht gefundene IDs)"""
    cards, missing = [], []
    for i in range(0, len(ids), 75):
        d = _call("https://api.scryfall.com/cards/collection", {"identifiers": [{"id": x} for x in ids[i:i + 75]]})
        cards += d["data"]
        missing += [x.get("id") for x in d["not_found"]]
        if progress:
            progress(min(i + 75, len(ids)), len(ids))
    return cards, missing


def scryfall_names(names):
    """Karten per Name (75 je Anfrage; Vorderseite genügt). -> (Karten, nicht gefundene Namen)"""
    cards, missing = [], []
    for i in range(0, len(names), 75):
        d = _call("https://api.scryfall.com/cards/collection", {"identifiers": [{"name": x} for x in names[i:i + 75]]})
        cards += d["data"]
        missing += [x.get("name") for x in d["not_found"]]
    return cards, missing


def scryfall_lookup(identifiers, progress=None):
    """Karten zu beliebigen Kennungen ({"id"}, {"set", "collector_number"}, {"name", "set"}, {"name"}), 75 je Anfrage.
    -> (Karten, nicht gefundene Kennungen); die Zuordnung macht der Aufrufer (Scryfall antwortet ohne Reihenfolge-Garantie)."""
    cards, missing = [], []
    for i in range(0, len(identifiers), 75):
        d = _call("https://api.scryfall.com/cards/collection", {"identifiers": identifiers[i:i + 75]})
        cards += d["data"]
        missing += d["not_found"]
        if progress:
            progress(min(i + 75, len(identifiers)), len(identifiers))
    return cards, missing


def scryfall_sets():
    """Alle Sets (eine Anfrage) mit code, name, set_type, released_at."""
    return _call("https://api.scryfall.com/sets")["data"]


def scryfall_rulings(scryfall_id):
    """Rulings einer Karte (offizielle Erläuterungen, Wizards und Scryfall)."""
    return _call(f"https://api.scryfall.com/cards/{scryfall_id}/rulings")["data"]


def scryfall_search(query, progress=None, unique="cards", seiten=None):
    """Alle Treffer einer Scryfall-Suche, seitenweise (seiten: höchstens so viele Seiten zu 175). unique: cards (eine Karte je Oracle-Text) oder
    prints (jeder Druck, z. B. für ein Set)."""
    url = "https://api.scryfall.com/cards/search?" + urllib.parse.urlencode({"q": query, "unique": unique})
    out, n = [], 0
    while url and (seiten is None or n < seiten):
        d = _call(url)
        n += 1
        if d is None:  # 404 = keine Treffer
            break
        out += d["data"]
        if progress:
            progress(len(out), d["total_cards"])
        url = d["next_page"] if d.get("has_more") else None
    return out


class _Zaehlend:
    """Reicht read() durch und meldet, wie viele Bytes bisher gelesen sind (für den Fortschritt eines Abrufs der Gesamtdaten)."""

    def __init__(self, datei, melde):
        self._datei, self._melde, self._n = datei, melde, 0

    def read(self, groesse=-1):
        b = self._datei.read(groesse)
        self._n += len(b)
        self._melde(self._n)
        return b


def scryfall_bulk(typ="default_cards", progress=None):
    """Scryfall-Gesamtdaten (`/bulk-data`, täglich neu; geprüft 2026-10-11: je Datei `jsonl_download_uri` auf data.scryfall.io, gzip, eine Karte
    je Zeile; default_cards = jeder Druck einmal, 79 MB gepackt). Liest den gzip-Strom Zeile für Zeile, nie die ganze Datei im Speicher; der
    Aufrufer (Katalog, Phase 31) holt sie höchstens einmal am Tag. progress(gelesen, gesamt): Bytes des gepackten Stroms (gesamt =
    `compressed_size` aus /bulk-data, 0 wenn es fehlt), für die Anzeige im Hintergrund-Job (Phase 45). -> Karten, eine nach der anderen"""
    datei = [x for x in _call("https://api.scryfall.com/bulk-data")["data"] if x["type"] == typ]
    if not datei:
        raise ValueError(f"Scryfall kennt keine Gesamtdaten „{typ}“")
    gesamt = datei[0].get("compressed_size") or 0
    time.sleep(max(0.0, _last.get("data.scryfall.io", 0) + GAP["data.scryfall.io"] - time.monotonic()))
    try:
        req = urllib.request.Request(datei[0]["jsonl_download_uri"], headers={"User-Agent": HEADERS["User-Agent"]})
        with urllib.request.urlopen(req, timeout=120) as r, gzip.GzipFile(fileobj=_Zaehlend(r, lambda n: progress(n, gesamt)) if progress else r) as strom:
            for zeile in strom:
                if zeile.strip():
                    yield json.loads(zeile)
    finally:
        _last["data.scryfall.io"] = time.monotonic()


def spellbook_combos(payload):
    """Combos zu einer Deckliste: {"main": [{"card", "quantity"}], "commanders": [...]} (Commander Spellbook find-my-combos)."""
    return _call("https://backend.commanderspellbook.com/find-my-combos", payload)


SPELLBOOK_MAX = 600  # find-my-combos nimmt höchstens so viele Karten in „main“ (Antwort 400 „no more than 600 elements“, geprüft 2026-10-08)


def spellbook_combo_karten(progress=None):
    """Alle Karten, die bei Commander Spellbook in mindestens einer Combo vorkommen, meiste Combos zuerst (2026-10-08: 7.471 Karten,
    75 Seiten zu 100). -> [(Name, Farbidentität, Zahl der Combos)]"""
    url, out = "https://backend.commanderspellbook.com/cards/?ordering=-variant_count&limit=100", []
    while url:
        d = _call(url)
        seite = d["results"]
        out += [(x["name"], x.get("identity") or "", x["variantCount"]) for x in seite if x["variantCount"] > 0]
        if progress:
            progress(len(out))
        url = d.get("next") if seite and seite[-1]["variantCount"] > 0 else None
    return out


def spellbook_bracket(payload):
    """Bracket-Einschätzung zu einer Deckliste (Commander Spellbook estimate-bracket): Karten mit Game Changer, Massen-Landzerstörung, Extrazug,
    Combos mit 2-Karten-Kennzeichen und Spellbooks eigene Einstufung (bracketTag). Nimmt dieselbe Form wie spellbook_combos."""
    return _call("https://backend.commanderspellbook.com/estimate-bracket", payload)


def edhrec_commander(slug):
    """EDHREC-Seite eines Commanders (slug) oder seines Themas („commander/thema“, Phase 10); fehlt sie, antwortet der Server mit 403 -> None."""
    return _call(f"https://json.edhrec.com/pages/commanders/{slug}.json", missing=(403, 404))


def edhrec_salt():
    """Die 100 „salzigsten“ Karten laut EDHREC-Umfrage (0 bis 4, je höher desto mehr ärgert die Karte den Tisch; geprüft 2026-10-08).
    -> [(Name, Salt)]"""
    d = _call("https://json.edhrec.com/pages/top/salt.json")
    return [(c["name"], c["salt"]) for liste in d["container"]["json_dict"]["cardlists"] for c in liste["cardviews"] if c.get("salt") is not None]


CARDMARKET_PREISE = "https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_1.json"


def cardmarket_guide():
    """Cardmarket-Preisliste für Magic als Text (öffentlich, täglich neu, ca. 26 MB; geprüft 2026-10-08). Je Produkt low, trend, avg1/7/30,
    jeweils auch Foil; Zuordnung über Scryfalls cardmarket_id. Der Aufrufer holt sie höchstens einmal am Tag."""
    pruefen("cardmarket")  # läuft nicht über _call
    time.sleep(max(0.0, _last.get("downloads.s3.cardmarket.com", 0) + GAP["downloads.s3.cardmarket.com"] - time.monotonic()))
    try:
        with urllib.request.urlopen(urllib.request.Request(CARDMARKET_PREISE, headers={"User-Agent": HEADERS["User-Agent"]}), timeout=120) as r:
            return r.read().decode("utf-8")
    finally:
        _last["downloads.s3.cardmarket.com"] = time.monotonic()


# --- Lokales Ollama (optional, PLAN E15): nur aus der Umgebung konfiguriert, nie aus der Oberfläche ------------------------------------
OLLAMA = os.environ.get("MTG_OLLAMA", "http://127.0.0.1:11434").rstrip("/")
OLLAMA_EMBED = os.environ.get("MTG_OLLAMA_EMBED", "nomic-embed-text")
OLLAMA_CHAT = os.environ.get("MTG_OLLAMA_CHAT", "qwen3:4b-instruct")


def _ollama(pfad, body=None, timeout=60):
    req = urllib.request.Request(OLLAMA + pfad, data=json.dumps(body).encode() if body is not None else None, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def ollama_modelle():
    """Installierte Modelle oder None, wenn Ollama nicht läuft (kurze Wartezeit, damit die Oberfläche nicht hängt)."""
    try:
        return [m["name"] for m in _ollama("/api/tags", timeout=1.5)["models"]]
    except (urllib.error.URLError, OSError, ValueError, KeyError):
        return None


def ollama_embed(texte):
    """Embeddings zu Texten (eine Anfrage). -> [[Zahlen]]"""
    return _ollama("/api/embed", {"model": OLLAMA_EMBED, "input": texte})["embeddings"]


def ollama_json(anleitung, frage, schema):
    """Antwort des Chat-Modells als JSON nach Schema (Ollama „format“, Temperatur 0)."""
    r = _ollama("/api/chat", {"model": OLLAMA_CHAT, "stream": False, "format": schema, "options": {"temperature": 0, "num_predict": 120},  # kurz: nur eine Suche
                             "messages": [{"role": "system", "content": anleitung}, {"role": "user", "content": frage}]})
    return json.loads(r["message"]["content"])
