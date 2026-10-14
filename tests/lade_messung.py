"""Phase 48: Messung der Ladezeit-Bytes (PLAN E32): was überträgt der erste und der zweite Aufruf der Seite, und wie groß sind die API-Antworten?
Von Hand, kein Teil von pytest, kein Netz: Die Instanz läuft in-process auf 127.0.0.1 (eigener Port) mit einer Datenbank in einem temporären Ordner und
der Beispielsammlung (Phase 47) aus tests/fixtures/beispiel.json. Die echte Sammlung wird nie angefasst (MTG_DB wird vor dem Import von mtg gesetzt).
Gemessen wird wie ein Browser: Accept-Encoding "gzip, deflate, br"; beim zweiten Aufruf mit If-None-Match, wenn der erste einen ETag lieferte.
Die Kartenbilder vom Bild-CDN zählen nicht mit (sie kommen nicht von der App). Bytes = Körper + Kopf (Statuszeile und Kopfzeilen, wie gesendet).
Aufruf: python tests/lade_messung.py            Tabelle ausgeben
        python tests/lade_messung.py --serve    Instanz weiterlaufen lassen (zum Ansehen im Browser; beenden mit der Prozessnummer, die dann steht)"""
import json
import os
import sys
import tempfile
import threading
import time
import zlib
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
WURZEL = Path(__file__).resolve().parent.parent
ORDNER = Path(tempfile.mkdtemp(prefix="mtg-lademessung-"))
os.environ["MTG_DB"] = str(ORDNER / "mtg.db")  # vor dem Import von mtg: nie die echte Sammlung
sys.path.insert(0, str(WURZEL))
import http.client  # noqa: E402
from contextlib import closing  # noqa: E402

import mtg  # noqa: E402
import server  # noqa: E402

# Was der Browser beim ersten Aufruf holt (aus der Netzwerkansicht der Seite) und was die Startseite danach von der API abfragt
STATISCH = ["/", "/style.css", "/app.js", "/fonts/Geist-Variable.woff2", "/favicon.svg", "/grain.svg", "/manifest.webmanifest", "/sw.js"]
API_START = ["/api/session", "/api/summary", "/api/jobs", "/api/beispiel"]
API_GROSS = ["/api/summary", "/api/cards", "/api/sets", "/api/sort", "/api/sell", "/api/sell.csv", "/api/decks", "/api/binders", "/api/fertige-decks",
             "/api/wuensche", "/api/rueckblick", "/api/bericht", "/api/spiele", "/api/funktionen", "/api/session", "/api/settings"]


def beispiel_laden():
    karten = json.loads((WURZEL / "tests" / "fixtures" / "beispiel.json").read_text(encoding="utf-8"))  # Kennung -> Karte (wie in test_mtg.BEISPIEL)

    def fetch(ids):
        return [karten[i] for i in ids if i in karten], [i for i in ids if i not in karten]

    def lookup(idents):
        gefunden, fehlt = [], []
        for x in idents:
            def passt(c):
                if "id" in x:
                    return c["id"] == x["id"]
                if "collector_number" in x:
                    return (c["set"], c["collector_number"]) == (x["set"].lower(), x["collector_number"])
                return mtg.name_key(c["name"]) == mtg.name_key(x["name"]) and x.get("set", c["set"]) == c["set"]
            c = next((c for c in karten.values() if passt(c)), None)
            (gefunden if c else fehlt).append(c or x)
        return gefunden, fehlt
    with closing(mtg.connect()) as conn:
        mtg.beispiel_laden(conn, fetch, lookup)


def starten():
    beispiel_laden()
    srv = server.ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    server.Handler.port, server.Handler.lokal = srv.server_address[1], True
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def holen(port, pfad, **kopf):
    """-> (Status, Antwortkopf als Liste, Körper, Bytes auf der Leitung, Dauer in ms)"""
    t0 = time.perf_counter()
    c = http.client.HTTPConnection("127.0.0.1", port)
    c.request("GET", pfad, headers={"Accept-Encoding": "gzip, deflate, br", **kopf})
    r = c.getresponse()
    body, ms = r.read(), (time.perf_counter() - t0) * 1000
    c.close()
    kopf_bytes = len(f"HTTP/1.0 {r.status} {r.reason}\r\n") + sum(len(k) + len(v) + 4 for k, v in r.getheaders()) + 2
    return r.status, r.getheaders(), body, kopf_bytes + len(body), ms


def runde(port, pfade, etags=None):
    zeilen, summe = [], 0
    for p in pfade:
        kopf = {"If-None-Match": etags[p]} if etags and p in etags else {}
        status, h, body, n, ms = holen(port, p, **kopf)
        h = dict(h)
        zeilen.append((p, status, h.get("Content-Encoding", "-"), len(body), n, ms, h.get("ETag"), h.get("Cache-Control", "-")))
        summe += n
    return zeilen, summe


def tabelle(zeilen):
    for p, status, enc, body, n, ms, _, cc in zeilen:
        print(f"  {p:34} {status} {enc:5} Körper {body:8,} B  gesendet {n:8,} B  {ms:6.1f} ms  {cc}".replace(",", "."))


def main():
    srv = starten()
    port = srv.server_address[1]
    print(f"Instanz: 127.0.0.1:{port}, Datenordner {ORDNER}, Prozess {os.getpid()}")
    erst, s1 = runde(port, STATISCH + API_START)
    etags = {z[0]: z[6] for z in erst if z[6]}
    zweit, s2 = runde(port, STATISCH + API_START, etags)
    print("\nErster Aufruf (Seite + Abfragen der Startseite):")
    tabelle(erst)
    print(f"  SUMME {s1:,} B = {s1 / 1024:.1f} KB".replace(",", "."))
    print("\nZweiter Aufruf (mit If-None-Match, wenn ein ETag da war):")
    tabelle(zweit)
    print(f"  SUMME {s2:,} B = {s2 / 1024:.1f} KB".replace(",", "."))
    print("\nAPI-Antworten, nach Größe (ohne Packen; 'gz' = so groß nach zlib-Stufe 6, Dauer des Packens in ms):")
    groesse = []
    for p in API_GROSS:
        status, h, body, n, ms = holen(port, p, **{"Accept-Encoding": "identity"})
        t0 = time.perf_counter()
        gz = len(zlib.compress(body, 6))
        groesse.append((len(body), p, status, gz, (time.perf_counter() - t0) * 1000, ms))
    for roh, p, status, gz, packen, ms in sorted(groesse, reverse=True):
        print(f"  {p:26} {status}  {roh:8,} B   gz {gz:8,} B   packen {packen:5.1f} ms   Antwort {ms:5.1f} ms".replace(",", "."))
    if "--serve" in sys.argv:
        print(f"\nläuft weiter auf http://127.0.0.1:{port}/ (Prozess {os.getpid()}); beenden: Prozess {os.getpid()} beenden", flush=True)
        while True:
            time.sleep(3600)


if __name__ == "__main__":
    main()
