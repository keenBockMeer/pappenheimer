#!/bin/sh
# Sicherung außer Haus (PLAN Phase 27): kopiert die jüngste tägliche Sicherung der App (data/sicherungen/mtg-JJJJ-MM-TT.zip) auf ein
# zweites Ziel. Das Skript fasst die Datenbanken nicht an (die Sicherung legt die laufende App selbst an), braucht also weder Docker noch
# den Nutzer der App und läuft per systemd jede Nacht (deploy/mtg-sicherung.service und .timer, Anleitung in der README).
# Danach steht in data/sicherungen/aussen.txt „Zeit Datei Art Ziel“ (Art: verschlüsselt oder unverschlüsselt); die App zeigt das unter
# „Konten und Sicherung“.
#
# MTG_AUSSEN (Pflicht), das Ziel:
#   rclone:REMOTE:ORDNER    mit rclone, zum Beispiel rclone:storagebox:pappenheimer (vorher einmal: rclone config). Am Ziel bleiben
#                           MTG_AUSSEN_TAGE Tage (Standard 60), ältere Sicherungen löscht das Skript dort.
#   scp:NUTZER@HOST:ORDNER  mit scp und SSH-Schlüssel ohne Passphrase, Port in MTG_AUSSEN_PORT (Standard 22). Aufräumen am Ziel selbst.
# MTG_AUSSEN_SCHLUESSEL (empfohlen), Pfad einer Datei mit dem Schlüssel, nur für root lesbar (chmod 600): Dann verschlüsselt das Skript die ZIP
#   vor dem Kopieren mit gpg (symmetrisch, AES256) und kopiert nur die Datei mtg-JJJJ-MM-TT.zip.gpg, denn die ZIP enthält Passwort-Hashes und
#   Kaufpreise. Ohne Schlüssel geht sie unverschlüsselt hinaus, mit einer Warnung und dem Vermerk „unverschlüsselt“ (so bricht kein laufender
#   Timer). Ist ein Schlüssel gesetzt, aber die Datei oder gpg fehlt, kopiert das Skript nichts und endet mit einem Fehler. Der Schlüssel
#   geht nie in der Befehlszeile an gpg (dort sähe ihn jeder Nutzer des Rechners in der Prozessliste), sondern als Datei.
#   Entschlüsseln: gpg --output mtg-JJJJ-MM-TT.zip --decrypt mtg-JJJJ-MM-TT.zip.gpg, danach mtg wiederherstellen (README).
# MTG_GPG: Pfad zu gpg, falls es nicht im Suchpfad liegt (Standard: gpg)
# MTG_DATEN: Datenordner der App (Standard: data/ im Projektordner)
set -eu

ZIEL=${MTG_AUSSEN:?"MTG_AUSSEN fehlt, zum Beispiel rclone:storagebox:pappenheimer"}
DATEN=${MTG_DATEN:-$(cd "$(dirname "$0")/.." && pwd)/data}
ORDNER=$DATEN/sicherungen

# shellcheck disable=SC2012  # die Namen sind fest (mtg-JJJJ-MM-TT.zip), ls -t sortiert nach Zeit
ZIP=$(ls -1t "$ORDNER"/mtg-*.zip 2>/dev/null | head -n 1)
if [ -z "$ZIP" ]; then
  echo "Keine Sicherung in $ORDNER. Die App legt jeden Tag eine an, solange sie läuft." >&2
  exit 1
fi
NAME=$(basename "$ZIP")
if [ -n "$(find "$ZIP" -mmin +2880)" ]; then  # älter als zwei Tage: Die App läuft wohl nicht, eine alte Kopie hilft niemandem
  echo "Die jüngste Sicherung $NAME ist älter als zwei Tage. Läuft die App? Nichts kopiert." >&2
  exit 1
fi
if command -v python3 >/dev/null 2>&1; then  # keine kaputte ZIP verschicken
  python3 -c 'import sys, zipfile; sys.exit(zipfile.ZipFile(sys.argv[1]).testzip() is not None)' "$ZIP" || {
    echo "$NAME ist beschädigt. Nichts kopiert." >&2
    exit 1
  }
fi

# Mit Schlüssel geht nur die verschlüsselte Datei hinaus. Alles, was dabei schiefgehen kann, endet hier, vor dem Kopieren und vor dem Vermerk.
SCHLUESSEL=${MTG_AUSSEN_SCHLUESSEL:-}
ART=unverschlüsselt
if [ -n "$SCHLUESSEL" ]; then
  if [ ! -r "$SCHLUESSEL" ] || [ -z "$(head -n 1 "$SCHLUESSEL")" ]; then
    echo "Die Schlüsseldatei $SCHLUESSEL fehlt, ist leer oder nicht lesbar. Nichts kopiert." >&2
    exit 1
  fi
  GPG=${MTG_GPG:-gpg}
  if ! command -v "$GPG" >/dev/null 2>&1; then
    echo "gpg fehlt (zum Beispiel: apt install gpg), aber MTG_AUSSEN_SCHLUESSEL ist gesetzt. Nichts kopiert." >&2
    exit 1
  fi
  TMP=$(mktemp -d)
  trap 'rm -rf "$TMP"' EXIT
  "$GPG" --batch --yes --quiet --pinentry-mode loopback --passphrase-file "$SCHLUESSEL" --compress-algo none \
    --symmetric --cipher-algo AES256 --output "$TMP/$NAME.gpg" "$ZIP" || {
    echo "gpg konnte $NAME nicht verschlüsseln. Nichts kopiert." >&2
    exit 1
  }
  if [ ! -s "$TMP/$NAME.gpg" ]; then
    echo "gpg hat für $NAME eine leere Datei geschrieben. Nichts kopiert." >&2
    exit 1
  fi
  ZIP=$TMP/$NAME.gpg
  NAME=$NAME.gpg
  ART=verschlüsselt
else
  echo "Warnung: MTG_AUSSEN_SCHLUESSEL ist nicht gesetzt, die Sicherung geht unverschlüsselt hinaus. Sie enthält Passwort-Hashes und Kaufpreise." >&2
fi

case $ZIEL in
  rclone:*)
    Z=${ZIEL#rclone:}
    rclone copy "$ZIP" "$Z"
    rclone delete "$Z" --include "mtg-*.zip" --min-age "${MTG_AUSSEN_TAGE:-60}d"
    rclone delete "$Z" --include "mtg-*.zip.gpg" --min-age "${MTG_AUSSEN_TAGE:-60}d"
    ;;
  scp:*)
    Z=${ZIEL#scp:}
    scp -q -o BatchMode=yes -P "${MTG_AUSSEN_PORT:-22}" "$ZIP" "$Z/"
    ;;
  *)
    echo "MTG_AUSSEN beginnt mit rclone: oder scp: (jetzt: $ZIEL)" >&2
    exit 2
    ;;
esac

printf '%s %s %s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$NAME" "$ART" "$ZIEL" > "$ORDNER/aussen.txt"
echo "Sicherung außer Haus: $NAME ($ART) nach $ZIEL"
