"""Suchsyntax über die eigene Sammlung (Phase 18), angelehnt an Scryfall: aus einer Suche wird ein SQL-Ausdruck über collection col JOIN cards c.

Beispiele: t:vampire c:r mv<=3 · o:"draw a card" -t:land · id:bg otag:ramp · (r:mythic or eur>=10) lang:de · fn:landfall is:foil
Wörter ohne Doppelpunkt suchen im Namen. Unbekannte Begriffe („protection:“) gelten als Wort im Namen und stehen in den Hinweisen."""
import json
import re

import deckbuild
import mtg

FARBEN = {"w": "W", "u": "U", "b": "B", "r": "R", "g": "G", "weiss": "W", "weiß": "W", "white": "W", "blau": "U", "blue": "U", "schwarz": "B",
          "black": "B", "rot": "R", "red": "R", "gruen": "G", "grün": "G", "green": "G"}
SELTEN = {"c": "common", "u": "uncommon", "r": "rare", "m": "mythic", "s": "special", "common": "common", "uncommon": "uncommon", "rare": "rare",
          "mythic": "mythic", "special": "special"}
ROLLEN = {"ramp": "ramp", "draw": "draw", "card-draw": "draw", "removal": "removal", "wipe": "boardwipe", "boardwipe": "boardwipe", "tutor": "tutor"}
OPS = ("<=", ">=", "!=", ":", "=", "<", ">")
SQL_OP = {":": "=", "=": "=", "!=": "!=", "<": "<", "<=": "<=", ">": ">", ">=": ">="}
TOKEN = re.compile(r'\(|\)|[A-Za-z]+(?:<=|>=|!=|:|=|<|>)"[^"]*"|"[^"]*"|[^\s()]+')
BEGRIFF = re.compile(r"^(-?)([A-Za-z]+)(<=|>=|!=|:|=|<|>)(.+)$")
SCHLUESSEL = "t, o, c, id, mv, r, set, lang, is, otag, fn, eur, ort, notiz"
NOTIZ = ("EXISTS (SELECT 1 FROM notizen n WHERE n.binder = col.binder AND n.scryfall_id = col.scryfall_id AND n.foil = col.foil "
         "AND n.condition = col.condition AND n.language = col.language AND {})")


class Suchfehler(ValueError):
    pass


def _zahl(v, was):
    try:
        return float(v.replace(",", "."))
    except ValueError:
        raise Suchfehler(f"„{v}“ ist keine Zahl ({was})") from None


def _farben(v):
    """Farbwort oder Buchstaben (rg, golgari nicht) -> Buchstaben; c = farblos, m = mehrfarbig."""
    v = v.lower()
    if v in FARBEN:
        return FARBEN[v]
    if v in ("c", "farblos", "colorless", "m", "mehrfarbig", "multicolor"):
        return v[0].upper()
    if not re.fullmatch(r"[wubrg]+", v):
        raise Suchfehler(f"„{v}“ ist keine Farbe (w, u, b, r, g, c für farblos, m für mehrfarbig)")
    return "".join(sorted(set(v.upper()), key="WUBRG".index))


def farbvergleich(hat, will, op):
    """SQLite-Funktion: Farben einer Karte (Buchstaben) gegen eine Suche. C = farblos, M = mehrfarbig."""
    hat = set(hat or "")
    if will == "C":
        return int(not hat if op in ("=", ":", "<=") else bool(hat) if op == "!=" else not hat)
    if will == "M":
        return int(len(hat) > 1 if op != "!=" else len(hat) <= 1)
    w = set(will)
    return int({"=": hat == w, "!=": hat != w, ">=": hat >= w, "<=": hat <= w, ">": hat > w, "<": hat < w}[op])


def kartenfarben(text):
    """SQLite-Funktion: Farben der Karte aus dem Scryfall-JSON (bei doppelseitigen Karten die Vorderseite)."""
    try:
        d = json.loads(text or "{}")
    except ValueError:
        return ""
    return "".join(d.get("colors") if d.get("colors") is not None else ((d.get("card_faces") or [{}])[0].get("colors") or []))


def funktion(text, typ, key):
    """SQLite-Funktion: passt die Funktion (deckbuild.FUNCTIONS, z. B. lands) zum Kartentext?"""
    f = deckbuild.FUNCTIONS.get(key)
    if not f:
        return 0
    t = deckbuild.REMINDER.sub(" ", (text or "").lower())
    return int(bool(f[1].search(t) or (f[2] and f[2].search(typ or ""))))


def registrieren(conn):
    """Die drei Hilfsfunktionen der Suche an die Verbindung hängen (jede neue Verbindung braucht sie)."""
    conn.create_function("farbvergleich", 3, farbvergleich, deterministic=True)
    conn.create_function("kartenfarben", 1, kartenfarben, deterministic=True)
    conn.create_function("funktion", 3, funktion, deterministic=True)


def _begriff(key, op, v, preis, hinweise):
    """Ein Suchbegriff -> (SQL, Parameter)."""
    key, v = key.lower(), v.strip('"')
    if key in ("t", "type", "typ"):
        return "c.type_line LIKE ?", [f"%{v}%"]
    if key in ("o", "oracle", "text"):
        return "c.oracle_text LIKE ?", [f"%{v}%"]
    if key in ("c", "color", "farbe", "id", "identity", "identität"):
        spalte = "c.color_identity" if key in ("id", "identity", "identität") else "kartenfarben(c.json)"
        standard = "<=" if spalte == "c.color_identity" else ">="  # wie Scryfall: id:bg passt in ein BG-Deck, c:rg ist mindestens Rot und Grün
        return f"farbvergleich({spalte}, ?, ?)", [_farben(v), standard if op == ":" else SQL_OP[op]]
    if key in ("mv", "cmc", "manawert"):
        return f"c.cmc {SQL_OP[op]} ?", [_zahl(v, "Manawert")]
    if key in ("eur", "preis"):
        return f"{preis} {SQL_OP[op]} ?", [_zahl(v, "Preis")]
    if key in ("r", "rarity", "seltenheit"):
        if v.lower() not in SELTEN:
            raise Suchfehler(f"„{v}“ ist keine Seltenheit (c, u, r, m)")
        return f"c.rarity {'!=' if op == '!=' else '='} ?", [SELTEN[v.lower()]]
    if key in ("set", "e", "s", "edition", "serie"):
        return "c.set_code = ?", [v.upper()]
    if key in ("lang", "sprache"):
        return "col.language = ?", [{"zhs": "zh_CN", "zht": "zh_TW"}.get(v.lower(), v.lower())]
    if key in ("otag", "rolle"):
        if v.lower() not in ROLLEN:
            raise Suchfehler(f"„{v}“ ist keine Rolle (ramp, draw, removal, wipe, tutor)")
        return "EXISTS (SELECT 1 FROM tags tg WHERE tg.oracle_id = c.oracle_id AND tg.tag = ?)", [ROLLEN[v.lower()]]
    if key in ("fn", "funktion"):
        k = v.lower()
        k = next((f for f, (label, _, _) in deckbuild.FUNCTIONS.items() if k in (f, label.lower())), next(
            (fn for t, fn in deckbuild.THEME_FN.items() if t == k), None))
        if not k:
            raise Suchfehler(f"„{v}“ ist keine Funktion ({', '.join(deckbuild.FUNCTIONS)})")
        return "funktion(c.oracle_text, c.type_line, ?)", [k]
    if key in ("ort", "lagerort"):
        return NOTIZ.format("n.ort LIKE ?"), [f"%{v}%"]
    if key in ("notiz", "note"):
        return NOTIZ.format("n.notiz LIKE ?"), [f"%{v}%"]
    if key == "is" and v.lower() == "verliehen":
        return NOTIZ.format("COALESCE(n.verliehen, '') != ''"), []
    if key == "is":
        sql = {"foil": "col.foil != 'normal'", "etched": "col.foil = 'etched'", "gamechanger": "c.game_changer = 1", "gc": "c.game_changer = 1",
               "reserved": "json_extract(c.json, '$.reserved') = 1", "arena": mtg.ARENA, "digital": mtg.ARENA,
               "commander": "c.legal_commander = 1 AND ((c.type_line LIKE '%Legendary%' AND c.type_line LIKE '%Creature%') OR c.oracle_text LIKE '%can be your commander%')"}
        if v.lower() not in sql:
            raise Suchfehler(f"„is:{v}“ kennt die Suche nicht (foil, etched, gamechanger, reserved, commander, verliehen, arena)")
        return sql[v.lower()], []
    hinweise.append(f"„{key}{op}“ ist kein Suchbegriff (bekannt: {SCHLUESSEL}), gesucht wurde im Namen")
    return "c.name LIKE ?", [f"%{key}{op}{v}%"]


def sql(text, preis="0"):
    """Suche -> (SQL-Ausdruck, Parameter, Hinweise). preis: SQL für den Preis einer Sammlungszeile (mtg.PRICE). Fehler: Suchfehler."""
    tokens, hinweise = TOKEN.findall(text or ""), []
    pos = 0

    def oder():
        nonlocal pos
        teile = [und()]
        while pos < len(tokens) and tokens[pos].lower() == "or":
            pos += 1
            teile.append(und())
        return (" OR ".join(f"({t[0]})" for t in teile), [p for t in teile for p in t[1]]) if len(teile) > 1 else teile[0]

    def und():
        nonlocal pos
        teile = []
        while pos < len(tokens) and tokens[pos] != ")" and tokens[pos].lower() != "or":
            teile.append(einzeln())
        if not teile:
            raise Suchfehler("Leere Suche oder „or“ ohne Begriff dahinter")
        return " AND ".join(f"({t[0]})" for t in teile), [p for t in teile for p in t[1]]

    def einzeln():
        nonlocal pos
        tok = tokens[pos]
        pos += 1
        if tok == "(":
            innen = oder()
            if pos >= len(tokens) or tokens[pos] != ")":
                raise Suchfehler("Klammer „(“ ohne „)“")
            pos += 1
            return innen
        if tok == "-" or (tok.startswith("-") and len(tok) > 1 and tok[1] == "("):
            raise Suchfehler("„-“ gehört direkt vor einen Begriff, zum Beispiel -t:land")
        m = BEGRIFF.match(tok)
        if m:
            s, p = _begriff(m.group(2), m.group(3), m.group(4), preis, hinweise)
            return (f"NOT ({s})", p) if m.group(1) else (s, p)
        neg, wort = tok.startswith("-") and len(tok) > 1, tok.strip('"')
        wort = wort[1:] if neg else wort
        return (f"{'NOT ' if neg else ''}c.name LIKE ?", [f"%{wort}%"])

    if not tokens:
        return "1", [], []
    out = oder()
    if pos < len(tokens):
        raise Suchfehler("Klammer „)“ ohne „(“")
    return out[0], out[1], hinweise


def ist_syntax(text):
    """Enthält die Eingabe Suchbegriffe (sonst: einfache Namenssuche wie bisher)?"""
    return bool(re.search(r'[A-Za-z]+(<=|>=|!=|:|=|<|>)|(^|\s)-\S|[()]|\sor\s', text or ""))


if __name__ == "__main__":  # Selbstprüfung ohne Datenbank: python suche.py
    s, p, h = sql('t:vampire c:r mv<=3 -o:"lose life" (r:m or eur>=10) protection:red', "price")
    assert "c.type_line LIKE ?" in s and "NOT (c.oracle_text LIKE ?)" in s and " OR " in s and h and p[0] == "%vampire%", (s, p)
    assert farbvergleich("BG", "B", ">=") and not farbvergleich("BG", "R", ">=") and farbvergleich("B", "BG", "<=") and farbvergleich("", "C", ":")
    for kaputt in ("(t:land", "t:land)", "mv<=drei", "r:x", "is:quatsch", "fn:quatsch", "c:xyz"):
        try:
            sql(kaputt)
            raise AssertionError(kaputt)
        except Suchfehler:
            pass
    print("ok")
