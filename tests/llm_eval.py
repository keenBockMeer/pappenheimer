"""Phase 6: Wie gut bedient ein lokales Modell `mtg` anhand des Skills? Treffer = erster Befehl passt, dazu Tokens/s.
Aufruf: .venv/Scripts/python tests/llm_eval.py qwen2.5:14b gpt-oss:20b   (braucht laufendes Ollama; nicht Teil von pytest)"""
import json
import re
import sys
import urllib.request
from pathlib import Path

SKILL = (Path(__file__).parent.parent / ".claude" / "skills" / "mtg" / "SKILL.md").read_text(encoding="utf-8")
ANWEISUNG = "\n\nAntworte ausschließlich mit dem einen passenden Befehl (eine Zeile, ohne Erklärung)."
# (Wunsch, Muster für den erwarteten ersten Befehl)
FAELLE = [
    ("Was ist meine Sammlung wert?", r"mtg stats"),
    ("Importiere die neuen Dateien aus der inbox", r"mtg sync"),
    ("Was kann ich ab 3 Euro verkaufen?", r"mtg sell --min 3"),
    ("Wie viele Sol Ring habe ich und was macht die Karte?", r'mtg card "?Sol Ring"?'),
    ("Baue mir ein Deck mit Akawalli, the Seething Tower, Bracket 2", r'mtg build "?Akawalli[^"]*"? --bracket 2'),
    ("Welche 5 Decks kann ich gleichzeitig bauen?", r"mtg plan-decks --count 5"),
    ("Was fehlt mir für Itzquinth, Firstborn of Gishath mit 20 Euro Budget?", r'mtg missing "?Itzquinth[^"]*"? --budget 20'),
    ("BG Friedhof Bracket 2", r"mtg commanders (--top \d+ )?--cached( --top \d+)?"),  # erst Ranking ansehen, dann bauen
    ("Gibt es Neuigkeiten seit dem letzten Import?", r"mtg news"),
    ("Gib mir die Textliste von Deck 3 für Moxfield", r"mtg decks 3 --text"),
]


def frage(modell, wunsch):
    body = {"model": modell, "stream": False, "options": {"temperature": 0},
            "messages": [{"role": "system", "content": SKILL + ANWEISUNG}, {"role": "user", "content": wunsch}]}
    if modell.startswith("gpt-oss"):
        body["think"] = "low"
    req = urllib.request.Request("http://127.0.0.1:11434/api/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    d = json.load(urllib.request.urlopen(req, timeout=600))
    return d["message"]["content"], d.get("eval_count", 0), d.get("eval_duration", 1) / 1e9


def erster_befehl(text):
    for zeile in text.splitlines():
        m = re.search(r"(mtg(?:\.cmd)?\s+[^`]+)", zeile.strip().strip("`$ "))
        if m:
            return re.sub(r"\s+", " ", m.group(1).replace("mtg.cmd", "mtg").strip().rstrip("."))
    return text.strip()[:80]


def entladen():
    """Geladene Modelle freigeben: sie teilen sich sonst den VRAM und verfälschen die Geschwindigkeit."""
    for m in json.load(urllib.request.urlopen("http://127.0.0.1:11434/api/ps"))["models"]:
        urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:11434/api/generate", data=json.dumps({"model": m["name"], "keep_alive": 0}).encode()))


def messen(modell):
    treffer, tokens, sekunden = 0, 0, 0.0
    entladen()
    frage(modell, "Was ist meine Sammlung wert?")  # Warmlauf: Modell laden, zählt nicht
    for wunsch, muster in FAELLE:
        antwort, n, s = frage(modell, wunsch)
        befehl = erster_befehl(antwort)
        ok = re.fullmatch(muster, befehl) is not None
        treffer, tokens, sekunden = treffer + ok, tokens + n, sekunden + s
        print(f"  {'ok ' if ok else 'FEHL'} {wunsch[:48]:<48} -> {befehl[:70]}")
    print(f"{modell}: {treffer}/{len(FAELLE)} Treffer, {tokens / sekunden:.1f} Tokens/s (Ø über {tokens} Tokens)")
    return treffer, tokens / sekunden


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    for m in sys.argv[1:] or ["qwen2.5:14b"]:
        messen(m)
