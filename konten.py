"""Konten (PLAN E14): ein Hauptkonto und Unterkonten, jedes mit eigener Sammlung (eigene Datenbank). Konten, Passwörter und Sitzungen
liegen in data/konten.db. Ohne Hauptkonto bleibt alles wie vor Phase 13: eine Sammlung, kein Login.

Modus: „einfach“ (keine Konten) · „lokal“ (Hauptkonto ohne Passwort: mehrere Sammlungen, kein Login, nur 127.0.0.1) ·
„anmeldung“ (Hauptkonto mit Passwort: Login Pflicht, auch auf dem Server). Ohne Hauptkonto auf einer anderen Adresse als 127.0.0.1 wartet der
Server auf die erste Einrichtung (PLAN E28): Code, Fehlversuche und „leerer Datenordner“ stehen hier, der Rest in server.py."""
import errno
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import shutil
import sqlite3
import stat
import subprocess
import tempfile
import threading
import time
import unicodedata
import zipfile
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path

import mtg

RUNDEN = 600_000                 # PBKDF2-SHA256 (OWASP-Empfehlung 2023); in Hash gespeichert, später erhöhbar
SITZUNG_S = 30 * 24 * 3600
FEHLVERSUCHE, SPERRE_S = 5, 15 * 60
FEHL_MAX = 10_000                # so viele Zähler (Absender-Adresse, Konto) höchstens im Speicher, darüber fallen die ältesten heraus
PRUEFUNGEN, PRUEF_WARTEN_S = 2, 10  # so viele Passwort-Prüfungen höchstens zugleich (jede rechnet RUNDEN Runden); so lange wartet die nächste
PW_MIN = 8
SCHEMA = """
CREATE TABLE IF NOT EXISTS konten(name TEXT PRIMARY KEY, anzeige TEXT, rolle TEXT, pw TEXT, angelegt TEXT);
CREATE TABLE IF NOT EXISTS sitzungen(token TEXT PRIMARY KEY, konto TEXT, aktiv TEXT, bis REAL);
"""
# ponytail: Fehlversuche im Speicher (ein Server-Prozess); nach einem Neustart beginnt die Zählung neu.
# _fehl: (Absender, Konto) -> (Zahl, Zeit des letzten Versuchs), in der Reihenfolge des letzten Versuchs (der älteste steht vorn)
_fehl, _lock, _attrappe = {}, threading.Lock(), []
_pruefung = threading.BoundedSemaphore(PRUEFUNGEN)


class Gesperrt(PermissionError):
    pass


class Ausgelastet(Gesperrt):
    """Gerade laufen schon PRUEFUNGEN Passwort-Prüfungen und es wurde keine frei: kein Fehlversuch, nur später noch einmal."""


def daten():
    """Datenordner (zur Laufzeit aus mtg.DB, damit MTG_DB und Tests greifen)."""
    return Path(mtg.DB).parent


def pfad():
    return daten() / "konten.db"


def _stand_1(conn, path):
    """Stand 1 = das Schema seit Phase 13 (es hat sich bis Phase 38 nie geändert)."""
    for sql in SCHEMA.split(";"):
        if sql.strip():
            conn.execute(sql)


# konten.db trägt denselben Stand wie die Sammlungen (mtg.STAND, PLAN E27), damit ein Versionssprung genau eine Sicherung für alle hat.
# Schritte für konten.db stehen hier unter ihrer Nummer; ein Stand ohne Eintrag ändert an konten.db nur die Nummer (Regeln: mtg.migrieren).
MIGRATIONEN = {1: _stand_1}


def _roh(path=None):
    """Verbindung ohne Migration: nur zum Lesen, wo auch eine noch nicht migrierte konten.db gelesen wird (Sicherung)."""
    conn = sqlite3.connect(path or pfad(), timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def connect(path=None):
    conn = _roh(path)
    try:
        mtg.migrieren(conn, path or pfad(), MIGRATIONEN)
    except BaseException:
        conn.close()
        raise
    return conn


def modus():
    if not pfad().exists():
        return "einfach"
    with closing(connect()) as c:
        r = c.execute("SELECT pw FROM konten WHERE rolle = 'haupt'").fetchone()
    return "einfach" if not r else "anmeldung" if r["pw"] else "lokal"


def kurz(name):
    """Kontoname als Ordnername: klein, ohne Akzente und Sonderzeichen."""
    s = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode().lower()).strip("-")[:40]
    if not s:
        raise ValueError("Bitte einen Namen angeben (Buchstaben oder Ziffern)")
    return s


def db_pfad(name, rolle):
    """Datenbank einer Sammlung: das Hauptkonto behält data/mtg.db, Unterkonten bekommen data/konten/<name>/mtg.db."""
    return Path(mtg.DB) if rolle == "haupt" else daten() / "konten" / name / "mtg.db"


def hash_pw(pw, runden=None):
    salt = secrets.token_bytes(16)
    runden = runden or RUNDEN
    return f"pbkdf2_sha256${runden}${salt.hex()}${hashlib.pbkdf2_hmac('sha256', pw.encode(), salt, runden).hex()}"


def pw_ok(pw, gespeichert):
    try:
        _, runden, salt, h = (gespeichert or "").split("$")
        neu = hashlib.pbkdf2_hmac("sha256", (pw or "").encode(), bytes.fromhex(salt), int(runden)).hex()
    except ValueError:
        return False
    return hmac.compare_digest(neu, h)


def _pruefe(pw):
    if len(pw or "") < PW_MIN:
        raise ValueError(f"Das Passwort braucht mindestens {PW_MIN} Zeichen")


def konto(conn, name):
    return conn.execute("SELECT * FROM konten WHERE name = ?", (name,)).fetchone()


def haupt(conn):
    return conn.execute("SELECT * FROM konten WHERE rolle = 'haupt'").fetchone()


def liste(conn):
    """Alle Konten, Hauptkonto zuerst, mit Pfad der Sammlung."""
    return [dict(r) | {"pw": bool(r["pw"]), "db": str(db_pfad(r["name"], r["rolle"]))}
            for r in conn.execute("SELECT * FROM konten ORDER BY rolle != 'haupt', anzeige COLLATE NOCASE")]


def anlegen(conn, name, pw=None, ist_haupt=False):
    """Konto anlegen. Erst das Hauptkonto, dann Unterkonten; pw None = ohne Passwort (Unterkonto: nur vom Hauptkonto verwaltet). -> Kurzname"""
    n = kurz(name)
    h = haupt(conn)
    if ist_haupt and h:
        raise ValueError("Es gibt schon ein Hauptkonto")
    if not ist_haupt and not h:
        raise ValueError("Erst das Hauptkonto anlegen")
    if konto(conn, n):
        raise ValueError(f"Ein Konto „{n}“ gibt es schon")
    if pw is not None:
        _pruefe(pw)
    werte = (n, name.strip(), "haupt" if ist_haupt else "unter", hash_pw(pw) if pw else None, mtg.now_iso())
    with conn:
        if ist_haupt:  # Prüfen und Anlegen in einer Anweisung: Zwei, die zugleich das erste Hauptkonto anlegen, gewinnen nicht beide (Phase 43)
            if not conn.execute("INSERT INTO konten SELECT ?,?,?,?,? WHERE NOT EXISTS (SELECT 1 FROM konten WHERE rolle = 'haupt')", werte).rowcount:
                raise ValueError("Es gibt schon ein Hauptkonto")
        else:
            conn.execute("INSERT INTO konten VALUES (?,?,?,?,?)", werte)
    if ist_haupt:
        einrichtung_ende()  # der Einrichtungs-Code gilt bis zum ersten Hauptkonto (PLAN E28), auch wenn es die Kommandozeile anlegt
    return n


def passwort(conn, name, pw):
    """Passwort setzen oder (pw None) entfernen. Ohne Passwort kann sich ein Konto nicht anmelden; beim Hauptkonto heißt das: kein Login."""
    if not konto(conn, name):
        raise ValueError(f"Kein Konto „{name}“")
    if pw is not None:
        _pruefe(pw)
    with conn:
        conn.execute("UPDATE konten SET pw = ? WHERE name = ?", (hash_pw(pw) if pw else None, name))
        conn.execute("DELETE FROM sitzungen WHERE konto = ?", (name,))  # alte Sitzungen gelten nicht weiter


def entfernen(conn, name):
    """Unterkonto entfernen (die Datenbank bleibt liegen, nichts geht verloren)."""
    k = konto(conn, name)
    if not k:
        raise ValueError(f"Kein Konto „{name}“")
    if k["rolle"] == "haupt":
        raise ValueError("Das Hauptkonto lässt sich nicht entfernen")
    with conn:
        conn.execute("DELETE FROM konten WHERE name = ?", (name,))
        conn.execute("DELETE FROM sitzungen WHERE konto = ?", (name,))  # wer die Sammlung offen hatte, landet wieder in seiner eigenen (sitzung)


def _h(token):
    return hashlib.sha256(token.encode()).hexdigest()


def _neue_sitzung(conn, name, jetzt):
    token = secrets.token_urlsafe(32)
    with conn:
        conn.execute("DELETE FROM sitzungen WHERE bis < ?", (jetzt,))
        conn.execute("INSERT INTO sitzungen VALUES (?,?,?,?)", (_h(token), name, name, jetzt + SITZUNG_S))
    return token


def _absender(adresse):
    """Schlüssel der Sperre für eine Absender-Adresse: IPv4 ganz, von IPv6 das /64-Netz (ein Anschluss hat dort beliebig viele Adressen,
    je Adresse gezählt wäre die Sperre wirkungslos). Was keine Adresse ist, zählt, wie es ist; ohne Angabe gilt die Sperre je Konto."""
    try:
        ip = ipaddress.ip_address(adresse)
    except ValueError:
        return str(adresse or "")
    ip = getattr(ip, "ipv4_mapped", None) or ip
    return str(ip) if ip.version == 4 else f"{ipaddress.IPv6Address(int(ip) >> 64 << 64)}/64"


def _versuch(key, jetzt):
    """Sperre prüfen und den Versuch gleich zählen (vor der Prüfung des Passworts: Auch gleichzeitige Versuche kommen so zusammen nicht über
    FEHLVERSUCHE; die richtige Anmeldung löscht den Zähler wieder). Der Zähler bleibt bei FEHL_MAX Einträgen: Erst fallen abgelaufene heraus,
    dann die ältesten ohne Sperre, zuletzt die ältesten überhaupt (erfundene Namen verdrängen so keine laufende Sperre)."""
    with _lock:
        zahl, seit = _fehl.get(key, (0, 0.0))
        if jetzt - seit >= SPERRE_S:
            zahl = 0
        if zahl >= FEHLVERSUCHE:
            raise Gesperrt(f"Zu viele Fehlversuche. Bitte in {int((SPERRE_S - (jetzt - seit)) // 60) + 1} Minuten noch einmal.")
        _fehl.pop(key, None)  # neu anfügen: der jüngste Versuch steht hinten
        _fehl[key] = (zahl + 1, jetzt)
        if len(_fehl) > FEHL_MAX:
            for k in [k for k, (_, s) in _fehl.items() if jetzt - s >= SPERRE_S]:
                del _fehl[k]
            while len(_fehl) > FEHL_MAX:
                del _fehl[next((k for k, (z, _) in _fehl.items() if z < FEHLVERSUCHE and k != key), None) or next(iter(_fehl))]


def anmelden(conn, name, pw, jetzt=None, adresse=""):
    """-> Sitzungs-Token. Falsches Passwort: ValueError; nach FEHLVERSUCHE Fehlern von derselben Absender-Adresse für dasselbe Konto ist
    diese Adresse für dieses Konto SPERRE_S Sekunden gesperrt: Gesperrt (PLAN E29: Wer den Namen kennt, sperrt nur sich selbst aus, nicht
    den Besitzer an einem anderen Gerät). Ohne adresse zählt die Sperre je Konto wie vor Phase 40. Höchstens PRUEFUNGEN Prüfungen zugleich,
    die übrigen warten bis PRUEF_WARTEN_S und bekommen sonst Ausgelastet."""
    jetzt = jetzt or time.time()
    try:
        n = kurz(name)
    except ValueError:
        n = ""
    key = (_absender(adresse), n)
    _versuch(key, jetzt)
    if not _pruefung.acquire(timeout=PRUEF_WARTEN_S):
        with _lock:  # nicht geprüft, also kein Fehlversuch
            zahl, seit = _fehl.get(key, (0, 0.0))
            if zahl > 1:
                _fehl[key] = (zahl - 1, seit)
            else:
                _fehl.pop(key, None)
        raise Ausgelastet("Gerade melden sich zu viele an. Bitte gleich noch einmal.")
    try:
        k = konto(conn, n) if n else None
        if not _attrappe:
            _attrappe.append(hash_pw(secrets.token_hex(8)))
        ok = pw_ok(pw, k["pw"] if k and k["pw"] else _attrappe[0])  # unbekannte Namen kosten dieselbe Rechenzeit (kein Raten von Namen)
    finally:
        _pruefung.release()
    if not (k and k["pw"] and ok):
        raise ValueError("Name oder Passwort stimmt nicht")
    with _lock:
        _fehl.pop(key, None)
    return _neue_sitzung(conn, n, jetzt)


def ohne_passwort(conn, jetzt=None):
    """Sitzung fürs Hauptkonto ohne Passwort (Modus „lokal“: nur 127.0.0.1, um die aktive Sammlung zu merken)."""
    h = haupt(conn)
    if not h or h["pw"]:
        raise PermissionError("Anmeldung nötig")
    return _neue_sitzung(conn, h["name"], jetzt or time.time())


# --- Erste Einrichtung im Browser (Phase 43, PLAN E28): der Code und der leere Datenordner ------------------------------

CODE_DATEI = "einrichtung.code"                   # im Datenordner, nur für den Nutzer der App lesbar (0600; unter Windows gelten die Rechte des Ordners)
EINRICHTUNG_ZIP = "einrichtung.zip"               # dorthin schreibt der Server die ZIP, die die Einrichtung einspielt (server.Handler._einspielen)
CODE_ZEICHEN = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"  # 31 Zeichen, ohne 0/O und 1/I/L: Der Code wird aus dem Protokoll abgetippt
CODE_GRUPPEN, CODE_GRUPPE = 4, 5                  # 20 Zeichen, also rund 99 Bit Zufall; geschrieben als XXXXX-XXXXX-XXXXX-XXXXX
CODE_KONTO = "#einrichtung"                       # Schlüssel der Fehlversuche in _fehl: So heißt kein Konto (kurz lässt nur a-z, 0-9 und - zu)
_CODE = re.compile(f"[{CODE_ZEICHEN}]{{{CODE_GRUPPEN * CODE_GRUPPE}}}")


def _code_roh(code):
    """Code, wie er verglichen wird: groß, ohne Leerraum und Bindestriche. Was kein Text ist oder zu lang, ist kein Code."""
    return re.sub(r"[\s-]", "", code).upper() if isinstance(code, str) and len(code) <= 100 else ""


def einrichtung_code():
    """Der Einrichtungs-Code, wie er im Datenordner liegt, oder None (keine Einrichtung offen, Datei unlesbar oder kein Code darin).
    Liest nur."""
    try:
        text = (daten() / CODE_DATEI).read_text(encoding="ascii").strip()
    except (OSError, ValueError):
        return None
    return text if _CODE.fullmatch(_code_roh(text)) else None


def einrichtung_beginnen():
    """Den Einrichtungs-Code anlegen, wenn noch keiner da ist (server.serve, ohne Hauptkonto auf einer fremden Adresse): Zufall aus secrets,
    die Datei nur für den Nutzer der App lesbar und nie über eine vorhandene geschrieben. Ein vorhandener Code bleibt, damit die Zeile im
    Protokoll auch nach einem Neustart stimmt. -> Code"""
    code = einrichtung_code()
    if code:
        try:  # eine Datei, die jemand mit weiteren Rechten dorthin kopiert hat (scp behält sie nicht), wird wieder eng
            os.chmod(daten() / CODE_DATEI, 0o600)
        except OSError:
            pass
        return code
    code = "-".join("".join(secrets.choice(CODE_ZEICHEN) for _ in range(CODE_GRUPPE)) for _ in range(CODE_GRUPPEN))
    daten().mkdir(parents=True, exist_ok=True)
    p = daten() / CODE_DATEI
    p.unlink(missing_ok=True)  # ein unlesbarer Rest
    with os.fdopen(os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="ascii") as f:
        f.write(code + "\n")
    return code


def einrichtung_ende():
    """Den Einrichtungs-Code löschen: Mit dem ersten Hauptkonto ist die Einrichtung vorbei (anlegen ruft das). Lässt sich die Datei nicht
    löschen, gilt der Code trotzdem nicht mehr: Der Server prüft vor jedem Schritt der Einrichtung, dass es kein Hauptkonto gibt."""
    try:
        (daten() / CODE_DATEI).unlink(missing_ok=True)
    except OSError:
        pass


def code_gilt(code):
    """Stimmt der Code mit dem im Datenordner überein? Vergleich in fester Zeit, ohne einen Fehlversuch zu zählen."""
    soll = einrichtung_code()
    return bool(soll) and hmac.compare_digest(_code_roh(code).encode("utf-8", "replace"), _code_roh(soll).encode())


def code_pruefen(code, adresse="", jetzt=None):
    """Einrichtungs-Code prüfen, mit der Sperre der Anmeldung (PLAN E29): Jeder Versuch zählt je Absender-Adresse, nach FEHLVERSUCHE
    falschen ist die Adresse SPERRE_S Sekunden gesperrt (Gesperrt), der richtige Code löscht den Zähler. Falsch: ValueError."""
    jetzt = jetzt or time.time()
    key = (_absender(adresse), CODE_KONTO)
    _versuch(key, jetzt)
    if not code_gilt(code):
        raise ValueError("Der Einrichtungs-Code stimmt nicht")
    with _lock:
        _fehl.pop(key, None)


def leer():
    """Ist der Datenordner leer? Nur dann spielt die Einrichtung im Browser eine Sicherung ein (PLAN E28): So ersetzt sie nie etwas.
    Positivliste: Leer heißt, im Datenordner liegt nichts außer dem, was ein frisch gestarteter Server selbst dort anlegt (die Sperre
    app.lock, der Einrichtungs-Code, die gerade hochgeladene ZIP), dem Katalog aller Karten (katalog.db samt dem, was SQLite daneben legt,
    und der Datei, in die er gerade gebaut wird: aus Scryfall neu ladbar, steckt in keiner Sicherung) und Ordnern ohne jede Datei. Jede
    andere Datei, auch eine leere konten.db oder eine alte Sicherung unter sicherungen/, heißt: nicht leer, weiter mit mtg wiederherstellen."""
    basis = daten()
    if not basis.is_dir():
        return True
    katalog = mtg.katalog_pfad().name
    erlaubt = {SPERRE, CODE_DATEI, EINRICHTUNG_ZIP, katalog + ".neu"} | {katalog + e for e in ("",) + NEBEN}
    for p in basis.iterdir():
        if p.is_symlink():
            return False
        if not (p.is_file() and p.name in erlaubt or p.is_dir() and not any(dateien for _, _, dateien in os.walk(p))):
            return False
    return True


def sitzung(conn, token, jetzt=None):
    """Gültige Sitzung -> {konto, rolle, anzeige, aktiv, aktiv_rolle} oder None."""
    if not token:
        return None
    r = conn.execute("SELECT s.konto, s.aktiv, k.rolle, k.anzeige, a.rolle AS aktiv_rolle FROM sitzungen s JOIN konten k ON k.name = s.konto "
                     "LEFT JOIN konten a ON a.name = s.aktiv WHERE s.token = ? AND s.bis > ?", (_h(token), jetzt or time.time())).fetchone()
    if not r:
        return None
    s = dict(r)
    if s["aktiv_rolle"] is None:  # aktive Sammlung wurde entfernt: zurück zur eigenen
        s["aktiv"], s["aktiv_rolle"] = s["konto"], s["rolle"]
    return s


def abmelden(conn, token):
    with conn:
        conn.execute("DELETE FROM sitzungen WHERE token = ?", (_h(token or ""),))


def wechseln(conn, token, ziel, s):
    """Aktive Sammlung wechseln: das Hauptkonto in jede, ein Unterkonto nur in die eigene."""
    if not konto(conn, ziel):
        raise ValueError(f"Keine Sammlung „{ziel}“")
    if s["rolle"] != "haupt" and ziel != s["konto"]:
        raise PermissionError("Diese Sammlung gehört einem anderen Konto")
    with conn:
        conn.execute("UPDATE sitzungen SET aktiv = ? WHERE token = ?", (ziel, _h(token)))


def sichtbar(conn, s):
    """Sammlungen, die diese Sitzung sehen darf."""
    return [k for k in liste(conn) if s["rolle"] == "haupt" or k["name"] == s["konto"]]


def sammlungen(roh=False):
    """Pfade aller Sammlungen (für täglichen Lauf und Sicherung): ohne Konten nur data/mtg.db. roh: konten.db nur lesen, nicht migrieren
    (die Sicherung läuft auch vor einer Migration); fehlt ihr die Tabelle noch, gibt es keine Konten. -> [(Name, Pfad)]"""
    if not pfad().exists():
        return [("", Path(mtg.DB))]
    with closing(_roh() if roh else connect()) as c:
        da = not roh or c.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'konten'").fetchone()
        alle = [(k["name"], Path(k["db"])) for k in liste(c)] if da else []
    return alle or [("", Path(mtg.DB))]


def _dateien():
    """Die Datenbanken einer Sicherung: konten.db und jede Sammlung, die es als Datei gibt. Gelesen ohne Migration. -> [(Pfad, Name in der ZIP)]"""
    basis = daten()
    return ([(pfad(), "konten.db")] if pfad().exists() else []) + [
        (p, (p.relative_to(basis) if p.is_relative_to(basis) else Path(p.name)).as_posix()) for _, p in sammlungen(roh=True) if p.exists()]


def _kopie(src, ziel):
    """Stimmige Kopie einer Datenbank, auch während jemand in sie schreibt (SQLite-Backup-API). Für denselben Stand ist sie Byte für Byte
    gleich: Darauf stützt sich sicherung_vor_migration."""
    with closing(sqlite3.connect(src)) as a, closing(sqlite3.connect(ziel)) as b:
        a.backup(b)


def sicherung(ziel, nur=None):
    """ZIP mit konten.db, allen Sammlungen (SQLite-Backup-API: stimmig auch bei laufendem Server) und ihren archivierten Importen.
    ziel: Pfad oder Datei-Objekt. nur: statt des Datenordners allein diese Datenbank samt ihren Importen (eine Datei, die nicht zum Datenordner
    gehört, vor ihrer Migration). Die Sicherung migriert selbst nichts. Zurück kommt sie mit zurueckspielen (mtg wiederherstellen), nicht
    durch Entpacken von Hand: Reste eines hart beendeten Prozesses neben einer Datenbank (-wal, -shm) spielte SQLite sonst in die
    zurückgespielte Datei ein. -> Zahl der Datenbanken"""
    n = 0
    # strict_timestamps: Eine archivierte Datei mit einer Uhrzeit vor 1980 (Rechner ohne Uhr) soll keine Sicherung scheitern lassen
    with zipfile.ZipFile(ziel, "w", zipfile.ZIP_DEFLATED, strict_timestamps=False) as z, tempfile.TemporaryDirectory() as tmp:
        for src, arc in ([(Path(nur), Path(nur).name)] if nur else _dateien()):
            kopie = Path(tmp) / f"{n}.db"
            try:
                _kopie(src, kopie)
            except sqlite3.Error as e:  # sagen, welche Datei es ist: Eine unlesbare Sammlung lässt die Sicherung für alle scheitern
                raise type(e)(f"{src}: {e}") from e
            z.write(kopie, arc)
            n += 1
            archiv = src.parent / "imports"
            if arc != "konten.db" and archiv.is_dir():
                for f in sorted(archiv.iterdir()):
                    z.write(f, (Path(arc).parent / "imports" / f.name).as_posix())
    return n


SICHERUNGEN_BEHALTEN = 14


AUSSEN = "aussen.txt"    # schreiben deploy/sicherung-aussen.sh und der zweite Ordner nach jeder Kopie außer Haus: „Zeit Datei Art Ziel“ (Phase 27, 42)
GELADEN = "geladen.txt"  # schreibt die App, wenn die Sicherung heruntergeladen wird
ARTEN = ("verschlüsselt", "unverschlüsselt")  # Art der Kopie in AUSSEN; Zeilen aus der Zeit davor haben sie nicht (Phase 27)


def aussen():
    """Wann zuletzt eine Sicherung das Haus verlassen hat (Phase 27): Kopie per deploy/sicherung-aussen.sh oder in den zweiten Ordner (aussen,
    Phase 42) oder Download (geladen). Eine Zeile ohne Art stammt aus der Zeit vor der Verschlüsselung: Sie gilt nach der Endung der Datei.
    -> {"aussen": {at, datei, ziel, verschluesselt} oder None, "geladen": Zeit oder None}"""
    def lesen(name):
        try:
            return (daten() / "sicherungen" / name).read_text(encoding="utf-8").split()
        except OSError:
            return []
    a, g = lesen(AUSSEN), lesen(GELADEN)
    if a:
        art = a[2] if len(a) > 2 and a[2] in ARTEN else None
        datei = a[1] if len(a) > 1 else ""
        a = {"at": a[0], "datei": datei, "ziel": " ".join(a[3:] if art else a[2:]), "verschluesselt": (art or ("verschlüsselt" if datei.endswith(".gpg") else "")) == "verschlüsselt"}
    return {"aussen": a or None, "geladen": g[0] if g else None}


def sicherung_geladen():
    ordner = daten() / "sicherungen"
    ordner.mkdir(parents=True, exist_ok=True)
    (ordner / GELADEN).write_text(mtg.now_iso() + "\n", encoding="utf-8")


def sicherung_vor(anlass, nur=None):
    """Sicherung vor einem Schritt ohne Rückweg (Übernahme eines ManaBox-Binders, Phase 26; Migration, Phase 39):
    data/sicherungen/vor-<anlass>-<Zeit>.zip, fällt nicht unter die tägliche Rotation. Der Name gehört dem, der die Datei als Erster anlegt
    (leer, bis die Sicherung fertig geschrieben daneben liegt und sie ersetzt): Zwei Sicherungen derselben Sekunde, auch aus zwei
    Prozessen, schreiben weder in dieselbe Datei noch überschreiben sie einander, und eine Datei mit Inhalt ist immer vollständig.
    nur: wie bei sicherung, sie liegt dann neben dieser Datenbank. -> Pfad"""
    ordner = (Path(nur).parent if nur else daten()) / "sicherungen"
    ordner.mkdir(parents=True, exist_ok=True)
    name, i = f"vor-{anlass}-{time.strftime('%Y-%m-%d-%H%M%S')}", 1
    while True:
        ziel = ordner / (f"{name}.zip" if i == 1 else f"{name}-{i}.zip")
        try:
            ziel.open("xb").close()
            break
        except FileExistsError:
            i += 1
    teil = ziel.with_suffix(".tmp")
    try:
        sicherung(teil, nur)
        teil.replace(ziel)
    except BaseException:
        for p in (teil, ziel):  # nichts liegen lassen, was wie eine Sicherung aussieht
            try:
                p.unlink(missing_ok=True)
            except OSError:
                pass
        raise
    return ziel


def _sha(f):
    h = hashlib.sha256()
    for block in iter(lambda: f.read(1 << 20), b""):
        h.update(block)
    return h.digest()


def sicherung_vor_migration(stand, db):
    """Sicherung, bevor eine Datenbank mit Inhalt auf den Stand `stand` gebracht wird (PLAN E27): data/sicherungen/vor-migration-v<stand>-<Zeit>.zip
    mit allen Sammlungen, einmal je Versionssprung. Gibt es zu diesem Sprung schon eine, in der diese Datenbank Byte für Byte in ihrem
    jetzigen Stand steckt, bleibt es bei ihr: So legen die übrigen Sammlungen und ein neuer Versuch nach einem Fehler keine weitere an.
    Hat sich die Datenbank seither geändert (etwa zurück zur alten Fassung, weitergearbeitet, neues Update), entsteht eine neue. Eine
    Datenbank, die nicht zum Datenordner gehört, wird allein gesichert, neben sich. -> Pfad"""
    db = Path(db).resolve()
    drin = {p.resolve(): arc for p, arc in _dateien()} if db.is_relative_to(daten().resolve()) else {}
    ordner, arc, jetzt = (daten() if db in drin else db.parent) / "sicherungen", drin.get(db, db.name), None
    with tempfile.TemporaryDirectory() as tmp:
        for z in sorted(ordner.glob(f"vor-migration-v{stand}-*.zip"), reverse=True):
            try:
                if not z.stat().st_size:  # reserviert: Daran schreibt gerade ein anderer Prozess
                    continue
                with zipfile.ZipFile(z) as f:
                    if arc not in f.namelist():
                        continue
                    if jetzt is None:
                        _kopie(db, Path(tmp) / "jetzt.db")
                        with open(Path(tmp) / "jetzt.db", "rb") as x:
                            jetzt = _sha(x)
                    with f.open(arc) as x:
                        if _sha(x) == jetzt:
                            return z
            except Exception:
                pass  # nicht lesbar oder nicht vergleichbar: zählt nicht, im Zweifel entsteht eine neue
    return sicherung_vor(f"migration-v{stand}", None if db in drin else db)


def taegliche_sicherung(heute):
    """Eine Sicherung je Tag unter data/sicherungen/, die letzten SICHERUNGEN_BEHALTEN bleiben. -> Pfad oder None (schon da)"""
    ordner = daten() / "sicherungen"
    ordner.mkdir(parents=True, exist_ok=True)
    ziel = ordner / f"mtg-{heute}.zip"
    if ziel.exists():
        return None
    teil = ziel.with_suffix(".tmp")
    sicherung(teil)
    teil.replace(ziel)
    for alt in sorted(ordner.glob("mtg-*.zip"))[:-SICHERUNGEN_BEHALTEN]:
        alt.unlink()
    return ziel


# --- Zweiter Ordner für die Sicherung, auch verschlüsselt (Phase 42, PLAN E30) ------------------------------------------

ORDNER_KEY = "sicherung:ordner"            # meta der Hauptsammlung (wie der Schalter des Posteingangs): {"an": bool, "pfad": str}
ORDNER_ERG = "sicherung:ordner:ergebnis"   # und der Ausgang des letzten Versuchs: {"at", "ok", "text"}
SCHLUESSEL = "MTG_AUSSEN_SCHLUESSEL"       # Umgebungsvariable: Datei mit dem Schlüssel für gpg (dieselbe wie bei deploy/sicherung-aussen.sh)
KOPIE_TAGE = 60                            # so lange bleiben die Kopien im zweiten Ordner
GPG_SEKUNDEN = 1800                        # so lange darf gpg für eine ZIP brauchen
SCHREIBPROBE = "mtg-schreibprobe.tmp"      # die einzige Datei, die die App beim Speichern der Einstellung anlegt (und gleich wieder löscht)
# Die Namen, die die App im zweiten Ordner schreibt und aufräumt, und keine anderen: mtg-JJJJ-MM-TT.zip, mit Schlüssel .zip.gpg, beim Schreiben .tmp
_KOPIE = re.compile(r"mtg-(\d{4})-(\d{2})-(\d{2})\.zip(?:\.gpg)?(?:\.tmp)?")


def _pfad_text(pfad):
    text = (pfad or "").strip()
    if len(text) > 1000 or any(ord(c) < 32 or ord(c) == 127 for c in text):
        raise ValueError("Der Pfad ist nicht gültig")
    return text


def ordner_pruefen(pfad, schreibprobe=True):
    """Ordner für die zweite Kopie der Sicherung prüfen. Der Pfad kommt aus der Oberfläche, ist also fremde Eingabe: Er wird nur als Pfad
    benutzt, nie als Teil eines Befehls. Verlangt: ganzer Pfad (kein relativer), Ordner vorhanden, nicht im Datenordner (das wäre keine zweite
    Kopie), beschreibbar (eine Probe mit der festen Datei SCHREIBPROBE, die gleich wieder weg ist; ohne beim täglichen Lauf, dort zeigt die Kopie
    selbst, ob es geht). -> der aufgelöste Ordner"""
    text = _pfad_text(pfad)
    if not text:
        raise ValueError("Bitte den Ordner angeben")
    if not Path(text).is_absolute():
        raise ValueError("Bitte den ganzen Pfad angeben, unter Windows mit Laufwerk (zum Beispiel D:\\Cloud\\Sicherung), keinen relativen")
    try:
        real = Path(text).resolve(strict=True)
    except (OSError, RuntimeError):
        raise ValueError("Diesen Ordner gibt es nicht (oder die App darf ihn nicht sehen)") from None
    if not real.is_dir():
        raise ValueError("Das ist kein Ordner")
    for q in (real, *real.parents):
        try:
            if q.samefile(daten()):
                raise ValueError("Dieser Ordner liegt im Datenordner der App. Eine zweite Kopie braucht einen anderen Ort, sonst geht sie mit dem Datenordner verloren")
        except OSError:
            pass
    if schreibprobe:
        probe = real / SCHREIBPROBE
        try:
            probe.unlink(missing_ok=True)
            with open(probe, "xb"):
                pass
            probe.unlink()
        except OSError as e:
            raise ValueError(f"In diesem Ordner lässt sich nichts anlegen und löschen ({e.strerror or type(e).__name__}). Die App braucht beides") from None
    return real


def ordner_einstellung(conn):
    """Der zweite Ordner, eine Einstellung der ganzen Installation: steht in der Tabelle meta der Hauptsammlung (conn) wie der Schalter des
    Posteingangs, ohne eigenes Schema. -> {an, pfad}"""
    r = conn.execute("SELECT value FROM meta WHERE key = ?", (ORDNER_KEY,)).fetchone()
    try:
        d = json.loads(r[0]) if r else {}
    except ValueError:
        d = {}
    d = d if isinstance(d, dict) else {}
    return {"an": d.get("an") is True, "pfad": d["pfad"] if isinstance(d.get("pfad"), str) else ""}


def ordner_setzen(conn, an, pfad):
    """Einstellung speichern. Eingeschaltet wird nur ein Ordner, der ordner_pruefen besteht (ValueError mit lesbarer Meldung, nichts gespeichert);
    ausgeschaltet bleibt der Pfad stehen. Der Ausgang des letzten Versuchs wird gelöscht. -> ordner_einstellung"""
    pfad = _pfad_text(pfad)
    if an:
        ordner_pruefen(pfad)
    with conn:
        conn.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (ORDNER_KEY, json.dumps({"an": bool(an), "pfad": pfad})))
        conn.execute("DELETE FROM meta WHERE key = ?", (ORDNER_ERG,))
    return ordner_einstellung(conn)


def ordner_ergebnis(conn):
    """Ausgang des letzten Versuchs, eine Kopie in den zweiten Ordner zu legen: {at, ok, text} oder None."""
    r = conn.execute("SELECT value FROM meta WHERE key = ?", (ORDNER_ERG,)).fetchone()
    try:
        d = json.loads(r[0]) if r else None
    except ValueError:
        return None
    return d if isinstance(d, dict) and isinstance(d.get("text"), str) else None


def gpg_programm():
    """Aufruf von gpg als Liste, None ohne: MTG_GPG (Pfad zum Programm), sonst gpg aus dem Suchpfad. gpg ist ein eigenes Programm, wie Tesseract."""
    eigen = os.environ.get("MTG_GPG", "").strip()
    gpg = shutil.which(eigen or "gpg")
    return [gpg] if gpg else None


def schluessel_stand():
    """Die Schlüsseldatei der App (Umgebungsvariable SCHLUESSEL): -> (Pfad oder None ohne Schlüssel, Problem oder None). Ein Problem ist alles,
    was die Verschlüsselung verhindert; dann kopiert die App nichts, statt unverschlüsselt weiterzumachen."""
    pfad = os.environ.get(SCHLUESSEL, "").strip()
    if not pfad:
        return None, None
    try:
        with open(pfad, "rb") as f:
            if not f.readline().strip():  # gpg nimmt die erste Zeile als Schlüssel
                return pfad, "Die Schlüsseldatei ist leer"
    except OSError as e:
        return pfad, f"Die Schlüsseldatei lässt sich nicht lesen ({e.strerror or type(e).__name__})"
    if not gpg_programm():
        return pfad, "gpg fehlt auf diesem Rechner"
    return pfad, None


def verschluesseln(quelle, ziel, schluessel):
    """ZIP mit gpg symmetrisch (AES256) verschlüsseln. Der Schlüssel geht als Datei an gpg (--passphrase-file), nie in der Befehlszeile: Dort
    sähe ihn jeder Nutzer des Rechners in der Prozessliste. Feste Argumente, keine Shell; die ZIP ist schon gepackt, gpg packt nicht noch einmal."""
    prog = gpg_programm()
    if not prog:
        raise ValueError("gpg fehlt auf diesem Rechner")
    try:
        r = subprocess.run([*prog, "--batch", "--yes", "--quiet", "--pinentry-mode", "loopback", "--passphrase-file", str(schluessel),
                            "--compress-algo", "none", "--symmetric", "--cipher-algo", "AES256", "--output", str(ziel), str(quelle)],
                           stdin=subprocess.DEVNULL, capture_output=True, timeout=GPG_SEKUNDEN)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise ValueError(f"gpg lässt sich nicht ausführen ({type(e).__name__})") from e
    if r.returncode or not Path(ziel).is_file() or not Path(ziel).stat().st_size:
        raise ValueError("gpg: " + (r.stderr.decode("utf-8", "replace").strip()[-200:] or f"Rückgabewert {r.returncode}"))


def _hinkopieren(quelle, ziel):
    """Unter anderem Namen schreiben (Ziel + .tmp), dann umbenennen: Im Ordner steht nie eine halbe Sicherung unter dem richtigen Namen."""
    tmp = ziel.with_name(ziel.name + ".tmp")
    tmp.unlink(missing_ok=True)
    try:
        with open(quelle, "rb") as a, open(tmp, "xb") as b:
            shutil.copyfileobj(a, b, 1 << 20)
        if tmp.stat().st_size != Path(quelle).stat().st_size:
            raise OSError("Die Kopie ist kürzer als das Original (Platte voll?)")
        os.replace(tmp, ziel)
    except BaseException:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _aufraeumen(ordner, heute):
    """Kopien aus ORDNER löschen, die älter als KOPIE_TAGE sind, und nur Dateien mit den Namen von _KOPIE (das Datum steht im Namen). -> Zahl"""
    grenze, n = date.fromisoformat(heute) - timedelta(days=KOPIE_TAGE), 0
    for f in ordner.iterdir():
        m = _KOPIE.fullmatch(f.name)
        try:
            if m and date(*map(int, m.groups())) < grenze and not f.is_dir():
                f.unlink()
                n += 1
        except ValueError:  # ein Datum, das es nicht gibt: nicht unser Name
            pass
    return n


def ordner_kopie(conn, heute=None):
    """Nach der täglichen Sicherung die ZIP von heute in den zweiten Ordner legen (Einstellung in conn, der Hauptsammlung), wenn er eingeschaltet
    ist und die Kopie dort noch fehlt. Mit Schlüsseldatei (SCHLUESSEL) und gpg wird vorher verschlüsselt und nur die .gpg-Datei kopiert; ist
    der Schlüssel gesetzt, aber unbrauchbar (oder gpg weg), geschieht nichts: Verschlüsselt gemeint heißt nie unverschlüsselt kopiert. Ohne
    Schlüssel geht die ZIP unverschlüsselt hinüber (die Oberfläche warnt). Die App schreibt und löscht dort nur Dateien mit ihrem festen
    Namen (_KOPIE), räumt nach KOPIE_TAGE auf und vermerkt die Kopie wie das Skript in aussen.txt. Jeder Fehler (Ordner weg, Platte voll,
    gpg) steht im Ausgang (ordner_ergebnis, Neuigkeiten, „Konten und Sicherung“) und bricht nichts ab; der nächste Lauf versucht es wieder.
    -> Protokollzeile oder None (nichts zu tun, schon da, oder derselbe Fehler wie zuvor)"""
    heute = heute or date.today().isoformat()
    e = ordner_einstellung(conn)
    if not e["an"] or not e["pfad"]:
        return None
    quelle, (schluessel, problem) = daten() / "sicherungen" / f"mtg-{heute}.zip", schluessel_stand()
    name = quelle.name + (".gpg" if schluessel else "")
    vorher = ordner_ergebnis(conn)
    try:
        ordner = ordner_pruefen(e["pfad"], schreibprobe=False)
        if (ordner / name).exists():
            if vorher and not vorher.get("ok"):  # der Ordner war weg und ist wieder da, die Kopie von heute liegt schon: Die Warnung endet jetzt, nicht erst morgen
                with conn:
                    conn.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (ORDNER_ERG, json.dumps(
                        {"at": mtg.now_iso(), "ok": True, "text": f"{name} ({'verschlüsselt' if schluessel else 'unverschlüsselt'}) nach {e['pfad']}"}, ensure_ascii=False)))
            return None
        if problem:
            raise ValueError(f"{problem}. Nichts kopiert")
        if not quelle.is_file():
            raise ValueError(f"Die Sicherung {quelle.name} fehlt")
        with tempfile.TemporaryDirectory(dir=quelle.parent) as tmp:
            senden = quelle
            if schluessel:
                senden = Path(tmp) / name
                verschluesseln(quelle, senden, schluessel)
            _hinkopieren(senden, ordner / name)
        if schluessel and (ordner / quelle.name).is_file():  # eine unverschlüsselte Kopie von heute, vor dem Schlüssel gelegt, soll nicht liegen bleiben
            (ordner / quelle.name).unlink()
        try:
            weg = _aufraeumen(ordner, heute)
            hinweis = f" ({weg} alte aufgeräumt)" if weg else ""
        except OSError as x:
            hinweis = f" (Aufräumen nicht möglich: {x.strerror or type(x).__name__})"
        art = "verschlüsselt" if schluessel else "unverschlüsselt"
        vermerk = daten() / "sicherungen" / (AUSSEN + ".tmp")
        vermerk.write_text(f"{mtg.now_iso()} {name} {art} {e['pfad']}\n", encoding="utf-8")
        vermerk.replace(vermerk.with_name(AUSSEN))
        text, ok = f"{name} ({art}) nach {e['pfad']}{hinweis}", True
    except (OSError, ValueError) as x:
        text, ok = (f"{x.strerror or type(x).__name__}" + (f" ({x.filename})" if x.filename else "") if isinstance(x, OSError) else str(x)), False
    with conn:
        conn.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (ORDNER_ERG, json.dumps({"at": mtg.now_iso(), "ok": ok, "text": text}, ensure_ascii=False)))
    if ok:
        return f"Sicherung im zweiten Ordner: {text}"
    return None if vorher and not vorher.get("ok") and vorher.get("text") == text else f"Sicherung im zweiten Ordner gescheitert: {text}"


def ordner_info(conn):
    """Für „Konten und Sicherung“: die Einstellung, der Ausgang des letzten Versuchs und der Stand der Verschlüsselung dieser App
    (verschluesselung: „aus“ ohne Schlüsseldatei, „ok“, „defekt“ mit dem Grund in problem)."""
    pfad, problem = schluessel_stand()
    return ordner_einstellung(conn) | {"ergebnis": ordner_ergebnis(conn), "verschluesselung": "aus" if not pfad else "defekt" if problem else "ok", "problem": problem or ""}


def ordner_news(conn):
    """Neuigkeit, solange die letzte Kopie in den zweiten Ordner gescheitert ist (conn = die Sammlung, die gerade offen ist: Nur in der
    Hauptsammlung steht die Einstellung, ein Unterkonto sieht nie etwas davon)."""
    r = ordner_ergebnis(conn)
    if not r or r.get("ok") or not ordner_einstellung(conn)["an"]:
        return []
    return [{"kind": "sicherung_warn", "icon": "!", "text": "Die Sicherung im zweiten Ordner ist gescheitert", "sub": r["text"]}]


# --- Sicherung zurückspielen (Phase 41, PLAN E30) ---------------------------------------------------------------------

SPERRE = "app.lock"                   # Datei im Datenordner, die die laufende Oberfläche gesperrt hält (belegen)
ENTPACKT_MAX = 8 * 1024 ** 3          # so viele Bytes darf eine Sicherung entpackt haben (ZIP-Bombe; eine Sammlung mit 60.000 Drucken hat rund 430 MB)
EINTRAEGE_MAX = 50_000                # und so viele Einträge
NEBEN = ("-wal", "-shm", "-journal")  # was SQLite neben eine Datenbank legt: Reste davon spielte es in eine zurückgespielte Datei ein
_KONTO = re.compile(r"[a-z0-9][a-z0-9-]{0,39}")                    # Kurzname eines Kontos, wie kurz ihn bildet
_GERAET = re.compile(r"(?i)(con|prn|aux|nul|com\d|lpt\d)(\..*)?")  # unter Windows keine Dateien, sondern Geräte
_verschieben = os.replace             # jede Bewegung beim Tauschen läuft hierüber (Tests lassen sie hier scheitern)
RUNDEN_MAX = 10_000_000               # mehr Runden hat kein Passwort in einer ZIP aus fremder Hand (_pruefen, streng): rund das 17-Fache von RUNDEN
_HASH = re.compile(r"pbkdf2_sha256\$([1-9][0-9]{0,7})\$[0-9a-f]{32}\$[0-9a-f]{64}")  # ein Passwort, wie hash_pw es schreibt


class KeineSicherung(ValueError):
    """Diese ZIP spielt die App nicht zurück: keine Sicherung der App, beschädigt, zu groß oder aus einer neueren Version. Nichts ist geändert."""


class AppLaeuft(ValueError):
    """Zurückgespielt wird nur bei stehender App. Nichts ist geändert."""


class NichtZurueck(RuntimeError):
    """Das Einsetzen ist gescheitert, und der alte Stand kam nicht von selbst zurück. Die Meldung nennt, wo er liegt; gelöscht ist nichts."""


def belegen():
    """Den Datenordner für diesen Prozess belegen, solange die zurückgegebene Datei offen ist: eine Sperre des Betriebssystems auf
    data/app.lock. Sie endet mit dem Prozess, auch wenn er hart beendet wird (keine liegen gebliebene Sperre), und sie gilt zwischen
    Prozessen und Containern, die denselben Ordner benutzen. Die Oberfläche hält sie, solange sie läuft (server.serve), das Zurückspielen
    verlangt sie: Daran erkennt es eine laufende App auch dann, wenn gerade keine Anfrage eine Datenbank offen hat.
    -> offene Datei, oder None: Ein anderer hält sie"""
    daten().mkdir(parents=True, exist_ok=True)
    try:
        f = open(daten() / SPERRE, "ab")
    except PermissionError:  # die Datei gehört einem anderen Nutzer (einmal als root zurückgespielt): Sperren geht auch nur lesend
        f = open(daten() / SPERRE, "rb")
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as e:
        f.close()
        if e.errno in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
            return None
        raise
    return f


def _allein():
    """Die Sperre für das Zurückspielen, oder AppLaeuft mit dem Hinweis, was zu tun ist."""
    try:
        f = belegen()
    except OSError as e:
        raise AppLaeuft(f"Der Datenordner lässt sich nicht sperren ({e.strerror or e}). Ohne Sperre spielt die App nichts zurück.") from e
    if f is None:
        raise AppLaeuft(f"Die App läuft noch, zurückgespielt wird nur, wenn sie beendet ist. Erst beenden (am Rechner das Fenster der App "
                        f"schließen oder „{mtg.version.NAME} beenden“, auf dem Server docker compose stop mtg, ohne Docker systemctl stop "
                        f"pappenheimer), dann noch einmal; mit Docker: docker compose run --rm mtg wiederherstellen /app/data/DATEI.zip")
    return f


def _laeuft():
    """Hält gerade ein anderer Prozess den Datenordner belegt? Legt selbst nichts an."""
    if not (daten() / SPERRE).exists():
        return False
    try:
        f = belegen()
    except OSError:
        return False
    if f:
        f.close()
    return f is None


def _konto_ok(name):
    return isinstance(name, str) and bool(_KONTO.fullmatch(name))


def _datei_ok(name):
    """Name eines archivierten Imports: ein einzelner Dateiname, der auf jedem System nur diese eine Datei meint (kein Trenner, kein
    Laufwerk, kein Punkt am Ende: Das schließt „.“ und „..“ ein und was Windows stillschweigend kürzt)."""
    return (0 < len(name) <= 200 and not re.search(r'[\x00-\x1f\x7f/\\:*?"<>|]', name)
            and name == name.strip() and not name.endswith(".") and not _GERAET.fullmatch(name))


def _einordnen(name):
    """Name eines ZIP-Eintrags -> (Art, Konto, Stelle im Datenordner) für genau das, was sicherung schreibt, sonst None. Art: „konten“
    (konten.db), „db“ (eine Sammlung), „import“ (archivierter Import), „ordner“ (Eintrag für einen Ordner: wird nicht angelegt). Konto:
    Kurzname des Unterkontos, „“ für die Hauptsammlung; sie heißt in der ZIP mtg.db oder wie mtg.DB und kommt an die Stelle von mtg.DB."""
    haupt = Path(mtg.DB).name
    t = name.split("/")
    ordner = t[-1] == ""
    if ordner:
        t.pop()
    if not t:
        return None
    konto, vor = "", ""
    if t[0] == "konten" and (len(t) > 1 or ordner):
        if len(t) == 1:
            return "ordner", "", "konten"
        if not _konto_ok(t[1]):
            return None
        konto, vor, t = t[1], f"konten/{t[1]}/", t[2:]
        if not t:
            return ("ordner", konto, vor[:-1]) if ordner else None
    if len(t) == 1 and not ordner:
        if not konto and t[0] == "konten.db":
            return "konten", "", "konten.db"
        if t[0] == "mtg.db" or (not konto and t[0] == haupt):
            return "db", konto, vor + ("mtg.db" if konto else haupt)
        return None
    if t[0] == "imports" and (len(t) == 1 or len(t) == 2 and _datei_ok(t[1])):
        return "ordner" if ordner else "import", konto, vor + "/".join(t)
    return None


def _entpacken(quelle, ziel):
    """Sicherung in den leeren Ordner ziel entpacken, ohne der ZIP etwas zu glauben. Erst wird jeder Eintrag geprüft: nur die Pfade, die
    sicherung schreibt (kein „..“, kein absoluter Pfad, kein Rückstrich, kein Laufwerk), keine Verweise oder Sonderdateien, nichts
    Verschlüsseltes, nichts doppelt (auch nicht nur in der Schreibweise verschieden), Zahl und angegebene Größe innerhalb der Grenzen. Dann
    wird geschrieben: nur an die geprüfte Stelle, nie über eine vorhandene Datei, und nie mehr als ENTPACKT_MAX Bytes, was immer die ZIP
    über ihre Größe sagt. -> ([(Art, Konto, Stelle)], Zeit der jüngsten Datenbank)"""
    if not Path(quelle).is_file():
        raise KeineSicherung(f"Datei nicht gefunden: {quelle}")
    zu_gross = f"Entpackt wäre die ZIP größer als {ENTPACKT_MAX // 1024 ** 2} MB, so groß ist keine Sicherung."
    geschrieben = 0
    try:
        with zipfile.ZipFile(quelle) as z:
            eintraege = z.infolist()
            if len(eintraege) > EINTRAEGE_MAX:
                raise KeineSicherung(f"Die ZIP hat mehr als {EINTRAEGE_MAX} Einträge, so sieht keine Sicherung aus.")
            plan, gesehen, summe = [], set(), 0
            for i in eintraege:
                name = i.orig_filename  # wie er in der ZIP steht: In filename hat zipfile unter Windows den Rückstrich schon ersetzt
                art = _einordnen(name)
                if not art:
                    raise KeineSicherung(f"{name[:80]!r} gehört nicht in eine Sicherung dieser App.")
                if i.flag_bits & 0x1:
                    raise KeineSicherung("Die ZIP ist verschlüsselt. Erst entschlüsseln, dann zurückspielen.")
                typ = stat.S_IFMT(i.external_attr >> 16)
                if typ and typ != (stat.S_IFDIR if art[0] == "ordner" else stat.S_IFREG):
                    raise KeineSicherung(f"{name[:80]!r} ist ein Verweis oder eine Sonderdatei.")
                if art[0] == "ordner":
                    continue
                schluessel = unicodedata.normalize("NFC", art[2]).casefold()
                if schluessel in gesehen:
                    raise KeineSicherung(f"{name[:80]!r} steht mehrfach in der ZIP.")
                gesehen.add(schluessel)
                summe += i.file_size
                plan.append((i, art))
            if summe > ENTPACKT_MAX:
                raise KeineSicherung(zu_gross)
            dbs = [i for i, art in plan if art[0] != "import"]
            if not dbs:
                raise KeineSicherung("In der ZIP steckt keine Datenbank, sie ist keine Sicherung dieser App.")
            for i, (_, _, stelle) in plan:  # erst jetzt wird geschrieben
                p = ziel.joinpath(*stelle.split("/"))
                p.parent.mkdir(parents=True, exist_ok=True)
                with z.open(i) as q, open(p, "xb") as f:
                    while block := q.read(1 << 20):
                        geschrieben += len(block)
                        if geschrieben > ENTPACKT_MAX:
                            raise KeineSicherung(zu_gross)
                        f.write(block)
                    f.flush()
                    os.fsync(f.fileno())  # liegt wirklich auf der Platte, bevor es an die Stelle der alten Datei rückt
    except KeineSicherung:
        raise
    except OSError as e:
        lang = "; der Pfad des Datenordners ist für Windows zu lang" if os.name == "nt" and len(str(e.filename or "")) > 240 else ""
        raise KeineSicherung(f"Die Sicherung ließ sich nicht entpacken ({e.strerror or e}{lang}).") from e
    except Exception as e:  # zipfile meldet Kaputtes auf viele Arten (BadZipFile, zlib.error, EOFError, NotImplementedError, …)
        raise KeineSicherung("Die Datei ist keine ZIP oder sie ist beschädigt.") from e
    return [art for _, art in plan], "%04d-%02d-%02d %02d:%02d" % tuple(max(i.date_time for i in dbs)[:5])


def _lesen(pfad):
    """Nur lesende Verbindung, die neben der Datei nichts anlegt und keine -wal einspielt (immutable): für die entpackten Kopien, die sonst
    niemand öffnet, und für die Vorschau des jetzigen Stands."""
    return sqlite3.connect(Path(pfad).resolve().as_uri() + "?immutable=1", uri=True)


def _zahlen(c):
    """Karten und Wert einer Sammlung, wie die Kontenliste sie zeigt (server._bestand)."""
    return tuple(c.execute(f"SELECT COALESCE(SUM(col.qty), 0), COALESCE(SUM(col.qty * {mtg.PRICE}), 0) FROM collection col "
                           f"LEFT JOIN cards c USING (scryfall_id) WHERE {mtg.OWNED}").fetchone())


def _datenbank(pfad, stelle, erwartet, lesen, streng=False):
    """Entpackte Datenbank prüfen: lesbar, Stand nicht über dem der App (Phase 39: eine ältere stellt die App beim nächsten Öffnen selbst
    um), PRAGMA integrity_check ohne Befund, und wenn sie Tabellen hat, dann die erwarteten (ganz ohne Tabellen ist sie eine leere
    Sammlung). streng (eine ZIP aus fremder Hand, Phase 43): dazu keine Auslöser und keine Sichten, die App legt keine an.
    -> (Stand, lesen(Verbindung) oder None ohne Tabellen)"""
    try:
        with closing(_lesen(pfad)) as c:
            stand = c.execute("PRAGMA user_version").fetchone()[0]
            if stand > mtg.STAND:
                raise KeineSicherung(f"Die Sicherung stammt aus einer neueren Version der App ({stelle}: Stand {stand}, diese App kennt "
                                     f"{mtg.STAND}). Bitte erst die App aktualisieren.")
            befund = [r[0] for r in c.execute("PRAGMA integrity_check")]
            if befund != ["ok"]:
                raise KeineSicherung(f"{stelle} in der Sicherung ist beschädigt ({str(befund[:1])[:120]}).")
            tabellen = {r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            if tabellen and not erwartet <= tabellen:
                raise KeineSicherung(f"{stelle} in der Sicherung ist keine Datenbank dieser App.")
            if streng and c.execute("SELECT 1 FROM sqlite_master WHERE type IN ('trigger', 'view')").fetchone():
                raise KeineSicherung(f"{stelle} in der Sicherung enthält Auslöser oder Sichten, wie die App keine anlegt.")
            return stand, lesen(c) if tabellen else None
    except sqlite3.Error as e:
        raise KeineSicherung(f"{stelle} in der Sicherung ist keine lesbare Datenbank ({e}).") from e


def _pruefen(quelle, neu, streng=False):
    """Sicherung nach neu entpacken (_entpacken) und prüfen (_datenbank); dazu: Kontonamen nur, wie die App sie vergibt (aus ihnen werden
    Pfade), eine Sammlung unter konten/ nur mit ihrem Unterkonto, Importe nur mit ihrer Sammlung. streng (eine ZIP aus fremder Hand, die
    Einrichtung im Browser): dazu Passwörter nur, wie hash_pw sie schreibt, mit höchstens RUNDEN_MAX Runden (sonst rechnete jede Anmeldung
    beliebig lange), und keine Auslöser oder Sichten. -> Auskunft (siehe pruefen)"""
    dateien, datum = _entpacken(quelle, neu)
    info = {"datei": Path(quelle).name, "datum": datum, "konten": [], "sammlungen": [], "stand": mtg.STAND}
    if ("konten", "", "konten.db") in dateien:
        info["stand"], gelesen = _datenbank(neu / "konten.db", "konten.db", {"konten", "sitzungen"}, lambda c: [
            tuple(r) for r in c.execute("SELECT name, rolle, pw FROM konten ORDER BY rolle != 'haupt', name")], streng)
        if streng and any(pw is not None and not ((m := _HASH.fullmatch(pw if isinstance(pw, str) else "")) and int(m[1]) <= RUNDEN_MAX)
                          for _, _, pw in gelesen or []):
            raise KeineSicherung("konten.db in der Sicherung enthält ein Passwort, wie die App keines speichert.")
        info["konten"] = [{"name": name, "rolle": rolle, "pw": bool(pw)} for name, rolle, pw in gelesen or []]
        if any(not _konto_ok(k["name"]) or k["rolle"] not in ("haupt", "unter") for k in info["konten"]) or sum(
                k["rolle"] == "haupt" for k in info["konten"]) > 1:
            raise KeineSicherung("konten.db in der Sicherung enthält ein Konto, wie die App keines anlegt.")
    haupt = next((k["name"] for k in info["konten"] if k["rolle"] == "haupt"), "")
    unter = {k["name"] for k in info["konten"] if k["rolle"] == "unter"}
    importe = [konto for art, konto, _ in dateien if art == "import"]
    if set(importe) - {konto for art, konto, _ in dateien if art == "db"}:
        raise KeineSicherung("In der ZIP stecken archivierte Importe ohne ihre Sammlung.")
    for art, konto, stelle in dateien:
        if art != "db":
            continue
        if konto and konto not in unter:
            raise KeineSicherung(f"Zu {stelle} steht in der Sicherung kein Unterkonto.")
        stand, zahlen = _datenbank(neu / stelle, stelle, {"collection", "cards"}, _zahlen, streng)
        karten, wert = zahlen or (0, 0.0)
        info["stand"] = min(info["stand"], stand)
        info["sammlungen"].append({"konto": konto or haupt, "stelle": stelle, "karten": karten, "wert": wert, "importe": importe.count(konto)})
    return info


def _stellen(info):
    """Was beim Zurückspielen beiseitegelegt wird, relativ zum Datenordner: konten.db, die Hauptsammlung und die Sammlung jedes Unterkontos,
    das es jetzt gibt oder das die Sicherung bringt, je mit dem, was SQLite daneben legt (NEBEN), und dem Archiv der Importe. Alles andere
    bleibt liegen: katalog.db, Messbilder, sicherungen/, Recherche, Posteingänge und die Datenbank eines entfernten Kontos, das auch die
    Sicherung nicht kennt. Reihenfolge: die Archive, die Sammlungen, konten.db zuletzt (die Anmeldung fällt als Letztes weg).
    -> (Stellen, davon die Datenbanken, Konten jetzt [(Name, Rolle)])"""
    jetzt = []
    if pfad().exists():
        try:  # gelesen, ohne etwas zu ändern; eine unlesbare konten.db meldet später die Sicherung des jetzigen Stands
            with closing(_lesen(pfad())) as c:
                jetzt = [(r[0], r[1]) for r in c.execute("SELECT name, rolle FROM konten ORDER BY rolle != 'haupt', name") if _konto_ok(r[0])]
        except sqlite3.Error:
            pass
    unter = sorted({n for n, rolle in jetzt if rolle != "haupt"} | {k["name"] for k in info["konten"] if k["rolle"] == "unter"})
    dbs = [f"konten/{n}/mtg.db" for n in unter] + [Path(mtg.DB).name, "konten.db"]
    return [f"konten/{n}/imports" for n in unter] + ["imports"] + [d + e for d in dbs for e in ("",) + NEBEN], dbs, jetzt


def _vergleich(info, stellen, dbs, jetzt, ohne="", laeuft=False):
    """Auskunft um das ergänzen, was das Zurückspielen am Datenordner ändert: „jetzt“ (jede Sammlung, die beiseitegelegt wird; drin = die
    Sicherung bringt an ihre Stelle eine andere, sonst entfällt sie; gesichert = sie steckt in der Sicherung des jetzigen Stands, sonst
    bleibt sie im Arbeitsordner liegen) und „bleibt“ (was liegen bleibt). Liest nur, und so, dass dabei keine Datei entsteht."""
    basis, bringt = daten(), {s["stelle"] for s in info["sammlungen"]}
    konto = {f"konten/{n}/mtg.db": n for n, rolle in jetzt if rolle != "haupt"} | {dbs[-2]: next((n for n, rolle in jetzt if rolle == "haupt"), "")}
    info |= {"ordner": str(basis), "laeuft": laeuft, "konten_jetzt": [n for n, _ in jetzt], "jetzt": [], "bleibt": []}
    for d in [dbs[-2]] + dbs[:-2]:
        p = basis / d
        if not p.exists():
            continue
        zahlen = None
        offen = [x for e in ("-wal", "-journal") if (x := Path(str(p) + e)).exists() and x.stat().st_size]
        if not offen:  # steht etwas in der -wal, zeigte der Blick ohne sie einen alten Stand (eine leere lässt jedes nur lesende Öffnen liegen)
            try:
                with closing(_lesen(p)) as c:
                    zahlen = _zahlen(c)
            except sqlite3.Error:
                pass
        info["jetzt"].append({"konto": konto.get(d, d.split("/")[1] if "/" in d else ""), "stelle": d, "karten": zahlen and zahlen[0],
                              "wert": zahlen and zahlen[1], "drin": d in bringt, "gesichert": d in konto})
    for p in sorted(basis.iterdir()) if basis.is_dir() else []:
        for u in sorted(x for k in p.iterdir() if k.is_dir() for x in k.iterdir()) if p.name == "konten" and p.is_dir() else [p]:
            stelle = u.relative_to(basis).as_posix()
            if stelle not in stellen and stelle not in (SPERRE, ohne):
                info["bleibt"].append(stelle + ("/" if u.is_dir() else ""))
    return info


def pruefen(quelle):
    """Sicherung prüfen, ohne im Datenordner etwas zu schreiben (PLAN E30): Entpackt wird in einen eigenen temporären Ordner. Lehnt mit
    KeineSicherung ab, was keine unbeschädigte Sicherung dieser App ist (_entpacken, _datenbank, _pruefen). -> Auskunft:
    datei, datum (Zeit der Sicherung), stand (kleinster Stand ihrer Datenbanken), konten [{name, rolle, pw}], sammlungen [{konto, stelle,
    karten, wert, importe}]; dazu der Vergleich mit dem Datenordner: ordner, konten_jetzt, jetzt [{konto, stelle, karten, wert, drin,
    gesichert}], bleibt [Stelle], laeuft (die App hält den Ordner gerade belegt)."""
    with tempfile.TemporaryDirectory() as tmp:
        info = _pruefen(quelle, Path(tmp))
    return _vergleich(info, *_stellen(info), laeuft=_laeuft())


def _raeumen(basis, stellen, ziel, weg):
    """Was an diesen Stellen liegt, nach ziel verschieben (dieselben Unterordner). weg nimmt jede verschobene Stelle auf, auch wenn es
    mittendrin scheitert: Daraus holt _tauschen sie zurück."""
    for s in stellen:
        if os.path.lexists(basis / s):
            (ziel / s).parent.mkdir(parents=True, exist_ok=True)
            _verschieben(basis / s, ziel / s)
            weg.append(s)


def _tauschen(basis, arbeit, stellen, dbs):
    """Der Tausch: erst alles an den Stellen nach arbeit/alt (jede Datenbank samt -wal, -shm und -journal, damit SQLite nichts Altes in die
    neue Datei einspielt und der alte Stand als Ganzes zurückkann), dann aus arbeit/neu einsetzen, konten.db zuerst. Jede Stelle muss beim
    Einsetzen frei sein. Scheitert irgendetwas, geht es zurück: das Eingesetzte wieder nach neu, was sonst inzwischen an den geräumten
    Stellen liegt (ein anderes Programm hat es angelegt) nach arbeit/fremd, dann der alte Stand an seinen Platz. Gelingt auch das nicht:
    NichtZurueck, und nichts wird mehr angefasst."""
    neu, alt = arbeit / "neu", arbeit / "alt"
    weg, da, frei = [], [], False
    try:
        _raeumen(basis, stellen, alt, weg)
        frei = True  # ab hier liegt an keiner Stelle mehr etwas vom alten Stand
        for s in [d for d in reversed(dbs) if (neu / d).exists()] + [s for s in stellen if (neu / s).is_dir()]:
            belegt = [s + e for e in (("",) + NEBEN if s in dbs else ("",)) if os.path.lexists(basis / (s + e))]
            if belegt:
                raise OSError(f"{belegt[0]} ist wieder da: Ein anderes Programm arbeitet im Datenordner")
            (basis / s).parent.mkdir(parents=True, exist_ok=True)
            _verschieben(neu / s, basis / s)
            da.append(s)
    except BaseException as e:
        try:
            for s in reversed(da):
                _verschieben(basis / s, neu / s)
            _raeumen(basis, stellen if frei else weg, arbeit / "fremd", [])  # nur wo der alte Stand schon weg ist: Der Rest ist der alte Stand
            for s in reversed(weg):
                _verschieben(alt / s, basis / s)
        except BaseException as e2:
            raise NichtZurueck(f"Das Zurückspielen ist gescheitert ({type(e).__name__}: {e}), und der alte Stand ließ sich nicht von selbst "
                               f"zurückholen ({type(e2).__name__}: {e2}). Gelöscht ist nichts: Was vom alten Stand nicht mehr an seinem Platz "
                               f"liegt, liegt mit denselben Namen in {alt}. Die App nicht starten, erst diese Dateien von Hand zurücklegen "
                               f"oder die Sicherung des alten Stands zurückspielen.") from e2
        if isinstance(e, Exception):
            raise ValueError(f"Das Einsetzen ist gescheitert ({type(e).__name__}: {e}). Der alte Stand ist wieder an seinem Platz.") from e
        raise


def _leer_raeumen(ordner):
    """Leere Ordner unter ordner entfernen, und ordner selbst, wenn nichts mehr darin liegt. Dateien fasst das nie an. -> True: ordner ist weg"""
    for unter, _, _ in os.walk(ordner, topdown=False):
        try:
            os.rmdir(unter)
        except OSError:
            pass
    return not ordner.exists()


def zurueckspielen(quelle, fragen=None, sperre=None, streng=False):
    """Sicherung zurückspielen (PLAN E30): Sie ersetzt konten.db, alle Sammlungen und ihre archivierten Importe; was nie in einer Sicherung
    steckt, bleibt liegen (_stellen). Die Schritte, vor dem fünften ist am Bestand nichts geändert:
    1. Läuft die App (belegen), bricht es ab: AppLaeuft.
    2. Entpacken in einen Arbeitsordner im Datenordner (wiederherstellung-…/neu: dasselbe Laufwerk, das Einsetzen ist dann nur ein
       Umbenennen) und prüfen wie pruefen: KeineSicherung, der Arbeitsordner verschwindet wieder.
    3. fragen(Auskunft), wenn angegeben: Bei Nein endet es hier mit None.
    4. Sperre nehmen, falls noch nicht geschehen; schreibt gerade jemand in eine der Datenbanken: AppLaeuft. Dann den jetzigen Stand
       sichern (sicherungen/vor-wiederherstellung-<Zeit>.zip, einmal ganz gelesen). Gelingt das nicht: ValueError, nichts geändert. Ein
       Datenordner ohne Datenbank braucht keine.
    5. Tauschen (_tauschen): Scheitert es, kommt der alte Stand zurück (ValueError), sonst NichtZurueck.
    6. Vom beiseitegelegten alten Stand wird gelöscht, was in der Sicherung aus Schritt 4 steckt. Alles andere (die Datenbank eines
       entfernten Kontos, Reste ohne Datenbank) bleibt unter wiederherstellung-…/alt liegen: Auskunft „rest“.
    Migriert wird hier nichts: Eine ältere Sicherung stellt die App beim nächsten Öffnen um, mit Sicherung davor (Phase 39).
    sperre: die Sperre aus belegen, wenn der Aufrufer sie schon hält (die Einrichtung im Browser, Phase 43). streng: Die ZIP kommt aus
    fremder Hand (dieselbe Einrichtung), _pruefen sieht dann genauer hin.
    -> Auskunft wie pruefen, dazu „sicherung“ (Pfad oder None) und „rest“ (Pfad oder None)"""
    basis, quelle = daten(), Path(quelle)
    eigene, arbeit = None, None
    try:
        if sperre is None and (basis / SPERRE).exists():  # früh, damit eine laufende App nicht erst nach dem Entpacken auffällt
            eigene = _allein()
        if not quelle.is_file():
            raise KeineSicherung(f"Datei nicht gefunden: {quelle}")
        basis.mkdir(parents=True, exist_ok=True)
        arbeit = Path(tempfile.mkdtemp(prefix="wiederherstellung-", dir=basis))  # kurz: Unter Windows zählt jedes Zeichen des Pfads
        neu, alt = arbeit / "neu", arbeit / "alt"
        neu.mkdir()
        info = _pruefen(quelle, neu, streng)
        stellen, dbs, jetzt = _stellen(info)
        _vergleich(info, stellen, dbs, jetzt, ohne=arbeit.name)
        if any(quelle.resolve().is_relative_to((basis / s).resolve()) for s in stellen):
            raise KeineSicherung("Die ZIP liegt in einem Ordner, den das Zurückspielen ersetzt. Bitte woanders ablegen, zum Beispiel "
                                 "direkt im Datenordner.")
        if fragen and not fragen(info):
            return None
        if sperre is None and eigene is None:
            eigene = _allein()
        for d in dbs:  # „nur bei stehender App“ heißt auch: kein anderes Programm mitten im Schreiben
            if (basis / d).exists():
                try:
                    with closing(sqlite3.connect(basis / d, timeout=1)) as c:
                        c.execute("BEGIN EXCLUSIVE")
                        c.rollback()
                except sqlite3.OperationalError as e:
                    if "locked" in str(e) or "busy" in str(e):
                        raise AppLaeuft(f"{d} ist gerade gesperrt: Ein anderes Programm arbeitet mit der Sammlung. Die App und laufende "
                                        f"mtg-Befehle beenden, dann noch einmal.") from e
                except sqlite3.Error:
                    pass  # unlesbar: Das meldet gleich die Sicherung des jetzigen Stands
        gesichert = set()
        try:
            info["sicherung"] = sicherung_vor("wiederherstellung") if _dateien() else None
            if info["sicherung"]:
                with zipfile.ZipFile(info["sicherung"]) as z:
                    if z.testzip() is not None:
                        raise zipfile.BadZipFile("nicht lesbar")
                    gesichert = set(z.namelist())
        except (sqlite3.Error, OSError, zipfile.BadZipFile) as e:
            raise ValueError(f"Der jetzige Stand ließ sich nicht sichern ({e}), deshalb wird nichts zurückgespielt. Ist die genannte Datei "
                             f"beschädigt: sie aus dem Datenordner nehmen (verschieben, nicht löschen), dann noch einmal.") from e
        try:
            _tauschen(basis, arbeit, stellen, dbs)
        except NichtZurueck:
            arbeit = None  # nichts mehr anfassen
            raise
        gesichert |= {d + e for d in dbs if d in gesichert for e in NEBEN}  # ihr Inhalt steckt in der gesicherten Datenbank
        try:
            for ordner, _, dateien in os.walk(alt):
                for p in (Path(ordner) / d for d in dateien):
                    if p.relative_to(alt).as_posix() in gesichert:
                        p.unlink()
        except OSError:
            pass  # zurückgespielt ist: Was sich nicht löschen lässt, bleibt als Rest liegen
        shutil.rmtree(neu, ignore_errors=True)
        info["rest"] = None if _leer_raeumen(arbeit) else alt
        return info
    finally:
        if arbeit is not None and arbeit.exists():
            shutil.rmtree(arbeit / "neu", ignore_errors=True)  # nur die entpackten Kopien; vom alten Stand löscht das nichts
            _leer_raeumen(arbeit)
        if eigene:
            eigene.close()
