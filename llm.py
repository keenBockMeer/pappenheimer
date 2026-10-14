"""Optional (PLAN E15): lokales LLM über Ollama, genau zwei Einsätze, beide durch Code geprüft. Ohne Ollama bleibt alles andere gleich.

1. Ähnliche Karten: Embedding (nomic-embed-text) je Karte im Besitz, Kosinus-Ähnlichkeit. Es wird nichts erzeugt, also nichts erfunden.
2. Frage → Suche: Das Modell übersetzt eine Frage („rote Drachen unter 2 Euro“) in die Suchsyntax von suche.py. Die App prüft die Suche mit dem
   Parser, zeigt sie an und führt sie selbst aus. Karten, Regeln oder Decks erzeugt das Modell nie."""
import array
import json
import math
import time

import mtg
import sources
import suche

DIM = 256          # nomic-embed-text liefert 768 Werte; die ersten 256, neu normiert, reichen zum Vergleichen (Matryoshka) und sparen Platz
STAPEL = 32        # Texte je Anfrage an Ollama
AEHNLICH_N = 12
SCHEMA = {"type": "object", "properties": {"suche": {"type": "string"}}, "required": ["suche"]}
ANLEITUNG = """Du übersetzt Fragen zu einer Magic-Sammlung in eine Suche. Antworte nur mit JSON {"suche": "..."}.
Begriffe (Werte englisch, wie auf den Karten):
t:creature, t:dragon, t:instant (Typ) · o:"draw a card" (Kartentext) · c:r (mindestens Rot; Farben w u b r g, c:c farblos, c:m mehrfarbig, c=rg genau Rot-Grün) · id:bg (passt in ein Schwarz-Grün-Deck) · mv<=3 (Manawert, auch = < > >=) · r:m (Mythic), r:r (Rare), r:u (Uncommon), r:c (Common) · set:dsk (Serie) · lang:de (deutsche Karte), lang:en · is:foil, is:gamechanger, is:commander, is:reserved · otag:ramp, otag:draw, otag:removal, otag:wipe, otag:tutor · fn:lands (Landfall), fn:counters, fn:tokens, fn:artifacts, fn:graveyard, fn:spells, fn:sacrifice, fn:blink, fn:treasure, fn:flying, fn:lifegain · eur<2 (Preis in Euro) · -t:land (nicht) · or · Klammern. Wörter ohne Doppelpunkt suchen im Kartennamen.
Deutsch nach Englisch: Drache=dragon, Elf=elf, Kreatur=creature, Spontanzauber=instant, Hexerei=sorcery, Artefakt=artifact, Verzauberung=enchantment, Land=land, rot=r, blau=u, schwarz=b, grün=g, weiß=w.
Beispiele: "rote Drachen unter 2 Euro" -> t:dragon c:r eur<2 · "Karten fürs schwarz-grüne Friedhofsdeck" -> id:bg fn:graveyard · "billige Ramp-Karten in Grün" -> otag:ramp c:g eur<1 · "meine teuersten Foils" -> is:foil eur>=5 · "deutsche Mythics" -> r:m lang:de · "Kreaturen mit Fliegen bis Manawert 3" -> t:creature o:flying mv<=3 · "Removal in Weiß oder Schwarz" -> otag:removal (c:w or c:b)
Was sich so nicht ausdrücken lässt (zum Beispiel Mengen), lässt du weg."""

_status = {"zeit": 0.0, "modelle": None}


def modelle(cache_s=30):
    """Installierte Ollama-Modelle (30 s gemerkt) oder None, wenn Ollama nicht läuft."""
    if time.monotonic() - _status["zeit"] > cache_s:
        _status.update(zeit=time.monotonic(), modelle=sources.ollama_modelle())
    return _status["modelle"]


def _hat(name, liste):
    """Modell installiert? „nomic-embed-text“ passt auch auf „nomic-embed-text:latest“, „qwen3:4b-instruct“ nur genau so."""
    return bool(liste) and any(m == name or (":" not in name and m.split(":")[0] == name) for m in liste)


def status(conn):
    m = modelle()
    karten = conn.execute(f"SELECT COUNT(DISTINCT c.oracle_id) FROM collection col JOIN cards c USING (scryfall_id) WHERE {mtg.OWNED}").fetchone()[0]
    vek = conn.execute(f"SELECT COUNT(*) FROM card_vec WHERE model = ? AND oracle_id IN (SELECT c.oracle_id FROM collection col JOIN cards c USING (scryfall_id) "
                       f"WHERE {mtg.OWNED})", (sources.OLLAMA_EMBED,)).fetchone()[0]
    return {"ollama": m is not None, "embed": _hat(sources.OLLAMA_EMBED, m), "chat": _hat(sources.OLLAMA_CHAT, m), "vektoren": vek, "karten": karten,
            "modelle": {"embed": sources.OLLAMA_EMBED, "chat": sources.OLLAMA_CHAT}}


def _text(r):
    return f"clustering: {r['name']}. {r['type_line'] or ''}. {(r['oracle_text'] or '').replace(chr(10), ' ')}"[:2000]


def _vek(werte):
    v = werte[:DIM]
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return array.array("f", (x / n for x in v)).tobytes()


def vektoren_laden(conn, embed=None, progress=None):
    """Embeddings für alle Karten im Besitz, die noch keins haben (Hintergrund-Job). -> Anzahl neu"""
    rows = conn.execute(f"SELECT c.oracle_id, c.name, c.type_line, c.oracle_text FROM cards c WHERE c.oracle_id IN (SELECT c2.oracle_id FROM collection col "
                        f"JOIN cards c2 USING (scryfall_id) WHERE {mtg.OWNED}) AND c.oracle_id NOT IN (SELECT oracle_id FROM card_vec "
                        f"WHERE model = ?) GROUP BY c.oracle_id", (sources.OLLAMA_EMBED,)).fetchall()
    for i in range(0, len(rows), STAPEL):
        teil = rows[i:i + STAPEL]
        werte = (embed or sources.ollama_embed)([_text(r) for r in teil])
        with conn:
            conn.executemany("INSERT OR REPLACE INTO card_vec VALUES (?,?,?)", [(r["oracle_id"], sources.OLLAMA_EMBED, _vek(w)) for r, w in zip(teil, werte)])
        if progress:
            progress(min(i + STAPEL, len(rows)), len(rows))
    return len(rows)


def aehnlich(conn, oracle_id, n=AEHNLICH_N, embed=None):
    """Die ähnlichsten Karten deiner Sammlung zu einer Karte (auch zu einer, die du nicht besitzt: ihr Embedding wird einmal berechnet).
    -> [{oracle_id, name, image, price, score}] oder None, wenn es noch keine Embeddings gibt"""
    r = conn.execute("SELECT vec FROM card_vec WHERE oracle_id = ? AND model = ?", (oracle_id, sources.OLLAMA_EMBED)).fetchone()
    if not r:
        karte = conn.execute("SELECT oracle_id, name, type_line, oracle_text FROM cards WHERE oracle_id = ? LIMIT 1", (oracle_id,)).fetchone()
        if not karte:
            raise ValueError("Unbekannte Karte")
        blob = _vek((embed or sources.ollama_embed)([_text(karte)])[0])
        with conn:
            conn.execute("INSERT OR REPLACE INTO card_vec VALUES (?,?,?)", (oracle_id, sources.OLLAMA_EMBED, blob))
    else:
        blob = r[0]
    ziel = array.array("f")
    ziel.frombytes(blob)
    alle = conn.execute(f"SELECT v.oracle_id, v.vec FROM card_vec v WHERE v.model = ? AND v.oracle_id != ? AND v.oracle_id IN (SELECT c.oracle_id FROM collection col "
                        f"JOIN cards c USING (scryfall_id) WHERE {mtg.OWNED})", (sources.OLLAMA_EMBED, oracle_id)).fetchall()
    if not alle:
        return None
    # ponytail: Kosinus in reinem Python über alle Karten (5.000 × 256 ≈ 0,3 s); mit numpy oder sqlite-vec erst, wenn es spürbar stört
    werte = []
    for oid, b in alle:
        v = array.array("f")
        v.frombytes(b)
        werte.append((sum(x * y for x, y in zip(ziel, v)), oid))
    besten = sorted(werte, reverse=True)[:n]
    info = {r["oracle_id"]: r for r in conn.execute(
        f"SELECT c.oracle_id, c.name, c.image_url, MIN({mtg.PRICE}) price FROM collection col JOIN cards c USING (scryfall_id) "
        f"WHERE {mtg.OWNED} AND c.oracle_id IN (SELECT value FROM json_each(?)) GROUP BY c.oracle_id", (json.dumps([o for _, o in besten]),))}
    return [{"oracle_id": o, "name": info[o]["name"], "image": info[o]["image_url"], "price": info[o]["price"], "score": round(s, 3)} for s, o in besten if o in info]


def frage(text, chat=None):
    """Frage -> geprüfte Suche. Das Modell liefert nur JSON {"suche"}; was der Parser nicht versteht, wird abgelehnt. -> {"suche", "hinweise"}"""
    text = (text or "").strip()[:300]
    if not text:
        raise ValueError("Keine Frage")
    try:
        antwort = (chat or sources.ollama_json)(ANLEITUNG, text, SCHEMA)
    except ValueError:  # abgeschnittenes oder kaputtes JSON
        antwort = None
    q = str(antwort.get("suche") or "").strip()[:300] if isinstance(antwort, dict) else ""
    if not q:
        raise ValueError("Das Modell hat keine Suche gebaut. Versuch es mit anderen Worten oder direkt mit Suchbegriffen.")
    try:
        _, _, hinweise = suche.sql(q)
    except suche.Suchfehler as e:
        raise ValueError(f"Das Modell hat eine ungültige Suche gebaut ({q}): {e}") from None
    return {"suche": q, "hinweise": hinweise}
