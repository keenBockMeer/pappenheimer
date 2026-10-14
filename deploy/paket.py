"""ZIP für Windows ohne Installation: dist/pappenheimer-windows.zip = git archive HEAD (ohne data/, inbox/ und was in .gitattributes
export-ignore hat) plus Python von python.org (embeddable, ohne Setup und ohne Admin) im Unterordner python/. Das Python kommt nur
mit der festen Prüfsumme PY_SHA256 in die ZIP. Aufruf: .venv/Scripts/python deploy/paket.py (nur Committetes kommt in die ZIP); bei
einem Tag baut sie .github/workflows/release.yml und hängt sie an die Veröffentlichung (PLAN Phase 49)."""
import hashlib
import io
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import version  # noqa: E402 (Name der Starter-Datei)

PY = "3.13.14"  # wie die .venv; embeddable gibt es nur für Bugfix-Releases, beim Wechsel prüfen, ob die Datei auf python.org liegt
# SHA-256 der Datei unten, wie python.org sie nennt (www.python.org/api/v2/downloads/release_file, Feld sha256_sum, nachgesehen 2026-10-13
# und mit einem frischen Abruf verglichen). Beim Wechsel von PY dort neu nachsehen, nie aus der geladenen Datei übernehmen.
PY_SHA256 = "90b4e5b9898b72d744650524bff92377c367f44bd5fbd09e3148656c080ad907"
URL = f"https://www.python.org/ftp/python/{PY}/python-{PY}-embed-amd64.zip"
ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
TOP = "pappenheimer/"            # Ordner in der ZIP: bleibt über Versionen gleich, ein Update entpackt man darüber (data/ liegt darin)
ZIP = "pappenheimer-windows.zip"  # ohne Version im Namen: …/releases/latest/download/pappenheimer-windows.zip zeigt so immer auf die neueste


def python_holen(dist):
    """Das eingebettete Python einmal laden und gegen PY_SHA256 prüfen, auch eine Datei, die schon da liegt: Eine andere Datei als die
    geprüfte kommt nie in die ZIP. Stimmt die Prüfsumme nicht, ist die Datei gelöscht und nichts gebaut."""
    emb = dist / f"python-{PY}-embed-amd64.zip"
    if not emb.exists():
        urllib.request.urlretrieve(URL, emb)
    ist = hashlib.sha256(emb.read_bytes()).hexdigest()
    if ist != PY_SHA256:
        emb.unlink()
        raise SystemExit(f"Die Prüfsumme von {emb.name} stimmt nicht (erwartet {PY_SHA256}, bekommen {ist}). Die Datei ist gelöscht, "
                         f"gebaut ist nichts. Ist PY neu, die Prüfsumme bei python.org nachsehen und PY_SHA256 anpassen.")
    return emb


def main(dist=DIST):
    dist.mkdir(exist_ok=True)
    emb = python_holen(dist)
    app = zipfile.ZipFile(io.BytesIO(subprocess.run(["git", "-C", str(ROOT), "archive", "--format=zip", "HEAD"],
                                                    check=True, capture_output=True).stdout))
    assert b"\r\n" in app.read("mtg.cmd"), "mtg.cmd ohne CRLF: Sprungmarken gehen nicht (.gitattributes)"
    ziel = dist / ZIP
    with zipfile.ZipFile(ziel, "w", zipfile.ZIP_DEFLATED) as z, zipfile.ZipFile(emb) as e:
        for quelle, unter in ((app, ""), (e, "python/")):
            for i in quelle.infolist():
                if i.is_dir():
                    continue
                daten = quelle.read(i)
                if i.filename.endswith("._pth"):  # mit ._pth landet der Ordner von mtg.py nicht von selbst in sys.path
                    daten = daten.rstrip() + b"\r\n..\r\n"
                i.filename = TOP + unter + i.filename
                z.writestr(i, daten)
        namen = set(z.namelist())
    assert {TOP + "python/python.exe", TOP + "mtg.py", TOP + f"{version.NAME} starten.cmd", TOP + "ui/mtg.ico"} <= namen
    assert {TOP + "beispiel/sammlung.csv", TOP + "beispiel/deck.txt"} <= namen, "die Beispielsammlung fehlt in der ZIP"
    assert not any(n.startswith((TOP + "data/", TOP + "inbox/")) or n.endswith(".db") for n in namen), "Sammlungsdaten in der ZIP"
    assert TOP + "docs/PLAN.md" not in namen, "der Plan gehört nicht in die ZIP (.gitattributes)"
    print(f"{ziel} ({ziel.stat().st_size / 2**20:.0f} MB, Python {PY})")


if __name__ == "__main__":
    main()
