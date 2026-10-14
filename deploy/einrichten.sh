#!/bin/sh
# Ersteinrichtung auf einem frischen Ubuntu- oder Debian-Server (etwa bei Hetzner), als root im Projektordner:
#   sh deploy/einrichten.sh
# Macht der Reihe nach: Docker (offizielles Skript von get.docker.com), Datenordner, Image holen, Hauptkonto mit Passwort, Start per
# docker compose, Tailscale mit HTTPS (tailscale serve) für Handy und Rechner, auf Wunsch die Sicherung außer Haus.
# Mehrfach ausführbar: Was schon erledigt ist, wird übersprungen. Anleitung drumherum: README, „Auf dem eigenen Server“.
set -eu
cd "$(dirname "$0")/.."
if [ "$(id -u)" != 0 ]; then
  echo "Bitte als root ausführen: sudo sh deploy/einrichten.sh" >&2
  exit 1
fi
schritt() { printf '\n== %s\n' "$*"; }

schritt "Docker"
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  echo "schon da: $(docker --version)"
else
  curl -fsSL https://get.docker.com | sh
fi

schritt "Datenordner"
mkdir -p data inbox
chown 1000:1000 data  # gehört dem Nutzer im Container
echo "$(pwd)/data (Sammlung, Konten, Sicherungen) und $(pwd)/inbox (Posteingang)"

schritt "App holen"
# compose.yaml zieht das veröffentlichte Image dieser Version. Wer aus dem Klon baut (compose.dev.yaml, etwa über COMPOSE_FILE in .env),
# bekommt hier nichts gezogen, sondern gebaut: pull lässt aus, was sich bauen lässt, und build tut nichts, wo es nichts zu bauen gibt.
docker compose pull --ignore-buildable
docker compose build

schritt "Hauptkonto"
if docker compose run --rm -T mtg konto list 2>/dev/null | grep -q "Modus: anmeldung"; then
  echo "schon da"
else
  printf 'Dein Name für die Anmeldung: '
  read -r NAME
  docker compose run --rm mtg konto add "$NAME" --haupt  # fragt zweimal nach dem Passwort (mindestens 8 Zeichen)
fi

schritt "Start"
docker compose up -d
echo "läuft, nur auf diesem Server erreichbar (127.0.0.1:8765)"

schritt "Tailscale (Zugang von Handy und Rechner, mit HTTPS für die Kamera)"
if ! command -v tailscale >/dev/null 2>&1; then
  curl -fsSL https://tailscale.com/install.sh | sh
fi
if ! tailscale status >/dev/null 2>&1; then
  echo "Gleich erscheint ein Link: im Browser öffnen und mit deinem Tailscale-Konto anmelden."
  tailscale up
fi
tailscale serve --bg 8765  # meldet einen Link, falls HTTPS im Tailnet erst noch eingeschaltet werden muss
tailscale serve status

schritt "Sicherung außer Haus"
if command -v rclone >/dev/null 2>&1 && rclone listremotes 2>/dev/null | grep -qx "storagebox:"; then
  # Schlüssel für die Kopie (PLAN E30): Die ZIP enthält Passwort-Hashes und Kaufpreise und verlässt den Server nur verschlüsselt (gpg). Ein
  # Schlüssel, der schon da ist, bleibt unberührt und wird nie noch einmal gezeigt; ohne Schlüssel läuft ein bestehender Timer unverändert
  # weiter (unverschlüsselt, mit Warnung), bis dieses Skript noch einmal läuft.
  SCHLUESSEL=/etc/pappenheimer/aussen.schluessel
  command -v gpg >/dev/null 2>&1 || apt-get install -y gpg
  if [ ! -s "$SCHLUESSEL" ]; then
    install -d -m 700 /etc/pappenheimer
    (umask 077; tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 40 > "$SCHLUESSEL")
    printf '\nSchlüssel für die Sicherung außer Haus (steht nur auf diesem Server, den es nicht mehr geben könnte):\n\n    %s\n\n' "$(cat "$SCHLUESSEL")"
    echo "Bitte jetzt aufschreiben (Papier oder Passwortmanager). Ohne ihn ist die Kopie auf der Storage Box wertlos, ein verlorener Schlüssel lässt sich nicht ersetzen."
    echo "Er wird nicht noch einmal angezeigt; wiederfinden kannst du ihn als root in $SCHLUESSEL."
    printf 'Weiter mit Enter, wenn er aufgeschrieben ist: '
    read -r _ || true
  fi
  sed "s|/opt/pappenheimer|$(pwd)|g" deploy/mtg-sicherung.service > /etc/systemd/system/mtg-sicherung.service
  sed -i 's|^#Environment=MTG_AUSSEN_SCHLUESSEL=|Environment=MTG_AUSSEN_SCHLUESSEL=|' /etc/systemd/system/mtg-sicherung.service
  cp deploy/mtg-sicherung.timer /etc/systemd/system/
  systemctl daemon-reload
  systemctl enable --now mtg-sicherung.timer
  echo "jede Nacht verschlüsselt nach storagebox:pappenheimer (Ziel ändern: /etc/systemd/system/mtg-sicherung.service)"
else
  echo 'noch nicht eingerichtet: erst die Storage Box mit rclone verbinden (README, „Sicherung außer Haus“), dann dieses Skript noch einmal'
fi

schritt "Hermes-Agent (nur wenn er auf diesem Server läuft)"
if [ -d /root/.hermes/skills ]; then  # Skill und Befehl, mit denen der Agent Fragen zur Sammlung beantwortet, ohne sie zu ändern
  sed "s|/opt/pappenheimer|$(pwd)|g" deploy/hermes/mtg-lesen > /usr/local/bin/mtg-lesen
  chmod 755 /usr/local/bin/mtg-lesen
  mkdir -p /root/.hermes/skills/gaming/mtg-sammlung
  sed "s|/opt/pappenheimer|$(pwd)|g" deploy/hermes/SKILL.md > /root/.hermes/skills/gaming/mtg-sammlung/SKILL.md
  echo "Skill mtg-sammlung und Befehl mtg-lesen eingerichtet"
else
  echo "kein Hermes-Agent gefunden"
fi

printf '\nFertig. Am Handy: Tailscale-App installieren, mit demselben Konto anmelden, die Adresse oben (https://….ts.net) öffnen,\n'
printf 'anmelden und im Browsermenü „App installieren“ bzw. „Zum Startbildschirm“. Aktualisieren: die compose.yaml der neuen\n'
printf 'Version holen (im Klon: git pull), dann docker compose pull && docker compose up -d.\n'
