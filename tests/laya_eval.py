"""Phase 7: Bewertet Laya (noul) Karten für einen Commander brauchbar? Nicht Teil von pytest, nicht im Kern.
  1) .venv/Scripts/python tests/laya_eval.py export        -> data/laya_eval.json (3 Commander x 300 eigene Karten, nur Daten)
  2) .venv-laya/Scripts/python tests/laya_eval.py run      -> Precision@30 gegen EDHREC für Laya, Embedding-Cosinus (Ollama) und Tags
Wahrheit: Karte steht auf der EDHREC-Liste des Commanders. Zufallsniveau = Anteil dieser Karten unter den 300."""
import json
import math
import random
import sys
import time
import urllib.request
from pathlib import Path

OUT = Path(__file__).parent.parent / "data" / "laya_eval.json"
COMMANDERS = ["Fynn, the Fangbearer", "Muerra, Trash Tactician", "The Most Dangerous Gamer"]
POOL, K = 300, 30
FRAGE = "Does this card support the strategy of the commander?"
ROLLEN = ("ramp", "draw", "removal", "boardwipe", "tutor")


def export():
    import deckbuild
    import mtg
    conn = mtg.connect()
    cards = deckbuild.owned_cards(conn, deckbuild.free_copies(conn))
    tags = {}
    for oid, t in conn.execute("SELECT oracle_id, tag FROM tags"):
        tags.setdefault(oid, set()).add(t)
    out = []
    for name in COMMANDERS:
        cmd = deckbuild.find_commander(cards, name)
        data = deckbuild.edhrec_data(conn, deckbuild.slug(cmd["name"]))
        ci = set(cmd["ci"])
        pool = [c for c in cards.values() if c["oracle_id"] != cmd["oracle_id"] and c["legal"] and set(c["ci"]) <= ci and not c["type_line"].startswith("Basic")]
        pos = [c for c in pool if deckbuild.key(c["name"]) in data["cards"]]
        neg = [c for c in pool if deckbuild.key(c["name"]) not in data["cards"]]
        rnd = random.Random(7)  # fester Startwert: gleiche Auswahl bei jedem Lauf
        probe = pos[:POOL] + rnd.sample(neg, min(len(neg), POOL - len(pos)))
        text = lambda c: f"{c['name']} ({c['type_line']}). {(c['text'] or '')[:700]}"
        out.append({"commander": {"name": cmd["name"], "text": text(cmd), "decks": data["decks"]}, "positives": len(pos),
                    "cards": [{"name": c["name"], "text": text(c), "wahr": deckbuild.key(c["name"]) in data["cards"],
                               "tags": sorted(t for t in tags.get(c["oracle_id"], ()) if t in ROLLEN)} for c in probe]})
        print(f"{cmd['name']}: {len(probe)} Karten, davon {len(pos)} auf der EDHREC-Liste (Zufallsniveau {len(pos) / len(probe):.0%})")
    OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")


def embed(texts):
    vecs = []
    for i in range(0, len(texts), 50):
        body = json.dumps({"model": "nomic-embed-text", "input": ["search_document: " + t for t in texts[i:i + 50]]}).encode()
        vecs += json.load(urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:11434/api/embed", data=body, headers={"Content-Type": "application/json"}), timeout=300))["embeddings"]
    return vecs


def cosinus(a, b):
    return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


def p_at_k(scores, wahr):
    """Anteil richtiger Karten unter den K höchsten Werten (gleiche Werte in fester Zufallsfolge)."""
    order = sorted(range(len(scores)), key=lambda i: (-scores[i], random.Random(i).random()))
    return sum(wahr[i] for i in order[:K]) / K


def run():
    from laya import Router
    router = Router()
    fragen = {"stuetzt": {"type": "noul", "instructions": FRAGE}}
    daten = json.loads(OUT.read_text(encoding="utf-8"))
    summe = {"zufall": [], "tags": [], "embedding": [], "laya": []}
    zeiten = []
    for d in daten:
        cmd, karten = d["commander"], d["cards"]
        wahr = [c["wahr"] for c in karten]
        laya = []
        for c in karten:
            t = time.perf_counter()
            r = router.predict(f"Commander: {cmd['text']}\nCard: {c['text']}", fragen)
            zeiten.append(time.perf_counter() - t)
            laya.append(r["answers"]["stuetzt"]["noul"])  # P(wahr)
        vec = embed([cmd["text"]] + [c["text"] for c in karten])
        emb = [cosinus(vec[0], v) for v in vec[1:]]
        tags = [len(c["tags"]) for c in karten]
        erg = {"zufall": sum(wahr) / len(wahr), "tags": p_at_k(tags, wahr), "embedding": p_at_k(emb, wahr), "laya": p_at_k(laya, wahr)}
        for k, v in erg.items():
            summe[k].append(v)
        print(f"{cmd['name']:<28} " + "  ".join(f"{k} {v:.0%}" for k, v in erg.items()))
    zeiten.sort()
    print("Mittel Precision@30: " + "  ".join(f"{k} {sum(v) / len(v):.0%}" for k, v in summe.items()))
    print(f"Laya-Latenz (CPU, ein Aufruf): Median {zeiten[len(zeiten) // 2] * 1000:.0f} ms, 95 % {zeiten[int(len(zeiten) * .95)] * 1000:.0f} ms, {len(zeiten)} Aufrufe")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.path.insert(0, str(Path(__file__).parent.parent))
    {"export": export, "run": run}[sys.argv[1] if len(sys.argv) > 1 else "run"]()
