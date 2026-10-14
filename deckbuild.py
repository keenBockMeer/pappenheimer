"""Commander-Ranking, Deckbau, Verteilung auf Decks. Rechnet aus Datenbank und Cache, Netz nur über übergebene Abruf-Funktionen."""
import html
import json
import math
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

import mtg
import sources

EDHREC_MAX_AGE = timedelta(days=30)
TAG_MAX_AGE = timedelta(days=30)
TAGS = ("ramp", "draw", "removal", "boardwipe", "tutor")
ROLE = {"ramp": "ramp", "draw": "draw", "removal": "removal", "boardwipe": "wipe", "tutor": "tutor"}
QUOTAS = (("ramp", 10), ("draw", 10), ("removal", 8), ("boardwipe", 3))
LABEL = {"commander": "Commander", "ramp": "Ramp", "draw": "Draw", "removal": "Removal", "wipe": "Wipes", "tutor": "Tutoren",
         "core": "Weitere Karten", "land": "Länder", "basic": "Basics"}
LANDS = 37
LAND_MIN_W = 0.15  # ponytail: Nicht-Basic-Länder erst ab diesem Gewicht, höchstens LAND_MAX; nach Phase 4 nachjustieren
LAND_MAX = 25
TOP10_MIN_W = 0.25  # ab diesem Gewicht gilt eine Karte auf der Liste eines Top-10-Commanders als relevant
BASIC_NAMES = {"Plains", "Island", "Swamp", "Mountain", "Forest", "Wastes"}
GC_LIMIT = {1: 0, 2: 0, 3: 3}  # Bracket -> höchstens so viele Game Changer; ab 4 unbegrenzt

# Themen (Phase 10): EDHREC kennt je Commander Themenseiten (…/commander/landfall.json) mit den Karten aus Decks genau dieses Themas.
THEME_TRIES = 3       # automatisch werden höchstens so viele gängige Themen geprüft (je eine EDHREC-Seite)
THEME_MIN_SHARE = 0.25  # „gängig“: mindestens ein Viertel der Decks des häufigsten Themas
THEME_MIN_DECKS = 10  # automatisch nur Themen mit mindestens so vielen Decks
THEME_PRIOR = 100     # Themenseite zählt n/(n+100): dünne Seiten (5 Decks) ändern kaum etwas, große (1600 Decks) fast alles
FIT_BONUS = 0.3       # ponytail: Zuschlag aufs Gewicht für Karten, deren Funktion zum Thema passt. Gemessen (Legolas, echte Sammlung): 0,15 → 13 von 28
                      # weiteren Karten passen bei 29 % Abdeckung · 0,3 → 20 von 30 bei 25 % · 0,5 → 26 von 31 bei 21 %; nach echten Decks nachjustieren
THEME_FIT_MIN = 0.5   # passen weniger als die Hälfte der weiteren Karten zum Thema, warnt der Deckbau
# Strategie-Etiketten ohne eigene Kartenfunktion: werden nicht automatisch gewählt (von Hand schon)
GENERIC = {"aggro", "midrange", "control", "combo", "good stuff", "ramp", "big mana", "stompy", "tempo", "toolbox", "group slug",
           "group hug", "politics", "chaos", "card draw", "cantrips"}
# Funktion einer Karte, erkannt am Kartentext (ohne Erinnerungstext in Klammern) und am Typ: Schlüssel -> (Anzeigename, Textmuster, Typmuster)
# ponytail: reine Textmuster, keine Bewertung. Sie ordnen Lückenfüller und zählen, wie viele Karten zum Thema passen; nach echten Decks nachjustieren
FUNCTIONS = {k: (label, re.compile(text), re.compile(typ) if typ else None) for k, (label, text, typ) in {
    "lands": ("Länder und Landfall", r"\blandfall\b|\blands? (?:you control )?enters?\b|additional lands?|play lands? from|\bfor each lands?\b|"
              r"\bnumber of lands\b|\bor more lands\b|search your library for [^.]{0,40}\bland\b|\bland cards? from your (?:graveyard|library|hand)|"
              r"\bland cards?[^.]{0,30}onto the battlefield|\bexplore\b|put (?:a|an|up to \w+|any number of) land", None),
    "counters": ("Marken (+1/+1)", r"[+-]1/[+-]1 counters?|\bproliferate\b|\b(?:evolve|adapt|bolster|outlast|fabricate|support|riot|modular|graft|"
                 r"reinforce|undying|backup|training)\b", None),
    "tokens": ("Spielsteine", r"\bcreates? [^.]{0,80}\btokens?\b|\bpopulate\b|\bamass\b|\btokens? you control\b|\bconvoke\b|"
               r"creatures you control (?:get|have)|each creature you control gets?", None),
    "artifacts": ("Artefakte", r"\bartifacts? (?:you control|spells?|creatures?|tokens?)|\byour artifacts?\b|\btreasures?\b|\bclues?\b|\baffinity\b|"
                  r"\bimprovise\b|\bmetalcraft\b", r"Artifact"),
    "attach": ("Ausrüstung und Auren", r"\bequip\b|equipped creature|enchanted creature|\battach|\bauras?\b|\breconfigure\b", r"Equipment|Aura"),
    "enchantments": ("Verzauberungen", r"\benchantments? (?:you control|spells?)|\byour enchantments?\b|\bconstellation\b|\bsagas?\b", r"Enchantment"),
    "lifegain": ("Lebensgewinn", r"\byou gain\b[^.]{0,30}\blife\b|\blifelink\b|\blife you gained\b|\bwhenever you gain life\b", None),
    "graveyard": ("Friedhof", r"\bgraveyards?\b|\bmill(?:s|ed)?\b|\bdredge\b|\bsurveil\b|\bflashback\b|\bescape\b|\bunearth\b|\bdelirium\b|"
                  r"\bthreshold\b|\bdescend\b|\bembalm\b|\beternalize\b|\bdisturb\b|\bretrace\b|\bjump-start\b|\baftermath\b", None),
    "spells": ("Zauber", r"\binstant or sorcery\b|\bnoncreature spells?\b|\bmagecraft\b|\bprowess\b|\bstorm\b|\bcopy target (?:instant|sorcery)|"
               r"\bcast (?:an? |your )?(?:instant|sorcery)", r"Instant|Sorcery"),
    "sacrifice": ("Opfern", r"\bsacrifice (?:a|an|another|two|three|x|any number of|up to)\b|whenever (?:a|another|one or more)[^.,]{0,40}\bdies?\b|"
                  r"whenever you sacrifice|\bexploit\b|\bdevour\b|\bafterlife\b|\bundying\b|\bpersist\b", None),
    "blink": ("Blinken", r"\bflicker\b|\bblink\b|exile[^.]{0,120}\breturn (?:it|that card|them|those cards|the exiled cards?)[^.]{0,40}"
              r"(?:to|onto) the battlefield|\bcauses? a triggered ability", None),
    "treasure": ("Schätze", r"\btreasures?\b", None),
    "flying": ("Flug", r"\bflying\b", None),
}.items()}
# EDHREC-Thema (kleingeschrieben) -> Funktion; Themen ohne Eintrag (Stämme, Strategien) bekommen nur die EDHREC-Gewichte
THEME_FN = {t: fn for fn, ts in {
    "lands": ("landfall", "lands matter"), "counters": ("+1/+1 counters", "counters matter", "proliferate", "infect", "-1/-1 counters"),
    "tokens": ("tokens", "go wide", "anthems", "populate", "amass"), "artifacts": ("artifacts", "affinity", "improvise"),
    "attach": ("equipment", "auras", "voltron"), "enchantments": ("enchantress", "sagas"), "lifegain": ("lifegain",),
    "graveyard": ("reanimator", "graveyard", "self-mill", "mill", "dredge", "flashback", "descend"),
    "spells": ("spellslinger", "storm", "spell copy", "x spells", "prowess", "all spells"), "sacrifice": ("aristocrats", "sacrifice"),
    "blink": ("blink", "etb"), "treasure": ("treasure",), "flying": ("flying",)}.items() for t in ts}
REMINDER = re.compile(r"\([^)]*\)")


def functions_of(text, type_line):
    """Funktionen einer Karte (Schlüssel aus FUNCTIONS)."""
    t = REMINDER.sub(" ", (text or "").lower())
    return {k for k, (_, rx, ty) in FUNCTIONS.items() if rx.search(t) or (ty and ty.search(type_line or ""))}


def key(name):
    return name.split(" // ")[0].strip().lower()


def slug(name):
    s = unicodedata.normalize("NFKD", name.split(" // ")[0]).encode("ascii", "ignore").decode().lower()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9 -]", "", s).strip().replace(" ", "-"))


def is_land(type_line):
    return "Land" in (type_line or "").split(" // ")[0]


# --- EDHREC (Parsing nur hier) -----------------------------------------------------------------------------------

def parse_edhrec(raw):
    """EDHREC-Seite -> kompakt: je Karte Gewicht w = Anteil der Decks + positive Synergie (ponytail: naive Heuristik)."""
    jd = raw["container"]["json_dict"]
    cards = {}
    for cl in jd["cardlists"]:
        for cv in cl["cardviews"]:
            if cv["name"] in BASIC_NAMES:
                continue
            pot = cv.get("potential_decks") or 0
            inc = (cv.get("num_decks") or 0) / pot if pot else 0.0
            syn = cv.get("synergy") or 0.0
            w = inc + max(syn, 0.0)
            k = key(cv["name"])
            if k not in cards or w > cards[k]["w"]:
                cards[k] = {"name": cv["name"], "w": round(w, 4), "inc": round(inc, 4), "syn": round(syn, 4)}
    c = jd["card"]
    return {"name": c["name"], "decks": c.get("num_decks") or 0, "rank": c.get("rank"), "ci": "".join(c.get("color_identity") or []),
            "cards": cards, "themes": [[t["value"], t["count"], t.get("slug") or slug(t["value"])]
                                       for t in (raw.get("panels", {}).get("taglinks") or [])[:10]]}


def edhrec_cached(conn, sl, now=None):
    """-> (frisch?, geparste Daten oder None)"""
    r = conn.execute("SELECT json, fetched_at FROM edhrec WHERE slug = ?", (sl,)).fetchone()
    if not r:
        return False, None
    alt = (now or datetime.now(timezone.utc)) - EDHREC_MAX_AGE
    return datetime.strptime(r["fetched_at"], mtg.TS).replace(tzinfo=timezone.utc) > alt, json.loads(r["json"])


def edhrec_vorhanden(conn, sl, now=None):
    """Gibt es EDHREC-Daten, mit denen sich ohne Abruf rechnen lässt? Frische immer; ältere nur, solange EDHREC abgeschaltet ist (dann gibt es keine
    neuen, und ein Ranking aus den gemerkten Daten ist besser als keins)."""
    fresh, data = edhrec_cached(conn, sl, now)
    return fresh or (data is not None and not sources.an("edhrec"))


def edhrec_data(conn, sl, fetch=None, now=None, force=False):
    """Geparste EDHREC-Daten eines Commanders (sl) oder eines Themas („commander/thema“) aus dem Cache (30 Tage) oder per Abruf;
    None = es gibt keine Seite (404/403). force: Cache übergehen."""
    fresh, data = edhrec_cached(conn, sl, now)
    if fresh and not force:
        return data
    try:
        raw = (fetch or sources.edhrec_commander)(sl)
    except sources.QuelleAus:  # Phase 44: abgeschaltet; was schon gemerkt ist, gilt weiter (auch über die 30 Tage hinaus), sonst gibt es nichts
        if data is not None:
            return data
        raise
    try:
        data = parse_edhrec(raw) if raw else None
    except (KeyError, TypeError, IndexError):  # Seite mit unerwartetem Aufbau (z. B. Partner): überspringen, nicht abbrechen
        data = None
    conn.execute("INSERT OR REPLACE INTO edhrec VALUES (?,?,?)", (sl, json.dumps(data, separators=(",", ":"), ensure_ascii=False),
                                                                    (now or datetime.now(timezone.utc)).strftime(mtg.TS)))
    conn.commit()
    return data


# --- Rollen-Tags (Scryfall-Suche) --------------------------------------------------------------------------------

def ensure_tags(conn, fetch=None, now=None, progress=None):
    """Rollen-Tags (ramp, draw, ...) monatlich neu laden. -> True, wenn geladen wurde"""
    now = now or datetime.now(timezone.utc)
    r = conn.execute("SELECT value FROM meta WHERE key = 'tags_at'").fetchone()
    if r and datetime.strptime(r[0], mtg.TS).replace(tzinfo=timezone.utc) > now - TAG_MAX_AGE:
        return False
    search = fetch or (lambda q: sources.scryfall_search(q, progress=progress))
    for tag in TAGS:
        found = search(f"otag:{tag} f:commander")
        ids = {d.get("oracle_id") or d["card_faces"][0]["oracle_id"] for d in found}
        with conn:
            conn.execute("DELETE FROM tags WHERE tag = ?", (tag,))
            conn.executemany("INSERT OR IGNORE INTO tags VALUES (?,?)", [(i, tag) for i in ids])
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('tags_at', ?)", (now.strftime(mtg.TS),))
    conn.commit()
    return True


# --- Verfügbarkeit und Commander-Kandidaten ----------------------------------------------------------------------

def free_copies(conn, extra=None):
    """oracle_id -> Kopien, die noch in kein gespeichertes Deck verplant sind (extra: zusätzlich Verplantes im Speicher)."""
    free = dict(mtg.available(conn))
    for oid, n in conn.execute("SELECT oracle_id, COUNT(*) FROM deck_cards GROUP BY oracle_id"):
        if oid in free:
            free[oid] -= n
    for oid, n in (extra or {}).items():
        if oid in free:
            free[oid] -= n
    return {o: n for o, n in free.items() if n > 0}


def owned_cards(conn, free):
    """Freie Karten, eine Zeile je oracle_id: Kartendaten und billigster Preis (ohne fertige Decks)."""
    ex = json.dumps(sorted(mtg.deck_binders(conn)))
    rows = conn.execute(
        f"SELECT c.oracle_id, c.name, c.type_line, c.mana_cost, c.cmc, c.color_identity ci, c.game_changer gc, c.legal_commander legal, "
        f"c.edhrec_rank rank, c.image_url image, json_extract(c.json, '$.artist') artist, c.oracle_text text, MIN({mtg.PRICE}) price "
        f"FROM collection col JOIN cards c USING (scryfall_id) "
        f"WHERE {mtg.OWNED} AND col.binder NOT IN (SELECT value FROM json_each(?)) AND c.oracle_id IN (SELECT value FROM json_each(?)) "
        f"GROUP BY c.oracle_id", (ex, json.dumps(list(free)))).fetchall()
    return {r["oracle_id"]: dict(r) for r in rows}


def candidates(cards):
    return [c for c in cards.values() if c["legal"] and (("Legendary" in c["type_line"] and "Creature" in c["type_line"])
                                                          or "can be your commander" in (c["text"] or ""))]


def find_commander(cards, name):
    if name in cards and cards[name] in candidates(cards):
        return cards[name]
    cs, n = candidates(cards), name.strip().lower()
    for hit in (lambda c: c["name"].lower() == n, lambda c: key(c["name"]) == n,
                lambda c: c["name"].lower().startswith(n), lambda c: n in c["name"].lower()):
        found = [c for c in cs if hit(c)]
        if found:
            return min(found, key=lambda c: (len(c["name"]), c["name"]))
    raise ValueError(f"Kein verfügbarer Commander „{name}“ in der Sammlung")


def coverage(data, have):
    """Abdeckung = Σ w der verfügbaren empfohlenen Karten / Σ w aller empfohlenen (ohne Basics). -> (Anteil, vorhanden, gesamt)"""
    tot = sum(c["w"] for c in data["cards"].values())
    mine = [c["w"] for k, c in data["cards"].items() if k in have]
    return (sum(mine) / tot if tot else 0.0), len(mine), len(data["cards"])


def ranking(conn, fetch=None, progress=None, only_cached=False, extra_used=None, now=None):
    """Commander nach Abdeckung. -> (Zeilen, noch nicht geladene Kandidaten). Erster Lauf lädt EDHREC mit 1 req/s."""
    cards = owned_cards(conn, free_copies(conn, extra_used))
    have = {key(c["name"]) for c in cards.values()}
    cands = sorted(candidates(cards), key=lambda c: c["name"])
    out, pending = [], 0
    for i, c in enumerate(cands, 1):
        sl = slug(c["name"])
        if only_cached and not edhrec_vorhanden(conn, sl, now):
            pending += 1
            continue
        if progress:
            progress(i, len(cands), c["name"])
        data = edhrec_data(conn, sl, fetch, now)
        if data:
            cov, n, total = coverage(data, have)
            out.append({"oracle_id": c["oracle_id"], "name": c["name"], "ci": c["ci"], "image": c["image"], "coverage": cov,
                        "have": n, "total": total, "decks": data["decks"], "price": c["price"], "artist": c["artist"],
                        "themes": [t[0] for t in data["themes"] if t[0].lower() not in GENERIC][:3]})
    out.sort(key=lambda r: (-r["coverage"], r["name"]))
    return out, pending


# --- Themen: welche Karten zum Commander passen, nicht nur welche beliebt sind --------------------------------------

def theme_options(data):
    """Themen eines Commanders laut EDHREC, häufigstes zuerst: [{name, slug, count, fn}] (fn: Funktion aus FUNCTIONS, falls bekannt)."""
    return [{"name": t[0], "count": t[1], "slug": t[2] if len(t) > 2 else slug(t[0]), "fn": THEME_FN.get(t[0].lower())} for t in data["themes"]]


def blend(general, theme):
    """Gewichte der Themenseite und der allgemeinen Liste mischen, die Themenseite zu n/(n+THEME_PRIOR) (n = Decks des Themas).
    Karten, die in Themendecks nicht auftauchen, verlieren entsprechend an Gewicht."""
    n, k = theme["decks"], THEME_PRIOR
    cards = {}
    for c in general["cards"].keys() | theme["cards"].keys():
        g, t = general["cards"].get(c), theme["cards"].get(c)
        mix = lambda f: round((n * (t[f] if t else 0.0) + k * (g[f] if g else 0.0)) / (n + k), 4)
        cards[c] = {"name": (t or g)["name"], "w": mix("w"), "inc": mix("inc"), "syn": mix("syn")}
    return general | {"cards": cards}


def pick_theme(conn, csl, data, have, theme, fetch, now, warnings):
    """Thema des Decks samt gemischter Gewichte (blend). "none" = keins (allgemeine Liste); Name oder Slug = genau dieses; "auto" = unter den
    gängigen Themen (höchstens THEME_TRIES, ohne GENERIC, mit mindestens THEME_MIN_DECKS Decks) das, dessen Karten du am vollständigsten hast.
    None, wenn es keine Themenseite gibt."""
    if theme == "none" or not data["themes"]:
        return None
    if len(data["themes"][0]) < 3:  # Cache aus der Zeit vor den Themen-Slugs: Seite einmal neu laden
        data = edhrec_data(conn, csl, fetch, now, force=True) or data
    opts = theme_options(data)
    if theme == "auto":
        pool = [o for o in opts if o["name"].lower() not in GENERIC and o["count"] >= THEME_MIN_DECKS]
        top = max((o["count"] for o in pool), default=0)
        cands = [o for o in pool if o["count"] >= THEME_MIN_SHARE * top][:THEME_TRIES]
    else:
        cands = [o for o in opts if theme.lower() in (o["name"].lower(), o["slug"])]
        if not cands:
            raise ValueError(f"EDHREC kennt zu diesem Commander kein Thema „{theme}“ ({', '.join(o['name'] for o in opts)})")
    best, tried = None, []
    for o in cands:
        td = edhrec_data(conn, f"{csl}/{o['slug']}", fetch, now)
        if td and td["cards"]:
            mixed = blend(data, td)
            cov = coverage(mixed, have)[0]
            tried.append([o["name"], round(cov, 4)])
            if best is None or cov > best[0]:
                best = (cov, o, mixed, td["decks"])
    if not best:
        if theme != "auto":
            warnings.append(f"keine EDHREC-Seite zum Thema {cands[0]['name']}: allgemeine Liste")
        return None
    return best[1] | {"data": best[2], "auto": theme == "auto", "tried": tried, "weight": round(best[3] / (best[3] + THEME_PRIOR), 3)}


def mark_top10(conn, rank, now=None):
    """Karten auf den EDHREC-Listen der 10 besten Commander gelten im Sortier-Plan als relevant (Tag top10). Wer auf mehreren dieser Listen
    steht, wird als gefragt gemerkt (meta „demand“), damit die Verkaufsliste davor warnt (Konfliktkarten)."""
    wanted = defaultdict(list)
    for r in rank[:10]:
        data = edhrec_cached(conn, slug(r["name"]), now)[1]
        for k, c in data["cards"].items():
            if c["w"] >= TOP10_MIN_W:
                wanted[k].append(r["name"])
    ids, mehrfach = set(), {}
    for oid, name in conn.execute("SELECT oracle_id, name FROM cards"):
        names = wanted.get(key(name))
        if names:
            ids.add(oid)
            if len(names) > 1:
                mehrfach[oid] = names
    with conn:
        conn.execute("DELETE FROM tags WHERE tag = 'top10'")
        conn.executemany("INSERT OR IGNORE INTO tags VALUES (?, 'top10')", [(i,) for i in ids])
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('demand', ?)", (json.dumps(mehrfach, ensure_ascii=False),))
    return len(ids)


def demand(conn):
    """oracle_id -> Namen der Top-Commander, auf deren Liste die Karte steht (nur Karten auf mindestens zwei Listen)."""
    r = conn.execute("SELECT value FROM meta WHERE key = 'demand'").fetchone()
    return json.loads(r[0]) if r else {}


# --- Deckbau -----------------------------------------------------------------------------------------------------

def distribute(n, weights):
    """n Stück im Verhältnis der Gewichte (größter Rest)."""
    tot = sum(weights.values())
    raw = {k: n * w / tot for k, w in weights.items()}
    out = {k: int(v) for k, v in raw.items()}
    for k in sorted(raw, key=lambda k: (-(raw[k] - out[k]), k))[:n - sum(out.values())]:
        out[k] += 1
    return out


def basic_info(conn, name):
    r = conn.execute("SELECT oracle_id, image_url FROM cards WHERE name = ? AND type_line LIKE 'Basic%' ORDER BY updated_at DESC LIMIT 1", (name,)).fetchone()
    return (r["oracle_id"], r["image_url"]) if r else (f"basic:{name.lower()}", None)


def card_rows(conn, names, fetch_names=None):
    """Kartenzeilen zu Namen aus der Datenbank; was fehlt, lädt fetch_names von Scryfall und speichert es. -> {Name: Zeile oder None}"""
    def lookup(n):
        return conn.execute("SELECT * FROM cards WHERE name = ? COLLATE NOCASE OR name LIKE ? ORDER BY updated_at DESC LIMIT 1", (n, n + " // %")).fetchone()
    rows = {n: lookup(n) for n in names}
    todo = [n for n, r in rows.items() if r is None]
    if todo and fetch_names:
        mtg.store_cards(conn, fetch_names(todo)[0])
        rows = {n: lookup(n) for n in names}
    return rows


def missing_cards(conn, data, have, ci, limit=40, fetch_names=None):
    """Empfohlene, aber nicht verfügbare Karten (nach Gewicht) mit Preis; nur commander-legal und in der Farbidentität."""
    want = sorted((v for k, v in data["cards"].items() if k not in have), key=lambda v: (-v["w"], v["name"]))[:limit]
    rows = card_rows(conn, [v["name"] for v in want], fetch_names)
    out = []
    for v in want:
        r = rows[v["name"]]
        if r and r["legal_commander"] and set(r["color_identity"]) <= ci:
            out.append({"name": r["name"], "w": v["w"], "inc": v["inc"], "price": r["price_eur"] if r["price_eur"] is not None else r["price_eur_foil"],
                        "image": r["image_url"], "gc": bool(r["game_changer"]), "oracle_id": r["oracle_id"]})
    return out


# --- Ranking-Modi und Lücken-Report ------------------------------------------------------------------------------

MODES = ("machbar", "beliebt", "geheimtipp", "guenstig")
MODE_MIN_DECKS = {"geheimtipp": 30}  # Mindestzahl EDHREC-Decks, wenn nichts gewählt ist (darunter ist die Kartenliste Rauschen)
MODE_MIN_COVERAGE = 0.2              # Beliebt: nur Commander, von denen du mindestens so viel frei hast
CHEAP_TOP, CHEAP_CARDS = 12, 10      # Günstig: für die 12 machbarsten Commander die 10 wichtigsten fehlenden Karten zusammenzählen
GAP_TOP, GAP_MAX = 10, 30            # Lücken: Listen der 10 besten Commander vergleichen, höchstens 30 Karten zeigen


def rank_modes(conn, rank, mode="machbar", min_decks=0, fetch_names=None, now=None):
    """Ranking anders sortiert. machbar: Abdeckung · beliebt: meiste EDHREC-Decks (ab MODE_MIN_COVERAGE Abdeckung) · geheimtipp: Abdeckung unter den
    Commandern mit höchstens der mittleren Deckzahl · guenstig: kleinster Zukauf (Preis der CHEAP_CARDS wichtigsten fehlenden Karten, Zeilen
    bekommen buy und buy_n). min_decks: nur Commander mit so vielen EDHREC-Decks. rank kommt nach Abdeckung sortiert aus ranking()."""
    rows = [r for r in rank if r["decks"] >= min_decks]
    if mode == "beliebt":
        return sorted((r for r in rows if r["coverage"] >= MODE_MIN_COVERAGE), key=lambda r: (-r["decks"], r["name"]))
    if mode == "geheimtipp":
        mitte = sorted(r["decks"] for r in rows)[(len(rows) - 1) // 2] if rows else 0  # unterer Median: bei zwei Commandern der weniger gespielte
        return [r for r in rows if r["decks"] <= mitte]
    if mode == "guenstig":
        have = {key(c["name"]) for c in owned_cards(conn, free_copies(conn)).values()}
        out = []
        for r in rows[:CHEAP_TOP]:
            preise = [m["price"] for m in missing_cards(conn, edhrec_cached(conn, slug(r["name"]), now)[1], have, set(r["ci"]), 40, fetch_names)
                      if m["price"] is not None][:CHEAP_CARDS]
            out.append(r | {"buy": round(sum(preise), 2), "buy_n": len(preise)})
        return sorted(out, key=lambda r: (r["buy"], -r["coverage"], r["name"]))
    return rows


def gaps(conn, top=GAP_TOP, limit=GAP_MAX, fetch_names=None, now=None):
    """Karten, die auf den Listen mehrerer deiner besten Commander stehen (Gewicht ab TOP10_MIN_W) und dir fehlen, mit Preis; die auf den meisten
    Listen zuerst. -> {"commanders": [Namen], "items": [{name, n, commanders, w, price, image, oracle_id, gc}]}"""
    have = {key(c["name"]) for c in owned_cards(conn, free_copies(conn)).values()}
    rank, _ = ranking(conn, only_cached=True, now=now)
    wanted = {}
    for r in rank[:top]:
        for k, c in edhrec_cached(conn, slug(r["name"]), now)[1]["cards"].items():
            if k not in have and c["w"] >= TOP10_MIN_W:
                e = wanted.setdefault(k, {"name": c["name"], "w": 0.0, "commanders": []})
                e["w"] += c["w"]
                e["commanders"].append(r["name"])
    best = sorted(wanted.values(), key=lambda e: (-len(e["commanders"]), -e["w"], e["name"]))[:limit * 2]  # Puffer für nicht legale Karten
    rows = card_rows(conn, [e["name"] for e in best], fetch_names)
    out = [{"name": rows[e["name"]]["name"], "n": len(e["commanders"]), "commanders": e["commanders"], "w": round(e["w"], 2),
            "price": rows[e["name"]]["price_eur"] if rows[e["name"]]["price_eur"] is not None else rows[e["name"]]["price_eur_foil"],
            "image": rows[e["name"]]["image_url"], "oracle_id": rows[e["name"]]["oracle_id"], "gc": bool(rows[e["name"]]["game_changer"])}
           for e in best if rows[e["name"]] and rows[e["name"]]["legal_commander"]]
    return {"commanders": [r["name"] for r in rank[:top]], "items": out[:limit]}


COMBO_MAX_AGE = timedelta(days=30)
COMBO_FARBEN = [set(x) for x in ("WUB", "WUR", "WUG", "WBR", "WBG", "WRG", "UBR", "UBG", "URG", "BRG")]  # je drei Farben eine Anfrage


def _combo(c, besitz):
    """Combo aus der Spellbook-Antwort -> kompakt; fehlt = Karten, die du nicht besitzt."""
    karten = [u["card"]["name"] for u in c["uses"]]
    folgen = [p["feature"]["name"] for p in c.get("produces", [])]
    return {"id": c["id"], "cards": karten, "fehlt": [k for k in karten if key(k) not in besitz], "identity": c.get("identity") or "",
            "result": next((f for f in folgen if "win" in f.lower()), (folgen or [""])[0]), "tag": BRACKET_TAG.get(c.get("bracketTag"), c.get("bracketTag"))}


def sammlung_combos(conn, karten=None, combos=None, progress=None, now=None):
    """Combos aus deiner ganzen Sammlung (Phase 18) über Commander Spellbook. find-my-combos nimmt höchstens 600 Karten, deshalb nur die Karten,
    die überhaupt in Combos vorkommen (Liste von Spellbook, 30 Tage im Cache), und je Kombination aus drei Farben eine Anfrage (Farblose immer
    dabei): Combos mit vier oder fünf Farben fehlen. Ergebnis 30 Tage in meta „combos:sammlung“.
    -> {"at", "fertig": [Combos, alle Karten im Besitz], "fast": [Combos, eine Karte fehlt], "karten": geprüfte, "abgeschnitten": zu viele je Anfrage}"""
    now = now or datetime.now(timezone.utc)
    alt = conn.execute("SELECT value FROM meta WHERE key = 'spellbook:karten'").fetchone()
    liste = json.loads(alt[0]) if alt else None
    if not liste or datetime.strptime(liste["at"], mtg.TS).replace(tzinfo=timezone.utc) < now - COMBO_MAX_AGE:
        liste = {"at": now.strftime(mtg.TS), "karten": (karten or sources.spellbook_combo_karten)()}
        with conn:
            conn.execute("INSERT OR REPLACE INTO meta VALUES ('spellbook:karten', ?)", (json.dumps(liste, ensure_ascii=False),))
    besitz = {key(r[0]) for r in conn.execute(f"SELECT DISTINCT c.name FROM collection col JOIN cards c USING (scryfall_id) WHERE {mtg.OWNED}")}
    meine = [(n, ci, v) for n, ci, v in liste["karten"] if key(n) in besitz]
    fertig, fast, abgeschnitten = {}, {}, 0
    for i, farben in enumerate(COMBO_FARBEN, 1):
        gruppe = [n for n, ci, v in meine if set(ci) <= farben]  # meine ist nach Zahl der Combos sortiert: abgeschnitten werden die seltensten
        abgeschnitten = max(abgeschnitten, len(gruppe) - sources.SPELLBOOK_MAX)
        if progress:
            progress(i, len(COMBO_FARBEN))
        res = (combos or sources.spellbook_combos)({"main": [{"card": n, "quantity": 1} for n in gruppe[:sources.SPELLBOOK_MAX]], "commanders": []})["results"]
        for c in res.get("included", []):
            fertig.setdefault(c["id"], _combo(c, besitz))
        for c in res.get("almostIncluded", []):
            k = _combo(c, besitz)
            if len(k["fehlt"]) == 1 and len(k["cards"]) > 1:  # eine Karte fehlt, mindestens eine hast du (Ein-Karten-Combos zählen nicht)
                fast.setdefault(c["id"], k)
    out = {"at": now.strftime(mtg.TS), "karten": len(meine), "abgeschnitten": abgeschnitten,
           "fertig": sorted(fertig.values(), key=lambda c: (len(c["cards"]), c["cards"])),
           "fast": sorted(fast.values(), key=lambda c: (len(c["cards"]), c["fehlt"], c["cards"]))}
    with conn:
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('combos:sammlung', ?)", (json.dumps(out, ensure_ascii=False),))
    return out


def sammlung_combos_cached(conn):
    r = conn.execute("SELECT value FROM meta WHERE key = 'combos:sammlung'").fetchone()
    return json.loads(r[0]) if r else None


def bedarf(conn, fetch=None, fetch_names=None, now=None, limit=GAP_MAX):
    """Was deinen Decks fehlt (Phase 16): Karten von den EDHREC-Listen der Commander deiner gebauten und fertigen Decks (Gewicht ab TOP10_MIN_W),
    die im jeweiligen Deck fehlen und nicht frei sind; je Karte, wie vielen Decks sie hilft, mit Preis. Fehlende EDHREC-Seiten (fertige Decks) lädt
    fetch einmal. -> {"decks": [Namen], "items": [{name, n, decks, w, price, image, oracle_id, scryfall_id, gc}]}"""
    decks = [deck_detail(conn, r[0]) for r in conn.execute("SELECT id FROM decks ORDER BY id").fetchall()] + [binder_deck(conn, b["binder"]) for b in binder_decks(conn)]
    frei = {key(c["name"]) for c in owned_cards(conn, free_copies(conn)).values()}
    wanted, namen = {}, []
    for d in decks:
        cmd = d.get("commander")
        data = cmd and edhrec_data(conn, slug(cmd["name"]), fetch, now)
        if not data:
            continue
        namen.append(d["name"])
        drin = {key(c["name"]) for c in d["cards"]} | {key(c["name"]) for c in (d.get("commanders") or [cmd])}
        for k, c in data["cards"].items():
            if k not in drin and k not in frei and c["w"] >= TOP10_MIN_W:
                e = wanted.setdefault(k, {"name": c["name"], "w": 0.0, "decks": []})
                e["w"] += c["w"]
                e["decks"].append(d["name"])
    best = sorted(wanted.values(), key=lambda e: (-len(e["decks"]), -e["w"], e["name"]))[:limit * 2]  # Puffer für nicht legale Karten
    rows = card_rows(conn, [e["name"] for e in best], fetch_names)
    out = [{"name": r["name"], "n": len(e["decks"]), "decks": e["decks"], "w": round(e["w"], 2), "oracle_id": r["oracle_id"], "scryfall_id": r["scryfall_id"],
            "price": r["price_eur"] if r["price_eur"] is not None else r["price_eur_foil"], "image": r["image_url"], "gc": bool(r["game_changer"])}
           for e in best if (r := rows[e["name"]]) and r["legal_commander"]]
    return {"decks": namen, "items": out[:limit]}


def groups(cards, theme=None):
    """Karten nach Rolle gruppiert (feste Reihenfolge), je Gruppe nach Manawert und Name. „Weitere Karten“, die zum Thema passen
    (fit), stehen als eigene Gruppe „Thema: …“ davor."""
    by = defaultdict(list)
    for c in cards:
        by["theme" if c["role"] == "core" and c.get("fit") else c["role"]].append(c)
    label = LABEL | {"theme": f"Thema: {theme}" if theme else "Thema"}
    order = ("commander", "theme", "ramp", "draw", "removal", "wipe", "tutor", "core", "land", "basic")
    return [{"role": r, "label": label[r], "count": sum(c["qty"] for c in by[r]),
             "cards": sorted(by[r], key=lambda c: (c["cmc"] or 0, c["name"]))} for r in order if r in by]


BASIC_COLOR = {"Plains": "W", "Island": "U", "Swamp": "B", "Mountain": "R", "Forest": "G"}


def deck_stats(conn, cards, ci):
    """Manakurve (Nichtland-Karten je Manawert 0 bis 6 und mehr) und Farbquellen: je Farbe der Farbidentität, wie viele Länder sie erzeugen
    und wie viele Farbsymbole die Zauber haben. cards: Einträge mit role, qty, cmc, mana_cost, name, oracle_id (ohne Commander)."""
    spells = [c for c in cards if c["role"] not in ("land", "basic", "commander")]
    lands = [c for c in cards if c["role"] in ("land", "basic")]
    curve = [0] * 7
    for c in spells:
        curve[min(int(c["cmc"] or 0), 6)] += c["qty"]
    produced = {r[0]: json.loads(r[1] or "[]") for r in conn.execute(
        "SELECT oracle_id, json_extract(json, '$.produced_mana') FROM cards WHERE oracle_id IN (SELECT value FROM json_each(?)) GROUP BY oracle_id",
        (json.dumps([c["oracle_id"] for c in lands]),))}
    colors = [x for x in "WUBRG" if x in ci]
    quellen, symbole = Counter(), Counter()
    for c in lands:
        for f in ([BASIC_COLOR.get(c["name"])] if c["role"] == "basic" else produced.get(c["oracle_id"], [])):
            quellen[f] += c["qty"]
    doppelt = Counter()  # meiste Symbole einer Farbe in einer einzelnen Karte (CC, CCC …)
    for c in spells:
        je = Counter()
        for s in re.findall(r"\{([^}]+)\}", c["mana_cost"] or ""):
            for p in s.split("/"):
                symbole[p] += c["qty"]
                je[p] += 1
        for f, n in je.items():
            doppelt[f] = max(doppelt[f], n)
    n, n_lands = sum(c["qty"] for c in cards if c["role"] != "commander"), sum(c["qty"] for c in lands)
    ramp = sum(c["qty"] for c in cards if c["role"] == "ramp")
    return {"curve": curve, "lands": n_lands, "colors": [farbe(x, quellen[x], symbole[x], doppelt[x], n) for x in colors],
            "hand": starthand(n, n_lands, ramp)}


# --- Starthand und Farbquellen: exakt gerechnet (hypergeometrisch), keine Simulation, keine übernommenen Tabellen ---------------
HAND, ZUG3, ZUG4 = 7, 9, 10   # gesehene Karten bis Zug 3 bzw. 4: 7 auf der Hand, dann eine je Zug ab Zug 2 (ponytail: wie für den Startspieler gerechnet)
GUT = 0.9                     # ab dieser Wahrscheinlichkeit klemmt eine Farbe selten (Faustregel, keine Quelle)


def mindestens(N, K, n, k):
    """Wahrscheinlichkeit, unter n von N Karten (K davon „Treffer“) mindestens k Treffer zu ziehen."""
    if N <= 0 or n <= 0:
        return 1.0 if k <= 0 else 0.0
    n = min(n, N)
    return sum(math.comb(K, i) * math.comb(N - K, n - i) for i in range(max(k, 0), min(K, n) + 1)) / math.comb(N, n)


def starthand(n, lands, ramp):
    """Starthand eines Decks mit n Karten: spielbare Hand (2 bis 5 Länder unter 7), drei Länder bis Zug 3, Ramp bis Zug 2. Werte 0 bis 1."""
    spielbar = mindestens(n, lands, HAND, 2) - mindestens(n, lands, HAND, 6)
    return {"n": n, "lands": lands, "ramp": ramp, "spielbar": round(spielbar, 4), "land3": round(mindestens(n, lands, ZUG3, 3), 4),
            "ramp2": round(mindestens(n, ramp, HAND + 1, 1), 4) if ramp else None,
            "lands_hand": round(lands * HAND / n, 2) if n else 0.0}


def farbe(c, quellen, symbole, doppelt, n):
    """Farbquellen einer Farbe: Länder, die sie erzeugen, Symbole der Zauber, Wahrscheinlichkeit einer Quelle bis Zug 3 und, wenn eine Karte
    zwei oder mehr Symbole dieser Farbe hat, von zwei Quellen bis Zug 4."""
    p1 = mindestens(n, quellen, ZUG3, 1) if symbole else None
    p2 = mindestens(n, quellen, ZUG4, 2) if doppelt >= 2 else None
    return {"c": c, "sources": quellen, "symbols": symbole, "p1": round(p1, 4) if p1 is not None else None,
            "p2": round(p2, 4) if p2 is not None else None, "knapp": any(p is not None and p < GUT for p in (p1, p2))}


def theme_label(target):
    return ", ".join(FUNCTIONS[k][0] for k in sorted(target))


def theme_name(info):
    """Name der Gruppe „Thema: …“: das EDHREC-Thema, wenn dessen Funktion geprüft wurde, sonst die geprüfte Funktion selbst."""
    return info and (info["name"] if info["fn_from"] == "theme" else info["fn_label"])


def theme_info(th, target, fit, of):
    """Thema eines Decks für Anzeige und Speicher: Name (None: nur die Funktion aus dem Text des Commanders), Funktionen, Treffer unter
    den „weiteren Karten“ (fit von of; None, wenn zum Thema keine Funktion bekannt ist)."""
    if not th and not target:
        return None
    return {"name": th["name"] if th else None, "slug": th["slug"] if th else None, "auto": bool(th and th["auto"]),
            "count": th["count"] if th else None, "weight": th["weight"] if th else None, "tried": th["tried"] if th else [],
            "fn": sorted(target), "fn_label": theme_label(target), "fn_from": "theme" if th and th["fn"] else "text",
            "fit": fit if target else None, "of": of}


def build(conn, name, bracket=3, fetch=None, fetch_names=None, now=None, extra_used=None, theme="auto"):
    """99 + Commander aus freien Karten: Quoten, dann nach Gewicht, 37 Länder, Rest Basics. Das Gewicht kommt von der EDHREC-Seite
    des Themas (theme: "auto" = gängiges Thema mit der besten Abdeckung, "none" = allgemeine Liste, sonst Name oder Slug); Lückenfüller
    ohne Gewicht werden nach Funktion (passt zum Thema) und erst dann nach edhrec_rank gewählt."""
    if bracket not in (1, 2, 3, 4, 5):
        raise ValueError("Bracket muss 1 bis 5 sein")
    cards = owned_cards(conn, free_copies(conn, extra_used))
    cmd = find_commander(cards, name)
    csl = slug(cmd["name"])
    data = edhrec_data(conn, csl, fetch, now)
    warnings = []
    if not data:
        data = {"cards": {}, "decks": 0, "themes": []}
        warnings.append("keine EDHREC-Seite zu diesem Commander: Karten nur nach edhrec_rank")
    have_keys = {key(c["name"]) for c in cards.values()}
    th = pick_theme(conn, csl, data, have_keys, theme, fetch, now, warnings)
    wdata = th["data"] if th else data
    target = {th["fn"]} if th and th["fn"] else functions_of(cmd["text"], cmd["type_line"])
    ci = set(cmd["ci"])
    tags = defaultdict(set)
    for oid, t in conn.execute("SELECT oracle_id, tag FROM tags"):
        tags[oid].add(t)
    has_tags = any(t in TAGS for ts in tags.values() for t in ts)
    if not has_tags:
        warnings.append("keine Rollen-Tags geladen (mtg commanders), Quoten greifen nicht")
    limit = GC_LIMIT.get(bracket)
    pool = [c | {"w": wdata["cards"].get(key(c["name"]), {}).get("w"), "fit": bool(target) and bool(target & functions_of(c["text"], c["type_line"]))}
            for c in cards.values()
            if c["oracle_id"] != cmd["oracle_id"] and c["legal"] and set(c["ci"]) <= ci and not c["type_line"].startswith("Basic")]
    by_w = lambda cs: sorted((c for c in cs if c["w"] is not None), key=lambda c: (-c["w"], c["name"]))
    spells = [c for c in pool if not is_land(c["type_line"])]
    # Gewicht plus Zuschlag für passende Funktion; Karten ohne EDHREC-Gewicht zählen 0 (Lückenfüller, passende vor unpassenden, dann edhrec_rank)
    order = sorted(spells, key=lambda c: (-((c["w"] or 0.0) + FIT_BONUS * c["fit"]), c["rank"] is None, c["rank"] or 0, c["name"]))
    slots, chosen, gc = 99 - LANDS, {}, [0]

    def take(c, role):
        if c["oracle_id"] in chosen or len(chosen) >= slots or (c["gc"] and limit is not None and gc[0] >= limit):
            return False
        chosen[c["oracle_id"]] = (c, role)
        gc[0] += c["gc"]
        return True
    for tag, n in QUOTAS:
        got = 0
        for c in order:
            if got >= n:
                break
            got += tag in tags[c["oracle_id"]] and take(c, ROLE[tag])
    for c in order:
        take(c, next((ROLE[t] for t in TAGS if t in tags[c["oracle_id"]]), "core"))
    for tag, n in QUOTAS:
        have = sum(tag in tags[oid] for oid in chosen)
        if has_tags and have < n:
            warnings.append(f"nur {have}/{n} {LABEL[ROLE[tag]]}")
    nonbasic = [c for c in by_w([c for c in pool if is_land(c["type_line"])]) if c["w"] >= LAND_MIN_W][:LAND_MAX]
    short = slots - len(chosen)
    if short:
        warnings.append(f"nur {len(chosen)}/{slots} Spells aus der Sammlung, {short} Basics zusätzlich")
    n_basic = LANDS - len(nonbasic) + short
    colors = [x for x in "WUBRG" if x in ci]
    sym = Counter()
    for c in [cmd] + [c for c, _ in chosen.values()]:
        for s in re.findall(r"\{([^}]+)\}", c["mana_cost"] or ""):
            sym.update(p for p in s.split("/") if p in colors)
    names = {"W": "Plains", "U": "Island", "B": "Swamp", "R": "Mountain", "G": "Forest"}
    basics = distribute(n_basic, {names[x]: max(sym[x], 1) for x in colors}) if colors else {"Wastes": n_basic}
    out = [{"oracle_id": c["oracle_id"], "name": c["name"], "role": role, "qty": 1, "price": c["price"], "image": c["image"], "cmc": c["cmc"],
            "mana_cost": c["mana_cost"], "type": c["type_line"], "w": c["w"], "gc": bool(c["gc"]), "fit": c["fit"]} for c, role in chosen.values()]
    out += [{"oracle_id": c["oracle_id"], "name": c["name"], "role": "land", "qty": 1, "price": c["price"], "image": c["image"], "cmc": 0,
             "mana_cost": "", "type": c["type_line"], "w": c["w"], "gc": False} for c in nonbasic]
    for b, n in sorted(basics.items()):
        if n:
            oid, img = basic_info(conn, b)
            out.append({"oracle_id": oid, "name": b, "role": "basic", "qty": n, "price": 0.0, "image": img, "cmc": 0, "mana_cost": "",
                        "type": f"Basic Land — {b}", "w": None, "gc": False})
    spells_chosen = [c for c, _ in chosen.values()]
    ups = [m for m in missing_cards(conn, wdata, have_keys, ci, 40, fetch_names) if not (m["gc"] and limit is not None and gc[0] + 1 > limit)][:10]
    cov, n_have, total = coverage(wdata, {key(c["name"]) for c in spells_chosen} | {key(c["name"]) for c in nonbasic}) if wdata["cards"] else (0, 0, 0)
    head = {"oracle_id": cmd["oracle_id"], "name": cmd["name"], "ci": cmd["ci"], "role": "commander", "qty": 1, "image": cmd["image"],
            "price": cmd["price"], "mana_cost": cmd["mana_cost"], "cmc": cmd["cmc"], "type": cmd["type_line"], "artist": cmd["artist"]}
    core = [c for c, role in chosen.values() if role == "core"]
    info = theme_info(th, target, sum(c["fit"] for c in core), len(core))
    if info and info["fn_from"] == "theme" and info["of"] >= 10 and info["fit"] < THEME_FIT_MIN * info["of"]:  # nur bei einem Thema, nicht bei der Vermutung aus dem Commander-Text
        warnings.append(f"nur {info['fit']} von {info['of']} weiteren Karten passen zu {info['name']} ({info['fn_label']})")
    return {"commander": head, "theme": info, "stats": deck_stats(conn, out, cmd["ci"]),
            "bracket": bracket, "cards": out, "groups": groups([head] + out, theme_name(info)), "warnings": warnings,
            "upgrades": ups, "themes": data["themes"], "gc": gc[0], "coverage": cov, "decks": data["decks"],
            "avg_cmc": sum(c["cmc"] or 0 for c in spells_chosen) / len(spells_chosen) if spells_chosen else 0.0,
            "value": (cmd["price"] or 0) + sum((c["price"] or 0) * c["qty"] for c in out)}


# --- Speichern, Liste, Detail, Export ----------------------------------------------------------------------------

def save_deck(conn, deck):
    cmd = deck["commander"]
    with conn:
        did = conn.execute("INSERT INTO decks(name, commander_oracle_id, bracket, saved_at) VALUES (?,?,?,?)",
                           (cmd["name"], cmd["oracle_id"], deck["bracket"], mtg.now_iso())).lastrowid
        rows = [(did, cmd["oracle_id"], "commander")]
        for c in deck["cards"]:
            rows += [(did, c["oracle_id"], c["role"])] * c["qty"]
        conn.executemany("INSERT INTO deck_cards VALUES (?,?,?)", rows)
        extra = {k: deck[k] for k in ("warnings", "upgrades", "themes", "theme", "coverage", "decks", "gc")}
        conn.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (f"deck:{did}", json.dumps(extra, ensure_ascii=False)))
    return did


def delete_deck(conn, did):
    with conn:
        conn.execute("DELETE FROM deck_cards WHERE deck_id = ?", (did,))
        conn.execute("DELETE FROM meta WHERE key = ?", (f"deck:{did}",))
        return conn.execute("DELETE FROM decks WHERE id = ?", (did,)).rowcount


def cheapest(conn):
    """oracle_id -> billigster Preis unter den Kopien im Besitz."""
    return {r[0]: r[1] for r in conn.execute(
        f"SELECT c.oracle_id, MIN({mtg.PRICE}) FROM collection col JOIN cards c USING (scryfall_id) WHERE {mtg.OWNED} GROUP BY c.oracle_id")}


def deck_detail(conn, did):
    d = conn.execute("SELECT * FROM decks WHERE id = ?", (did,)).fetchone()
    if not d:
        return None
    price = cheapest(conn)
    meta = conn.execute("SELECT value FROM meta WHERE key = ?", (f"deck:{did}",)).fetchone()
    extra = json.loads(meta[0]) if meta else {}
    theme = extra.get("theme")
    target = set(theme["fn"]) if theme and theme.get("fn") else set()
    cards, cmd = [], None
    for oid, role, n in conn.execute("SELECT oracle_id, role, COUNT(*) FROM deck_cards WHERE deck_id = ? GROUP BY oracle_id, role", (did,)).fetchall():
        c = conn.execute("SELECT name, image_url, cmc, mana_cost, type_line, oracle_text, color_identity, json_extract(json, '$.artist') artist FROM cards "
                         "WHERE oracle_id = ? ORDER BY updated_at DESC LIMIT 1", (oid,)).fetchone()
        item = {"oracle_id": oid, "name": c["name"] if c else oid.split(":")[-1].title(), "role": role, "qty": n, "image": c["image_url"] if c else None,
                "cmc": c["cmc"] if c else 0, "mana_cost": c["mana_cost"] if c else "", "type": c["type_line"] if c else "",
                "price": 0.0 if role == "basic" else price.get(oid),
                "fit": bool(c and role == "core" and target & functions_of(c["oracle_text"], c["type_line"]))}
        if role == "commander":
            cmd = item | {"ci": c["color_identity"] if c else "", "artist": c["artist"] if c else None}
        else:
            cards.append(item)
    core = [c for c in cards if c["role"] == "core"]
    if theme:  # Treffer aus den Karten, wie sie jetzt im Deck stehen
        theme = theme | {"fit": sum(c["fit"] for c in core) if target else None, "of": len(core)}
    spells = [c for c in cards if c["role"] not in ("land", "basic")]
    return {"id": did, "name": d["name"], "bracket": d["bracket"], "saved_at": d["saved_at"], "commander": cmd, "cards": cards,
            "groups": groups([cmd] + cards if cmd else cards, theme_name(theme)), "theme": theme, "stats": deck_stats(conn, cards, (cmd or {}).get("ci", "")),
            "avg_cmc": sum(c["cmc"] or 0 for c in spells) / len(spells) if spells else 0.0,
            "value": ((cmd or {}).get("price") or 0) + sum((c["price"] or 0) * c["qty"] for c in cards),
            "warnings": extra.get("warnings", []), "upgrades": extra.get("upgrades", []), "themes": extra.get("themes", []),
            "coverage": extra.get("coverage", 0), "gc": extra.get("gc", 0)}


def binder_deck(conn, name):
    """Fertiges Deck aus seinem Binder (importierte Deckliste oder ManaBox-Deck): Commander aus der Liste, Rollen wie beim Deckbau."""
    rows = conn.execute(
        f"SELECT c.oracle_id, c.name, c.image_url, c.cmc, c.mana_cost, c.type_line, c.color_identity, c.game_changer, "
        f"json_extract(c.json, '$.artist') artist, SUM(col.qty) qty, MIN({mtg.PRICE}) price FROM collection col JOIN cards c USING (scryfall_id) "
        f"WHERE col.binder = ? AND {mtg.OWNED} GROUP BY c.oracle_id", (name,)).fetchall()
    if not rows:
        return None
    m = conn.execute("SELECT value FROM meta WHERE key = ?", ("deckbinder:" + name,)).fetchone()
    cmd_ids = json.loads(m[0])["commanders"] if m else []
    tags = defaultdict(set)
    for oid, t in conn.execute("SELECT oracle_id, tag FROM tags WHERE oracle_id IN (SELECT value FROM json_each(?))",
                               (json.dumps([r["oracle_id"] for r in rows]),)):
        tags[oid].add(t)
    cmds, cards = [], []
    for r in rows:
        tl = r["type_line"] or ""
        role = ("commander" if r["oracle_id"] in cmd_ids else "basic" if tl.startswith("Basic") else "land" if is_land(tl)
                else next((ROLE[t] for t in TAGS if t in tags[r["oracle_id"]]), "core"))
        item = {"oracle_id": r["oracle_id"], "name": r["name"], "role": role, "qty": r["qty"], "image": r["image_url"], "cmc": r["cmc"],
                "mana_cost": r["mana_cost"], "type": tl, "price": 0.0 if role == "basic" else r["price"], "gc": bool(r["game_changer"]),
                "ci": r["color_identity"] or ""}
        if role == "commander":
            item["artist"] = r["artist"]
        (cmds if role == "commander" else cards).append(item)
    farben = "".join(c["ci"] for c in (cmds or cards))
    ci = "".join(x for x in "WUBRG" if x in farben)
    spells = [c for c in cards if c["role"] not in ("land", "basic")]
    return {"binder": name, "name": name, "kind": "fertig", "commander": cmds[0] | {"ci": ci} if cmds else None, "stats": deck_stats(conn, cards, ci),
            "commanders": cmds, "ci": ci, "cards": cards, "groups": groups(cmds + cards),
            "count": sum(c["qty"] for c in cmds + cards), "basics": sum(c["qty"] for c in cards if c["role"] == "basic"),
            "avg_cmc": sum((c["cmc"] or 0) * c["qty"] for c in spells) / max(1, sum(c["qty"] for c in spells)),
            "value": sum((c["price"] or 0) * c["qty"] for c in cmds + cards), "gc": sum(c["qty"] for c in cmds + cards if c["gc"]),
            "bracket": None, "warnings": [], "upgrades": [], "themes": [], "coverage": 0, "log": mtg.deck_log(conn, name)}


def binder_decks(conn):
    """Alle fertigen Decks (Deck-Binder im Bestand), nach Name."""
    da = {r[0] for r in conn.execute(f"SELECT DISTINCT col.binder FROM collection col WHERE {mtg.OWNED}")}
    out = []
    for name in sorted(mtg.deck_binders(conn) & da, key=str.lower):
        d = binder_deck(conn, name)
        out.append({k: d[k] for k in ("binder", "name", "kind", "commander", "ci", "value", "avg_cmc", "gc", "basics")} | {"cards": d["count"]})
    return out


def decks_list(conn):
    out = []
    for r in conn.execute("SELECT id FROM decks ORDER BY id"):
        d = deck_detail(conn, r["id"])
        out.append({k: d[k] for k in ("id", "name", "bracket", "value", "avg_cmc", "warnings", "saved_at")}
                   | {"commander": d["commander"], "cards": sum(c["qty"] for c in d["cards"]) + 1,
                      "basics": sum(c["qty"] for c in d["cards"] if c["role"] == "basic")})
    return out


def export_text(deck):
    """Textliste im Arena-Format (Köpfe Commander und Deck), das Moxfield und Archidekt beim Einfügen lesen."""
    cmds = deck.get("commanders") or ([deck["commander"]] if deck.get("commander") else [])
    lines = (["Commander"] + [f"1 {c['name']}" for c in cmds] + [""] if cmds else []) + ["Deck"]
    lines += [f"{c['qty']} {c['name']}" for c in sorted(deck["cards"], key=lambda c: (c["role"] in ("land", "basic"), c["name"]))]
    return "\n".join(lines) + "\n"


# --- Bracket-Check einer Deckliste -------------------------------------------------------------------------------

BRACKET_TAG = {"E": "Exhibition", "C": "Core", "P": "Powerful", "O": "Oddball", "S": "Spicy", "R": "Ruthless", "B": "Banned"}  # Spellbooks eigene Skala


def bracket_check(text, estimate):
    """Welche Brackets passen zu einer Deckliste (Text, wie beim Import)? Commander Spellbook (estimate = sources.spellbook_bracket) klassifiziert Karten
    und Combos; die Mindest-Stufe folgt den Regeln dieses Projekts: Game Changer wie bei GC_LIMIT, Massen-Landzerstörung und Combos mit Lock ab 4,
    Extrazug-Karten ab 3, 2-Karten-Combos ab COMBO_WARN_BRACKET + 1. Das Bracket selbst bleibt Absprache am Tisch.
    -> {commanders, cards, min_bracket, why, game_changers, mass_land_denial, extra_turns, banned, combos, spellbook}"""
    deck = mtg.parse_decklist(text)
    if not deck["cards"]:
        raise ValueError("Keine Karten erkannt: eine Karte je Zeile, zum Beispiel „1 Sol Ring“")
    cmds = [c for c in deck["cards"] if c["commander"]]
    res = estimate({"main": [{"card": c["name"], "quantity": c["qty"]} for c in deck["cards"] if not c["commander"]],
                    "commanders": [{"card": c["name"], "quantity": 1} for c in cmds]})
    flagged = lambda flag: sorted(c["card"]["name"] for c in res["cards"] if c[flag])
    combos = []
    try:
        gc, mld, extra, banned = flagged("gameChanger"), flagged("massLandDenial"), flagged("extraTurn"), flagged("banned")
        for c in res["combos"]:
            if c.get("relevant"):
                v = c["combo"]
                folgen = [p["feature"]["name"] for p in v.get("produces", [])]
                combos.append({"cards": [u["card"]["name"] for u in v["uses"]], "two_card": bool(c["definitelyTwoCard"]), "result": next((f for f in folgen if "win" in f.lower()), (folgen or [""])[0]),
                               "tag": BRACKET_TAG.get(v.get("bracketTag"), v.get("bracketTag")), "mass_land_denial": bool(c["massLandDenial"]), "extra_turn": bool(c["extraTurn"]),
                               "lock": bool(c["lock"] or c["skipTurns"] or c["controlAllOpponents"])})
    except (KeyError, TypeError) as e:  # Spellbook hat das Antwortformat geändert (tests/live_check.py prüft es)
        raise ValueError(f"Unerwartete Antwort von Commander Spellbook ({type(e).__name__}: {e})") from None
    low, why = 1, []

    def need(n, grund):
        nonlocal low
        low = max(low, n)
        why.append(f"ab Bracket {n}: {grund}")
    if gc:
        need(4 if len(gc) > GC_LIMIT[3] else 3, f"{len(gc)} Game Changer")
    if mld or any(c["mass_land_denial"] for c in combos):
        need(4, "Massen-Landzerstörung")
    if extra:
        need(3, f"{len(extra)} Extrazug-Karte{'n' if len(extra) > 1 else ''}")
    if any(c["two_card"] for c in combos):
        need(COMBO_WARN_BRACKET + 1, f"{sum(c['two_card'] for c in combos)} 2-Karten-Combo{'s' if sum(c['two_card'] for c in combos) > 1 else ''}")
    if any(c["lock"] for c in combos):
        need(4, "Combo, die Gegner aussetzen oder kontrolliert")
    if any(c["extra_turn"] for c in combos):
        need(4, "Combo mit Extrazügen")
    return {"commanders": [c["name"] for c in cmds], "cards": sum(c["qty"] for c in deck["cards"]), "min_bracket": low, "why": why, "game_changers": gc,
            "mass_land_denial": mld, "extra_turns": extra, "banned": banned, "combos": combos, "spellbook": BRACKET_TAG.get(res["bracketTag"], res["bracketTag"])}


# --- Deck verbessern, Pick-Liste (Phase 15) -------------------------------------------------------------------------

STUFEN = (("frei", "Aus deiner Sammlung", None), ("1", "Kauf bis 1 €", 1.0), ("5", "Kauf bis 5 €", 5.0))
STUFE_JE = 5  # Tauschvorschläge je Stufe


def improve(conn, deck, fetch_names=None, now=None, fetch=None):
    """Upgrade-Leiter für ein gebautes oder fertiges Deck: Karten von der EDHREC-Liste des Commanders (beim gebauten Deck mit seinem Thema), die
    fehlen, je mit der schwächsten Karte derselben Rolle als Tausch („rein X, raus Y“, nur wenn X beliebter ist). Stufen: frei in der Sammlung,
    Kauf bis 1 €, bis 5 €. Fehlt die EDHREC-Seite des Commanders (bei fertigen Decks üblich), lädt sie fetch einmal (Cache 30 Tage).
    -> {"stufen": [{key, label, items}], "grund": Text, wenn es nichts zu rechnen gibt}"""
    cmd = deck.get("commander")
    if not cmd:
        return {"stufen": [], "grund": "Erst einen Commander wählen."}
    sl = slug(cmd["name"])
    data = edhrec_data(conn, sl, fetch, now)
    if not data:
        return {"stufen": [], "grund": "EDHREC kennt zu diesem Commander keine Empfehlungen."}
    th = deck.get("theme")
    td = th and th.get("slug") and edhrec_cached(conn, f"{sl}/{th['slug']}", now)[1]
    if td:
        data = blend(data, td)
    w = lambda name: (data["cards"].get(key(name)) or {}).get("w") or 0.0
    # wie beim Deckbau: Karten, deren Funktion zum Thema passt, bekommen FIT_BONUS (sonst schlüge die Leiter vor, das Thema wieder abzubauen)
    target = set(th["fn"]) if th and th.get("fn") else set()
    texte = {r[0]: (r[1], r[2]) for r in conn.execute("SELECT oracle_id, oracle_text, type_line FROM cards WHERE oracle_id IN (SELECT value FROM json_each(?)) "
                                                      "GROUP BY oracle_id", (json.dumps([c["oracle_id"] for c in deck["cards"]]),))}
    wert = lambda name, text, typ: w(name) + FIT_BONUS * (bool(target) and bool(target & functions_of(text, typ)))
    ci = set(cmd.get("ci") or deck.get("ci") or "")
    drin = {key(c["name"]) for c in deck["cards"]} | {key(c["name"]) for c in (deck.get("commanders") or [cmd])}
    tags = defaultdict(set)
    for oid, t in conn.execute("SELECT oracle_id, tag FROM tags"):
        tags[oid].add(t)
    rolle = lambda oid, typ: "land" if is_land(typ) else next((ROLE[t] for t in TAGS if t in tags[oid]), "core")
    raus = defaultdict(list)  # Rolle -> Karten im Deck, schwächste zuerst (Basics und Commander tauscht die App nicht)
    for c in deck["cards"]:
        if c["role"] not in ("basic", "commander"):
            raus[c["role"]].append((wert(c["name"], *texte.get(c["oracle_id"], ("", c.get("type") or ""))), c["name"], c))
    for r in raus.values():
        r.sort(key=lambda t: (t[0], t[1]))
    frei = {key(c["name"]): c for c in owned_cards(conn, free_copies(conn)).values()}
    wanted = sorted((v for k, v in data["cards"].items() if k not in drin), key=lambda v: (-v["w"], v["name"]))[:80]
    zeilen = card_rows(conn, [v["name"] for v in wanted if key(v["name"]) not in frei], fetch_names)
    limit = GC_LIMIT.get(deck.get("bracket") or 5)
    gc, weg, out = deck.get("gc") or 0, set(), {k: [] for k, _, _ in STUFEN}
    for v in wanted:
        c, r = frei.get(key(v["name"])), zeilen.get(v["name"])
        if c:
            karte = {"oracle_id": c["oracle_id"], "name": c["name"], "image": c["image"], "price": c["price"], "type": c["type_line"],
                     "ci": c["ci"], "legal": c["legal"], "gc": bool(c["gc"]), "text": c["text"]}
            stufe = "frei"
        elif r:
            preis = r["price_eur"] if r["price_eur"] is not None else r["price_eur_foil"]
            karte = {"oracle_id": r["oracle_id"], "name": r["name"], "image": r["image_url"], "price": preis, "type": r["type_line"],
                     "ci": r["color_identity"] or "", "legal": r["legal_commander"], "gc": bool(r["game_changer"]), "text": r["oracle_text"]}
            stufe = next((k for k, _, bis in STUFEN[1:] if preis is not None and preis <= bis), None)
        else:
            continue
        if not stufe or len(out[stufe]) >= STUFE_JE or not karte["legal"] or not set(karte["ci"]) <= ci or (karte["gc"] and limit is not None and gc >= limit):
            continue
        role, neu = rolle(karte["oracle_id"], karte["type"]), wert(v["name"], karte.pop("text"), karte["type"])
        schwach = next((t for t in raus[role] if t[1] not in weg and t[0] < neu), None)
        if not schwach:
            continue
        weg.add(schwach[1])
        out[stufe].append({"rein": karte | {"w": round(neu, 4), "inc": v["inc"]}, "raus": {"oracle_id": schwach[2]["oracle_id"], "name": schwach[1],
                           "image": schwach[2].get("image"), "w": schwach[0]}, "role": role, "label": LABEL.get(role, role)})
    return {"stufen": [{"key": k, "label": lab, "items": out[k]} for k, lab, _ in STUFEN], "grund": None}


def pick_list(conn, did, order="set"):
    """Wo die Karten eines gespeicherten Decks liegen, damit du es aus den Bindern zusammensuchen kannst: die Kopien, die der Sortier-Plan
    diesem Deck gibt (die billigsten), nach Binder, Edition und Nummer. Was keine Kopie hat (Standardländer, verplante Karten), steht extra.
    -> {"name", "binders": [{binder, items}], "basics": [...], "fehlt": [...]} oder None"""
    d = deck_detail(conn, did)
    if not d:
        return None
    zeilen = [r for r in mtg.plan(conn) if r["stack"] == "deck" and r["deck"] == d["name"] and r["binder"] not in mtg.deck_binders(conn)]
    hat = Counter()
    je = defaultdict(list)
    nach = (lambda r: (r["added"] or "", r["name"])) if order == "scan" else (lambda r: (r["set"], int(re.match(r"\d*", r["number"]).group() or 0), r["number"], r["name"]))
    for r in sorted(zeilen, key=nach):  # scan: wie eingescannt (so liegen die Karten, wenn der Binder nach dem Scan nicht umsortiert wurde)
        je[r["binder"]].append({k: r[k] for k in ("oracle_id", "name", "set", "number", "foil", "language", "condition", "qty", "image")})
        hat[r["oracle_id"]] += r["qty"]
    alle = ([d["commander"]] if d["commander"] else []) + d["cards"]
    return {"id": did, "name": d["name"], "binders": [{"binder": b, "items": je[b], "cards": sum(i["qty"] for i in je[b])} for b in sorted(je, key=str.lower)],
            "basics": [{"name": c["name"], "qty": c["qty"]} for c in d["cards"] if c["role"] == "basic"],
            "fehlt": [{"oracle_id": c["oracle_id"], "name": c["name"], "qty": c["qty"] - hat[c["oracle_id"]]} for c in alle
                      if c["role"] != "basic" and hat[c["oracle_id"]] < c["qty"]]}


def zerlegen(conn, deck):
    """Rückweg zur Pick-Liste: wohin die Karten gehen, wenn du ein Deck zerlegst (deck = ID eines gespeicherten oder Name eines fertigen Decks).
    Vergleicht den Sortier-Plan mit und ohne das Deck; Kopien mit gleichem Schlüssel sind gleich, also zählt je Druck die Differenz.
    -> {"name", "ziele": [{stack, deck, items}], "karten"} oder None"""
    if isinstance(deck, int):
        r = conn.execute("SELECT name FROM decks WHERE id = ?", (deck,)).fetchone()
        name = r and r[0]
    else:
        name = deck if deck in mtg.deck_binders(conn) else None
    if not name:
        return None
    schl = lambda r: (r["binder"], r["scryfall_id"], r["foil"], r["condition"], r["language"])
    vorher = mtg.plan(conn)
    meine = {schl(r): r for r in vorher if r["stack"] == "deck" and r["deck"] == name}  # ponytail: gleichnamiges gebautes und fertiges Deck zählen zusammen
    alt, neu = Counter(), Counter()
    for r in vorher:
        if schl(r) in meine and not (r["stack"] == "deck" and r["deck"] == name):
            alt[(schl(r), r["stack"], r["deck"])] += r["qty"]
    for r in mtg.plan(conn, zerlegt=deck):
        if schl(r) in meine:
            neu[(schl(r), r["stack"], r["deck"])] += r["qty"]
    ziele = defaultdict(list)
    for (k, stack, ziel), n in sorted((neu - alt).items(), key=lambda x: (meine[x[0][0]]["name"], x[0][0])):
        r = meine[k]
        ziele[(stack, ziel)].append({"oracle_id": r["oracle_id"], "name": r["name"], "set": r["set"], "number": r["number"], "binder": r["binder"],
                                     "foil": r["foil"], "qty": n, "price": r["price"]})
    reihe = {"keep": 0, "deck": 1, "sell": 2, "bulk": 3}
    return {"name": name, "karten": sum(r["qty"] for r in meine.values()),
            "ziele": [{"stack": s, "deck": z, "items": ziele[(s, z)]} for s, z in sorted(ziele, key=lambda x: (reihe[x[0]], x[1] or ""))]}


def proxy_liste(conn, text, fetch_names=None):
    """Proxy-Blatt (Phase 22): Kartennamen, eine je Zeile (Anzahl davor erlaubt, Decklisten gehen auch) -> Bilder aus der Datenbank, sonst Scryfall.
    -> {"karten": [{name, image, qty}], "fehlt": [Namen]}"""
    zeilen = "\n".join(z if not z.strip() or z.strip()[0].isdigit() or z.strip().startswith(("#", "//")) else "1 " + z.strip() for z in (text or "").splitlines())
    liste = mtg.parse_decklist(zeilen)["cards"]
    if not liste:
        raise ValueError("Keine Karten: ein Name je Zeile, zum Beispiel 1 Sol Ring")
    anzahl = Counter()
    for c in liste:
        anzahl[c["name"]] += c["qty"]
    if sum(anzahl.values()) > PROXY_MAX:
        raise ValueError(f"Höchstens {PROXY_MAX} Karten je Blatt-Satz")
    rows = card_rows(conn, list(anzahl), fetch_names)
    return {"karten": [{"name": rows[n]["name"], "image": rows[n]["image_url"], "qty": q} for n, q in anzahl.items() if rows[n]],
            "fehlt": [n for n in anzahl if not rows[n]]}


PROXY_MAX = 120  # ponytail: 14 Seiten; ein ganzes Deck passt, mehr wäre kein Playtest mehr


# --- Mehrere Decks gleichzeitig, Einkaufsliste -------------------------------------------------------------------

def plan_decks(conn, count, bracket=3, save=False, fetch=None, fetch_names=None, progress=None, now=None, only_cached=False, theme="auto"):
    """Gierig: besten Commander bauen, Karten verplanen, nächsten (andere Farbidentität bevorzugt) ... -> fertige Decks
    only_cached: nur Commander mit geladenen EDHREC-Daten (Oberfläche, kein langer Abruf). theme wie bei build (je Commander das beste)."""
    used, decks, seen = Counter(), [], set()
    for i in range(count):
        rank, _ = ranking(conn, fetch, progress if i == 0 else None, only_cached=only_cached, extra_used=used, now=now)
        if not rank:
            break
        # ponytail: Farbidentität, die schon vorkommt, zählt nur 60 %; nach Phase 4 nachjustieren
        pick = max(rank, key=lambda r: (r["coverage"] * (0.6 if r["ci"] in seen else 1.0), r["name"]))
        deck = build(conn, pick["oracle_id"], bracket, fetch, fetch_names, now, extra_used=used, theme=theme)
        seen.add(pick["ci"])
        if save:
            deck["id"] = save_deck(conn, deck)  # gespeichert zählt es über deck_cards als verplant
        else:
            used.update({c["oracle_id"]: c["qty"] for c in deck["cards"] if c["role"] != "basic"})
            used[deck["commander"]["oracle_id"]] += 1
        decks.append(deck)
    return decks


def shopping_list(conn, name, budget=20.0, fetch=None, fetch_names=None, now=None):
    """Fehlende Karten eines Commanders, nach Gewicht je Euro, bis das Budget aufgebraucht ist."""
    cards = owned_cards(conn, free_copies(conn))
    cmd = find_commander(cards, name)
    data = edhrec_data(conn, slug(cmd["name"]), fetch, now)
    if not data:
        raise ValueError(f"keine EDHREC-Seite zu {cmd['name']}")
    have = {key(c["name"]) for c in cards.values()}
    miss = [m for m in missing_cards(conn, data, have, set(cmd["ci"]), 80, fetch_names) if m["price"]]
    miss.sort(key=lambda m: (-m["w"] / m["price"], m["name"]))
    out, spent = [], 0.0
    for m in miss:
        if spent + m["price"] <= budget:
            out.append(m)
            spent += m["price"]
    return cmd, out, spent


# --- Ausgabe (CLI) -----------------------------------------------------------------------------------------------

def format_deck(d):
    cmd, g = d["commander"], {x["role"]: x["count"] for x in d["groups"]}
    out = [f"{cmd['name']} · {cmd['ci'] or 'farblos'} · Bracket {d['bracket']} · Wert {mtg.eur(d['value'])} · Ø Manawert {d['avg_cmc']:.2f}",
           f"  Ramp {g.get('ramp', 0)} · Draw {g.get('draw', 0)} · Removal {g.get('removal', 0)} · Wipes {g.get('wipe', 0)} · Tutoren {g.get('tutor', 0)}"
           f" · Weitere {g.get('core', 0) + g.get('theme', 0)} · Länder {g.get('land', 0) + g.get('basic', 0)} (davon {g.get('basic', 0)} Basics) · Game Changer {d['gc']}"]
    t = d.get("theme")
    if t:
        out.append(f"  Thema: {t['name'] or t['fn_label']}{' (automatisch gewählt)' if t['auto'] else ''}"
                   + (f" · {t['fit']} von {t['of']} weiteren Karten passen ({t['fn_label']}"
                      f"{', laut Kartentext des Commanders' if t['fn_from'] == 'text' else ''})" if t["fit"] is not None else "")
                   + (" · geprüft: " + ", ".join(f"{n} {mtg.pct(c)}" for n, c in t["tried"]) if len(t["tried"]) > 1 else ""))
    out += [f"  ! {w}" for w in d["warnings"]]
    if d["upgrades"]:
        out.append("  Fehlende Upgrades:")
        out += [f"   {u['w']:.2f}  {mtg.eur(u['price']) if u['price'] is not None else 'kein Preis':>9}  {u['name']}" for u in d["upgrades"]]
    return "\n".join(out)


def format_bracket(r):
    out = [f"{', '.join(r['commanders']) or 'Commander unbekannt'} · {r['cards']} Karten · mindestens Bracket {r['min_bracket']} · Spellbook: {r['spellbook']}"]
    out += [f"  {w}" for w in r["why"]] or ["  nichts gefunden, das mehr als Bracket 1 bis 2 verlangt"]
    out += [f"  {label}: {', '.join(r[k])}" for label, k in (("Game Changer", "game_changers"), ("Massen-Landzerstörung", "mass_land_denial"),
                                                              ("Extrazüge", "extra_turns"), ("Gebannt", "banned")) if r[k]]
    out += [f"  Combo{' (2 Karten)' if c['two_card'] else ''}: {' + '.join(c['cards'])} → {c['result']} (Spellbook: {c['tag']})" for c in r["combos"]]
    return "\n".join(out + ["  Das Bracket selbst bleibt Absprache am Tisch."])


def format_ranking(rank, pending, top=20):
    out = [f"{'Abdeckung':>9}  {'Karten':>9}  Commander" if rank else "Keine Ergebnisse."]
    out += [f"{mtg.pct(r['coverage']):>9}  {r['have']:>4}/{r['total']:<4}  {r['name']} ({r['ci'] or '-'}){'  ' + mtg.eur(r['price']) if r['price'] else ''}"
            f"  · {mtg.zahl(r['decks'])} Decks{'  · Zukauf ' + mtg.eur(r['buy']) if 'buy' in r else ''}" for r in rank[:top]]
    if pending:
        out.append(f"({pending} Kandidaten noch nicht geladen: mtg commanders)")
    return "\n".join(out)


# --- Neuigkeiten nach einem Import (Phase 5) ----------------------------------------------------------------------

NEW_COMMANDER_MIN = 0.5  # neuer Commander ab dieser Abdeckung
SELL_NEWS_MIN = 5.0      # neue Karten im Stapel Verkaufen ab diesem Preis
COMBO_WARN_BRACKET = 3   # 2-Karten-Combos warnen in Decks bis zu diesem Bracket
NEWS_MAX = 5             # je Art höchstens so viele Meldungen (ein großer Import soll nicht überfluten)


def new_cards(conn, import_id):
    """Was der Import neu gebracht hat: oracle_id -> Karte mit Menge."""
    return {r["oracle_id"]: dict(r) for r in conn.execute(
        "SELECT c.oracle_id, c.name, SUM(ch.delta) AS n, c.type_line, c.color_identity ci, c.legal_commander legal, c.game_changer gc "
        "FROM changes ch JOIN cards c USING (scryfall_id) WHERE ch.import_id = ? AND ch.delta > 0 GROUP BY c.oracle_id", (import_id,))}


def upgrade_news(conn, new):
    """Neue Karte steht auf der EDHREC-Liste eines gespeicherten Decks und ist beliebter als dessen schwächste Karte derselben Rolle.
    Nur mit freier Kopie: Karten aus fertigen Decks (importierte Decklisten) oder aus einem anderen gespeicherten Deck zählen nicht."""
    free = free_copies(conn)
    tags = defaultdict(set)
    for oid, t in conn.execute("SELECT oracle_id, tag FROM tags"):
        tags[oid].add(t)
    out = []
    for d in conn.execute("SELECT id, name, bracket FROM decks ORDER BY id").fetchall():
        deck = deck_detail(conn, d["id"])
        cmd = deck["commander"]
        data = edhrec_cached(conn, slug(cmd["name"]))[1]
        if not data:
            continue
        th = deck["theme"] if deck["theme"] and deck["theme"].get("slug") else None  # ein Deck mit Thema misst sich an den gemischten Gewichten wie beim Bauen
        tdata = th and edhrec_cached(conn, f"{slug(cmd['name'])}/{th['slug']}")[1]
        if tdata:
            data = blend(data, tdata)
        w = lambda name: data["cards"].get(key(name), {}).get("w", 0.0)
        drin = {c["oracle_id"] for c in deck["cards"]} | {cmd["oracle_id"]}
        limit = GC_LIMIT.get(d["bracket"])
        cand = []
        for oid, c in new.items():
            if oid in drin or oid not in free or key(c["name"]) not in data["cards"] or not c["legal"] or not set(c["ci"]) <= set(cmd["ci"]):
                continue
            if c["gc"] and limit is not None and deck["gc"] + 1 > limit:
                continue
            role = "land" if is_land(c["type_line"]) else next((ROLE[t] for t in TAGS if t in tags[oid]), "core")
            cand.append((-w(c["name"]), c["name"], role))
        weg = set()
        for negw, name, role in sorted(cand):
            same = [c for c in deck["cards"] if c["role"] == role and c["oracle_id"] not in weg]
            if not same:
                continue
            schwach = min(same, key=lambda c: (w(c["name"]), c["name"]))
            if -negw > w(schwach["name"]):
                weg.add(schwach["oracle_id"])
                out.append({"kind": "upgrade", "icon": "↑", "deck": d["id"], "text": f"Upgrade für {d['name']}: {name} rein, {schwach['name']} raus",
                            "sub": f"{name} ist in {mtg.pct(data['cards'][key(name)]['inc'])} der {cmd['name']}-Decks"
                                   f"{' mit Thema ' + th['name'] if tdata else ''}"})
    return out[:NEWS_MAX]


def commander_news(conn, new, edhrec=None, now=None):
    """Neue legendäre Kreatur, zu der du schon genug Empfehlungen hast. edhrec=None: nur schon geladene Seiten."""
    cards = owned_cards(conn, free_copies(conn))
    have = {key(c["name"]) for c in cards.values()}
    cands = {c["oracle_id"] for c in candidates(cards)}
    out = []
    for oid, c in sorted(new.items(), key=lambda t: t[1]["name"]):
        if oid not in cands:
            continue
        sl = slug(c["name"])
        data = edhrec_data(conn, sl, edhrec, now) if edhrec else edhrec_cached(conn, sl, now)[1]
        if data:
            cov = coverage(data, have)[0]
            if cov >= NEW_COMMANDER_MIN:
                out.append({"kind": "commander", "icon": "★", "oracle_id": oid, "text": f"Neuer möglicher Commander: {c['name']}",
                            "sub": f"{mtg.pct(cov)} der empfohlenen Karten hast du schon"})
    return out[:NEWS_MAX]


def sell_news(rows, new):
    """Neue Karten ab SELL_NEWS_MIN €, die im Stapel Verkaufen landen."""
    out = []
    for r in sorted(rows, key=lambda r: (-r["price"], r["name"])):
        if r["stack"] == "sell" and r["oracle_id"] in new and r["price"] >= SELL_NEWS_MIN:
            out.append({"kind": "sell", "icon": "€", "oracle_id": r["oracle_id"], "text": f"{r['name']} → Verkaufen, {mtg.eur(r['price'])}",
                        "sub": "Extra-Kopie, eine behältst du"})
    return out[:NEWS_MAX]


def spellbook_payload(conn, did):
    """Decklisten-Anfrage für Commander Spellbook."""
    d = deck_detail(conn, did)
    return {"main": [{"card": c["name"], "quantity": c["qty"]} for c in d["cards"]],
            "commanders": [{"card": d["commander"]["name"], "quantity": 1}]}


def combo_news(conn, import_id, spellbook):
    """Alle gespeicherten Decks an find-my-combos; neue Combos melden, 2-Karten-Combos in niedrigen Brackets als Warnung."""
    out = []
    for d in conn.execute("SELECT id, name, bracket FROM decks ORDER BY id").fetchall():
        res = (spellbook(spellbook_payload(conn, d["id"])) or {}).get("results", {}).get("included", [])
        r = conn.execute("SELECT value FROM meta WHERE key = ?", (f"combos:{d['id']}",)).fetchone()
        bekannt = set(json.loads(r[0])) if r else set()
        for c in res:
            if c["id"] in bekannt:
                continue
            karten = [u["card"]["name"] for u in c["uses"]]
            warn = len(karten) == 2 and d["bracket"] <= COMBO_WARN_BRACKET
            folge = (c.get("produces") or [{}])[0].get("feature", {}).get("name", "")
            out.append({"kind": "combo_warn" if warn else "combo", "icon": "!" if warn else "∞", "deck": d["id"],
                        "text": f"{'Achtung, 2-Karten-Combo' if warn else 'Neue Combo'} in {d['name']}: {' + '.join(karten)}",
                        "sub": (f"{folge}; " if folge else "") + (f"passt nicht zu Bracket {d['bracket']}" if warn else f"{len(karten)} Karten")})
        conn.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (f"combos:{d['id']}", json.dumps(sorted(c["id"] for c in res))))
    r = conn.execute("SELECT value FROM meta WHERE key = 'news:combos'").fetchone()
    stored = json.loads(r[0]) if r else {}
    if not out and stored.get("import") == import_id:  # zweiter Lauf zum selben Import: die Meldungen bleiben stehen
        return stored["items"]
    conn.execute("INSERT OR REPLACE INTO meta VALUES ('news:combos', ?)", (json.dumps({"import": import_id, "items": out}, ensure_ascii=False),))
    conn.commit()
    return out


def waechter_news(conn, tage=None, now=None):
    """Meldungen des Wächters (Phase 19) zu Karten, die du besitzt oder in Decks hast: gebannt, wieder erlaubt, neu oder nicht mehr Game Changer
    (mit gespeicherten Decks, deren Bracket das nicht mehr erlaubt), Reprint in einem neuen Set."""
    tage = tage or mtg.WAECHTER_TAGE
    ab = ((now or datetime.now(timezone.utc)).date() - timedelta(days=tage)).isoformat()
    besitz = {r[0]: r[1] for r in conn.execute(f"SELECT c.oracle_id, SUM(col.qty) FROM collection col JOIN cards c USING (scryfall_id) WHERE {mtg.OWNED} GROUP BY c.oracle_id")}
    gebaut = defaultdict(list)
    for o, name, br in conn.execute("SELECT dc.oracle_id, d.name, d.bracket FROM deck_cards dc JOIN decks d ON d.id = dc.deck_id GROUP BY dc.oracle_id, d.id"):
        gebaut[o].append((name, br))
    fertig = defaultdict(list)
    fest = mtg.deck_binders(conn)
    for o, b in conn.execute(f"SELECT DISTINCT c.oracle_id, col.binder FROM collection col JOIN cards c USING (scryfall_id) WHERE {mtg.OWNED}"):
        if b in fest:
            fertig[o].append(b)
    out = []
    for w in conn.execute("SELECT w.*, (SELECT name FROM cards c WHERE c.oracle_id = w.oracle_id LIMIT 1) name FROM waechter w WHERE w.day >= ? ORDER BY w.day DESC, w.id DESC", (ab,)):
        o = w["oracle_id"]
        decks = [n for n, _ in gebaut[o]] + fertig[o]
        if o not in besitz and not decks:
            continue
        wo = f"steckt in {', '.join(decks)}" if decks else f"du hast {besitz[o]}"
        if w["art"] == "ban":
            out.append({"kind": "ban", "oracle_id": o, "text": f"{w['name']} ist in Commander jetzt gebannt", "sub": wo})
        elif w["art"] == "unban":
            out.append({"kind": "unban", "oracle_id": o, "text": f"{w['name']} ist in Commander wieder erlaubt", "sub": wo})
        elif w["art"] == "gc":
            zu_tief = [n for n, br in gebaut[o] if GC_LIMIT.get(br) == 0]  # Bracket 1 und 2 erlauben keine Game Changer
            out.append({"kind": "gc", "oracle_id": o, "text": f"{w['name']} ist jetzt Game Changer",
                        "sub": (f"{', '.join(zu_tief)} passt damit nicht mehr zu Bracket 1 oder 2. " if zu_tief else "") + wo})
        elif w["art"] == "gc_weg":
            out.append({"kind": "gc_weg", "oracle_id": o, "text": f"{w['name']} ist kein Game Changer mehr", "sub": wo})
        elif w["art"] == "reprint":
            out.append({"kind": "reprint", "oracle_id": o, "text": f"Reprint: {w['name']} in {w['info']}",
                        "sub": wo if decks else f"{wo}. Neuauflagen drücken oft den Preis, verkaufen lohnt eher vorher."})
    return out


def news(conn, edhrec=None, spellbook=None, now=None, rows=None):
    """Neuigkeiten zum letzten Import mit neuen Karten. Ohne edhrec/spellbook nur aus Datenbank und Cache (kein Netz)."""
    imp = conn.execute("SELECT id FROM imports WHERE added > 0 ORDER BY id DESC LIMIT 1").fetchone()
    if not imp:
        return []
    new = new_cards(conn, imp["id"])
    items = upgrade_news(conn, new) + commander_news(conn, new, edhrec, now) + sell_news(mtg.plan(conn) if rows is None else rows, new)
    if spellbook:
        return items + combo_news(conn, imp["id"], spellbook)
    r = conn.execute("SELECT value FROM meta WHERE key = 'news:combos'").fetchone()
    stored = json.loads(r[0]) if r else {}
    return items + (stored["items"] if stored.get("import") == imp["id"] else [])


# --- Spiel-Log und Spielgruppe (Phase 21) ----------------------------------------------------------------------------
SPIELE_MIN = 5   # Siegquote erst ab so vielen Spielen, vorher ist sie Zufall
RUHT_TAGE = 60   # so lange nicht gespielt: Kandidat zum Zerlegen


def _bracket_geschaetzt(gc):
    """Mindest-Stufe aus den Game Changern (Bracket 1 und 2 erlauben keine, 3 bis zu drei, 4 beliebig viele)."""
    return 2 if not gc else 3 if gc <= 3 else 4


def meine_decks(conn):
    """Gebaute und fertige Decks fürs Spiel-Log: Name, Farbidentität, Bracket (gebaut: beim Bauen gewählt; fertig: eigene Angabe, sonst
    aus den Game Changern geschätzt). ponytail: Spiele hängen am Decknamen, zwei gleichnamige Decks zählen zusammen."""
    eigen = json.loads((conn.execute("SELECT value FROM meta WHERE key = 'deckbracket'").fetchone() or ["{}"])[0])
    out = [{"name": r["name"], "ci": r["ci"] or "", "bracket": r["bracket"], "geschaetzt": False, "kind": "gebaut"} for r in conn.execute(
        "SELECT d.name, d.bracket, c.color_identity ci FROM decks d LEFT JOIN cards c ON c.oracle_id = d.commander_oracle_id GROUP BY d.id ORDER BY d.name")]
    return out + [{"name": d["name"], "ci": d["ci"], "bracket": eigen.get(d["name"]) or _bracket_geschaetzt(d["gc"]), "geschaetzt": d["name"] not in eigen,
                   "kind": "fertig"} for d in binder_decks(conn)]


def deck_bracket_setzen(conn, name, bracket):
    """Eigene Bracket-Angabe für ein fertiges Deck (None = wieder schätzen)."""
    if bracket not in (None, 1, 2, 3, 4, 5):
        raise ValueError("Bracket 1 bis 5")
    r = conn.execute("SELECT value FROM meta WHERE key = 'deckbracket'").fetchone()
    eigen = json.loads(r[0]) if r else {}
    if bracket is None:
        eigen.pop(name, None)
    else:
        eigen[name] = bracket
    with conn:
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('deckbracket', ?)", (json.dumps(eigen, ensure_ascii=False),))


def _zahl(v, was, lo, hi):
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise ValueError(f"{was}: keine Zahl") from None
    if not lo <= n <= hi:
        raise ValueError(f"{was}: {lo} bis {hi}")
    return n


def spiel_neu(conn, deck, won, pod="", players=4, turns=None, notes="", at=None):
    """Ein Spiel eintragen: Deck, gewonnen ja/nein, optional Tisch (Spielgruppe), Spielerzahl, Züge, Notiz. -> id"""
    deck = (deck or "").strip()
    if not deck:
        raise ValueError("Welches Deck?")
    werte = (at or mtg.now_iso(), deck[:100], (pod or "").strip()[:100], _zahl(players or 4, "Spieler", 2, 10), int(bool(won)),
             None if turns in (None, "") else _zahl(turns, "Züge", 1, 99), (notes or "").strip()[:500])
    with conn:
        return conn.execute("INSERT INTO games(at, deck, pod, players, won, turns, notes) VALUES (?,?,?,?,?,?,?)", werte).lastrowid


def salt_merken(conn, liste):
    """EDHREC-Salt (sources.edhrec_salt) in der Sammlung merken; der tägliche Lauf holt die Liste."""
    with conn:
        conn.execute("INSERT OR REPLACE INTO meta VALUES ('salt', ?)", (json.dumps({mtg.name_key(n): round(s, 2) for n, s in liste}),))


def _deck_namen(conn):
    """Deckname -> Kartennamen (gebaut: Liste mit Commander; fertig: Binder-Inhalt)."""
    out = defaultdict(set)
    for name, karte in conn.execute("SELECT d.name, c.name FROM decks d JOIN deck_cards dc ON dc.deck_id = d.id JOIN cards c ON c.oracle_id = dc.oracle_id "
                                    "UNION SELECT d.name, c.name FROM decks d JOIN cards c ON c.oracle_id = d.commander_oracle_id"):
        out[name].add(karte)
    fertig = mtg.deck_binders(conn)
    for binder, karte in conn.execute(f"SELECT col.binder, c.name FROM collection col JOIN cards c USING (scryfall_id) WHERE {mtg.OWNED}"):
        if binder in fertig:
            out[binder].add(karte)
    return out


def spiele(conn, heute=None):
    """Auswertung: je Deck Spiele, Siege, Quote (ab SPIELE_MIN), zuletzt gespielt, Salt; Decks, die seit RUHT_TAGE ruhen; letzte Spiele; Tische."""
    heute = heute or datetime.now(timezone.utc).date()
    je = {r["deck"]: dict(r) for r in conn.execute("SELECT deck, COUNT(*) spiele, SUM(won) siege, MAX(at) zuletzt, AVG(turns) zuege FROM games GROUP BY deck")}
    r = conn.execute("SELECT value FROM meta WHERE key = 'salt'").fetchone()
    salz, namen = (json.loads(r[0]) if r else {}), _deck_namen(conn)
    decks = []
    for d in meine_decks(conn) + [{"name": n, "ci": "", "bracket": None, "geschaetzt": False, "kind": None} for n in je if n not in namen]:
        g = je.get(d["name"]) or {"spiele": 0, "siege": 0, "zuletzt": None, "zuege": None}
        salzig = sorted(((salz[mtg.name_key(k)], k) for k in namen.get(d["name"], ()) if mtg.name_key(k) in salz), reverse=True)
        decks.append(d | {k: g[k] for k in ("spiele", "siege", "zuletzt", "zuege")} | {
            "quote": g["siege"] / g["spiele"] if g["spiele"] >= SPIELE_MIN else None,
            "tage": (heute - datetime.fromisoformat(g["zuletzt"][:10]).date()).days if g["zuletzt"] else None,
            "salt": {"summe": round(sum(s for s, _ in salzig), 2), "karten": [k for _, k in salzig[:3]]} if salz else None})
    decks.sort(key=lambda d: (-d["spiele"], d["name"].lower()))
    erstes = conn.execute("SELECT MIN(at) FROM games").fetchone()[0]  # nie gespielt zählt erst, wenn das Log selbst RUHT_TAGE alt ist
    lang = bool(erstes) and (heute - datetime.fromisoformat(erstes[:10]).date()).days >= RUHT_TAGE
    return {"decks": decks, "ruhen": [d["name"] for d in decks if d["kind"] and (d["tage"] >= RUHT_TAGE if d["tage"] is not None else lang)],
            "letzte": [dict(x) for x in conn.execute("SELECT * FROM games ORDER BY at DESC, id DESC LIMIT 20")],
            "pods": [x[0] for x in conn.execute("SELECT pod FROM games WHERE pod != '' UNION SELECT pod FROM gruppe WHERE pod != '' ORDER BY 1")],
            "gruppe": [dict(x) for x in conn.execute("SELECT * FROM gruppe ORDER BY pod COLLATE NOCASE, spieler COLLATE NOCASE, deck COLLATE NOCASE")],
            "min": SPIELE_MIN, "ruht_tage": RUHT_TAGE, "salt_da": bool(salz)}


def gruppe_neu(conn, pod, spieler, deck, bracket, farben="", fetch_names=None):
    """Deck aus der Spielgruppe merken (Freund, Deck oder Commander, Bracket). Farben als Buchstaben (wub); leer = vom Commander (Datenbank,
    sonst fetch_names bei Scryfall, voller englischer Name), sonst unbekannt."""
    spieler, deck = (spieler or "").strip()[:60], (deck or "").strip()[:100]
    if not spieler or not deck:
        raise ValueError("Spieler und Deck angeben")
    farben = (farben or "").strip().upper()
    if farben and not re.fullmatch(r"[WUBRGC]+", farben):
        raise ValueError("Farben als Buchstaben, zum Beispiel wub (c für farblos)")
    if not farben:
        r = card_rows(conn, [deck], fetch_names)[deck]
        farben = (r["color_identity"] or "") if r else ""
    ci = "".join(x for x in "WUBRG" if x in farben)
    with conn:
        return conn.execute("INSERT INTO gruppe(pod, spieler, deck, bracket, ci) VALUES (?,?,?,?,?)",
                            ((pod or "").strip()[:100], spieler, deck, _zahl(bracket, "Bracket", 1, 5), ci)).lastrowid


def tisch(conn, ids):
    """Welches meiner Decks passt heute? Gegner = Decks aus der Spielgruppe. Ziel-Bracket = Median der Gegner (bei gerader Zahl der höhere),
    Abstand höchstens 1; vorn: gleiches Bracket, wenig gemeinsame Farben mit dem Tisch, am längsten nicht gespielt."""
    gegner = [dict(r) for r in conn.execute("SELECT * FROM gruppe WHERE id IN (SELECT value FROM json_each(?))", (json.dumps([int(i) for i in ids]),))]
    if not gegner:
        raise ValueError("Wer sitzt am Tisch? Wähl mindestens ein Deck aus der Spielgruppe.")
    ziel = sorted(g["bracket"] for g in gegner)[len(gegner) // 2]
    farben = set("".join(g["ci"] for g in gegner))
    zuletzt = {r[0]: r[1] for r in conn.execute("SELECT deck, MAX(at) FROM games GROUP BY deck")}
    out = [d | {"abstand": abs(d["bracket"] - ziel), "gleich": "".join(x for x in "WUBRG" if x in farben and x in d["ci"]), "zuletzt": zuletzt.get(d["name"])}
           for d in meine_decks(conn) if d["bracket"] and abs(d["bracket"] - ziel) <= 1]
    out.sort(key=lambda d: (d["abstand"], len(d["gleich"]), d["zuletzt"] or ""))
    return {"ziel": ziel, "gegner": gegner, "decks": out}


# --- Recherche (Phase 23): Dossiers und Markt-Radar schreibt Claude Code (Skill mtg-recherche), der Kern prüft, speichert und zeigt nur ---------
RECHERCHE = mtg.ARCHIVE.parent  # data/ (für alle Sammlungen gemeinsam: Wissen über Commander und Markt ist nicht persönlich)
DOSSIER_TEILE = ("Strategie", "Themen", "Typische Fehler", "Regelfallen", "Upgrade-Pfad", "Quellen")
DOSSIER_MAX = 20_000  # Zeichen
RADAR_TAGE = 14       # ältere Radar-Dateien gelten nicht mehr
RADAR_RICHTUNG = {"steigt": "steigt", "fällt": "faellt", "faellt": "faellt"}
LINK = re.compile(r"https?://(?:&amp;|[^\s<>&\"'])+")


def dossier_pruefen(text):
    """Festes Schema: Abschnitte „## Strategie“ … „## Quellen“, unter Quellen mindestens ein Link mit Abrufdatum (JJJJ-MM-TT). Sonst ValueError."""
    text = (text or "").strip()
    if not text or len(text) > DOSSIER_MAX:
        raise ValueError(f"Dossier leer oder länger als {DOSSIER_MAX} Zeichen")
    teile = re.split(r"^## +", text, flags=re.M)[1:]
    fehlt = [t for t in DOSSIER_TEILE if not any(x.startswith(t) for x in teile)]
    if fehlt:
        raise ValueError(f"Dossier: Abschnitte fehlen: {', '.join(fehlt)}")
    quellen = next(x for x in teile if x.startswith("Quellen"))
    if not any(re.search(r"https?://\S+", z) and re.search(r"\d{4}-\d{2}-\d{2}", z) for z in quellen.splitlines()):
        raise ValueError("Dossier ohne Quellen: unter „## Quellen“ je Zeile ein Link mit Abrufdatum (JJJJ-MM-TT)")
    return text + "\n"


def dossier_speichern(commander, text):
    pfad = RECHERCHE / "dossiers" / f"{slug(commander)}.md"
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(dossier_pruefen(text), encoding="utf-8")
    return pfad


def dossier(commander):
    """Gespeichertes Dossier zu einem Commander (geprüft) oder None."""
    pfad = RECHERCHE / "dossiers" / f"{slug(commander)}.md"
    try:
        return dossier_pruefen(pfad.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _zeile(t):
    """Text escapen, danach nur nackte http(s)-Links klickbar machen (Texte aus dem Netz sind Daten, nie Markup)."""
    return LINK.sub(lambda m: f'<a href="{m.group()}" target="_blank" rel="noopener noreferrer">{m.group()}</a>', html.escape(t))


def dossier_html(text):
    """Markdown-Teilmenge (## Überschrift, - Liste, Absätze) als HTML; alles andere bleibt escapeter Text."""
    out, liste = [], False
    for z in text.splitlines():
        z = z.rstrip()
        if z.startswith(("- ", "* ")):
            out += [] if liste else ["<ul>"]
            liste = True
            out.append(f"<li>{_zeile(z[2:])}</li>")
            continue
        if liste:
            out.append("</ul>")
            liste = False
        if z.startswith("#"):
            if not z.startswith("# "):  # die erste Überschrift (Commander) steht schon über dem Deck
                out.append(f"<h3>{_zeile(z.lstrip('#').strip())}</h3>")
        elif z:
            out.append(f"<p>{_zeile(z)}</p>")
    return "".join(out + (["</ul>"] if liste else []))


def radar_pruefen(daten):
    """Festes Schema je Eintrag: genau name, richtung (steigt/fällt), grund, quelle (http-Link). Sonst ValueError. -> bereinigte Liste"""
    if not isinstance(daten, list) or not daten:
        raise ValueError("Radar: eine Liste mit Einträgen erwartet")
    out = []
    for i, e in enumerate(daten, 1):
        if not isinstance(e, dict) or set(e) != {"name", "richtung", "grund", "quelle"} or not all(isinstance(v, str) and v.strip() for v in e.values()):
            raise ValueError(f"Radar, Eintrag {i}: genau name, richtung, grund, quelle als Text")
        richtung = RADAR_RICHTUNG.get(e["richtung"].strip().lower())
        if not richtung or not re.fullmatch(r"https?://\S+", e["quelle"].strip()):
            raise ValueError(f"Radar, Eintrag {i}: richtung steigt oder fällt, quelle als http-Link")
        out.append({"name": e["name"].strip()[:100], "richtung": richtung, "grund": e["grund"].strip()[:300], "quelle": e["quelle"].strip()})
    return out


def radar_speichern(daten, tag=None):
    tag = tag or datetime.now(timezone.utc).date().isoformat()
    pfad = RECHERCHE / "radar" / f"{tag}.json"
    pfad.parent.mkdir(parents=True, exist_ok=True)
    pfad.write_text(json.dumps(radar_pruefen(daten), ensure_ascii=False, indent=1), encoding="utf-8")
    return pfad


def radar_news(conn, heute=None):
    """Neueste Radar-Datei (höchstens RADAR_TAGE alt) gegen den Bestand: „X steigt laut Markt-Radar, du hast 3 Kopien“. Nur Hinweise."""
    heute = heute or datetime.now(timezone.utc).date()
    dateien = sorted((RECHERCHE / "radar").glob("*.json"))
    if not dateien:
        return []
    tag = dateien[-1].stem
    try:
        if (heute - datetime.fromisoformat(tag).date()).days > RADAR_TAGE:
            return []
        eintraege = radar_pruefen(json.loads(dateien[-1].read_text(encoding="utf-8")))
    except (ValueError, OSError):
        return []
    hat = {}
    for name, oid, n in conn.execute(f"SELECT c.name, c.oracle_id, SUM(col.qty) FROM collection col JOIN cards c USING (scryfall_id) WHERE {mtg.OWNED} GROUP BY c.oracle_id"):
        hat[mtg.name_key(name)] = (oid, n)
    out = []
    for e in eintraege:
        if mtg.name_key(e["name"]) in hat:
            oid, n = hat[mtg.name_key(e["name"])]
            hoch = e["richtung"] == "steigt"
            out.append({"kind": "radar_up" if hoch else "radar_down", "icon": "↗" if hoch else "↘", "oracle_id": oid,
                        "text": f"{e['name']} {'steigt' if hoch else 'fällt'} laut Markt-Radar, du hast {n} {'Kopie' if n == 1 else 'Kopien'}",
                        "sub": f"{e['grund']} ({e['quelle'].split('/')[2]}, {tag}). Nur ein Hinweis, keine Anlageberatung."})
    return out


def format_news(items):
    return "\n".join(f"{i['icon']} {i['text']}\n    {i['sub']}" for i in items) or "Keine Neuigkeiten."
