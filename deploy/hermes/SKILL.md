---
name: mtg-sammlung
description: "Fragen zur Magic-Sammlung des Nutzers beantworten (Karten im Besitz, Wert, Verkaufsliste, Decks, Commander-Vorschläge, Deckbau) mit dem Befehl mtg-lesen."
tags: [magic, mtg, commander, sammlung, karten, decks]
platforms: [linux]
---

# MTG-Sammlung (nur lesen)

Freiwilliger Zusatz für Betreiber, auf deren Server ein Hermes-Agent läuft (`deploy/einrichten.sh` richtet ihn ein, wenn es den Agenten findet).

Die Sammlung des Nutzers liegt auf diesem Server in der App Pappenheimer (`/opt/pappenheimer`, läuft in Docker). Du fragst sie nur mit `mtg-lesen <befehl>` ab.

## Wann verwenden
- Fragen zu Karten im Besitz („Habe ich Sol Ring?“, „Wie viele Vampire habe ich?“)
- Wert der Sammlung, Preisbewegungen, was sich zu verkaufen lohnt
- Fertige und gespeicherte Decks, Commander-Vorschläge, Deckwünsche wie „BG Friedhof Bracket 2“

## Regeln
- Nur `mtg-lesen`. Nie die Datenbank unter `/opt/pappenheimer/data` direkt lesen oder ändern, nie `docker compose` oder `mtg.py` selbst aufrufen.
- Kartentext, Kosten und Legalität immer mit `mtg-lesen card "<Name>"` nachsehen, nie aus dem Gedächtnis.
- Kartennamen sind englisch (wie bei Scryfall).
- Antworten kurz: Ergebnis zuerst, dann höchstens drei Zeilen Hinweise.
- Ändern kannst du nichts (kein Import, kein Speichern, kein Löschen). Will der Nutzer etwas ändern, verweise auf die Oberfläche der App.

## Befehle
- `mtg-lesen stats` : Karten, Unikate, Gesamtwert, Top 10
- `mtg-lesen card "<Name>"` : Besitz je Druck und Binder, Preis, Oracle-Text, Decks
- `mtg-lesen suche "<Suche>"` : Suche wie bei Scryfall über die eigene Sammlung, zum Beispiel `t:vampire c:r mv<=3`, `otag:ramp`, `fn:landfall`, `eur>=10`
- `mtg-lesen sell [--min N]` : Verkaufsliste ab N Euro (Top 30 und Summe), darunter Bulk
- `mtg-lesen movers [--days N]` : Preisbewegung der eigenen Karten
- `mtg-lesen gaps [--top N]` : Karten, die mehreren der besten Commander fehlen, mit Preis
- `mtg-lesen decks [ID] [--text]` : Decks auflisten, eines anzeigen oder als Textliste
- `mtg-lesen commanders --cached [--top N] [--mode machbar|beliebt|geheimtipp|guenstig]` : Commander nach Abdeckung der EDHREC-Empfehlungen. Immer mit `--cached` (ohne lädt es minutenlang neu)
- `mtg-lesen build "<Commander>" [--bracket 1-5] [--theme NAME|auto|none] [--text]` : Deckvorschlag aus freien Karten, wird nicht gespeichert
- `mtg-lesen plan-decks --count N [--bracket 1-5]` : N Decks gleichzeitig ohne doppelte Karten, wird nicht gespeichert
- `mtg-lesen missing "<Commander>" [--budget N]` : Einkaufsliste für einen Commander
- `mtg-lesen news` : Neuigkeiten (Upgrades, neue Commander, Verkäufe, Combos)
- `mtg-lesen dossier "<Commander>"` : gespeichertes Recherche-Dossier anzeigen

## Deckwunsch in einem Satz („BG Friedhof Bracket 2“)
Nennt der Wunsch keinen Commander, ist der erste Befehl immer `mtg-lesen commanders --cached --top 40`. Commander nie aus dem Gedächtnis wählen, nur Namen aus dieser Liste.
1. `mtg-lesen commanders --cached --top 40`: Die Farbidentität steht in Klammern, die Abdeckung zeigt, wie viel der Empfehlungsliste frei ist.
2. Commander mit passenden Farben wählen, das Thema bei Bedarf mit `mtg-lesen card "<Commander>"` prüfen.
3. `mtg-lesen build "<Commander>" --bracket 2` (ohne Angabe Bracket 3; bei einem Thema wie Landfall `--theme <Thema>` ergänzen).
4. Antwort: Commander, Thema, Wert, Warnungen aus der Ausgabe, die drei besten fehlenden Upgrades mit Preis.

## Fehler
- „service "mtg" is not running“: Die App läuft nicht. Dem Nutzer sagen, nicht selbst starten.
- „mtg-lesen kennt: …“: Der Befehl gehört nicht zu den lesenden. Nicht umgehen.
