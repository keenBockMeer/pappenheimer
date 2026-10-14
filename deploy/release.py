"""Hilfen für die Veröffentlichung (.github/workflows/release.yml, PLAN Phase 49), nur Standardbibliothek und ohne Netz:
  python deploy/release.py pruefen TAG      passt der Tag zur Version im Code? Zeilen für $GITHUB_OUTPUT (version, image, vorab), sonst Fehler
  python deploy/release.py notizen          der Abschnitt dieser Version aus CHANGELOG.md, als Text der Veröffentlichung
  python deploy/release.py summen DATEI…    Prüfsummen (SHA-256) im Format von sha256sum, prüfbar mit sha256sum -c"""
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import version  # noqa: E402


def image(repo=version.REPO):
    """Name des Images in der Registry von GitHub: wie das Repository, klein geschrieben (die Registry nimmt keine Großbuchstaben)."""
    return "ghcr.io/" + repo.split("github.com/", 1)[1].strip("/").lower()


def tag_version(tag, code=version.VERSION):
    """Version einer Veröffentlichung aus ihrem Tag: v<Version im Code> oder, zur Probe, v<Version>-rc<Zahl>. Alles andere ist ein Fehler:
    Ein Tag, der eine andere Version nennt als der Code, würde ein Image unter falschem Namen ausliefern. -> (Version, Vorabversion?)"""
    m = re.fullmatch(rf"v{re.escape(code)}(-rc[1-9]\d*)?", tag)
    if not m:
        raise ValueError(f"Der Tag {tag} passt nicht zur Version {code} im Code (version.py). Erwartet: v{code} oder zur Probe v{code}-rc1.")
    return code + (m[1] or ""), bool(m[1])


def notizen(text, code=version.VERSION):
    """Der Abschnitt der Version aus dem Changelog (von „## <Version>“ bis zur nächsten Überschrift dieser Ebene), ohne die Überschrift."""
    m = re.search(rf"^## {re.escape(code)}(?:[ \t][^\n]*)?\n(.*?)(?=^## |\Z)", text, re.M | re.S)  # „## 1.1“ trifft „## 1.1.0“ nicht
    if not m or not m[1].strip():
        raise ValueError(f"CHANGELOG.md hat keinen Abschnitt für {code}.")
    return m[1].strip() + "\n"


def summen(dateien):
    return "".join(f"{hashlib.sha256(Path(d).read_bytes()).hexdigest()}  {Path(d).name}\n" for d in dateien)


def main(argv):
    try:
        if argv[:1] == ["pruefen"] and len(argv) == 2:
            v, vorab = tag_version(argv[1])
            print(f"version={v}\nimage={image()}\nvorab={'true' if vorab else 'false'}")
        elif argv == ["notizen"]:
            sys.stdout.write(notizen((ROOT / "CHANGELOG.md").read_text(encoding="utf-8")))
        elif argv[:1] == ["summen"] and len(argv) > 1:
            sys.stdout.write(summen(argv[1:]))
        else:
            raise ValueError(__doc__)
    except (ValueError, OSError) as e:
        print(f"Fehler: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    sys.exit(main(sys.argv[1:]))
